# -*- coding: utf-8 -*-
import os
import json
import time
import requests
import math
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
                             QSplitter, QLineEdit, QPushButton,
                             QGroupBox, QComboBox, QLabel, QApplication, QMessageBox,
                             QSizePolicy, QCompleter)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QUrl, QMetaObject, Q_ARG, pyqtSignal, QStringListModel
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from PyQt5.QtWebChannel import QWebChannel
import json

from src.utils.logger import logger
from src.utils.config import DEFAULT_TLE_SOURCES

from src.ui.bridge import MapBridge
from src.ui.widgets.telemetry_panel import TelemetryPanel
from src.ui.widgets.log_panel import LogPanel
from src.ui.dialogs.api_dialog import ApiKeysDialog
from src.ui.dialogs.source_dialog import SourceSelectionDialog
from src.ui.dialogs.login_dialog import LoginDialog
from src.ui.dialogs.start_screen import StartScreen

from src.api.n2yo_client import N2YOClient
from src.api.geocode_client import GeocodeClient
from src.api.spacetrack_client import SpaceTrackClient

from src.managers.data_manager import DataManager
from src.managers.auth_manager import ApiKeyManager, CredentialManager
from src.managers.hardware_manager import HardwareManager
from src.managers.background_manager import BackgroundManager
from src.core.engine import OrbitEngine
from src.core.tracking_worker import TrackingWorker
from src.core.prediction_worker import PredictionWorker

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MainWindow(QMainWindow):
    sig_update_sat_list = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SatTrack Terminal v5.0")
        self.resize(1500, 950)

        # 1. Initialize Attributes (FIXED: Prevent AttributeError)
        self.active_tracking_worker = None
        self.active_prediction_worker = None
        self.satellites: Dict[str, Dict] = {}
        self.selected_sat_name: Optional[str] = None
        self.map_js_ready = False
        self.last_pass_data = {}
        self.lat_station = 0.0
        self.lng_station = 0.0

        # 2. Service Orchestration
        self.data_manager = DataManager()
        self.api_key_manager = ApiKeyManager()
        self.cred_manager = CredentialManager()
        self.hw_manager = HardwareManager()
        self.bg_manager = BackgroundManager()
        self.engine = OrbitEngine()

        # 3. UI Construction
        self.setup_ui()
        self.setup_clients()

        # 4. Signals & Timers
        self.sig_update_sat_list.connect(self._finalize_sync)

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self.sync_realtime_ui)
        self.ui_timer.start(1000)

        self.celestial_timer = QTimer(self)
        self.celestial_timer.timeout.connect(self.update_celestial_positions)
        self.celestial_timer.start(300000)

        # 5. Background Init
        QTimer.singleShot(1000, self.load_tles_from_disk)

    def setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        # --- LEFT COMMAND PANEL ---
        self.left_panel = QWidget()
        self.left_panel.setFixedWidth(400)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setSpacing(0)
        left_layout.setContentsMargins(1, 1, 1, 1)

        # 2. Target Acquisition (Search with auto-completer - list moved to start screen)
        self.sat_group = QGroupBox("Target Acquisition")
        sat_vbox = QVBoxLayout(self.sat_group)

        # Parity: Dynamic count display
        self.sat_count_label = QLabel("Active database: Synchronizing...")
        self.sat_count_label.setStyleSheet("color: #64B5F6; font-weight: bold;")

        self.sat_search = QLineEdit()
        self.sat_search.setPlaceholderText("Type satellite name or NORAD ID...")

        # Auto-completer for quick satellite selection without the list widget
        self.sat_completer = QCompleter(self)
        self.sat_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.sat_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.sat_completer.activated.connect(self._on_completer_activated)
        self.sat_search.setCompleter(self.sat_completer)
        self.sat_search.returnPressed.connect(self._on_search_return_pressed)

        self.sync_btn = QPushButton("Sync Global TLE Catalogs")
        self.sync_btn.clicked.connect(self.show_source_dialog)

        sat_vbox.addWidget(self.sat_count_label)
        sat_vbox.addWidget(self.sat_search)
        sat_vbox.addWidget(self.sync_btn)
        self.sat_group.setMaximumHeight(140)
        left_layout.addWidget(self.sat_group)

        # 3. Ground Station (Observer)
        self.obs_group = QGroupBox("Ground Station Config")
        obs_grid = QGridLayout(self.obs_group)
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("Damascus, London, NYC...")
        self.city_btn = QPushButton("Establish")
        self.city_btn.clicked.connect(self.geocode_city)
        self.alt_input = QLineEdit("0")
        self.poll_rate = QComboBox()
        self.poll_rate.addItems(["1", "2", "5", "10", "30", "60"])
        self.poll_rate.setCurrentText("2")

        obs_grid.addWidget(QLabel("City Search:"), 0, 0)
        obs_grid.addWidget(self.city_input, 0, 1)
        obs_grid.addWidget(self.city_btn, 0, 2)
        obs_grid.addWidget(QLabel("Altitude (m):"), 1, 0)
        obs_grid.addWidget(self.alt_input, 1, 1)
        obs_grid.addWidget(QLabel("Poll Rate:"), 2, 0)
        obs_grid.addWidget(self.poll_rate, 2, 1)
        self.obs_group.setMaximumHeight(160)
        left_layout.addWidget(self.obs_group)

        # 4. Hardware Master Console
        self.hw_group = QGroupBox("Hardware Tracking Interface")
        hw_grid = QGridLayout(self.hw_group)
        self.board_type = QComboBox()
        self.board_type.addItems(["Select Board..."] + sorted(self.hw_manager.BOARDS.keys()))
        self.port_list = QComboBox()
        self.btn_refresh_hw = QPushButton("Scan")
        self.btn_refresh_hw.clicked.connect(self.refresh_ports)
        self.baud_input = QLineEdit("115200")
        self.btn_test_hw = QPushButton("Test Hardware")
        self.btn_test_hw.clicked.connect(self.toggle_hardware)

        hw_grid.addWidget(QLabel("Board:"), 0, 0)
        hw_grid.addWidget(self.board_type, 0, 1, 1, 2)
        hw_grid.addWidget(QLabel("Port:"), 1, 0)
        hw_grid.addWidget(self.port_list, 1, 1)
        hw_grid.addWidget(self.btn_refresh_hw, 1, 2)
        hw_grid.addWidget(QLabel("Baud:"), 2, 0)
        hw_grid.addWidget(self.baud_input, 2, 1)
        hw_grid.addWidget(self.btn_test_hw, 2, 2)
        self.hw_group.setMaximumHeight(160)
        left_layout.addWidget(self.hw_group)

        # 5. Engagement Buttons
        self.start_btn = QPushButton("Start Traking")
        self.start_btn.setStyleSheet(
            "background-color: #1B5E20; color: white; height: 50px; font-weight: bold;")
        self.start_btn.clicked.connect(self.start_tracking)
        self.stop_btn = QPushButton("Stop Traking")
        self.stop_btn.setStyleSheet(
            "background-color: #B71C1C; color: white; height: 50px; font-weight: bold;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_tracking)
        left_layout.addWidget(self.start_btn)
        left_layout.addWidget(self.stop_btn)

        # --- CENTER VISUALS ---
        self.center_splitter = QSplitter(Qt.Vertical)
        self.map_view = QWebEngineView()
        map_path = os.path.join(PROJECT_ROOT, "assets", "map", "index.html")
        self.map_view.setUrl(QUrl.fromLocalFile(map_path))

        self.map_bridge = MapBridge(self)
        self.channel = QWebChannel()
        self.channel.registerObject("pyBridge", self.map_bridge)
        self.map_view.page().setWebChannel(self.channel)
        self.map_bridge.js_ready_signal.connect(self.on_map_ready)

        self.log_panel = LogPanel()
        self.center_splitter.addWidget(self.map_view)
        self.center_splitter.addWidget(self.log_panel)
        self.center_splitter.setStretchFactor(0, 4)

        # --- RIGHT TELEMETRY ---
        self.telemetry_panel = TelemetryPanel()
        self.telemetry_panel.setFixedWidth(330)

        self.main_layout.addWidget(self.left_panel)
        self.main_layout.addWidget(self.center_splitter, 1)
        self.main_layout.addWidget(self.telemetry_panel)

        self.refresh_ports()

    def setup_clients(self):
        n2yo_key = self.api_key_manager.get_key("N2YO")
        geo_key = self.api_key_manager.get_key("OpenCage")
        if not n2yo_key or not geo_key:
            dialog = ApiKeysDialog(self)
            keys = dialog.get_keys()
            if keys:
                self.api_key_manager.store_key("N2YO", keys['n2yo'])
                self.api_key_manager.store_key("OpenCage", keys['opencage'])
                n2yo_key, geo_key = keys['n2yo'], keys['opencage']
        self.n2yo_client = N2YOClient(n2yo_key)
        self.geo_client = GeocodeClient(geo_key)
        self.st_client = SpaceTrackClient()

    def sync_realtime_ui(self):
        lt, ut = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"), datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        self.telemetry_panel.update_time(lt, ut)
        if self.last_pass_data:
            self.update_pass_countdown()

    def _merge_satellite_data(self, target_dict: Dict[str, Dict], source_dict: Dict[str, Dict]) -> None:
        """
        Name-prioritized merge of satellite data into target_dict.
        Logic ported from PySatTrack .py:
        1. Specific name beats generic name (OBJECT/UNKNOWN)
        2. If name quality is equal, newer epoch wins
        """
        for norad_id, new_sat in source_dict.items():
            if norad_id not in target_dict:
                target_dict[norad_id] = new_sat
                continue

            existing = target_dict[norad_id]
            existing_name = existing.get('name', 'UNKNOWN')
            new_name = new_sat.get('name', 'UNKNOWN')

            is_existing_specific = not (existing_name.startswith(
                'UNKNOWN') or existing_name.startswith('OBJECT '))
            is_new_specific = not (new_name.startswith(
                'UNKNOWN') or new_name.startswith('OBJECT '))

            # Rule 1: Specific name always beats generic name
            if is_new_specific and not is_existing_specific:
                target_dict[norad_id] = new_sat
                continue

            # Rule 2: Generic name cannot overwrite specific name
            if not is_new_specific and is_existing_specific:
                continue

            # Rule 3: Same quality -> use epoch as tiebreaker
            existing_epoch = existing.get('epoch')
            new_epoch = new_sat.get('epoch')
            if new_epoch and existing_epoch and new_epoch > existing_epoch:
                target_dict[norad_id] = new_sat

    def load_tles_from_disk(self):
        self.satellites.clear()
        for f in self.data_manager.list_downloaded_tles():
            path = self.data_manager.get_tle_path(f)
            parsed = self.engine.parse_tle_file(path)
            self._merge_satellite_data(self.satellites, parsed)

        count = len(self.satellites)
        self.sat_count_label.setText(f"Active database: {count:,} Objects")
        self.sat_search.setEnabled(True)
        self.sat_search.setPlaceholderText("Type satellite name or NORAD ID...")

        # Update completer model with all satellite names
        sat_names = sorted([s['name'] for s in self.satellites.values()])
        self.sat_completer.setModel(QStringListModel(sat_names, self))

        # Show start screen on first load if no satellite selected
        if not self.selected_sat_name and self.satellites:
            QTimer.singleShot(500, self.show_start_screen)

    def _on_completer_activated(self, text):
        """Handle selection from the auto-completer dropdown."""
        self.on_sat_selected(text)

    def _on_search_return_pressed(self):
        """Handle Enter key press in the search field."""
        text = self.sat_search.text().strip()
        if not text:
            return
        # Try exact match first
        sat_info = next((v for v in self.satellites.values() if v['name'] == text), None)
        if sat_info:
            self.on_sat_selected(text)
        else:
            # Try case-insensitive match
            sat_info = next((v for v in self.satellites.values() if v['name'].lower() == text.lower()), None)
            if sat_info:
                self.on_sat_selected(sat_info['name'])
            else:
                QMessageBox.warning(self, "Not Found", f"Satellite '{text}' not found in database.")

    def show_start_screen(self):
        """Show the start screen dialog for satellite selection."""
        if not self.satellites:
            QMessageBox.warning(self, "No Data", "Please sync TLE catalogs first.")
            return

        dialog = StartScreen(self.satellites, parent=self)
        result = dialog.get_result()

        if result:
            sat_info = result['satellite']
            self.selected_sat_name = sat_info['name']
            self.sat_search.setText(self.selected_sat_name)
            self.telemetry_panel.update_telemetry({
                'sat_name': sat_info['name'],
                'norad_id': sat_info['norad_id']
            })

            # Update ground station config from start screen
            if result['city']:
                self.city_input.setText(result['city'])
                self.geocode_city()

            if result['altitude'] is not None:
                self.alt_input.setText(str(result['altitude']))

            logger.info(f"Main: Launched with {self.selected_sat_name}.")

    def on_sat_selected(self, sat_name):
        """Handle satellite selection (called from start screen or other sources)."""
        self.selected_sat_name = sat_name
        self.sat_search.setText(sat_name)
        sat_info = next(
            (v for v in self.satellites.values() if v['name'] == sat_name), None)
        if sat_info:
            self.telemetry_panel.update_telemetry({
                'sat_name': sat_info['name'],
                'norad_id': sat_info['norad_id']
            })
        logger.info(f"Main: Selected {sat_name}.")

    def geocode_city(self):
        city = self.city_input.text().strip()
        if not city:
            return

        def task():
            lat, lng = self.geo_client.get_coordinates(city)
            QMetaObject.invokeMethod(self, "_update_station", Qt.QueuedConnection,
                                     Q_ARG(float, lat if lat else 0.0),
                                     Q_ARG(float, lng if lng else 0.0),
                                     Q_ARG(str, city))
        threading.Thread(target=task, daemon=True).start()

    @pyqtSlot(float, float, str)
    def _update_station(self, lat, lng, city):
        if lat != 0.0:
            self.lat_station, self.lng_station = lat, lng
            tz = datetime.now().astimezone().tzname() or "UTC"
            self.telemetry_panel.update_observer(
                lat, lng, float(self.alt_input.text()), tz)
            if self.map_js_ready:
                self.map_bridge.update_observer_position.emit(lat, lng)
                self.map_bridge.set_map_view.emit(lat, lng, 4)
                self.update_celestial_positions()
            logger.info(f"Station established at {city}.")
        else:
            self.log_panel.append_error(f"Geocode Error: '{city}' not found.")

    def show_source_dialog(self):
        last = self.load_source_settings()
        dialog = SourceSelectionDialog(DEFAULT_TLE_SOURCES, last, self)
        selected = dialog.get_selected_sources()
        if selected:
            # Login Gatekeeper on Main Thread (Thread Safety)
            if any(DEFAULT_TLE_SOURCES[s].get('auth_required') == 'space-track' for s in selected):
                if not self.st_client._client:
                    login = LoginDialog(
                        "Space-Track.org", "https://www.space-track.org/auth/createAccount", parent=self)
                    creds = login.get_credentials()
                    if creds:
                        if not self.st_client.authenticate(creds['username'], creds['password']):
                            return self.log_panel.append_error("Space-Track login failed.")
                    else:
                        return

            self.save_source_settings(selected)
            self.sync_btn.setEnabled(False)
            threading.Thread(target=self._run_sync,
                             args=(selected,), daemon=True).start()

    def _run_sync(self, sources):
        new_data = {}
        for key in sources:
            info = DEFAULT_TLE_SOURCES[key]
            save_path = self.data_manager.get_tle_path(info['filename'])
            if info.get('auth_required') == 'space-track':
                lines = self.st_client.get_gp_data(
                    info['query_class'], info.get('query_filters', {}))
                if lines:
                    with open(save_path, 'w') as f:
                        for line in lines:
                            f.write(line)
                    self._merge_satellite_data(
                        new_data, self.engine.parse_tle_file(save_path))
            else:
                urls = info.get('url', [])
                if isinstance(urls, str):
                    urls = [urls]
                for url in urls:
                    try:
                        r = requests.get(url, timeout=20)
                        if r.status_code == 200:
                            with open(save_path, 'wb') as f:
                                f.write(r.content)
                            self._merge_satellite_data(
                                new_data, self.engine.parse_tle_file(save_path))
                            break
                    except:
                        continue
        self.sig_update_sat_list.emit(new_data)

    @pyqtSlot(dict)
    def _finalize_sync(self, new_sats):
        self.satellites.update(new_sats)
        self.load_tles_from_disk()
        self.sync_btn.setEnabled(True)
        QMessageBox.information(
            self, "Sync Complete", f"Database updated with {len(new_sats):,} objects.")

    def manual_login_trigger(self):
        login = LoginDialog(
            "Space-Track.org", "https://www.space-track.org/auth/createAccount", parent=self)
        creds = login.get_credentials()
        if creds:
            self.st_client.authenticate(creds['username'], creds['password'])

    def show_diagnostics(self):
        from src.ui.dialogs.diagnostics_dialog import LoggingVerificationDialog
        LoggingVerificationDialog(self).exec_()

    def start_tracking(self):
        if not self.selected_sat_name:
            return
        sat = next((s for s in self.satellites.values()
                   if s['name'] == self.selected_sat_name), None)
        if not sat:
            return

        try:
            obs = {'lat': self.lat_station, 'lng': self.lng_station,
                   'alt': float(self.alt_input.text()), 'interval': int(self.poll_rate.currentText())}
        except:
            return

        if self.map_js_ready:
            self.map_bridge.clear_satellite_data.emit()
            self.update_celestial_positions()

        if self.active_prediction_worker:
            self.active_prediction_worker.terminate()
            self.active_prediction_worker.wait()

        self.active_prediction_worker = PredictionWorker(
            sat, obs['lat'], obs['lng'], obs['alt'])
        self.active_prediction_worker.prediction_ready.connect(
            self.on_prediction_complete)
        self.active_prediction_worker.start()

        if self.active_tracking_worker:
            self.active_tracking_worker.stop()
            self.active_tracking_worker.wait()

        config = {'sat_id': sat['norad_id'], 'sat_name': sat['name'], **obs}
        freqs = self.n2yo_client.get_frequency_data(int(sat['norad_id']))
        if freqs:
            config.update(freqs)

        self.active_tracking_worker = TrackingWorker(
            self.n2yo_client, self.data_manager, config)
        self.active_tracking_worker.data_ready.connect(self.on_telemetry)
        self.active_tracking_worker.error_occurred.connect(
            self.log_panel.append_error)
        self.active_tracking_worker.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_tracking(self):
        if self.active_tracking_worker:
            self.active_tracking_worker.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def on_telemetry(self, data):
        self.telemetry_panel.update_telemetry(data)
        if self.map_js_ready:
            self.map_bridge.update_satellite_position.emit(
                data['satlatitude'], data['satlongitude'], data['sataltitude'],
                data['speed_kms'], data['azimuth'], data['elevation']
            )
            self.map_bridge.add_track_step.emit(
                data['satlatitude'], data['satlongitude'])
            radius = math.sqrt(data['sataltitude'] *
                               (2 * 6371.0 + data['sataltitude'])) * 1.15
            self.map_bridge.update_satellite_range.emit(
                data['satlatitude'], data['satlongitude'], radius)
        if self.hw_manager.connection:
            self.hw_manager.send_telemetry(data['azimuth'], data['elevation'])

    @pyqtSlot(dict)
    def on_prediction_complete(self, data):
        if not self.map_js_ready:
            return

        def segment(pts):
            if not pts:
                return []
            segs, cur = [], [pts[0]]
            for i in range(1, len(pts)):
                if abs(pts[i][1] - pts[i-1][1]) > 180:
                    segs.append(cur)
                    cur = []
                cur.append(pts[i])
            segs.append(cur)
            return segs
        for s in segment(data.get('orbit_path', [])):
            self.map_bridge.draw_orbit_path.emit(s)
        for s in segment(data.get('pass_path', [])):
            self.map_bridge.highlight_visible_pass.emit(s)
        if 'pass_details' in data:
            self.last_pass_data = data['pass_details']

    def update_pass_countdown(self):
        if not self.last_pass_data or not self.map_js_ready:
            return
        now = datetime.now(timezone.utc)
        rise = self.last_pass_data['rise_time_utc'].replace(tzinfo=timezone.utc)
        aset = self.last_pass_data['set_time_utc'].replace(tzinfo=timezone.utc)
        info = {'rise_time': rise.strftime("%H:%M:%S"), 'max_el': self.last_pass_data['max_el'],
                'set_time': aset.strftime("%H:%M:%S"), 'countdown': ""}
        if now > rise:
            info['countdown'] = "STATION IN VIEW"
        else:
            d = rise - now
            h, r = divmod(d.total_seconds(), 3600)
            m, s = divmod(r, 60)
            info['countdown'] = f"AOS AT: {int(h):02}:{int(m):02}:{int(s):02}"
        self.map_bridge.update_pass_info.emit(json.dumps(info))

    def on_map_ready(self):
        self.map_js_ready = True
        self.map_bridge.set_map_view.emit(0, 0, 2)
        self.update_celestial_positions()

    def update_celestial_positions(self):
        if not self.map_js_ready:
            return
        now = datetime.now(timezone.utc)
        s_lat, s_lng = self.engine.get_sun_position(now)
        m_lat, m_lng = self.engine.get_moon_position(now)
        self.map_bridge.update_celestial_position.emit('sun', s_lat, s_lng)
        self.map_bridge.update_celestial_position.emit('moon', m_lat, m_lng)

    def refresh_ports(self):
        self.port_list.clear()
        self.port_list.addItems(self.hw_manager.get_available_ports())

    def toggle_hardware(self):
        if self.hw_manager.connection:
            self.hw_manager.disconnect()
            self.btn_test_hw.setText("Test Hardware")
        else:
            port, board = self.port_list.currentText(), self.board_type.currentText()
            success, msg = self.hw_manager.connect(
                port, board, baud=int(self.baud_input.text()))
            if success:
                self.btn_test_hw.setText("Disengage")
            else:
                self.log_panel.append_error(f"HW Error: {msg}")

    def update_times(self):
        lt, ut = datetime.now().strftime(
            "%H:%M:%S"), datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        self.telemetry_panel.update_time(lt, ut)

    def load_source_settings(self):
        p = os.path.join(PROJECT_ROOT, "tle_source_settings.json")
        return json.load(open(p)) if os.path.exists(p) else ["active", "visual"]

    def save_source_settings(self, settings):
        json.dump(settings, open(os.path.join(
            PROJECT_ROOT, "tle_source_settings.json"), 'w'))

    def closeEvent(self, event):
        self.stop_tracking()
        self.hw_manager.disconnect()
        event.accept()

