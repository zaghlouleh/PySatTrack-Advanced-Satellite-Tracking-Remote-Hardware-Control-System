# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import math
import zipfile
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QTabWidget, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QMenu, QComboBox, QSplitter,
    QHBoxLayout, QListWidget, QGridLayout, QListWidgetItem, QDialog, QSizePolicy,
    QGroupBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QMetaObject, Q_ARG, QUrl, pyqtSignal
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtGui import QTextCursor, QColor, QTextCharFormat, QFont

# Internal Imports
from src.config.settings import (
    DEFAULT_TLE_SOURCES, TLE_DATA_DIR, OPENCAGE_API_KEY, 
    N2YO_API_KEY, SPACE_TRACK_USER, SPACE_TRACK_PASSWORD
)
from src.core.calculations import SKYFIELD_AVAILABLE, CelestialCalculator, EarthSatellite
from src.core.api_client import APIClient
from src.core.data_manager import DataManager
from src.hardware.board_manager import BoardManager
from src.ui.worker import WorkerThread
from src.ui.map_bridge import MapBridge
from src.utils.logger import logger, LOG_FILE, LoggingVerificationDialog

class SatelliteTracker(QWidget):
    log_message_signal = pyqtSignal(str)
    error_message_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        if not SKYFIELD_AVAILABLE:
            self.show_critical_error("Skyfield library not found. Application requires Skyfield.")
            QTimer.singleShot(100, QApplication.instance().quit)
            raise ImportError("Skyfield not found.")

        self.api = APIClient()
        self.data_manager = DataManager()
        self.board_manager = BoardManager()
        self.worker = None
        self.satellites = {}
        self.selected_satellite_name = None
        self.last_log_stat = None

        self.init_ui()
        self.init_map_bridge()
        self.init_map_view()

        # Timers
        self.log_update_timer = QTimer(self)
        self.log_update_timer.timeout.connect(self._check_log_file_update)
        self.log_update_timer.start(1500)

        self.mem_display_timer = QTimer(self)
        self.mem_display_timer.timeout.connect(self.update_memory_display)
        self.mem_display_timer.start(2000)

        # Signal Connections
        self.log_message_signal.connect(self._append_log_message)
        self.error_message_signal.connect(self._append_error_message)
        self.board_manager.connection_changed.connect(self._update_board_status_ui)

        # Initial Actions
        self._load_satellites_from_tle()
        QTimer.singleShot(2000, self.start_celestial_updates)

    def init_ui(self):
        self.setWindowTitle("Satellite Tracker (TLE Direct Mode)")
        self.setGeometry(100, 100, 1300, 850)
        main_layout = QHBoxLayout(self)

        # --- LEFT PANEL ---
        left_widget = QWidget()
        left_v_layout = QVBoxLayout(left_widget)
        left_widget.setMinimumWidth(350)
        left_widget.setMaximumWidth(500)

        top_controls_widget = QWidget()
        top_controls_layout = QVBoxLayout(top_controls_widget)
        top_controls_layout.setContentsMargins(0, 0, 0, 0)

        self.create_satellite_input_fields(top_controls_layout)
        
        self.control_tab_widget = QTabWidget()
        # Observer Tab
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        self.create_location_input_fields(settings_layout)
        self.create_update_settings_fields(settings_layout)
        settings_layout.addStretch(1)
        # Hardware Tab
        board_tab = QWidget()
        board_layout = QVBoxLayout(board_tab)
        self.create_board_config_fields(board_layout)
        board_layout.addStretch(1)

        self.control_tab_widget.addTab(settings_tab, "Observer")
        self.control_tab_widget.addTab(board_tab, "Hardware")
        top_controls_layout.addWidget(self.control_tab_widget)
        self.create_control_buttons(top_controls_layout)

        # Splitter for Logs
        log_tab_widget = self.create_tab_widget()
        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.setHandleWidth(6)
        left_splitter.setStyleSheet("QSplitter::handle { background-color: #4A4A4A; }")
        left_splitter.addWidget(top_controls_widget)
        left_splitter.addWidget(log_tab_widget)
        
        # Set initial size ratio (65% for controls, 35% for logs)
        left_splitter.setSizes([550, 250])
        left_v_layout.addWidget(left_splitter)

        # --- CENTER PANEL (Map) ---
        self.map_view = QWebEngineView()
        self.map_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.map_view.setMinimumWidth(500)

        # --- RIGHT PANEL ---
        right_widget = QWidget()
        right_panel = QVBoxLayout(right_widget)
        right_widget.setMinimumWidth(300)
        right_widget.setMaximumWidth(400)

        self.create_info_displays(right_panel)
        self.create_frequency_info_display(right_panel)
        right_panel.addStretch(1)

        main_layout.addWidget(left_widget, 3)
        main_layout.addWidget(self.map_view, 5)
        main_layout.addWidget(right_widget, 2)

    def create_satellite_input_fields(self, layout):
        sat_group = QGroupBox("Satellite Selection (from TLE Source)")
        sat_layout = QVBoxLayout(sat_group)
        filter_layout = QHBoxLayout()

        self.sat_name_input = QLineEdit()
        self.sat_name_input.setPlaceholderText("Loading TLE data...")
        self.sat_name_input.textChanged.connect(self.filter_satellites)
        self.sat_name_input.setEnabled(False)

        self.refresh_tle_btn = QPushButton("Refresh TLE")
        self.refresh_tle_btn.clicked.connect(self._load_satellites_from_tle)

        filter_layout.addWidget(self.sat_name_input, 1)
        filter_layout.addWidget(self.refresh_tle_btn)

        self.sat_list = QListWidget()
        self.sat_list.setVisible(False)
        self.sat_list.itemClicked.connect(self.select_satellite)
        self.sat_list.setMaximumHeight(150)

        self.sat_list_status_label = QLabel("Loading TLE data...")
        self.sat_list_status_label.setStyleSheet("font-style: italic; color: #aaaaaa;")

        sat_layout.addWidget(QLabel("Filter/Select Satellite:"))
        sat_layout.addLayout(filter_layout)
        sat_layout.addWidget(self.sat_list)
        sat_layout.addWidget(self.sat_list_status_label)
        layout.addWidget(sat_group)

    def create_location_input_fields(self, layout):
        loc_group = QGroupBox("Observer Location")
        loc_layout = QGridLayout(loc_group)
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("e.g., London, UK")
        self.alt_input = QLineEdit("0")
        self.fetch_coords_btn = QPushButton("Get Lat/Lon")
        self.fetch_coords_btn.clicked.connect(self._fetch_observer_coords)
        loc_layout.addWidget(QLabel("City/Location:"), 0, 0)
        loc_layout.addWidget(self.city_input, 0, 1)
        loc_layout.addWidget(self.fetch_coords_btn, 0, 2)
        loc_layout.addWidget(QLabel("Altitude (m):"), 1, 0)
        loc_layout.addWidget(self.alt_input, 1, 1, 1, 2)
        layout.addWidget(loc_group)

    def create_update_settings_fields(self, layout):
        interval_group = QGroupBox("Update Settings")
        interval_layout = QHBoxLayout(interval_group)
        self.interval_input = QLineEdit("10")
        interval_layout.addWidget(QLabel("N2YO Update Interval (s):"))
        interval_layout.addWidget(self.interval_input)
        layout.addWidget(interval_group)

    def create_board_config_fields(self, layout):
        board_group = QGroupBox("Hardware Board Configuration")
        board_layout = QGridLayout(board_group)
        self.board_type_combo = QComboBox()
        self.board_type_combo.addItems(["Select Board..."] + sorted(self.board_manager.boards.keys()))
        self.board_type_combo.currentTextChanged.connect(self._handle_board_type_change)
        
        self.model_combo = QComboBox()
        self.model_combo.setEnabled(False)
        
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        
        self.refresh_ports_btn = QPushButton("Scan Ports")
        self.refresh_ports_btn.clicked.connect(self._refresh_port_list)
        
        self.baud_rate_input = QLineEdit("9600")
        self.connection_status = QLabel()
        self.connection_status.setFixedSize(20, 20)
        self.connection_status.setStyleSheet("border-radius: 10px; background-color: gray;")
        
        self.board_status_label = QLabel("Disconnected")
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self.test_board_connection)
        
        board_layout.addWidget(QLabel("Board Type:"), 0, 0)
        board_layout.addWidget(self.board_type_combo, 0, 1, 1, 2)
        board_layout.addWidget(QLabel("Model:"), 1, 0)
        board_layout.addWidget(self.model_combo, 1, 1, 1, 2)
        board_layout.addWidget(QLabel("Port:"), 2, 0)
        board_layout.addWidget(self.port_combo, 2, 1)
        board_layout.addWidget(self.refresh_ports_btn, 2, 2)
        board_layout.addWidget(QLabel("Baud:"), 3, 0)
        board_layout.addWidget(self.baud_rate_input, 3, 1, 1, 2)
        board_layout.addWidget(QLabel("Status:"), 4, 0)
        board_layout.addWidget(self.connection_status, 4, 1, Qt.AlignLeft)
        board_layout.addWidget(self.board_status_label, 4, 1, 1, 2, Qt.AlignCenter)
        board_layout.addWidget(self.test_btn, 5, 0, 1, 3)
        layout.addWidget(board_group)

    def create_control_buttons(self, layout):
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Tracking")
        self.stop_btn = QPushButton("Stop Tracking")
        self.start_btn.clicked.connect(self.start_tracking)
        self.stop_btn.clicked.connect(self.stop_tracking)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)

    def create_tab_widget(self):
        self.tab_widget = QTabWidget()
        log_font = QFont("Consolas", 9)
        
        self.error_display = QTextEdit()
        self.error_display.setReadOnly(True)
        self.error_display.setFont(log_font)
        self.error_display.setStyleSheet("color: #FF6347;")
        
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(log_font)
        
        self.memory_tab = QWidget()
        mem_layout = QGridLayout(self.memory_tab)
        self.memory_labels = {k: QLabel("---") for k in ['rss', 'pct', 'avail', 'total', 'sys_pct']}
        
        fields = [("App Memory (RSS):", 'rss'), ("App Memory (%):", 'pct'), 
                  ("Sys Mem Avail:", 'avail'), ("Sys Mem Total:", 'total'), ("Sys Mem Used %:", 'sys_pct')]
        for i, (label, key) in enumerate(fields):
            mem_layout.addWidget(QLabel(label), i, 0)
            mem_layout.addWidget(self.memory_labels[key], i, 1)
        
        diag_btn = QPushButton("Logging Diagnostics")
        diag_btn.clicked.connect(lambda: LoggingVerificationDialog(self).exec_())
        mem_layout.addWidget(diag_btn, 5, 0, 1, 2)
        
        self.tab_widget.addTab(self.error_display, "Problems")
        self.tab_widget.addTab(self.log_display, "Output")
        self.tab_widget.addTab(self.memory_tab, "Memory Info")
        return self.tab_widget

    def create_info_displays(self, layout):
        # Observer Info
        obs_group = QGroupBox("Observer Info")
        obs_layout = QGridLayout(obs_group)
        self.observer_values = {k: QLabel("---") for k in ['local_time', 'utc', 'latitude', 'longitude', 'altitude_km', 'altitude_mi', 'timezone']}
        fields = [('Local Time:', 'local_time'), ('UTC:', 'utc'), ('Latitude:', 'latitude'), ('Longitude:', 'longitude'), 
                  ('Altitude [km]:', 'altitude_km'), ('Altitude [mi]:', 'altitude_mi'), ('Timezone:', 'timezone')]
        for i, (label, key) in enumerate(fields):
            obs_layout.addWidget(QLabel(label), i, 0)
            obs_layout.addWidget(self.observer_values[key], i, 1)
        layout.addWidget(obs_group)

        # Satellite Telemetry
        sat_group = QGroupBox("Satellite Telemetry")
        sat_layout = QGridLayout(sat_group)
        self.satellite_values = {k: QLabel("---") for k in ['speed_kms', 'speed_mis_s', 'altitude_km', 'altitude_mi', 'azimuth', 'elevation', 'ra', 'dec', 'lst', 'period', 'eclipsed']}
        fields = [('Speed [km/s]:', 'speed_kms'), ('Speed [mi/s]:', 'speed_mis_s'), ('Altitude [km]:', 'altitude_km'), ('Altitude [mi]:', 'altitude_mi'),
                  ('Azimuth:', 'azimuth'), ('Elevation:', 'elevation'), ('RA:', 'ra'), ('Dec:', 'dec'), ('LST:', 'lst'), ('Period:', 'period'), ('Eclipsed:', 'eclipsed')]
        for i, (label, key) in enumerate(fields):
            sat_layout.addWidget(QLabel(label), i, 0)
            sat_layout.addWidget(self.satellite_values[key], i, 1)
        layout.addWidget(sat_group)

    def create_frequency_info_display(self, layout):
        freq_group = QGroupBox("Frequency Information")
        freq_layout = QGridLayout(freq_group)
        self.frequency_values = {k: QLabel("---") for k in ['downlink_mhz', 'uplink_mhz', 'mode', 'beacon_mhz', 'status', 'bandwidth_khz', 'baud', 'service']}
        fields = [('Downlink [MHz]:', 'downlink_mhz'), ('Uplink [MHz]:', 'uplink_mhz'), ('Mode:', 'mode'), ('Beacon [MHz]:', 'beacon_mhz'),
                  ('Status:', 'status'), ('Bandwidth [kHz]:', 'bandwidth_khz'), ('Baud Rate:', 'baud'), ('Service:', 'service')]
        for i, (label, key) in enumerate(fields):
            freq_layout.addWidget(QLabel(label), i, 0)
            freq_layout.addWidget(self.frequency_values[key], i, 1)
        layout.addWidget(freq_group)

    # --- BRIDGE & MAP ---
    def init_map_bridge(self):
        self.map_bridge = MapBridge()
        self.channel = QWebChannel(self.map_view.page())
        self.map_view.page().setWebChannel(self.channel)
        self.channel.registerObject("pyBridge", self.map_bridge)
        
        # Connect Bridge signals to JS with restored logic
        self.map_bridge.update_observer_position.connect(lambda lat, lon: self.map_view.page().runJavaScript(f"updateObserver({lat}, {lon});"))
        self.map_bridge.update_satellite_position.connect(lambda lat, lon: self.map_view.page().runJavaScript(f"updateSatellite({lat}, {lon});"))
        self.map_bridge.update_celestial_position.connect(lambda t, lat, lon: self.map_view.page().runJavaScript(f"updateCelestial('{t}', {lat}, {lon});"))
        self.map_bridge.add_satellite_track_point.connect(lambda lat, lon: self.map_view.page().runJavaScript(f"addTrackPoint({lat}, {lon});"))
        self.map_bridge.clear_satellite_track.connect(lambda: self.map_view.page().runJavaScript("clearTrack();"))
        self.map_bridge.set_map_view.connect(lambda lat, lon, z: self.map_view.page().runJavaScript(f"setView({lat}, {lon}, {z});"))

    def init_map_view(self):
        # EXACT FULL HTML RESTORED (Including Emojis, Icons, and marker management)
        html_content = """
           <!DOCTYPE html><html><head><title>Satellite Map</title><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0"><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script src="qrc:///qtwebchannel/qwebchannel.js"></script><style>html, body, #map { height: 100%; width: 100%; margin: 0; padding: 0; background-color: #333; }.leaflet-control-attribution { display: none; }.leaflet-tile-container { filter: brightness(0.7) contrast(1.1) grayscale(0.1); }</style></head><body><div id="map"></div><script>
           var map = L.map('map', {center: [20, 0], zoom: 2, worldCopyJump: true, maxBounds: [[-90, -180], [90, 180]]});
           L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
           
           var observerMarker=null, satelliteMarker=null, sunMarker=null, moonMarker=null, satellitePath=null, pathPoints=[];
           
           var observerIcon = L.icon({ iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png', iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png', shadowSize: [41, 41] });
           var satelliteIcon = L.divIcon({className: 'sat-icon', html: '🛰️', iconSize: [24, 24], iconAnchor: [12, 12]}); 
           var sunIcon = L.divIcon({className: 'sun-icon', html: '☀️', iconSize: [30, 30], iconAnchor: [15, 15]}); 
           var moonIcon = L.divIcon({className: 'moon-icon', html: '🌕', iconSize: [26, 26], iconAnchor: [13, 13]});
           
           new QWebChannel(qt.webChannelTransport, function (channel) { window.pyBridge = channel.objects.pyBridge; });
           
           function updateObserver(lat, lon) { if (!observerMarker) observerMarker = L.marker([lat, lon], { icon: observerIcon, zIndexOffset: 500 }).addTo(map).bindPopup("Observer"); else observerMarker.setLatLng([lat, lon]); }
           function updateSatellite(lat, lon) { if (!satelliteMarker) satelliteMarker = L.marker([lat, lon], { icon: satelliteIcon, zIndexOffset: 1000 }).addTo(map).bindPopup("Satellite"); else satelliteMarker.setLatLng([lat, lon]); }
           function updateCelestial(type, lat, lon) { 
               let marker, icon, popupText; 
               if (type === 'sun') { marker = sunMarker; icon = sunIcon; popupText = "Subsolar Point"; } 
               else if (type === 'moon') { marker = moonMarker; icon = moonIcon; popupText = "Sublunar Point"; } 
               else return; 
               if (!marker) { marker = L.marker([lat, lon], { icon: icon, zIndexOffset: 400 }).addTo(map).bindPopup(popupText); if (type === 'sun') sunMarker = marker; else moonMarker = marker; } 
               else marker.setLatLng([lat, lon]); 
           }
           function addTrackPoint(lat, lon) { if (!satellitePath) satellitePath = L.polyline([], { color: '#FFD700', weight: 2 }).addTo(map); satellitePath.addLatLng([lat, lon]); }
           function clearTrack() { if (satellitePath) satellitePath.setLatLngs([]); }
           function setView(lat, lon, zoom) { map.setView([lat, lon], zoom); }
           </script></body></html>"""
        self.map_view.setHtml(html_content)

    # --- TLE Management ---
    def _download_tle_file(self, url, save_path):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=20) as response, open(save_path, 'wb') as out_file:
                out_file.write(response.read())
            return True
        except: return False

    def _load_satellites_from_tle(self):
        self.sat_list_status_label.setText("Loading TLE data...")
        self.refresh_tle_btn.setEnabled(False)
        def task():
            all_parsed = {}
            for k, info in DEFAULT_TLE_SOURCES.items():
                path = os.path.join(TLE_DATA_DIR, info['filename'])
                if not os.path.exists(path) or (time.time() - os.path.getmtime(path) > info['cache_days']*86400):
                    self._download_tle_file(info['url'], path)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    for i in range(0, len(lines)-2, 3):
                        n, l1, l2 = lines[i].strip(), lines[i+1].strip(), lines[i+2].strip()
                        if l1.startswith('1 ') and l2.startswith('2 '):
                            sat = EarthSatellite(l1, l2, n)
                            all_parsed[n] = {'norad_id': sat.model.satnum, 'line1': l1, 'line2': l2}
                except: pass
            QMetaObject.invokeMethod(self, "_finalize_tle_load", Qt.QueuedConnection, Q_ARG(dict, all_parsed))
        threading.Thread(target=task, daemon=True).start()

    @pyqtSlot(dict)
    def _finalize_tle_load(self, sats):
        self.satellites = sats
        self.sat_list_status_label.setText(f"{len(sats)} satellites loaded.")
        self.refresh_tle_btn.setEnabled(True)
        self.sat_name_input.setEnabled(True)
        self.sat_name_input.setPlaceholderText("Type to filter satellites...")

    # --- TRACKING CONTROL ---
    def start_tracking(self):
        try:
            name = self.selected_satellite_name or self.sat_name_input.text().strip()
            sat_info = self.satellites.get(name)
            if not sat_info: raise ValueError("Select a valid satellite.")
            
            lat_str = self.observer_values['latitude'].text()
            if "---" in lat_str: raise ValueError("Observer coordinates not set.")
            
            lat = float(lat_str)
            lon = float(self.observer_values['longitude'].text())
            alt = float(self.alt_input.text())
            
            # TLE Period Calculation
            mean_motion = float(sat_info['line2'][52:63].strip())
            period = 1440.0 / mean_motion if mean_motion > 0 else 0

            self._attempt_board_connection()
            
            config = {
                'sat_id': sat_info['norad_id'], 'sat_name': name,
                'obs_lat': lat, 'obs_lng': lon, 'obs_alt': alt,
                'interval': int(self.interval_input.text()),
                'period_tle_calculated_min': period
            }
            
            freq_data = self.api.get_satnogs_frequencies(sat_info['norad_id'])
            if freq_data: config.update(freq_data)

            if self.worker: self.worker.stop()
            self.worker = WorkerThread(self.api, self.data_manager, config)
            self.worker.data_ready.connect(self.update_satellite_data)
            self.worker.error_occurred.connect(self.show_error)
            self.worker.start()

            self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)
            self.map_bridge.clear_satellite_track.emit()
            self.map_bridge.update_observer_position.emit(lat, lon)
            self.map_bridge.set_map_view.emit(lat, lon, 5)
        except Exception as e: self.show_error(str(e))

    def update_satellite_data(self, data):
        # Restore telemetry display exactly as in original
        self.satellite_values['speed_kms'].setText(f"{data.get('speed_kms', 0):.2f} km/s")
        self.satellite_values['speed_mis_s'].setText(f"{data.get('speed_mis_s', 0):.2f} mi/s")
        self.satellite_values['altitude_km'].setText(f"{data.get('sataltitude', 0):.2f} km")
        self.satellite_values['altitude_mi'].setText(f"{data.get('sataltitude', 0)*0.621:.2f} mi")
        self.satellite_values['azimuth'].setText(f"{data.get('azimuth', 0):.2f}°")
        self.satellite_values['elevation'].setText(f"{data.get('elevation', 0):.2f}°")
        self.satellite_values['ra'].setText(f"{data.get('ra', 0):.4f}°")
        self.satellite_values['dec'].setText(f"{data.get('dec', 0):.4f}°")
        self.satellite_values['lst'].setText(f"{data.get('lst', 0):.4f} h")
        self.satellite_values['period'].setText(f"{data.get('period_tle_calculated_min', 0):.2f} min")
        self.satellite_values['eclipsed'].setText("Yes" if data.get('eclipsed') else "No")

        for k in self.frequency_values: self.frequency_values[k].setText(str(data.get(k, "---")))

        now = datetime.now()
        self.observer_values['local_time'].setText(now.strftime("%Y-%m-%d %H:%M:%S"))
        self.observer_values['utc'].setText(now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"))

        self.map_bridge.update_satellite_position.emit(data['satlatitude'], data['satlongitude'])
        self.map_bridge.add_satellite_track_point.emit(data['satlatitude'], data['satlongitude'])
        if self.board_manager.connection: self.board_manager.send_data(data)

    def stop_tracking(self):
        if self.worker: self.worker.stop()
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)

    # --- UI HELPERS ---
    def filter_satellites(self):
        text = self.sat_name_input.text().lower().strip()
        self.sat_list.clear()
        if not text or not self.satellites:
            self.sat_list.setVisible(False)
            return
        matches = [n for n in self.satellites if text in n.lower()]
        if matches:
            self.sat_list.addItems(sorted(matches)[:50])
            self.sat_list.setVisible(True)
        else:
            self.sat_list.setVisible(False)

    def select_satellite(self, item):
        self.selected_satellite_name = item.text()
        self.sat_name_input.setText(self.selected_satellite_name)
        self.sat_list.setVisible(False)

    def _fetch_observer_coords(self):
        city = self.city_input.text().strip()
        if not city: return
        def task():
            lat, lon = self.api.get_geolocation(city)
            QMetaObject.invokeMethod(self, "_update_fetched_coords", Qt.QueuedConnection, Q_ARG(float, lat or 0.0), Q_ARG(float, lon or 0.0))
        threading.Thread(target=task, daemon=True).start()

    @pyqtSlot(float, float)
    def _update_fetched_coords(self, lat, lon):
        self.observer_values['latitude'].setText(f"{lat:.4f}")
        self.observer_values['longitude'].setText(f"{lon:.4f}")

    def _handle_board_type_change(self, t):
        self.model_combo.clear()
        info = self.board_manager.boards.get(t, {})
        models = info.get("models", {})
        if models: 
            self.model_combo.addItems(sorted(models.keys()))
            self.model_combo.setEnabled(True)
        else: 
            self.model_combo.addItem("---")
            self.model_combo.setEnabled(False)

    def _refresh_port_list(self):
        self.port_combo.clear()
        self.port_combo.addItems(self.board_manager.get_available_ports())

    def test_board_connection(self):
        t = self.board_type_combo.currentText()
        if t == "Select Board...": return
        p = self.port_combo.currentText()
        b = int(self.baud_rate_input.text())
        m = self.model_combo.currentText()
        self.board_manager.connect(p, {'baud_rate': b}, t, m if m != "---" else None)

    def _update_board_status_ui(self, connected, msg):
        self.board_status_label.setText(msg)
        self.connection_status.setStyleSheet(f"border-radius:10px; background-color: {'#00cc00' if connected else '#cc0000'};")

    def _attempt_board_connection(self):
        t = self.board_type_combo.currentText()
        if t != "Select Board...": self.test_board_connection()

    def update_memory_display(self):
        try:
            import psutil
            p = psutil.Process()
            m = p.memory_info()
            v = psutil.virtual_memory()
            self.memory_labels['rss'].setText(f"{m.rss/1e6:.1f} MB")
            self.memory_labels['pct'].setText(f"{p.memory_percent():.1f}%")
            self.memory_labels['avail'].setText(f"{v.available/1e6:.0f} MB")
            self.memory_labels['total'].setText(f"{v.total/1e6:.0f} MB")
            self.memory_labels['sys_pct'].setText(f"{v.percent:.1f}%")
        except: pass

    def start_celestial_updates(self):
        self.cel_timer = QTimer(self)
        self.cel_timer.timeout.connect(self.update_celestial_positions)
        self.cel_timer.start(300000); self.update_celestial_positions()

    def update_celestial_positions(self):
        try:
            now = datetime.now(timezone.utc)
            sla, slo = CelestialCalculator.sun_position(now)
            mla, mlo = CelestialCalculator.moon_position(now)
            self.map_bridge.update_celestial_position.emit('sun', sla, slo)
            self.map_bridge.update_celestial_position.emit('moon', mla, mlo)
        except: pass

    def _check_log_file_update(self):
        if not os.path.exists(LOG_FILE): return
        s = os.stat(LOG_FILE)
        if self.last_log_stat is None: self.last_log_stat = s.st_size
        if s.st_size > self.last_log_stat:
            with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(self.last_log_stat)
                self.log_display.append(f.read().strip())
        self.last_log_stat = s.st_size

    def _append_log_message(self, m): self.log_display.append(m)
    def _append_error_message(self, m): self.error_display.append(m)
    def show_error(self, m): self.error_message_signal.emit(m)
    def show_critical_error(self, m): QMessageBox.critical(self, "Critical Error", m)

    def closeEvent(self, event):
        self.stop_tracking()
        self.board_manager.disconnect()
        event.accept()
 