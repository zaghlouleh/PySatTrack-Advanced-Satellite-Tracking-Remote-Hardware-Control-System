# REUSE & Licensing / Code Documentation

This repository contains:
- A Python/Tkinter desktop application that fetches satellite TLE data from **N2YO** and computes orbital parameters using **Skyfield**.
- A serial (UART) pipeline that sends the computed values as JSON to an Arduino sketch.
- An Arduino sketch that parses the JSON and drives two stepper motors and an LCD.

## 1) License overview (REUSE)

This project is released under the **MIT License** (see `LICENSE`).

### Third-party components
This repository also uses third-party libraries and tools, including (but not limited to):
- Python libraries: `requests`, `skyfield`, `ttkthemes`, `pyserial`
- Arduino libraries: `ArduinoJson`, `AccelStepper`, `LiquidCrystal`
- A data source: N2YO API

These components are governed by their own licenses. They are not relicensed by this repository.

### Repository files under MIT
All repository-owned source and documentation files created as part of this project are intended to be MIT.

## 2) Prerequisites before running (API keys / account info)

This application must be configured before it can fetch TLE data.

1. Open `config.py`.
2. Set `N2YO_API_KEY` to your N2YO account API key.
3. Start the program only after the API key is set correctly.

If you use a `.env`-based workflow, ensure the environment variables are loaded into `config.py` (current code reads the API key directly from `config.py`).

---

## 3) How the application works (high-level)

The overall flow is:

1. **GUI input (Tkinter)**
   - User selects a satellite name.
   - User selects an Arduino serial port and baud rate.

2. **Satellite ID resolution**
   - The app loads `namesat+idsat.json` to map satellite display names to numeric satellite IDs.

3. **Network fetch (N2YO)**
   - The app calls the N2YO REST API endpoint to fetch the satellite TLE lines.

4. **Orbital computation (Skyfield)**
   - The app constructs a Skyfield `EarthSatellite` from the TLE lines.
   - The app extracts model parameters from Skyfield.

5. **Serialization (JSON)**
   - The app writes the computed orbital parameters to a local JSON file named after the satellite.

6. **Serial transfer to Arduino**
   - The app JSON-serializes the computed parameters and writes them over the serial port.

7. **Arduino parsing and actuation**
   - The Arduino sketch receives the JSON string.
   - It parses the values and performs calculations to derive Cartesian coordinates.
   - It uses AccelStepper to move two stepper motors (one per axis) and displays status on the LCD.

## 4) File-by-file explanation

### `main.py`
Entry point for the desktop application.

Key responsibilities:
- Configures logging to write to `script.log`.
- Creates the main Tk window using `ThemedTk` from `ttkthemes`.
- Instantiates the main UI container `MainView`.
- Runs the Tk event loop.

Important code paths:
- `main()` sets up `logging.basicConfig(...)`.
- The UI is started by:
  - `root = ThemedTk(theme=config.THEME_NAME)`
  - `app = MainView(root)`
  - `root.mainloop()`

### `config.py`
Central configuration/constants.

Contains:
- N2YO API configuration:
  - `N2YO_API_KEY`: placeholder string.
  - `N2YO_BASE_URL`: base URL (not directly used by current code; the URL is composed in `satellite_service.py`).
- Retry/timeout settings:
  - `MAX_RETRIES`, `RETRY_DELAY` (note: `RETRY_DELAY` is defined but currently unused in `fetch_tle_data`), `TIMEOUT`.
- Data source:
  - `DB_FILENAME = "namesat+idsat.json"`
- UI settings:
  - theme (`THEME_NAME`), window title/size.
- Style constants:
  - font families, and Tkinter style dicts (`STYLE_LABEL`, `STYLE_ENTRY`, `STYLE_BUTTON`, `STYLE_TEXT`).

### `services/__init__.py`
Marks the `services` package.

### `services/satellite_service.py`
All satellite-related functionality:

#### `load_satellite_data(filename)`
- Loads the JSON mapping from disk.
- Returns a dict of `{satellite_name: satellite_id}`.

#### `load_satellite_names(filename)`
- Loads the JSON mapping and returns `list(data.keys())`.
- Present but not currently used by the UI (the UI uses `load_satellite_data`).

#### `get_satellite_id(satellite_name, satellite_data)`
- Looks up the numeric ID for a chosen satellite name.

#### `fetch_tle_data(satellite_id, api_key, max_retries=3, timeout=50)`
- Calls N2YO API to fetch TLE data.
- Retries on network/request exceptions.
- Handles common response error patterns:
  - `403` indicates API key issues.
  - Non-200 status codes raise.
  - JSON parse failures raise.
  - If response contains `error` or missing `tle`, raises.
- Returns the raw `data['tle']` string on success.

#### `calculate_orbital_data(satellite_name, tle_str)`
- Splits TLE string into lines.
- Constructs `EarthSatellite` using Skyfield.
- Loads a timescale via `load.timescale()` (currently not used for propagation; it’s used in the model parameter extraction stage).
- Extracts model parameters from `satellite.model`:
  - semi-major axis, eccentricity, inclination
  - argument of periapsis
  - ascending node
  - mean anomaly
- Computes a `longitude` term as:
  - `ascending_node + mean_anomaly`
- Returns a dict with these values:
  - `argument_periapsis`, `eccentricity`, `inclination`, `mean_anomaly`, `semi_major_axis`, `ascending_node`, `longitude`

### `services/arduino_service.py`
All serial communications and port discovery.

#### `find_arduino_ports(description)`
- Uses `serial.tools.list_ports.comports()` to enumerate ports.
- If `description` is empty, returns all devices.
- Otherwise filters ports whose `p.description` contains `description` (case-insensitive).

#### `send_data_to_arduino(port, baud_rate, data_dict)`
- Opens serial with `serial.Serial(port, baud_rate)`.
- Waits 2 seconds for Arduino bootloader/serial readiness.
- Serializes `data_dict` to JSON string and writes bytes to serial.
- Closes the serial port in a `finally` block.

### `views/__init__.py`
Marks the `views` package.

### `views/main_view.py`
GUI and application orchestration.

#### `MainView.__init__(self, root)`
- Configures the window (title, geometry, background).
- Loads `namesat+idsat.json` using `satellite_service.load_satellite_data(...)`.
- Builds the UI widgets.
- Registers event bindings.
- Auto-scans for Arduino ports on startup.

#### `build_ui(self)`
Creates:
- Satellite input `Entry`.
- Arduino port input `Entry`.
- Baud rate input `Entry` (defaults to `9600`).
- Arduino board description filter `Entry` (defaults to `Arduino`).
- “Fetch & Send Data” button.
- A scrollable log console.
- A floating Listbox used for satellite name autocomplete.

#### Autocomplete logic
- `setup_bindings()` binds focus/key events on satellite entry.
- `render_suggestions()`:
  - If user input exactly matches a known satellite name, hides the list.
  - Otherwise filters names by substring matching (case-insensitive).
  - Shows a listbox positioned below the entry.
- `on_suggestion_select()` handles click selection in the listbox.

#### `auto_verify_ports(self)`
- Reads the Arduino description filter.
- Calls `arduino_service.find_arduino_ports(...)`.
- If ports are found:
  - Displays them in the log.
  - Prefills `entry_port` with the first port if port input is currently empty.

#### Main action: `on_fetch_clicked(self)`
- Validates required fields: satellite name, port, baud.
- Parses baud as integer.
- Clears the log output.
- Calls `display_web_browser()` to open N2YO website.
- Starts the background worker thread to keep the UI responsive.

#### `transfer_process_worker(self, sat_name, port, baud_rate)`
Runs the full pipeline asynchronously:
1. Resolve satellite id with `satellite_service.get_satellite_id(...)`.
2. Fetch TLE via `satellite_service.fetch_tle_data(...)`.
3. Compute orbital values via `satellite_service.calculate_orbital_data(...)`.
4. Save computed orbital data to `<sat_name>.json`.
5. Send orbital data JSON over serial via `arduino_service.send_data_to_arduino(...)`.
6. Logs success/failure for each step.

### `Export_TLE_data_to_Arduino.ino`
Arduino sketch receiving JSON and moving stepper motors.

Key dependencies:
- `ArduinoJson` for parsing JSON from `Serial`.
- `AccelStepper` for motor control.
- `LiquidCrystal` for LCD display.

#### Hardware configuration
- Defines two stepper motor driver pin pairs:
  - Stepper 1: pins 2 and 3
  - Stepper 2: pins 4 and 5
- Defines LCD wiring pins:
  - LCD pins are configured for `LiquidCrystal lcd(12, 11, 7, 6, 5, 4)`
- `STEPS_PER_REV = 200` is used to scale computed coordinates into stepper targets.

#### `setup()`
- Initializes the LCD and prints “Ready”.
- Sets max speed and acceleration for both steppers.
- Starts serial at 9600 baud.

#### `loop()`
- Waits for incoming serial bytes.
- Parses incoming JSON using `deserializeJson`.
- On JSON parse error:
  - LCD shows “JSON Error” briefly, then “Ready”.
- On success:
  - Reads values from JSON into variables:
    - `radius` and `inclination`, `azimuth`, `speed`, `argument_periapsis`, `eccentricity`, `mean_anomaly`, `semi_major_axis`, `longitude`
  - Computes:
    - `true_anomaly` from mean anomaly and eccentricity
    - recomputes `radius` using semi-major axis, eccentricity, and anomaly
    - Cartesian coordinates `x`, `y`, `z` using inclination, argument of periapsis, and longitude
  - Displays “Cartesian:” and prints coordinates on LCD.
  - Moves both steppers:
    - `stepper1.moveTo(x * STEPS_PER_REV)`
    - `stepper2.moveTo(y * STEPS_PER_REV)`
  - Calls `runToPosition()` for each motor.

**Note about data schema mismatch:**
The Python side currently computes and sends:
- `argument_periapsis`, `eccentricity`, `inclination`, `mean_anomaly`, `semi_major_axis`, `ascending_node`, `longitude`

The Arduino sketch tries to read additional keys:
- `radius`, `azimuth`, `speed`

If those keys are absent, Arduino will read default/zero values for missing keys, which will affect motor movements/calculations. You may want to align the JSON schema if you extend the project.

## 4) Dependency & build information

### Python dependencies
Declared in `requirements.txt`.

### Arduino dependencies
Arduino dependencies are library-specific and typically installed via the Arduino IDE/library manager.

## 5) Data file: `namesat+idsat.json`

- This file is a large JSON mapping from human-readable satellite names to numeric IDs.
- The desktop UI uses it to resolve the selected satellite name to an ID used for N2YO API requests.

License note: this repository treats it as MIT content (per this repository’s REUSE documentation). If you change the data source or provenance, re-evaluate licensing accordingly.

## 6) REUSE compliance status

- `REUSE.md`, `LICENSE`, `REUSE.toml`, and `REUSE-toolbox.txt` have been added.
- The repository uses a uniform MIT license for project-owned files.

To fully automate REUSE scanning in future, the recommended next step is to add SPDX license headers to each source file that needs attribution (Python and Arduino), or to maintain a toolbox-based mapping and run `reuse-toolbox` / `reuse lint` in your workflow.

