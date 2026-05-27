# REUSE.md (Repository-wide licensing + code documentation)

This document serves two purposes:
1. Explain how licensing is handled using the **REUSE** specification.
2. Provide a detailed, code-oriented walkthrough of the repository so that new
   contributors can quickly understand the project structure.

---

## 1) REUSE / licensing overview

### License
- This repository uses the **MIT** license.
- The full license text is in: `LICENSE`.

### REUSE configuration
- `REUSE.toml` configures the repository for REUSE compliance.
- `REUSE-toolbox.txt` contains helper notes and suggested workflow.

### Practical note about SPDX headers
- REUSE can work in “best effort” mode even if files don’t carry SPDX
  identifiers, but the strictest REUSE compliance expects SPDX headers per
  file.
- Currently, most source files in `src/` do not include SPDX license headers.
- If you want strict REUSE conformance, add at the top of each source file:
  `SPDX-License-Identifier: MIT`

---

## 2) Codebase documentation (detailed walkthrough)

### Top-level files

#### `main.py`
Entry point for the Qt application.

Key steps:
1. Calls `src.utils.logger.setup_logging()` to configure logging and obtain
   the log file path.
2. Creates `QApplication` and sets the window icon (`icon.ico`).
3. Applies a global dark-theme stylesheet to common widgets.
4. Instantiates `src.ui.main_window.SatelliteTracker(log_file)` and shows the
   main window.
5. Starts the Qt event loop (`app.exec_()`), logging a critical message if the
   process crashes.

Dependencies:
- PyQt5 (widgets, GUI styling)
- `src.utils.logger` (logging setup)
- `src.ui.main_window` (main UI)

---

### `src/` package layout

- `src/config/` — environment variables and constants
- `src/core/` — orbital/astronomical mathematics + domain calculations
- `src/services/` — API clients + hardware/board integration
- `src/ui/` — PyQt5 UI, widgets, and the Leaflet map container
- `src/utils/` — logging utilities
- `src/workers/` — background worker thread for periodic updates

---

## 3) `src/config/`

### `src/config/settings.py`
Holds configuration constants and loads environment variables.

**Required setup before running (so the app works):**
- This application makes external API calls for geolocation and satellite
  positions.
- The API credentials are configured in `src/config/settings.py` and can
  also be overridden via environment variables (commonly using a `.env` file).
- Before starting the program, open `src/config/settings.py`, `.env` and set your
  own keys:
  - `OPENCAGE_KEY` (OpenCage geocoding)
  - `N2YO_KEY` (N2YO satellite positions)

If these keys are invalid/missing, API calls will fail and the tracking
and map updates will not function correctly.

Main contents:
- Loads `.env` via `dotenv.load_dotenv()`.
- API keys (with defaults):
  - `OPENCAGE_KEY`
  - `N2YO_KEY`
- Physical/astronomical constants:
  - `EARTH_RADIUS_KM`
  - `MU_EARTH` (Earth gravitational parameter in km³/s²)
- Application defaults:
  - `DEFAULT_INTERVAL`, `DEFAULT_ALTITUDE`
- Hardware protocol default:
  - `DEFAULT_BAUD_RATE`

How it’s used:
- `CelestialCalculator` imports constants from here.
- `APIClient` imports API keys from here.

---

## 4) `src/core/`

### `src/core/calculator.py`
Contains `CelestialCalculator`, a static utility class for astronomical and
orbital calculations.

Methods:

#### `sun_position(dt)`
- Uses Skyfield’s `de421.bsp` ephemeris.
- Computes subsolar-related coordinates by observing the Sun from the Earth.
- Steps (high level):
  1. Convert `dt` to UTC.
  2. Build a Skyfield time from the datetime.
  3. Observe Sun from Earth.
  4. Retrieve RA/Dec.
  5. Compute an approximate longitude using GMST and RA.
- Returns `(dec_degrees, lon_degrees)`.

#### `moon_position(dt)`
- Similar to `sun_position`, but observes the Moon.
- Returns `(lat_degrees, lng_degrees)` using a derived longitude formula.

#### `calculate_lst(longitude, dt)`
- Computes Local Sidereal Time (LST).
- Returns a rounded float in hours.
- Used for displaying the LST and for downstream telemetry context.

#### `calculate_speed(positions)`
- Estimates speed by applying the haversine distance formula between the first
  two position samples from N2YO.
- Converts angular distance to kilometers using `EARTH_RADIUS_KM`.
- Uses the timestamps embedded in the API response.
- Returns km/s.

#### `calculate_orbital_period(altitude_km)`
- Uses Kepler’s third law (simplified) to compute an orbital period from a
  given altitude.
- Uses:
  - semi-major axis `a = EARTH_RADIUS_KM + altitude_km`
  - `T = 2π * sqrt(a^3 / MU_EARTH)`
- Returns minutes (rounded).

Notes:
- All methods are `@staticmethod` and therefore stateless.

---

### `src/core/data_manager.py`
Provides `DataManager`, a thread-safe caching and persistence layer for
satellite telemetry.

Key elements:
- `self._lock` — ensures safe access from the worker thread and UI.
- `self._cache` — in-memory cache keyed by `satellite_name`.

Methods:

#### `save_satellite_data(satellite_name, data)`
- Writes `data` to a JSON file named: `<satellite_name>.json`.
- Updates `_cache`.
- Logs success/failure.

#### `load_satellite_data(satellite_name)`
- Checks `_cache` first.
- Otherwise loads `<satellite_name>.json` if present.
- Returns `None` for missing files or errors.

Global instance:
- `satellite_data_manager = DataManager()`
- The UI imports this instance and passes it to the worker.

---

## 5) `src/services/`

### `src/services/api_client.py`
`APIClient` centralizes all external HTTP communication.

#### `get_geolocation(city)`
- Calls OpenCage Geocoding API.
- Builds endpoint using `OPENCAGE_KEY`.
- Returns `(lat, lng)` floats on success, otherwise `(None, None)`.
- Handles common HTTP errors and request exceptions.

#### `get_satellite_position(sat_id, lat, lng, alt)`
- Calls N2YO REST API for satellite positions.
- Requests 2 positions (for speed calculation between timestamps).
- Returns JSON response on HTTP 200, otherwise returns `None`.

---

### `src/services/board_manager.py`
`BoardManager` abstracts hardware integration.

Key concepts:
- It is a `QObject` that emits `connection_changed(bool)`.
- Supports multiple “board types” defined in `self.boards`:
  - UART boards (e.g., Arduino, ESP32, Raspberry Pi)
  - I2C boards (Adafruit Feather models)
  - SPI boards (SparkFun models)

Hardware handling:
- Uses `pyserial` for UART when available.
- Imports `smbus2` and `spidev` on Linux.
- On non-Linux platforms, it defines mock classes so the UI can still run.

Main methods:

#### `detect_os_specific_ports()`
- Windows: queries registry entries for serial ports.
- Linux: glob `/dev/tty[A-Za-z]*`.
- macOS: glob `/dev/cu.*` and `/dev/tty.*`.
- Returns sorted list.

#### `connect(port, config, board_type, model=None)`
- Dispatches to the correct protocol based on `board_type`.
- Calls:
  - `_connect_uart(port, baud_rate)`
  - `_connect_i2c(bus_num)`
  - `_connect_spi(port)`
- Emits `connection_changed(True/False)` and returns a boolean.

#### `disconnect()`
- Closes UART serial if open.
- Resets state.

#### `_connect_uart(port, baud_rate)`
- Opens `serial.Serial(port, baudrate=..., timeout=2)`.

#### `_connect_i2c(bus_num)`
- On non-Linux: logs a warning and assumes success.
- On Linux: opens an SMBus instance to validate the bus.

#### `_connect_spi(port)`
- Expects `port` formatted as `bus,device` (comma-separated).
- Opens and closes an SPI device.

#### `send_data(data)`
- Currently implemented for UART only.
- Formats command as: `"<azimuth>,<elevation>\n"`
- Sends over serial if connected.

---

## 6) `src/workers/`

### `src/workers/tracking_worker.py`
Implements the periodic tracking loop in a background thread.

`TrackingWorker`:
- Subclasses `QThread`.
- Signals:
  - `data_ready(dict)` emitted with computed telemetry
  - `error_occurred(str)` emitted for UI error display

Constructor:
- Receives:
  - `api: APIClient`
  - `data_manager: DataManager`
  - `config: dict` with keys:
    - `sat_id`, `sat_name`
    - `obs_lat`, `obs_lng`, `obs_alt`
    - `interval` (seconds)

Core loop (`run`) behavior:
1. Calls `api.get_satellite_position(...)` requesting 2 positions.
2. Validates the response contains at least two samples.
3. Extracts altitude (`sataltitude`) from the first position.
4. Computes:
   - orbital period via `CelestialCalculator.calculate_orbital_period`
   - speed via `CelestialCalculator.calculate_speed`
   - converts speed to miles/sec
   - LST via `CelestialCalculator.calculate_lst`
5. Builds `full_data` dict including:
   - `satlatitude`, `satlongitude`, `sataltitude`
   - `azimuth`, `elevation`
   - `ra`, `dec`, `lst`
   - `speed_kms`, `speed_mis`
   - `period`, `eclipsed`
   - `timestamp` (ISO string)
   - `observer` object with input location
6. Saves data to JSON via `data_manager.save_satellite_data`.
7. Emits `data_ready(full_data)` to update the UI.
8. Sleeps for `interval` seconds.

Stop mechanism:
- `stop()` sets `self.running = False` so the loop ends gracefully.

---

## 7) `src/ui/`

### `src/ui/main_window.py`
Provides the main GUI widget class: `SatelliteTracker`.

Imports:
- `CelestialCalculator`
- `satellite_data_manager`
- `APIClient`
- `BoardManager`
- `TrackingWorker`
- `LoggingVerificationDialog`
- PyQt5 map view: `QWebEngineView`

#### Constructor `__init__(self, log_file)`
- Stores the log file path.
- Instantiates:
  - `self.api = APIClient()`
  - `self.data_manager = satellite_data_manager`
  - `self.board_manager = BoardManager()`
- Loads satellite name/id mapping from `namesat+idsat.json`.
- Initializes dictionaries for labels.
- Calls:
  - `init_ui()`
  - `init_map()`
- Starts two timers:
  - `log_timer`: every 1s refreshes log contents into a QTextEdit
  - `mem_display_timer`: every 1s updates memory usage labels

#### `load_satellites()`
- Reads `namesat+idsat.json` from the working directory.
- Returns a dict mapping satellite name to ID.

#### `init_ui()`
Builds the widget tree:
- Main horizontal layout:
  - left: input & settings panels (30%)
  - center: Leaflet web map (`QWebEngineView`) (50%)
  - right: telemetry display panels (20%)

Calls:
- `create_input_fields(left_panel)`
- `create_info_displays(right_panel)`

#### `create_input_fields(layout)`
Creates:
- Satellite search group:
  - QLineEdit for satellite name/id
  - QListWidget for filtered matches
- Settings tab widget (`QTabWidget`) with 2 tabs:
  1. Location & Update Settings
     - City input
     - Altitude input (meters)
     - Interval input
  2. Hardware Settings
     - Board type combobox populated from `BoardManager.boards`
     - Port input
     - Baud rate input (shown only for UART)
     - “Test Connection” button
     - “Logging Diagnostics” button

Also adds:
- Start/Stop Tracking buttons.
- A tab widget containing:
  - Problems
  - Output
  - Memory Info

#### `init_map()`
Sets the HTML content for the embedded web map:
- Leaflet CSS/JS via unpkg CDN
- OpenStreetMap tile layer
- Declares JS variables for:
  - observerMarker
  - satelliteMarker
  - sunMarker
  - moonMarker
  - satellitePath (polyline)

#### `_update_board_ui()`
Shows/hides baud rate fields depending on protocol type.

#### `test_board_connection()`
- Validates user inputs.
- Parses baud rate.
- Calls `self.board_manager.connect(...)`.
- Updates the connection status indicator and/or shows errors.

#### `start_tracking()`
- Validates:
  - city is provided
  - satellite is provided and exists in satellite database
- Geolocates city with `api.get_geolocation(city)`.
- Parses observer altitude.
- Updates UI labels for observer data.
- Creates a `TrackingWorker` with the combined config.
- Connects signals:
  - `worker.data_ready -> update_satellite_data`
  - `worker.error_occurred -> show_error`
- Starts the worker thread.
- Places the initial observer marker on the map.

#### `update_satellite_data(data)`
- Updates all telemetry labels with new values.
- Updates local time/UTC/timezone labels.
- Computes current Sun & Moon positions using `CelestialCalculator`.
- Executes JavaScript in the embedded map to:
  - remove and recreate satellite/sun/moon markers
  - extend the satellite path polyline
- Sends telemetry to the board through `self.board_manager.send_data(data)`.

#### `stop_tracking()`
- Stops the worker and resets UI button states.

#### `filter_satellites()` / `select_satellite()`
- Implements client-side satellite name filtering.

#### `show_error(message)`
- Appends a timestamped line into the “Problems” text panel.

#### Logging and monitoring helpers
- `show_logging_diagnostics()` opens `LoggingVerificationDialog`.
- `update_log_display()` reloads the log file content into the Output tab.
- `update_memory_display()` uses `psutil` to show RSS and system memory.

---

### `src/ui/map_bridge.py`
Defines `MapBridge`, a QObject-based signal bridge for JS/Python communication.

Currently:
- It defines an `update_map(lat, lng)` signal.
- Includes a `update_position(lat, lng)` slot that emits the signal.

The current `main_window.py` implementation does not appear to wire this
bridge into JavaScript; it is provided for future extension.

---

### `src/ui/components.py`
Includes UI components related to logging diagnostics.

#### `LoggingVerificationDialog`
A dialog that runs logging tests and verifies log file write permissions.

`run_full_test()`:
- Emits one test message at each logging level: DEBUG/INFO/WARNING/ERROR.
- Checks if the log file exists.
- Attempts to append to the log file.

#### `LogMonitor` (not currently used by main UI)
A QThread that periodically checks log file size to detect:
- ACTIVE (file grows)
- STALLED (size unchanged)
- MISSING

---

## 8) `src/__init__.py` and package `__init__.py` files

The package initializers exist so Python treats directories as importable
packages. They typically contain minimal or no logic.

---

## 9) Summary of runtime flow

High-level execution path:
1. `main.py` starts the Qt app and builds `SatelliteTracker`.
2. `SatelliteTracker.start_tracking()`:
   - geolocates city
   - spawns `TrackingWorker`
3. `TrackingWorker.run()` periodically calls N2YO API and computes telemetry.
4. Telemetry is emitted to UI; UI updates:
   - text labels
   - Leaflet map markers/path
   - UART board output
5. UI timers keep refreshing:
   - log file content
   - process/system memory info

---

## 10) REUSE actions you may take next (recommended)

To improve REUSE strictness:
- Add `SPDX-License-Identifier: MIT` to each `*.py` file (including inside `src/`).
- Optionally update `REUSE.toml` if you add third-party code/files with
  different licenses.

---

End of REUSE.md

