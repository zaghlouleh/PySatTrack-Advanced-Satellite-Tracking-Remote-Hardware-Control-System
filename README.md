# REUSE.md — Project documentation for REUSE Software compliance

This repository follows the **REUSE Software** specification for licensing and
attribution.

## License overview

- The project license is the existing `LICENSE` file at the repository root.
- Source code and documentation in this repository are intended to be covered
  by that license.

## How the code is organized

The application is a **PyQt5 desktop UI** that:

1. Lets the user select a satellite and enter an observer location (city + altitude).
2. Uses external APIs to fetch:
   - geolocation from OpenCage
   - satellite position data from N2YO
3. Polls periodically in a background thread.
4. Updates the UI (telemetry panels) and a Leaflet map rendered inside a `QWebEngineView`.
5. (Optionally) sends azimuth/elevation values to an Arduino controller over a serial connection.

## Runtime flow (high level)

- `main.py`
  - creates the `QApplication`
  - applies the global stylesheet
  - instantiates `SatelliteTracker` from `src/ui/main_window.py`

- `SatelliteTracker` (`src/ui/main_window.py`)
  - builds the UI widgets (input panel, telemetry panel, tabs)
  - builds the Leaflet HTML map via `setHtml()`
  - when tracking starts, creates a `WorkerThread`

- `WorkerThread` (`src/ui/worker.py`)
  - loops while running
  - calls `APIClient.get_satellite_position()`
  - derives speed and orbital period
  - emits `data_ready` with a normalized telemetry dict

- UI update
  - `SatelliteTracker.update_satellite_data()` receives the dict
  - updates labels (speed, azimuth, elevation, RA/DEC, LST, etc.)
  - updates the Leaflet markers/polyline using `runJavaScript()`

- Persistence
  - `WorkerThread` saves each telemetry payload via `DataManager.save_satellite_data()`

## File-by-file documentation

### `main.py`

Purpose: Application entrypoint.

Key steps:
- Initializes `QApplication(sys.argv)`.
- Sets application name and organization.
- Sets window icon from `icon.ico`.
- Applies `APP_STYLESHEET` from `src/ui/styles.py`.
- Creates `SatelliteTracker()` and shows it maximized.
- Starts the Qt event loop with `app.exec_()`.

### `src/config.py`

Purpose: Central configuration.

Components:
- Loads environment variables from `.env` using `python-dotenv`.
- Provides API keys with fallbacks:
  - `N2YO_API_KEY`
  - `OPENCAGE_API_KEY`
- Defines tuning defaults:
  - `DEFAULT_BAUD_RATE`
  - `MAX_SECONDS`, `MAX_DAYS`
- Sets up logging:
  - `LOG_FILE = 'satellite_tracker.log'`
  - `logging.basicConfig(...)`
- Exposes `get_logger()` for retrieving a named logger.

### `src/core/models.py`

Purpose: Data structures (domain models).

Defines dataclasses:
- `SatellitePosition`
  - latitude, longitude, altitude, azimuth, elevation
- `SatellitePass`
  - start/max/end times and maximum elevation
- `Observer`
  - observer latitude/longitude/altitude + city name

Note: In the current codebase, these models are not extensively used by the UI/worker
(the worker uses plain dictionaries). They remain available for future refactors.

### `src/core/calculator.py`

Purpose: Astronomical calculations.

Defines `CelestialCalculator`:
- `sun_position(dt)`
  - uses `skyfield` ephemeris (`de421.bsp`) and timescale
  - computes Sun position as seen from Earth
  - returns a latitude/longitude pair representing the subsolar point

- `moon_position(dt)`
  - similar approach using `eph['moon']`
  - returns approximate geographic coordinates derived from RA/DEC

These calculations are called from the UI during telemetry updates to draw sun/moon
markers on the map.

### `src/services/api_client.py`

Purpose: All external HTTP API interactions.

Defines `APIClient`:
- `get_geolocation(city)`
  - calls OpenCage geocoding endpoint
  - returns `(lat, lng)` or `(None, None)` on errors/unauthorized responses

- `get_satellite_position(sat_id, lat, lng, alt)`
  - calls N2YO satellite positions endpoint requesting two positions (`/2/`)
  - returns parsed JSON on success, otherwise `None`

Important behavior:
- N2YO is expected to provide fields used by the worker:
  - `positions[*].satlatitude`, `satlongitude`, `sataltitude`, `azimuth`, `elevation`, `ra`, `dec`, `eclipsed`, `timestamp`

### `src/services/data_manager.py`

Purpose: Thread-safe caching + persistence.

Defines `DataManager`:
- Holds:
  - a `threading.Lock`
  - an in-memory `_cache` dict
- `save_satellite_data(satellite_name, data)`
  - writes `f"{satellite_name}.json"` with pretty JSON
  - updates the in-memory cache
  - logs success/failure
- `load_satellite_data(satellite_name)`
  - returns cached data if available
  - otherwise tries to read `f"{satellite_name}.json"`

Also exports a global instance:
- `satellite_data_manager = DataManager()`

### `src/services/arduino.py`

Purpose: Serial communication with an Arduino controller.

Defines `ArduinoManager` (QObject + signals):
- `connection_changed = pyqtSignal(bool)`

Methods:
- `connect(port, baud_rate)`
  - opens a `serial.Serial(...)` connection
  - emits `connection_changed(True)` on success
- `send_data(data)`
  - expects a dict with keys `azimuth` and `elevation`
  - sends `"{azimuth},{elevation}\n"` over serial

Important note:
- While the Arduino manager exists, the main UI currently does not wire its output
  into the tracking update loop.

### `src/ui/styles.py`

Purpose: Central stylesheet constants.

Exposes:
- `APP_STYLESHEET`
  - global dark theme
  - widget styling
  - styling rules based on dynamic Qt properties:
    - `QLineEdit[valid=true|false]`
    - `QLabel[role=telemetry]`
    - `QLabel[elevation-green|elevation-red]`
    - `QLabel[speed-high]`
- `TAB_WIDGET_STYLE`
  - QTabWidget + tab appearance
- `ERROR_DISPLAY_STYLE`
  - red text on dark background
- `LOG_DISPLAY_STYLE`
  - normal log text on dark background

### `src/ui/main_window.py`

Purpose: Main Qt window and UI logic.

Defines `SatelliteTracker(QWidget)`.

Core state:
- `self.api`: instance of `APIClient`
- `self.data_manager`: shared global `satellite_data_manager`
- `self.arduino`: instance of `ArduinoManager`
- `self.worker`: the currently running `WorkerThread` (or `None`)
- `self.satellites`: loaded satellite name -> id mapping from `namesat+idsat.json`
- `self.observer_values` and `self.satellite_values`: dicts of `QLabel` widgets

Key methods:
- `load_satellites()`
  - reads `namesat+idsat.json`

- `init_ui()`
  - creates the left input panel:
    - satellite search input + list
    - city input
    - altitude input
    - update interval input
    - Arduino port/baud inputs (currently not used in `start_tracking`)
  - creates the map container (`QWebEngineView`)
  - creates the right telemetry panel and tabs
  - starts a timer to refresh the log display

- `create_input_fields(layout)`
  - constructs input widgets and connects signals:
    - `textChanged -> validate_inputs`
    - `textChanged -> filter_satellites`
    - list item click -> `select_satellite`

- `create_info_displays(layout)`
  - constructs UI groups and their labeled telemetry fields
  - telemetry labels are keyed so updates can address them by name

- `init_map()`
  - sets Leaflet HTML via `map_view.setHtml(...)`
  - adds OpenStreetMap tile layer
  - defines JS variables for:
    - observerMarker, satelliteMarker, satellitePath
    - sunMarker, moonMarker
  - starts `celestial_timer` (every 300000ms), but the current
    implementation of `update_celestial_positions()` is a placeholder (`pass`).

- `validate_inputs()`
  - validates that satellite exists in the loaded dataset
  - validates non-empty city input
  - validates interval and altitude numeric parsing
  - updates Qt dynamic properties so styling reflects validity
  - enables/disables the start button

- `start_tracking()`
  - validates the button state
  - fetches geolocation for the entered city
  - creates `WorkerThread(...)` with tracking config
  - connects:
    - `worker.data_ready -> update_satellite_data`
    - `worker.error_occurred -> show_error`
  - starts the worker thread
  - initializes JS markers and map view centered on the observer

- `update_satellite_data(data)`
  - updates telemetry label values and applies dynamic styling
  - uses `CelestialCalculator` to compute sun/moon coordinates
  - updates Leaflet using `runJavaScript()`:
    - moves/extends satellite marker/path
    - re-renders sun/moon markers

- `stop_tracking()`
  - stops the worker thread
  - clears satellite marker/path
  - resets UI controls

- `update_log_display()`
  - reads `LOG_FILE` and shows it in the Output tab

### `src/ui/worker.py`

Purpose: Background polling + derived metrics.

Defines `WorkerThread(QThread)`:
- Signals:
  - `data_ready = pyqtSignal(dict)`
  - `error_occurred = pyqtSignal(str)`

Constructor:
- Accepts:
  - `api: APIClient`
  - `data_manager: DataManager`
  - `config: dict` with keys:
    - `sat_id`, `sat_name`, `obs_lat`, `obs_lng`, `obs_alt`, `interval`

Metric helpers:
- `calculate_lst(longitude, dt)`
  - computes local sidereal time from a simplified GMST approximation

- `calculate_speed(positions)`
  - uses the Haversine formula between two consecutive N2YO positions
  - divides by the time difference (in hours) to return km/s

`run()` loop behavior:
1. Call `api.get_satellite_position(...)`.
2. Validate response has at least two positions.
3. Derive:
   - `speed_kms`, `speed_mis`
   - orbital period (Kepler’s third law) from `sataltitude`
   - `lst`
4. Create `full_data` dict with normalized keys (UI expects these).
5. Save payload to JSON using `DataManager.save_satellite_data(...)`.
6. Emit `data_ready(full_data)`.
7. Sleep for `config['interval']`.

`stop()`:
- sets `self.running = False` to exit the loop.

### `src/ui/map_bridge.py`

Purpose: Intended JS/Python bridge.

Defines `MapBridge(QObject)`:
- `update_map = pyqtSignal(float, float)`
- `update_position(lat, lng)` emits the signal

Note:
- The current Leaflet HTML does not connect to this bridge.

## External dependencies

The application depends on:
- PyQt5 + PyQtWebEngine for GUI and embedded browser
- requests for HTTP calls
- pyserial for Arduino serial I/O
- python-dotenv for environment variables
- skyfield for celestial computations (requires `de421.bsp`)
- numpy (present in requirements though not heavily used by current code)

## Required user configuration (.env)

This application will contact external services (OpenCage + N2YO) using API keys.

Before starting the program:
1. Open the repository `.env` file.
2. Set your API keys:
   - `N2YO_API_KEY` (used by `src/services/api_client.py`)
   - `OPENCAGE_API_KEY` (used by `src/services/api_client.py`)
3. Confirm any defaults in `src/config.py` match your expected setup.

If these keys are missing or incorrect, the app’s API calls will fail (geolocation
may not resolve, and satellite position updates will not be retrieved).

## REUSE verification

To validate licensing metadata compliance:

- Run:
  - `reuse lint`

If this repository reports missing license headers, update the source files with SPDX
headers matching the SPDX license identifier for MIT (e.g. `MIT`).

## Notes found during code review (non-blocking)

- `src/ui/main_window.py` contains:
  - a TODO placeholder for fullscreen map toggling
  - `update_celestial_positions()` currently has a `pass`
- UI currently collects Arduino port/baud values but does not connect/start Arduino.

These are implementation notes and do not affect licensing.


