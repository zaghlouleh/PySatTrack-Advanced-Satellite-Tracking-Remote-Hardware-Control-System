# REUSE / Licensing & Code Overview (SatTrack v4)

This repository contains the **SatTrack v4** application (Python + PyQt5 + Skyfield + hardware abstraction). This document has two purposes:

1. Provide a **REUSE.md** style explanation of how licensing/compliance is handled (using REUSE tooling).
2. Give a **detailed, code-part walkthrough** explaining what each module/file does and how the application works.

> Note on REUSE compliance: REUSE’s automated tooling primarily relies on **file headers / annotations** and the presence of a **REUSE.toml** + a **LICENSE** file. This repository currently uses a top-level MIT `LICENSE` and a `REUSE.toml` that declares MIT for the project. The code in this snapshot does not include per-file `SPDX-License-Identifier` headers, so automated REUSE checks may report missing per-file identifiers.

---

## 1) Licensing / REUSE setup

### 1.1 License used for project source code
- **Top-level license**: `LICENSE` (MIT)
- **REUSE configuration**: `REUSE.toml`

`REUSE.toml` currently annotates common source/text asset types (e.g., `*.py`, `*.md`, `*.txt`, `*.ico`, `*.bsp`) with the **MIT** identifier.

### 1.2 How to keep REUSE compliance going
- Ensure every new file added to the repository is covered either by REUSE **annotations** or a per-file header.
- If you add third-party assets (icons, datasets, binaries, ephemeris bundles, etc.), document their licensing separately.

Suggested maintenance checklist is in `REUSE-toolbox.txt`.

---

## 2) Application architecture (high level)

The app is organized as a small set of packages under `src/`:

- `src/config/` — settings/constants and TLE source definitions.
- `src/core/` — API client, computations (astronomy), and data persistence.
- `src/hardware/` — board connection + protocol abstraction (UART/I2C/SPI).
- `src/ui/` — PyQt5 GUI, map bridge (Leaflet via QWebChannel), and the worker thread.
- `src/utils/` — logging and platform-specific helpers.

Entry points:
- `main.py` starts the Qt application, sets a stylesheet, and opens the main window.

---

## 3) File-by-file code walkthrough

### 3.1 `main.py` (application entry point)
**Location:** `/main.py`

Responsibilities:
- Calls `setup_qt_environment()` from `src/utils/platform_utils.py` (Windows QtWebEngine deployment fixes).
- Configures Qt high-DPI attributes when available.
- Creates `QApplication`, applies the (large) monolithic stylesheet (dark theme) used by the UI.
- Installs a global exception hook (`sys.excepthook`) that logs a critical error and exits.
- Instantiates `SatelliteTracker` from `src/ui/main_window.py` and runs the Qt event loop.

Key control flow:
1. `setup_qt_environment()`
2. Create `QApplication`
3. Apply stylesheet
4. Set `sys.excepthook`
5. `window = SatelliteTracker(); window.show(); app.exec_()`

---

## 4) Configuration

### 4.1 `src/config/settings.py`
**Responsibilities:**
- Defines the project root path (`BASE_DIR`) and creates runtime directories:
  - `TLE_DATA_DIR` → `BASE_DIR/tle_data`
  - `SATNOGS_CACHE_DIR` → `BASE_DIR/satnogs_cache`
- Loads environment variables via `python-dotenv` (`load_dotenv()`).
- Defines API keys/credentials (OpenCage, N2YO, Space-Track).
- Defines `DEFAULT_TLE_SOURCES`: a dictionary of named TLE feeds and their caching metadata.

Important fields in `DEFAULT_TLE_SOURCES`:
- `url`: where to download a TLE text file.
- `filename`: local filename inside `tle_data/`.
- `cache_days`: how old a local copy is allowed to be before redownloading.
- `auth_required` (for some feeds): indicates Space-Track login is required.

How it is used:
- `src/ui/main_window.py` iterates this structure inside `_load_satellites_from_tle()`.

---

## 5) Core / Back-end logic

### 5.1 `src/core/api_client.py` — external API access
**Class:** `APIClient`

Responsibilities:
- Provides:
  - Geo lookup via **OpenCage** (`get_geolocation`)
  - Satellite positions via **N2YO** (`get_satellite_position`)
  - Transmitter/downlink/uplink/frequency info via **SatNOGS** (`get_satnogs_frequencies`)
  - Optional Space-Track login for protected feeds.

Key parts:

#### Space-Track session
- `_setup_space_track_session()` tries to log in via an AJAX endpoint using `requests.Session`.
- Uses a retry-enabled HTTPAdapter.
- Stores:
  - `self.space_track_session`
  - `self.space_track_logged_in`
- `get_authenticated_session()` returns the session only if logged in.

> In the current code snapshot, the Space-Track session is set up, but `main_window.py` does not appear to use it directly during TLE download.

#### OpenCage geocoding
- `get_geolocation(city)` calls the OpenCage geocode endpoint.
- Returns `(lat, lon)` or `(None, None)`.

#### N2YO positions
- `get_satellite_position(sat_id, lat, lng, alt)` calls N2YO REST positions endpoint.
- Returns JSON response or `None` on error.

#### SatNOGS frequency lookup + caching
- `get_satnogs_frequencies(norad_id)`:
  - Uses a JSON cache file at `SATNOGS_CACHE_DIR/{norad_id}.json`.
  - Cache age is fixed to 2 days (`cache_age_sec = 172800`).
  - If cache is valid, loads and returns cached data.
  - Otherwise calls:
    - `https://db.satnogs.org/api/transmitters/?satellite__norad_cat_id={norad_id}`
  - Processes the response by selecting an “alive” transmitter record when possible.
  - Normalizes output fields into a “processed” dict (downlink frequency, mode, status, bandwidth, baud, service, etc.).
  - Writes processed JSON back to disk.

---

### 5.2 `src/core/calculations.py` — astronomy calculations
**Class:** `CelestialCalculator`

Responsibilities:
- Uses **Skyfield** + `de421.bsp` ephemeris file to compute:
  - subsolar (Sun) point
  - sublunar (Moon) point

Skyfield availability:
- The module attempts to import Skyfield.
- If imports fail, it sets `SKYFIELD_AVAILABLE = False` and defines dummy classes/values to prevent NameErrors.

Methods:
- `sun_position(dt)`
  - Loads timescale and `de421.bsp`.
  - Observes the Sun from Earth, then computes the subpoint using `wgs84.subpoint`.
  - Returns `(latitude_degrees, longitude_degrees)`.
- `moon_position(dt)`
  - Same logic but with the Moon body.

Failure behavior:
- Any exception logs an error and returns `(0.0, 0.0)`.

---

### 5.3 `src/core/data_manager.py` — persistence for satellite telemetry
**Class:** `DataManager`

Responsibilities:
- Saves telemetry snapshots to JSON files.
- Loads saved telemetry snapshots if they exist.

Key implementation details:
- Uses a `threading.Lock` to protect concurrent access.
- Stores an in-memory cache `self._cache`.
- Writes files into `self.data_dir = BASE_DIR` (project root). Each satellite produces a file like:
  - `{BASE_DIR}/{safe_satellite_name}.json`

Important helper:
- `_get_filepath(satellite_name)`
  - Sanitizes the name by allowing alphanumerics, spaces, `_`, `-`, then replaces spaces with `_`.

Methods:
- `save_satellite_data(satellite_name, data)`
  - Writes JSON with `ensure_ascii=False`.
- `load_satellite_data(satellite_name)`
  - Checks cache first.
  - If file exists, loads JSON.

---

## 6) Hardware abstraction layer

### 6.1 `src/hardware/board_manager.py` — connect and transmit
**Class:** `BoardManager` (inherits `QObject`)

Responsibilities:
- Provides a hardware-connection API for multiple microcontroller/board types.
- Abstracts transport protocols:
  - UART
  - I2C
  - SPI
- Communicates using board-specific “identity” commands and model definitions.

Qt integration:
- Emits `connection_changed = pyqtSignal(bool, str)`
  - Called on connect success/failure.

Key data model:
- `boards` dictionary describes supported boards.
  - UART boards define a default `command` and `response_contains` string.
  - I2C/SPI boards define model-specific bus/address/device and a `command`.

Core API:
- `get_available_ports()`
  - Delegates to `safe_port_detection()` from `src/utils/platform_utils.py`.
- `connect(port, config, board_type, model=None)`
  - Calls protocol-specific connect methods:
    - `_connect_uart`
    - `_connect_i2c`
    - `_connect_spi`
  - On success it sets internal state and emits UI signals.
- `disconnect()`
  - Closes underlying connection if present.

Transmission:
- `send_data(data)` decides based on `self.protocol`.
- `_send_uart(data)`
  - Reads azimuth/elevation from telemetry.
  - Builds a line like: `AZ:{az},EL:{el},VIS:{0|1}`
- `_send_i2c(data)`
  - Builds payload bytes derived from azimuth and elevation.
  - Uses `write_i2c_block_data(address, cmd_byte, payload)`.
- `_send_spi(data)`
  - Builds a command byte + 4 bytes payload, then `xfer2(...)`.

Platform dependencies:
- `smbus2` and `spidev` are obtained via `get_i2c_smbus()` / `get_spidev()` wrappers that may create mock objects if not available.

---

## 7) UI layer (PyQt + Leaflet)

### 7.1 `src/ui/main_window.py` — main GUI
**Class:** `SatelliteTracker(QWidget)`

Responsibilities:
- Builds the entire PyQt interface:
  - Satellite selection from downloaded/parsing TLE sources
  - Observer location inputs
  - Hardware configuration (board type/model/port)
  - Start/Stop tracking buttons
  - Displays for observer and satellite telemetry
  - Map view (Leaflet) embedded in `QWebEngineView`
  - A JS bridge via `MapBridge`
  - Logging UI with in-app “Problems / Output / Memory Info” tabs
- Manages tracking orchestration:
  - Starts `WorkerThread` for periodic API polling and calculations
  - Updates telemetry labels and map markers
  - Feeds telemetry to hardware via `BoardManager` when connected

Qt signals:
- `log_message_signal`, `error_message_signal` used to append messages.

Key initialization:
- On construction:
  1. Validates Skyfield availability; shows a critical error and quits if missing.
  2. Creates:
     - `APIClient`
     - `DataManager`
     - `BoardManager`
  3. Calls UI builders:
     - `init_ui()`
     - `init_map_bridge()`
     - `init_map_view()`
  4. Creates timers:
     - `log_update_timer` (reads `satellite_tracker.log` file changes)
     - `mem_display_timer` (updates memory tab using psutil)
  5. Loads TLE satellites via `_load_satellites_from_tle()`
  6. Schedules `start_celestial_updates()` after a delay.

#### UI composition methods
- `create_satellite_input_fields(layout)`
  - Filter line edit + “Refresh TLE” button + satellite list.
- `create_location_input_fields(layout)`
  - City input, altitude input, and a “Get Lat/Lon” button.
- `create_update_settings_fields(layout)`
  - N2YO update interval.
- `create_board_config_fields(layout)`
  - Board type/model selection, port scanning, baud, and connection status.
- `create_tab_widget()`
  - Creates Output/Problems tabs and Memory Info tab.

#### Map bridge
- `init_map_bridge()` creates `MapBridge` and registers it through `QWebChannel`.
- Connects `MapBridge` signals to Leaflet JS functions.

#### Map HTML (`init_map_view`)
- Uses `setHtml(html_content)` with inline HTML:
  - Leaflet map
  - Markers for observer, satellite, sun, moon
  - Functions:
    - `updateObserver(lat, lon)`
    - `updateSatellite(lat, lon)`
    - `updateCelestial(type, lat, lon)`
    - `addTrackPoint(lat, lon)`
    - `clearTrack()`
    - `setView(lat, lon, zoom)`

#### TLE download and parsing
- `_load_satellites_from_tle()` runs in a background `threading.Thread`.
- For each entry in `DEFAULT_TLE_SOURCES`:
  - checks if the file exists and is “fresh” based on `cache_days`
  - downloads if stale
  - parses TLE file in blocks of 3 lines (name + line1 + line2)
  - for each valid pair, constructs `EarthSatellite(l1,l2,n)`
  - stores in `self.satellites` keyed by the satellite’s name.

- `_finalize_tle_load(sats)` runs on the Qt thread using `QMetaObject.invokeMethod`.

#### Tracking start
- `start_tracking()`:
  1. Resolves selected satellite name and looks up TLE entry.
  2. Reads observer lat/lon/alt from UI.
  3. Computes a “TLE period” using mean motion extracted from `line2`.
  4. Attempts board connection (if board type selected).
  5. Builds a `config` dict for the worker thread:
     - sat_id, sat_name, obs_lat/lng/alt, interval, period_tle_calculated_min
  6. Calls `api.get_satnogs_frequencies(norad_id)` and merges returned dict fields.
  7. Starts `WorkerThread(api, data_manager, config)`.
  8. Connects worker signals:
     - `data_ready` → `update_satellite_data`
     - `error_occurred` → `show_error`
  9. Updates UI state and map initial view.

#### Updating telemetry
- `update_satellite_data(data)` updates:
  - speed, altitude, azimuth/elevation, RA/Dec, LST, period, eclipsed flag
  - frequency information labels
  - local/UTC time labels
  - map satellite marker + track polyline
  - and if hardware is connected: `board_manager.send_data(data)`.

#### Stop tracking
- `stop_tracking()` stops the worker thread and updates button states.

#### Celestial updates
- `start_celestial_updates()` starts a QTimer that every 5 minutes computes:
  - Sun subsolar point
  - Moon sublunar point
- `update_celestial_positions()` emits to the map bridge for JS rendering.

#### Log streaming in UI
- `_check_log_file_update()` reads new content appended to `LOG_FILE`.
- `LoggingVerificationDialog` is accessible from the Memory Info tab.

#### Cleanup
- `closeEvent()` stops tracking, disconnects hardware, and accepts the close.

---

### 7.2 `src/ui/worker.py` — background polling & computations
**Class:** `WorkerThread(QThread)`

Responsibilities:
- Runs a loop that periodically:
  1. Calls N2YO to get satellite positions for a given observer.
  2. Computes approximate speed between successive points.
  3. Calculates Local Sidereal Time (LST) if Skyfield is available.
  4. Merges API data into a single telemetry dict.
  5. Emits the dict to the UI.
  6. Saves telemetry snapshots using `DataManager`.

Key methods:
- `calculate_lst(longitude, dt)`
  - Uses Skyfield timescale.
  - Computes `gmst + longitude/15`.
- `calculate_speed(positions)`
  - Sorts positions by timestamp.
  - Uses a haversine distance approximation (Earth radius 6371 km).
  - Divides distance by time difference.
  - Returns km/s.

Main loop (`run()`):
- While `self.running`:
  - record `start_time`
  - call `api.get_satellite_position(...)`
  - validate response
  - process:
    - choose `latest_pos = n2yo_positions[0]`
    - compute speed
    - compute `lst`
  - build `full_data` combining config and API response fields
  - emit `data_ready(full_data)`
  - save via `data_manager.save_satellite_data(full_data['sat_name'], full_data)`
  - sleep for remaining time of `interval`

`stop()` sets `self.running = False`.

---

### 7.3 `src/ui/map_bridge.py` — QWebChannel interface
**Class:** `MapBridge(QObject)`

Responsibilities:
- Defines PyQt signals that are connected to JavaScript functions in `main_window.py`.
- Provides slots for JS→Python calls:
  - `js_log(message)` logs a message sent from JS console
  - `map_clicked(lat,lng)` logs click coordinates

Signals exposed to JS:
- `update_observer_position(float,float)`
- `update_satellite_position(float,float)`
- `update_celestial_position(str,float,float)`
- `add_satellite_track_point(float,float)`
- `clear_satellite_track()`
- `set_map_view(float,float,int)`
- `fit_map_bounds(list)`

---

## 8) Utilities

### 8.1 `src/utils/logger.py` — application logging
**Responsibilities:**
- Creates a log file handler that flushes on each log emission.
- Provides a configured `logger` used across modules.

Key symbols:
- `BASE_DIR` (computed from file location)
- `LOG_FILE` = `BASE_DIR/satellite_tracker.log`

Components:
- `ImmediateFlushFileHandler(logging.FileHandler)`
  - Overrides `emit()` to `flush()` after writing.
- `setup_logger()`
  - Creates a logger named `satellite_tracker`.
  - Adds:
    - file handler to `LOG_FILE`
    - stream handler to stdout
- `logger = setup_logger()`

Also includes UI helper classes:
- `LoggingVerificationDialog(QDialog)`
  - Runs debug/info/warning/error test logs.
  - Checks whether `LOG_FILE` exists.

There is also a `LogMonitor(QThread)` intended to monitor rotation/status of the log file.

---

### 8.2 `src/utils/platform_utils.py` — platform-dependent helpers
**Responsibilities:**
- Fixes Windows-specific QtWebEngine environment variables (`setup_qt_environment`).
- Provides wrappers for optional hardware libraries:
  - `get_i2c_smbus()` returns `smbus2` or a mock on non-Linux / missing package.
  - `get_spidev()` returns `spidev` or a mock.
- Provides cross-platform serial port detection:
  - `_windows_board_check()` via registry (`winreg`)
  - `_linux_board_check()` via glob on `/dev/tty*`
  - `_macos_board_check()` via glob on `/dev/cu.*` and `/dev/tty.*`
  - `safe_port_detection()` dispatches by OS.

---

## 9) Third-party / data files

### 9.1 `de421.bsp`
- Ephemeris file used by Skyfield in `CelestialCalculator`.
- Kept at repo root.

### 9.2 `tle_data/*`
- Cached TLE text files downloaded from Celestrak/AMSAT sources.
- `main_window.py` parses these to build `EarthSatellite` objects.

### 9.3 `satnogs_cache/*.json`
- Cached SatNOGS transmitter frequency data.
- Managed by `APIClient.get_satnogs_frequencies()`.

---

## 10) Execution flow (end-to-end)

### 10.1 Required user configuration before running
This application is designed to use real API accounts for:
- **OpenCage** geocoding
- **N2YO** satellite position
- **Space-Track** authentication (for protected TLE feeds)

The code loads configuration from:
- Top-level `.env` (via `python-dotenv` in `src/config/settings.py`)
- `src/config/settings.py` defaults if variables are missing

To make the program function correctly (especially for geolocation, satellite positions, and protected TLE sources), you must:
1. Create/edit the **`.env` file** in the repository root.
2. Put your API keys / account info in it (at minimum `OPENCAGE_API_KEY`, `N2YO_API_KEY`, and—if you want protected TLEs—`SPACE_TRACK_USER` and `SPACE_TRACK_PASSWORD`).
3. Verify that any defaults embedded in `src/config/settings.py` are replaced with your own credentials.

After updating `.env`, start the program normally with `python main.py`.


Typical run:
1. `python main.py`
2. Qt app starts and creates `SatelliteTracker`.
3. `SatelliteTracker` loads cached TLE files or downloads refreshed ones.
4. User selects a satellite + enters observer location.
5. User clicks **Start Tracking**.
6. `WorkerThread` starts polling N2YO every `interval` seconds.
7. Each worker tick:
   - merges telemetry + computed LST/speed
   - emits data to UI
   - UI updates labels and Leaflet markers
   - optionally sends azimuth/elevation to connected hardware
   - persists telemetry snapshot as JSON.

---

## 11) Notes on future REUSE improvements (optional)

If you want REUSE tooling to pass cleanly, the next best step is:
- Add per-file SPDX headers, e.g.:
  - `# SPDX-License-Identifier: MIT`

For example, update each `.py` file under `src/` with an SPDX line.

This repository currently documents compliance via `REUSE.toml` and a top-level MIT `LICENSE`, but the code snapshot does not include SPDX identifiers in file headers.

