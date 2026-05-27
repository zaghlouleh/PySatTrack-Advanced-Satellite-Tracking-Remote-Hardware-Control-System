# REUSE.md — Repository documentation (code overview)

This document explains the parts of the codebase in this repository and how they relate to each other.

## 1. High-level architecture

The project is a “satellite tracker” application with:
- **Python GUI** (PyQt5) that lets a user select a satellite and a city, then fetches real-time satellite position data.
- **API integration** to:
  - Geocode a city into latitude/longitude.
  - Fetch satellite position (azimuth/elevation and related coordinates).
- **Local persistence** of fetched data into JSON files.
- **Arduino communication** over a serial connection, sending the fetched data to firmware.
- An **Arduino sketch** (`Export_TLE_data_to_Arduino.ino`) that reads JSON from serial and moves stepper motors.

### Modules by responsibility
- `main.py`: Python entrypoint, starts the GUI event loop.
- `src/config.py`: configuration (API keys, paths) + logging setup.
- `src/services/api_service.py`: external API calls (geocoding + satellite positions).
- `src/services/tracking_service.py`: orchestrates fetching + saving + sending to Arduino.
- `src/models/data_manager.py`: loads/stores satellite mappings and tracking JSON outputs.
- `src/hardware/arduino.py`: discovers Arduino ports and sends JSON over serial.
- `src/ui/main_window.py`: GUI widgets and user interaction.
- `Export_TLE_data_to_Arduino.ino`: Arduino firmware (LCD + stepper motors) that parses incoming JSON.

## 2. Python entrypoint

### `main.py`

Responsibilities:
- Calls `setup_logging()`.
- Creates `QApplication`.
- Sets the application icon (`icon.ico`).
- Instantiates and shows the main GUI window: `SatelliteUpdater`.
- Starts the Qt event loop.

Key function:
- `main()` — wraps GUI initialization and execution.

Execution:
- `if __name__ == '__main__': main()`.

## 3. Configuration & logging

### Required user setup: API keys (.env and `src/config.py`)
Before running the program, you **must** provide your own API keys.

1. Open **`.env`** in the repository root.
   - Add your OpenCage and N2YO API values (exact variable names should match what the project expects).
2. Open **`src/config.py`**.
   - Replace the placeholder values in:
     - `Add_Your_OPENCAGE_API_KEY`
     - `Add_Your_N2YO_API_KEY`

If you do not set these values, calls in `src/services/api_service.py` will fail and the GUI will show errors when fetching data.



### `src/config.py`

Responsibilities:
- Stores external API keys (OpenCage + N2YO).
- Computes repository-relative paths:
  - `DATA_DIR` → `./data`
  - `LOG_DIR` → `./logs`
  - `SATELLITE_DATA_FILE` → `data/namesat+idsat.json`
  - `LOG_FILE` → `logs/script.log`
- Ensures `data/` and `logs/` exist.
- Exposes `setup_logging()`.

Important values:
- `OPENCAGE_API_KEY`
- `N2YO_API_KEY`
- `SATELLITE_DATA_FILE`
- `LOG_FILE`

Logging:
- `setup_logging()` calls `logging.basicConfig(...)` so all modules using `logging` write to `logs/script.log`.

## 4. External APIs

### `src/services/api_service.py`

Responsibilities:
- `fetch_geolocation_data(city_name)`: uses **OpenCage** API to convert a city name to `(lat, lng)`.
- `fetch_satellite_position(observer_lat, observer_lng, observer_alt, seconds, satellite_id)`: uses **N2YO** API to retrieve satellite position for a given observer and time window.

#### `fetch_geolocation_data(city_name)`
- Builds URL:
  - `https://api.opencagedata.com/geocode/v1/json?q={city_name}&key={OPENCAGE_API_KEY}`
- Sends `requests.get(...)`.
- If results exist, returns:
  - `lat = results[0]['geometry']['lat']`
  - `lng = results[0]['geometry']['lng']`
- On failure (HTTP error or missing data): logs error and returns `(None, None)`.

#### `fetch_satellite_position(...)`
- Builds URL:
  - `https://api.n2yo.com/rest/v1/satellite/positions/{satellite_id}/{observer_lat}/{observer_lng}/{observer_alt}/{seconds}/&apiKey={N2YO_API_KEY}`
- Calls `requests.get(...)` and parses JSON.
- Reads `position_data['positions']` and selects the latest entry (`positions[-1]`).
- Returns a dict with:
  - `satlatitude`
  - `satlongitude`
  - `sataltitude`
  - `azimuth`
  - `elevation`
- If no positions are present or request fails, returns `None`.

## 5. Orchestration (fetch loop + Arduino send)

### `src/services/tracking_service.py`

Responsibilities:
- Provides functions that:
  1. Resolve satellite name → satellite ID.
  2. Fetch geolocation for a city.
  3. Fetch satellite position.
  4. Save the results as JSON.
  5. Optionally send the results to an Arduino.
- Supports both:
  - a **single fetch**
  - a **continuous background update** loop

Key functions:

#### `continuous_update(satellite_name, city_name, observer_alt, seconds, arduino_port, baud_rate, satellite_id, callback_msg_func)`
- Runs an infinite `while True` loop.
- Steps per iteration:
  1. Geocode city → `(observer_lat, observer_lng)`.
  2. Fetch satellite position using N2YO.
  3. Save satellite tracking info to `data/{satellite_name}.json`.
  4. Wait: `time.sleep(int(seconds))`.

Notes:
- On geolocation/position failure, it writes an error message to the GUI via `callback_msg_func` and returns.

#### `run_single_fetch_and_send(...)`
- Validates GUI inputs:
  - `seconds` must be an integer <= 300
  - `observer_alt` must be convertible to float
- Resolves satellite ID using the mapping from `data/namesat+idsat.json`.
- Fetches geolocation, then fetches satellite position.
- Saves fetched data to `data/{satellite_name}.json`.
- Sends JSON to Arduino using `send_data_to_arduino(...)`.
- Reports success/failure to GUI using `callback_msg_func(message, color)`.

#### `fetch_satellite_data_threaded(...)`
- Creates a daemon `threading.Thread` running `continuous_update(...)`.
- Resolves satellite ID before starting the thread.
- Starts the thread and returns immediately.

Important threading behavior:
- The continuous update function uses the API and file writes repeatedly in the background.

## 6. Data persistence (satellite mappings + outputs)

### `src/models/data_manager.py`

Responsibilities:
- Load the mapping between satellite names and satellite IDs.
- Provide helper functions to:
  - list satellite names for auto-suggestion in the GUI
  - get a satellite ID for a selected satellite name
  - save fetched tracking data into JSON files

Key functions:

#### `load_all_satellite_mappings()`
- Loads JSON from `SATELLITE_DATA_FILE`.
- Returns `{}` and logs an error if the file is missing or parsing fails.

#### `load_satellite_names()`
- Uses `load_all_satellite_mappings()`.
- Returns a list of keys (satellite names).

#### `get_satellite_id(satellite_name, mapping_data)`
- Returns `mapping_data.get(satellite_name, None)`.

#### `save_satellite_tracking_info(satellite_name, data)`
- Writes JSON to `DATA_DIR/{satellite_name}.json`.
- Returns the filename on success; logs error and returns `None` on failure.

## 7. Arduino hardware integration

### `src/hardware/arduino.py`

Responsibilities:
- Discover candidate Arduino serial ports.
- Send JSON data to an Arduino using serial communication.

#### `get_arduino_ports(arduino_description)`
- Uses `serial.tools.list_ports.comports()`.
- Filters ports where `arduino_description in p.description`.
- Returns a list of matching device paths.

#### `send_data_to_arduino(arduino_port, baud_rate, data_dict)`
- Opens serial connection:
  - `serial.Serial(arduino_port, baud_rate)`
- Waits 2 seconds for the Arduino to initialize.
- Verifies `arduino.is_open`.
- Sends data:
  - `json.dumps(data_dict)`
  - writes bytes via `arduino.write(...)`.
- Closes the serial connection.
- Returns `(True, "...")` or `(False, "error...")`.

## 8. GUI (user interaction + display/logging)

### `src/ui/main_window.py`

Responsibilities:
- Defines `SatelliteUpdater(QWidget)` — the main PyQt window.
- Provides inputs for:
  - satellite name
  - city name
  - observer altitude
  - update seconds
  - Arduino port / baud rate / Arduino description
- Provides an auto-suggestion list for satellite names.
- Provides a log/status text area.
- Triggers background fetching via `fetch_satellite_data_threaded`.

Key class: `SatelliteUpdater`

#### Initialization
- `__init__`:
  - loads satellite name list via `load_satellite_names()`
  - builds the UI via `init_ui()`
  - checks for an Arduino port via `check_initial_arduino()`

#### UI creation: `init_ui()`
- Creates labels + `QLineEdit` inputs.
- Satellite name input connects `textChanged` → `update_suggestions()`.
- Suggestion list uses `itemClicked` → `on_suggestion_select()`.
- Fetch button connects `clicked` → `on_fetch_clicked()`.
- Logs panel uses `QTextEdit` in a scroll area.

#### Suggestion logic
- `update_suggestions()`:
  - filters loaded satellite names by the current partial input (case-insensitive)
  - shows up to 5 matches

#### Arduino discovery
- `check_initial_arduino()`:
  - reads user-provided Arduino description string
  - calls `get_arduino_ports(desc)`
  - appends a green “Arduino found” message or red “No Arduino” message

#### Fetch trigger
- `on_fetch_clicked()`:
  - shows an indeterminate progress bar (`setRange(0, 0)`)
  - disables the fetch button
  - uses `QTimer.singleShot(3000, self.on_fetch_complete)` to simulate a delay
  - appends “Fetching...” to the log
  - calls `fetch_satellite_data_threaded(...)`, passing:
    - satellite name
    - city name
    - observer altitude
    - seconds
    - arduino port
    - baud rate
    - arduino description
    - `self.append_log` as callback

#### Logging helper
- `append_log(message, color_name="black")`:
  - moves cursor to end
  - sets text color
  - appends message

## 9. Arduino firmware

### `Export_TLE_data_to_Arduino.ino`

Responsibilities:
- Initializes:
  - LiquidCrystal LCD
  - two AccelStepper stepper motors (FULL4WIRE mode)
  - Serial communication at 9600 baud
- In `loop()`:
  - reads JSON messages from serial
  - deserializes JSON using ArduinoJson
  - computes Cartesian coordinates from orbital/Kepler-related values
  - displays “Cartesian” on the LCD
  - uses computed coordinates to move stepper motors

Important code sections:
- Includes:
  - `ArduinoJson.h`, `AccelStepper.h`, `LiquidCrystal.h`
- Hardware pin mapping:
  - Stepper 1 pins: 2, 3
  - Stepper 2 pins: 4, 5
- `setup()`:
  - LCD “Ready”
  - sets speed/acceleration
  - `Serial.begin(9600)`
- `loop()`:
  - if `Serial.available()`:
    - creates `StaticJsonDocument<256>`
    - `deserializeJson(jsonBuffer, Serial)`
    - extracts many fields (radius, inclination, azimuth, speed, argument_periapsis, eccentricity, mean_anomaly, semi_major_axis, longitude)
    - computes `true_anomaly`
    - updates `radius` based on Kepler relation
    - computes `x,y,z`
    - updates LCD
    - moves motors:
      - `stepper1.moveTo(x * STEPS_PER_REV)`
      - `stepper2.moveTo(y * STEPS_PER_REV)`

## 10. REUSE/SBOM-style notes

This repository uses the REUSE specification via:
- `REUSE.toml`
- `REUSE-toolbox.txt`

License:
- MIT license text is in `./LICENSE`.

## 11. What to do next (maintainers)

If you extend the project:
- Prefer updating `src/config.py` for new configuration items.
- Keep API calls inside `src/services/api_service.py`.
- Keep orchestration in `src/services/tracking_service.py`.
- Keep persistence logic in `src/models/data_manager.py`.
- Keep hardware I/O in `src/hardware/arduino.py`.
- Keep GUI logic in `src/ui/main_window.py`.

