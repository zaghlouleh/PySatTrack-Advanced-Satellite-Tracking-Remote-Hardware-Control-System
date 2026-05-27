# REUSE Compliance & Code Explanation

This repository uses the **REUSE Specification** (https://reuse.software/) to make licensing clear and machine-checkable.

## 1) License Files

- **`LICENSE`**: MIT license text for this repository.
- **`REUSE.toml`**: REUSE configuration (defaults to MIT for annotated files).
- **`REUSE-toolbox.txt`**: A lightweight checklist of file patterns and intended license ownership.
- **`REUSE.md`**: Explanation of the repository’s major components (and how to interpret license coverage).

> Note: Third-party assets/binaries (e.g., `de421.bsp`, `video/*.mp4`, images in `assets/`) may be governed by their own licenses. Add/adjust `REUSE-toolbox.txt` (and eventually `REUSE.toml` path annotations) if you discover different terms.

## 2) Project Architecture (High-level)

This project is a **desktop “Satellite Tracker” ground-station** application built with **PyQt5 + PyQtWebEngine**.

At a high level:

1. **TLE catalog sync**: download and cache Two-Line Element (TLE) data from multiple sources.
2. **Orbit prediction**: compute the satellite future orbit path and the next visible pass.
3. **Tracking loop**: poll external services (SatTrack via N2YO/other providers) and/or local hardware to drive the antenna/switch.
4. **Visualization**: render a map (HTML/JS) and show telemetry plots (pyqtgraph).
5. **Hardware bridge + diagnostics**: optional TCP bridge to external controllers + a diagnostics dashboard.

## 3) Code Modules and Their Responsibilities

### 3.1 `main.py`

- Entry point for the desktop application.
- Loads environment variables (`python-dotenv`).
- Applies Qt high-DPI settings.
- Installs a global exception hook that logs unhandled exceptions and shows a `QMessageBox`.
- Creates and shows the `MainWindow`.

Key behavior:
- Sets `QTWEBENGINE_CHROMIUM_FLAGS` to disable GPU for stability.
- Uses the dark theme defined in `src/ui/styles.py`.

### 3.2 `src/__init__.py`

- Marks the `src` directory as a package.

### 3.3 API clients (`src/api/*`)

#### `src/api/base_client.py`

- `BaseAPIClient` provides a shared `requests.Session` with:
  - retry logic (`urllib3.util.retry.Retry`)
  - common headers (browser-like `User-Agent`)
- `_get()` performs JSON GET requests with consistent logging and safe failure behavior.

#### `src/api/n2yo_client.py`

- `N2YOClient` fetches real-time satellite positions/frequencies.
- Includes local caching for SatNOGS transmitter frequency queries.
- Uses `BaseAPIClient.session` for request retries/headers.

#### `src/api/geocode_client.py`

- `GeocodeClient` resolves user-entered cities into `(lat, lng)`.

#### `src/api/spacetrack_client.py`

- `SpaceTrackClient` handles Space-Track login and authenticated TLE query execution.
- Provides `authenticate()` and `get_gp_data()`.
- Performs query-filter validation logic before requesting results.

### 3.4 Core orbit math (`src/core/*`)

#### `src/core/engine.py`

- `OrbitEngine` is the mathematical “heart” of the system.
- Initializes Skyfield:
  - `self.ts = load.timescale()`
  - attempts to load `de421.bsp` (ephemeris data)
- `parse_tle_file(filepath)`:
  - reads TLE files line-by-line
  - supports 2-line TLE pairs (`1 ...` then `2 ...`)
  - supports optional 3-line format by inferring the name from the preceding line
  - parses NORAD ID and epoch, returning a dict keyed by NORAD ID string
- `get_sun_position(dt)` and `get_moon_position(dt)`:
  - computes subpoint lat/lon via Skyfield.

#### `src/core/prediction_worker.py`

- `PredictionWorker` is a `QThread`.
- `run()`:
  1. Builds a Skyfield `EarthSatellite` from `line1/line2`.
  2. Computes ground track points for the next ~95 minutes.
  3. Predicts the next pass within a 2-day window using `satellite.find_events()`.
  4. Emits a dict containing:
     - `orbit_path` (list of `[lat, lon]`)
     - `pass_details` (rise/max/set times + max elevation)
     - `pass_path` (ground track during the pass)

### 3.5 Workers (`src/core/tracking_worker.py`)

- Not included in the snippets above, but this module typically:
  - polls satellite position / link metrics
  - computes and/or forwards telemetry
  - emits `data_ready` and `error_occurred` signals

### 3.6 Managers (`src/managers/*`)

#### `src/managers/data_manager.py`

- `DataManager` owns local persistence:
  - `satellite_data/` directory for telemetry JSON
  - `tle_data/` directory for cached TLE text files
- Provides:
  - `_get_telemetry_path(satellite_name)` sanitization
  - `save_satellite_telemetry()` (thread-safe via `Lock`)
  - `load_satellite_telemetry()`
  - `get_tle_path(filename)`
  - `list_downloaded_tles()`

#### `src/managers/tle_sync_manager.py`

- `TleSyncManager` downloads and caches TLE sources.
- Uses:
  - `_is_cache_fresh()` based on `mtime` and `cache_days`
  - `_download_url()` with retries and streamed downloads
  - `_download_spacetrack_source()` for authenticated sources
- `download_sources(selected_sources)` returns saved file paths for synced sources.

#### `src/managers/auth_manager.py`

- `ApiKeyManager`: stores/retrieves API keys via system keyring.
- `CredentialManager`: stores/retrieves Space-Track username/password securely.

#### `src/managers/background_manager.py`

- Provides background setup for UI dialogs.
- Used by dialogs (e.g. `SourceSelectionDialog`) to render a video/visual background.

#### `src/managers/hardware_manager.py`

- Not shown in full above, but it is responsible for:
  - connecting to Arduino/ESP32 boards over serial
  - selecting RF coupler channels
  - sending antenna telemetry (az/el)
  - maintaining `connection_changed` signals and an `arduino_data_received` signal

#### `src/managers/hardware_bridge*.py`

- Provides TCP bridge server/client capabilities.
- Used by:
  - main UI for networked hardware control
  - diagnostics dashboard for remote telemetry

### 3.7 UI (`src/ui/*`)

#### `src/ui/main_window.py`

- The primary Qt window.
- Constructs:
  - left command panel: satellite search, ground station config, hardware interface config, and source selection.
  - center split view: map view (QWebEngineView) + log panel.
  - right telemetry panel.
- Integrates:
  - `OrbitEngine` for TLE parsing and sun/moon positions.
  - `PredictionWorker` and tracking worker threads.
  - `TleSyncManager` via `show_source_dialog()`.

Key workflows:

- **TLE sync**:
  - `show_source_dialog()` opens `SourceSelectionDialog`
  - optionally gates Space-Track login
  - sync runs in a background thread calling `_run_sync()`
  - results merged and emitted back to UI via signals

- **Start tracking**:
  - validates selected satellite and observer inputs
  - optionally queries bridge for GPS status
  - creates `PredictionWorker` and tracking worker(s)
  - forwards real-time telemetry to:
    - map bridge
    - telemetry panel
    - `HardwareManager` (local) and/or TCP bridge (remote)

#### `src/ui/dialogs/source_dialog.py`

- `SourceSelectionDialog` (QDialog) shows categorized checkboxes for TLE sources.
- `setup_ui()` groups sources by `group` field from `DEFAULT_TLE_SOURCES`.
- Supports “Select All” / “Deselect All”.
- `get_selected_sources()` returns a list of selected source keys after dialog is accepted.

#### `src/ui/hardware_diagnostics_window.py`

- A full-screen (desktop) diagnostics dashboard.
- Contains custom widgets:
  - `CircularGauge` for critical telemetry
  - `PlatformAttitudeWidget` for pitch/roll stabilization display
  - `LimitSwitchesWidget` for safety/limit states
  - `HealthIndicator` and `ResourceBar` UI elements
  - `RFSignalChainWidget` for showing the active RF switch channel
- Uses `HardwareDiagnosticsClient` to receive telemetry.
- Maintains deques and pyqtgraph curves for:
  - tracking errors over time
  - motor current requirements
  - RF spectrum

Important runtime behaviors:
- `_on_telemetry_update()`:
  - resets waveform history when the satellite changes
  - handles simulation vs direct hardware modes
  - updates both gauges and plots
- `closeEvent()` stops the client and background polling timers.

### 3.8 Map assets

- `assets/map/index.html` is rendered inside `QWebEngineView`.
- `src/ui/bridge.py` exposes a JS bridge (`QWebChannel`) so Python can update:
  - observer position
  - satellite position
  - predicted orbit and pass paths

### 3.9 Configuration (`src/utils/config.py`)

- Defines `DEFAULT_TLE_SOURCES`.
- Each TLE source includes metadata used by:
  - source dialog grouping
  - sync logic (URL/mirrors/auth/cache days)
  - Space-Track query parameters

### 3.10 Logging (`src/utils/logger.py`)

- Configures a global logger instance named `PySatTrack`.
- Uses a custom `ImmediateFlushFileHandler` to flush logs to disk after each write.

## 4) REUSE Coverage and What You Should Add Next

The files created for REUSE are present at repository root.

However, REUSE (strict) typically relies on **per-file SPDX headers** (or REUSE annotations per path). This repository currently does not automatically embed SPDX headers in every source file.

To make strict REUSE checks pass in the future, preferred options are:

1. Add SPDX headers to each source file (e.g. `# SPDX-License-Identifier: MIT`).
2. Or expand `REUSE.toml` with `[[annotations]]` rules that fully cover all relevant file types and confirm the checkers accept directory-level coverage (behavior depends on the REUSE tool version).

`REUSE-toolbox.txt` already documents what to review (assets, third-party binaries, TLE catalogs).

## 5) Third-Party Dependencies Notice

This project uses external Python dependencies listed in `requirements.txt`:
- PyQt5 / PyQtWebEngine
- skyfield
- requests
- spacetrack
- pyserial
- python-dotenv
- keyring
- psutil
- pyqtgraph

Their licenses are separate from this repository’s MIT license. This REUSE documentation focuses on licensing for this repository’s code.

## 6) Quick Map of Runtime Flow

- User selects TLE sources (`SourceSelectionDialog`).
- `TleSyncManager` downloads/cache files.
- `OrbitEngine.parse_tle_file()` loads TLEs.
- `PredictionWorker` computes orbit + pass.
- Tracking worker repeatedly updates telemetry.
- UI renders:
  - map updates through `MapBridge`
  - plots through pyqtgraph
  - hardware states through diagnostics and/or hardware managers

---

### End of REUSE.md

