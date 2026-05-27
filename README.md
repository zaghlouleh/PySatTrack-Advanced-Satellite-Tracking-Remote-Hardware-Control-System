# SatTrack V5 — Comprehensive Code & Licensing README (REUSE-style)

This document has two goals:
1) Provide a **detailed walkthrough of all parts of the codebase** (modules, responsibilities, and key flows).
2) Provide a **clear licensing posture** for the project’s original code and how third-party licenses/assets should be handled.

---

## 1) High-level overview

SatTrack Terminal v5 is a Python (PyQt5) desktop application that:
- Loads and parses TLE (Two-Line Element) catalogs.
- Predicts orbits/pass geometry using Skyfield.
- Continuously tracks a selected satellite using N2YO real-time telemetry.
- Optionally queries radio frequency info from SatNOGS (with local caching).
- Optionally queries geocoding (OpenCage) to configure the ground station.
- Displays an interactive map (Leaflet HTML/JS) and overlays predicted and tracked telemetry.
- Optionally connects to external hardware (via `pyserial`) to provide real-time tracking angles.

---

## 2) Repository layout

At the root you have:
- `main.py` — Application entry point (Qt initialization + window creation).
- `requirements.txt` — Python dependencies.
- `LICENSE` — License for the repository’s original source code (MIT).
- `REUSE.toml`, `REUSE.md`, `REUSE-toolbox.txt` — Licensing compliance scaffolding.

Key folders:
- `src/` — Application source code.
- `assets/` — Web map assets (Leaflet page, etc.).
- `video/` and `Photo/` — Media assets bundled with the project.
- `tle_data/` — TLE seed/catalog files (varies by provider/type).
- `satnogs_cache/` — Local cache for SatNOGS-derived transmitter/frequency lookups.
- `satellite_data/` — Local telemetry storage (created/used by the app at runtime).
- `logs/` — Application log output.
- `firmware/` — Arduino firmware source.
- `de421.bsp` — JPL ephemeris kernel used by Skyfield for Sun/Moon positions.

---

## 3) Application entry point (`main.py`)

### Responsibilities
- Configures Qt WebEngine paths (important on Windows).
- Sets application-wide environment flags (e.g., GPU disable for stability).
- Installs a global exception hook that logs and shows a critical UI error.
- Creates `QApplication`, applies the UI theme (`CYBER_DARK_THEME`), and opens `MainWindow`.

### Key behaviors
- `global_exception_hook(...)`:
  - Logs the exception to the app logger.
  - Displays a `QMessageBox` with the exception type/message.
  - Exits with code `1`.

---

## 4) UI layer (`src/ui/*`)

### 4.1 `src/ui/main_window.py`

This is the central orchestrator for UI + background workers.

#### Main attributes
- `self.data_manager`: handles TLE file management and telemetry persistence.
- `self.api_key_manager` / `self.cred_manager`: manages API keys and credentials.
- `self.hw_manager`: handles serial/hardware connection.
- `self.bg_manager`: background tasks coordination (initialized but its internal details are in `src/managers/background_manager.py`).
- `self.engine`: `OrbitEngine` instance for Sun/Moon + TLE parsing.

#### UI construction (left panel / map / telemetry)
- **Target Acquisition**
  - Satellite search input with auto-completer (works off loaded TLEs).
  - Sync button to download/update global TLE catalogs.

- **Ground Station Config**
  - City text input + “Establish” button.
  - Altitude input.
  - Poll rate selector.

- **Hardware Tracking Interface**
  - Board type selection.
  - Port list, baud configuration.
  - Scan + Test/Disengage hardware buttons.

- **Center**
  - `QWebEngineView` showing `assets/map/index.html`.
  - `QWebChannel` wiring to `src/ui/bridge.py` for Python<->JS events.
  - Log panel beneath the map.

- **Right Telemetry**
  - `TelemetryPanel` (UI widget updated by tracking worker signals).

#### Core flows
1) **Load TLEs**
   - `load_tles_from_disk()`:
     - Clears current catalog.
     - Iterates downloaded TLE files via `DataManager`.
     - Parses each file via `OrbitEngine.parse_tle_file()`.
     - Merges results using `_merge_satellite_data()`.
     - Updates the completer with satellite names.
     - Shows `StartScreen` on first load.

2) **Start/Stop tracking**
   - `start_tracking()`:
     - Determines selected satellite object.
     - Reads observer config (lat/lng/alt/poll interval).
     - Starts `PredictionWorker` thread for future orbit and pass geometry.
     - Starts `TrackingWorker` thread for real-time telemetry from N2YO.
     - Updates button enabled states.

   - `stop_tracking()`:
     - Signals tracking stop.
     - Re-enables Start button.

3) **Receive telemetry + update map**
   - `on_telemetry(data)`:
     - Updates `TelemetryPanel`.
     - Emits map bridge signals:
       - satellite position
       - orbit trail steps
       - visible range circle
     - If hardware is connected, sends azimuth/elevation to hardware.

4) **Receive predictions**
   - `on_prediction_complete(data)`:
     - Draws orbit path and highlights the visible pass.
     - Stores pass details for countdown UI updates.

5) **Countdown to next pass**
   - `update_pass_countdown()`:
     - Uses stored `pass_details`.
     - Computes AOS time and countdown.
     - Emits updated pass info to JS.

6) **Geocoding city name**
   - `geocode_city()` runs a background thread:
     - calls `GeocodeClient.get_coordinates(city)`
     - invokes `_update_station` via queued Qt method calls.

7) **TLE catalog synchronization**
   - `show_source_dialog()`:
     - Opens source selection.
     - Gatekeeps Space-Track login if needed.
     - Spawns `_run_sync()` in a thread.

   - `_run_sync(sources)`:
     - For each chosen source:
       - Downloads TLE file(s) via HTTP or Space-Track client.
       - Saves to disk.
       - Parses and merges.
     - Emits results to `sig_update_sat_list`, which triggers `_finalize_sync()`.

#### Satellite merge logic (`_merge_satellite_data`)
- Ensures name quality wins when multiple providers yield the same NORAD.
- Rule summary:
  1) Specific name beats generic (`UNKNOWN` / `OBJECT ...`).
  2) Generic cannot overwrite specific.
  3) If both are equal quality, newer `epoch` wins.

---

### 4.2 `src/ui/styles.py`

Defines the global Qt stylesheet string:
- `CYBER_DARK_THEME`
- Applied once in `main.py` via `app.setStyleSheet(CYBER_DARK_THEME)`.

---

### 4.3 `src/ui/bridge.py`

Defines `MapBridge(QObject)` used for WebChannel communication.

#### Signals (Python -> JS)
- `update_satellite_position(float, float, float, float, float, float)`
- `update_observer_position(float, float)`
- `update_celestial_position(str, float, float)`
- `set_map_view(float, float, int)`
- `clear_satellite_data()`
- `draw_orbit_path(list)`
- `highlight_visible_pass(list)`
- `update_satellite_range(float, float, float)`
- `add_track_step(float, float)`
- `clear_track_steps()`
- `update_pass_info(str)`

#### Slots (JS -> Python)
- `on_js_ready()` — sets readiness flag.
- `js_log(str)` — forwards JS console messages into Python logger.
- `map_clicked(lat, lng)` — logs map click.

---

## 5) Core computation (`src/core/*`)

### 5.1 `src/core/engine.py` — `OrbitEngine`

#### Responsibilities
- Loads Skyfield timescale.
- Loads the DE421 ephemeris kernel (`de421.bsp`) for Sun/Moon positions.
- Parses TLE catalogs into a normalized internal dict keyed by NORAD ID.

#### Key methods
- `parse_tle_file(filepath)`:
  - Accepts 2-line and 3-line variants.
  - Reads blocks starting with TLE Line 1 (`1 ...`).
  - Extracts NORAD id and epoch.
  - Produces a dict entry with:
    - `name`, `norad_id`, `line1`, `line2`, `epoch`.

- `get_sun_position(dt)` and `get_moon_position(dt)`:
  - Computes subpoint lat/lng of Sun/Moon as observed from Earth using DE421.

---

### 5.2 `src/core/prediction_worker.py` — `PredictionWorker`

#### Responsibilities
Background Qt thread computing:
- An orbit ground track for the next ~95 minutes.
- The next pass rise/max/set within a ~2-day window.

#### Output format (`dict` emitted)
- `orbit_path`: list of `[lat, lon]` points.
- `pass_details`: dict with:
  - `rise_time_utc`, `set_time_utc`, `max_el`.
- `pass_path`: list of `[lat, lon]` points representing the pass track.

---

### 5.3 `src/core/tracking_worker.py` — `TrackingWorker`

#### Responsibilities
Background Qt thread polling N2YO for real-time telemetry.

#### Key behaviors
- Uses config (`sat_id`, `lat`, `lng`, `alt`, `interval`).
- Calls `N2YOClient.get_satellite_position(...)`.
- Computes additional derived values:
  - `speed_kms` and `speed_mis_s` using previous sample.
  - local sidereal time (`lst`).

#### Emitted telemetry dict includes (examples)
- `satlatitude`, `satlongitude`, `sataltitude`
- `azimuth`, `elevation`
- `ra`, `dec`
- `timestamp`, `speed_kms`, `speed_mis_s`, `lst`, `eclipsed`

---

## 6) API clients (`src/api/*`)

### 6.1 `src/api/base_client.py`

`BaseAPIClient` provides:
- A reusable `requests.Session()` with retry logic.
- Standard browser-like headers.
- `_get(...)` helper that returns JSON or `None` on failure.

### 6.2 `src/api/geocode_client.py` — `GeocodeClient`

Uses OpenCage Geocoding API:
- `get_coordinates(city)` returns `(lat, lng)` or `(None, None)`.

### 6.3 `src/api/n2yo_client.py` — `N2YOClient`

Two major responsibilities:
- `get_satellite_position(norad_id, obs_lat, obs_lng, obs_alt, seconds=1)`
- `get_frequency_data(norad_id)`

The frequency data:
- is cached under `satnogs_cache/{norad_id}.json`.
- uses a 48-hour cache age.

### 6.4 `src/api/spacetrack_client.py` — `SpaceTrackClient`

- `authenticate(username, password)` uses `spacetrack` library with an `httpx_client`.
- `get_gp_data(query_class, filters)`:
  - attempts to fetch allowed predicates first.
  - filters requested keys to allowed ones.
  - requests TLE data (`format='tle'`).

---

## 7) Managers (`src/managers/*`)

This folder contains internal application service modules:
- `auth_manager.py` — API keys and credential storage.
- `data_manager.py` — TLE file management and telemetry persistence.
- `hardware_manager.py` — serial/board communication.
- `background_manager.py` — background task orchestration.

(Their code is part of the `src/` tree; the public interfaces are used throughout `MainWindow`, and the details are encapsulated within the manager modules.)

---

## 8) Firmware (`firmware/arduino_sensor.ino`)

Arduino sketch used for external tracking sensor/interface.

It is not built by Python directly; it is shipped as source so you can compile it for your hardware.

---

## 9) Assets and media

- `assets/map/index.html` (and related JS/CSS in `assets/map/`) implements the Leaflet web map.
- `Photo/` and `video/` are bundled media for UI/background.
- `tle_data/` contains TLE catalogs by provider/type.

### Licensing note for assets
This repository’s `LICENSE` applies to the project’s original source code. For any bundled third-party assets (e.g., web libraries, media from external sources), their licenses should be preserved alongside the assets or documented in a follow-up licensing manifest.

---

## 10) Licensing / REUSE posture

### 10.1 Repository original code
- `LICENSE` defines the license for this repository’s original source.
- Current default for original code: **MIT**.

### 10.2 Third-party dependencies
Your installed dependencies (PyQt5, Skyfield, spacetrack, requests, etc.) are governed by their own licenses.

### 10.3 Third-party assets
Any externally sourced assets may have separate licenses. When you add or replace assets, keep their license terms in mind.

### 10.4 Improving REUSE automation (recommended)
To be fully REUSE/SPDX-friendly, each source file should include an SPDX header such as:
- `SPDX-License-Identifier: MIT`

At the moment, this repo contains REUSE scaffolding (`REUSE.toml` etc.) and a root `LICENSE`, but SPDX headers are not yet applied per-file.

---

## 11) Files created by this licensing request
- `LICENSE` (MIT)
- `REUSE.toml`
- `REUSE-toolbox.txt`
- This file: `REUSE.md`


