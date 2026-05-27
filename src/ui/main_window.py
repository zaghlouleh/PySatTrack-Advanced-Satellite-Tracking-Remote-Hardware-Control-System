import json
import logging
import time
from datetime import datetime, timezone
from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit, QTabWidget,
                            QPushButton, QTextEdit, QVBoxLayout, QMenu,
                            QHBoxLayout, QListWidget, QGridLayout, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QTextCursor, QColor, QTextCharFormat

from src.services.api_client import APIClient
from src.services.data_manager import DataManager, satellite_data_manager
from src.services.arduino import ArduinoManager
from src.ui.worker import WorkerThread
from src.core.calculator import CelestialCalculator
from src.ui.styles import TAB_WIDGET_STYLE, ERROR_DISPLAY_STYLE, LOG_DISPLAY_STYLE
from src.config import LOG_FILE

class SatelliteTracker(QWidget):
    """Main application window controlling the UI and logic flow"""
    def __init__(self):
        super().__init__()
        self.api = APIClient()
        self.data_manager = satellite_data_manager
        self.arduino = ArduinoManager()
        self.worker = None
        self.is_map_fullscreen = False
        self.satellites = self.load_satellites()
        
        # Initialize value containers
        self.observer_values = {}
        self.satellite_values = {}
        self.error_count = 0
        self.log_count = 0
        
        self.init_ui()
        self.init_map()
        self.sat_list.setVisible(False)

        self.tab_widget.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(self.create_tab_context_menu)

    def load_satellites(self):
        """Load satellite database from local JSON file"""
        try:
            with open('namesat+idsat.json') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load satellites: {str(e)}")
            return {}

    def init_ui(self):
        self.setWindowTitle("Satellite Tracker v2")
        self.setGeometry(100, 100, 1400, 900)
        self.showMaximized()  # Start maximized for better map view
        
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        
        # Left panel (30%) with min width
        left_panel = QVBoxLayout()
        left_panel.setSpacing(12)
        self.create_input_fields(left_panel)
        
        # Map view (50%) - dominant panel
        map_container = QWidget()
        map_layout = QVBoxLayout(map_container)
        map_layout.setContentsMargins(0, 0, 0, 0)
        self.map_toggle_btn = QPushButton("🗺️ Fullscreen Map")
        self.map_toggle_btn.clicked.connect(lambda: None)  # TODO: implement toggle_map_fullscreen
        self.map_toggle_btn.setToolTip("Toggle map fullscreen")
        map_layout.addWidget(self.map_toggle_btn)
        self.map_view = QWebEngineView()
        map_layout.addWidget(self.map_view)
        
        # Right panel (20%) - telemetry
        right_panel = QVBoxLayout()
        right_panel.setSpacing(12)
        self.create_info_displays(right_panel)
        
        # Responsive weights
        main_layout.addLayout(left_panel, 3)
        main_layout.addWidget(map_container, 5)
        main_layout.addLayout(right_panel, 2)
        self.setLayout(main_layout)

    def create_input_fields(self, layout):
        # Satellite input group
        sat_group = QVBoxLayout()
        sat_label = QLabel("Satellite Name:")
        sat_label.setToolTip("Type to search 6000+ satellites (e.g. 'ISS', 'Starlink')")
        sat_group.addWidget(sat_label)
        self.sat_name_input = QLineEdit()
        self.sat_name_input.setPlaceholderText("e.g. ISS (Si)")
        self.sat_name_input.setToolTip("Satellite name or NORAD ID")
        self.sat_list = QListWidget()
        self.sat_list.setMaximumHeight(120)
        self.sat_list.setVisible(False)
        self.sat_name_input.textChanged.connect(self.validate_inputs)
        self.sat_name_input.textChanged.connect(self.filter_satellites)
        self.sat_list.itemClicked.connect(self.select_satellite)
        sat_group.addWidget(self.sat_name_input)
        sat_group.addWidget(self.sat_list)
        
        # Location inputs
        loc_group = QVBoxLayout()
        city_label = QLabel("City:")
        city_label.setToolTip("Your city for geolocation (auto-fetches lat/lng)")
        loc_group.addWidget(city_label)
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("e.g. New York, London")
        self.city_input.setToolTip("Any recognizable city name")
        self.city_input.textChanged.connect(self.validate_inputs)
        loc_group.addWidget(self.city_input)
        alt_label = QLabel("Altitude (meters):")
        alt_label.setToolTip("Observer elevation above sea level")
        loc_group.addWidget(alt_label)
        self.alt_input = QLineEdit("0")
        self.alt_input.setToolTip("0-9000m typical")
        self.alt_input.textChanged.connect(self.validate_inputs)
        loc_group.addWidget(self.alt_input)
        
        # Update interval
        interval_group = QVBoxLayout()
        interval_label = QLabel("Update Interval (1-300 seconds):")
        interval_label.setToolTip("How often to refresh tracking data")
        interval_group.addWidget(interval_label)
        self.interval_input = QLineEdit("60")
        self.interval_input.setToolTip("1-300 seconds")
        self.interval_input.textChanged.connect(self.validate_inputs)
        interval_group.addWidget(self.interval_input)
        
        # Arduino inputs
        arduino_group = QVBoxLayout()
        port_label = QLabel("Arduino Port:")
        port_label.setToolTip("Serial port for antenna controller (e.g. COM3, /dev/ttyUSB0)")
        arduino_group.addWidget(port_label)
        self.arduino_port = QLineEdit()
        self.arduino_port.setPlaceholderText("e.g. COM3, /dev/ttyUSB0")
        self.arduino_port.textChanged.connect(self.validate_inputs)
        arduino_group.addWidget(self.arduino_port)
        baud_label = QLabel("Baud Rate:")
        baud_label.setToolTip("Serial communication speed (9600 default)")
        arduino_group.addWidget(baud_label)
        self.baud_rate = QLineEdit("9600")
        self.baud_rate.textChanged.connect(self.validate_inputs)
        arduino_group.addWidget(self.baud_rate)
        
        # Controls with status
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶ Start Tracking")
        self.start_btn.setToolTip("Begin real-time satellite tracking")
        self.stop_btn = QPushButton("⏹ Stop Tracking")
        self.stop_btn.setToolTip("Stop tracking and clear displays")
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        self.start_btn.clicked.connect(self.start_tracking)
        self.stop_btn.clicked.connect(self.stop_tracking)
        
        # Status indicator
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("QLabel { color: #3DDC84; font-weight: bold; padding: 4px; }")
        btn_layout.addWidget(self.status_label)

        # Error and log displays first
        self.error_display = QTextEdit()
        self.error_display.setReadOnly(True)
        self.error_display.setStyleSheet(ERROR_DISPLAY_STYLE)
        
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet(LOG_DISPLAY_STYLE)
        
        # Tabbed interface (VS Code Style) with badges
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(TAB_WIDGET_STYLE)
        self.tab_widget.addTab(self.error_display, "Problems")
        self.tab_widget.setTabToolTip(0, "Validation & API errors")
        
        self.tab_widget.addTab(self.log_display, "Output")
        self.tab_widget.setTabToolTip(1, "Application logs")
        
        layout.addLayout(sat_group)
        layout.addLayout(loc_group)
        layout.addLayout(interval_group)
        layout.addLayout(arduino_group)
        layout.addLayout(btn_layout)
        layout.addWidget(self.tab_widget, stretch=1)
        layout.addStretch()

        # Log timer
        self.log_update_timer = QTimer()
        self.log_update_timer.timeout.connect(self.update_log_display)
        self.log_update_timer.start(2000)

    def create_info_displays(self, layout):
        # Observer Section - Responsive height
        observer_container = QGroupBox("👤 Your Current Location")
        observer_layout = QVBoxLayout(observer_container)
        observer_group = QGridLayout()
        observer_group.setVerticalSpacing(4)
        observer_group.setHorizontalSpacing(12)
        
        self.observer_values = {
            'local_time': QLabel("N/A"), 'utc': QLabel("N/A"),
            'latitude': QLabel("N/A"), 'longitude': QLabel("N/A"),
            'altitude_km': QLabel("N/A"), 'altitude_mi': QLabel("N/A"),
            'timezone': QLabel("N/A")
        }
        
        row = 0
        labels = [("🕐 Local Time:", "local_time"), ("🌍 UTC:", "utc"), 
                  ("📍 Latitude:", "latitude"), ("📍 Longitude:", "longitude"),
                  ("📏 Altitude [km]:", "altitude_km"), ("📏 Altitude [mi]:", "altitude_mi"),
                  ("⏰ Timezone:", "timezone")]
        for text, key in labels:
            lbl = QLabel(text)
            lbl.setStyleSheet("font-size: 11px; color: #CCCCCC;")
            observer_group.addWidget(lbl, row, 0)
            self.observer_values[key].setProperty("role", "telemetry")
            observer_group.addWidget(self.observer_values[key], row, 1)
            row += 1
        observer_layout.addLayout(observer_group)

        # Satellite Section - Responsive height
        satellite_container = QGroupBox("🛰️ Satellite Telemetry")
        satellite_layout = QVBoxLayout(satellite_container)
        satellite_group = QGridLayout()
        satellite_group.setVerticalSpacing(4)
        satellite_group.setHorizontalSpacing(12)
        
        self.satellite_values = {
            'speed_kms': QLabel("N/A"), 'speed_mis': QLabel("N/A"),
            'azimuth': QLabel("N/A"), 'elevation': QLabel("N/A"),
            'ra': QLabel("N/A"), 'dec': QLabel("N/A"),
            'lst': QLabel("N/A"), 'period': QLabel("N/A"),
            'eclipsed': QLabel("N/A"), 'altitude_km': QLabel("N/A"),
            'altitude_mi': QLabel("N/A")
        }
        
        sat_fields = [("⚡ Speed [km/s]:", "speed_kms"), ("⚡ Speed [mi/s]:", "speed_mis"),
                      ("🧭 Azimuth:", "azimuth"), ("📐 Elevation:", "elevation"),
                      ("⭐ RA:", "ra"), ("⭐ DEC:", "dec"), ("🌌 LST:", "lst"),
                      ("🔄 Period:", "period"), ("🌑 Shadow:", "eclipsed"),
                      ("📏 Alt [km]:", "altitude_km"), ("📏 Alt [mi]:", "altitude_mi")]
        
        row = 0
        for text, key in sat_fields:
            lbl = QLabel(text)
            lbl.setStyleSheet("font-size: 11px; color: #CCCCCC;")
            satellite_group.addWidget(lbl, row, 0)
            self.satellite_values[key].setProperty("role", "telemetry")
            satellite_group.addWidget(self.satellite_values[key], row, 1)
            row += 1
        satellite_layout.addLayout(satellite_group)
        
        # Responsive stretch
        layout.addWidget(observer_container, 1)
        layout.addWidget(satellite_container, 1)
        layout.addStretch()

    def init_map(self):
        self.map_view.setHtml("""
            <!DOCTYPE html>
            <html>
            <head>
                <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css"/>
                <style>#map { height: 100vh; width: 100%; }</style>
            </head>
            <body>
                <div id="map"></div>
                <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
                <script>
                    var map = L.map('map', {worldCopyJump: true}).setView([0, 0], 2);
                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
                    var observerMarker = null; var satelliteMarker = null; var satellitePath = null;
                    var sunMarker = null; var moonMarker = null;
                    
                    var observerIcon = L.icon({iconUrl: 'https://cdn-icons-png.flaticon.com/512/447/447031.png', iconSize: [22, 22]});
                    var satelliteIcon = L.icon({iconUrl: 'https://cdn-icons-png.flaticon.com/512/1062/1062195.png', iconSize: [32, 32]});
                </script>
            </body>
            </html>
        """)
        self.celestial_timer = QTimer()
        self.celestial_timer.timeout.connect(self.update_celestial_positions)
        self.celestial_timer.start(300000)

    def filter_satellites(self):
        text = self.sat_name_input.text().lower()
        self.sat_list.clear()
        if text:
            self.sat_list.setVisible(True)
            for name in self.satellites:
                if text in name.lower(): self.sat_list.addItem(name)
        else: self.sat_list.setVisible(False)

    def select_satellite(self, item):
        self.clear_previous_satellite()
        self.sat_name_input.setText(item.text())
        self.sat_list.setVisible(False)

    def clear_previous_satellite(self):
        for val in self.satellite_values.values(): val.setText("N/A")
        self.map_view.page().runJavaScript("""
            if (satelliteMarker) map.removeLayer(satelliteMarker);
            if (satellitePath) map.removeLayer(satellitePath);
            satelliteMarker = null; satellitePath = null;
        """)

    def validate_inputs(self):
        """Real-time input validation with styling"""
        valid = True
        
        # Satellite name
        sat_valid = bool(self.sat_name_input.text().strip() and self.sat_name_input.text().strip() in self.satellites)
        self.sat_name_input.setProperty("valid", "true" if sat_valid else "false")
        
        # City (basic check)
        city_valid = bool(self.city_input.text().strip())
        self.city_input.setProperty("valid", "true" if city_valid else "false")
        
        # Numbers
        try:
            int(self.interval_input.text()) if self.interval_input.text() else 60
            float(self.alt_input.text()) if self.alt_input.text() else 0
            self.interval_input.setProperty("valid", "true")
            self.alt_input.setProperty("valid", "true")
        except:
            self.interval_input.setProperty("valid", "false")
            self.alt_input.setProperty("valid", "false")
            valid = False
            
        self.style().unpolish(self.sat_name_input)
        self.style().polish(self.sat_name_input)
        self.style().unpolish(self.city_input)
        self.style().polish(self.city_input)
        self.style().unpolish(self.interval_input)
        self.style().polish(self.interval_input)
        self.style().unpolish(self.alt_input)
        self.style().polish(self.alt_input)
        
        # Update start button
        self.start_btn.setEnabled(sat_valid and city_valid)
        
        # Status
        if sat_valid and city_valid:
            sat = self.sat_name_input.text()
            self.status_label.setText(f"Ready: {sat} ({self.satellites.get(sat, 'N/A')})")
            self.status_label.setStyleSheet("QLabel { color: #3DDC84; font-weight: bold; padding: 4px; }")
        else:
            self.status_label.setText("Enter satellite & city")
            self.status_label.setStyleSheet("QLabel { color: #F14C4C; font-weight: bold; padding: 4px; }")
    
    def start_tracking(self):
        try:
            if not self.start_btn.isEnabled():
                self.show_error("Please fix input validation errors")
                return
                
            self.start_btn.setText("⏳ Starting...")
            self.start_btn.setProperty("loading", "true")
            self.start_btn.repaint()
            
            interval = int(self.interval_input.text())
            sat_name = self.sat_name_input.text()
            city = self.city_input.text()
            
            lat, lng = self.api.get_geolocation(city)
            if not lat: 
                self.show_error("City validation failed")
                self.start_btn.setText("▶ Start Tracking")
                self.start_btn.setProperty("loading", "false")
                self.start_btn.repaint()
                return

            self.observer_values['latitude'].setText(f"{lat:.4f}°")
            self.observer_values['longitude'].setText(f"{lng:.4f}°")
            self.observer_values['timezone'].setText(datetime.now(timezone.utc).astimezone().tzinfo.tzname(datetime.now()))

            self.worker = WorkerThread(self.api, self.data_manager, {
                'sat_id': self.satellites[sat_name], 'sat_name': sat_name,
                'obs_lat': lat, 'obs_lng': lng, 'obs_alt': float(self.alt_input.text()),
                'interval': interval
            })
            self.worker.data_ready.connect(self.update_satellite_data)
            self.worker.error_occurred.connect(self.show_error)
            self.worker.start()

            self.map_view.page().runJavaScript(f"""
                if (observerMarker) map.removeLayer(observerMarker);
                observerMarker = L.marker([{lat}, {lng}], {{icon: observerIcon}}).addTo(map)
                    .bindPopup('Your Location').openPopup();
                satellitePath = L.polyline([], {{color: 'red', weight: 3}}).addTo(map);
                satelliteMarker = L.marker([0, 0], {{icon: satelliteIcon}}).addTo(map);
                map.setView([{lat}, {lng}], 8);
            """)
            
            # UI state
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.status_label.setText(f"Tracking {sat_name}...")
            self.status_label.setStyleSheet("QLabel { color: #3DDC84; font-weight: bold; padding: 4px; }")
            
        except Exception as e: 
            self.show_error(f"Input error: {str(e)}")
            self.start_btn.setText("▶ Start Tracking")
            self.start_btn.setProperty("loading", "false")
            self.start_btn.repaint()


    def update_satellite_data(self, data):
        # Update telemetry with styling
        speed_kms = data.get('speed_kms', 0)
        self.satellite_values['speed_kms'].setText(f"{speed_kms:.2f}")
        if speed_kms > 6.5:  # Orbital speeds
            self.satellite_values['speed_kms'].setProperty("speed-high", "true")
        else:
            self.satellite_values['speed_kms'].setProperty("speed-high", "false")
        
        az = data.get('azimuth', 'N/A')
        self.satellite_values['azimuth'].setText(f"{az}°")
        
        el = data.get('elevation', 0)
        el_text = f"{el:.1f}°"
        self.satellite_values['elevation'].setText(el_text)
        if el > 0:
            self.satellite_values['elevation'].setProperty("elevation-green", "true")
            self.satellite_values['elevation'].setProperty("elevation-red", "false")
        else:
            self.satellite_values['elevation'].setProperty("elevation-green", "false")
            self.satellite_values['elevation'].setProperty("elevation-red", "true")
        
        # Style refresh
        for label in self.satellite_values.values():
            self.style().unpolish(label)
            self.style().polish(label)
        
        self.observer_values['local_time'].setText(datetime.now().strftime("%H:%M:%S"))
        self.observer_values['utc'].setText(datetime.now(timezone.utc).strftime("%H:%M:%S UTC"))
        
        # Update other fields
        self.satellite_values['speed_mis'].setText(f"{data.get('speed_mis', 0):.2f}")
        self.satellite_values['ra'].setText(f"{data.get('ra', 'N/A')}")
        self.satellite_values['dec'].setText(f"{data.get('dec', 'N/A')}")
        self.satellite_values['lst'].setText(f"{data.get('lst', 'N/A')}")
        self.satellite_values['period'].setText(f"{data.get('period', 'N/A')} min")
        self.satellite_values['eclipsed'].setText("Yes" if data.get('eclipsed') else "No")
        self.satellite_values['altitude_km'].setText(f"{data.get('sataltitude', 0):.0f}")
        self.satellite_values['altitude_mi'].setText(f"{data.get('sataltitude', 0)*0.621371:.0f}")
        
        # Map update
        self.map_view.page().runJavaScript(f"""
            if (satelliteMarker) {{
                satelliteMarker.setLatLng([{data['satlatitude']}, {data['satlongitude']}]).
                bindPopup('Elev: {el_text}<br>Speed: {speed_kms:.1f} km/s');
            }}
            if (satellitePath) {{
                satellitePath.addLatLng([{data['satlatitude']}, {data['satlongitude']}]).
                bringToFront();
            }}
        """)
        
        sun_lat, sun_lng = CelestialCalculator.sun_position(datetime.now(timezone.utc))
        sun_lat, sun_lng = CelestialCalculator.sun_position(datetime.now(timezone.utc))
        moon_lat, moon_lng = CelestialCalculator.moon_position(datetime.now(timezone.utc))
        self.map_view.page().runJavaScript(f"""
            if (window.sunMarker) map.removeLayer(window.sunMarker);
            window.sunMarker = L.icon({{iconUrl: 'https://cdn-icons-png.flaticon.com/512/979/979534.png', iconSize: [24, 24], iconAnchor: [12, 24] }});
            L.marker([{sun_lat}, {sun_lng}], {{icon: window.sunMarker}}).addTo(map).bindPopup('Sun');
            
            if (window.moonMarker) map.removeLayer(window.moonMarker);
            window.moonMarker = L.icon({{iconUrl: 'https://cdn-icons-png.flaticon.com/512/9689/9689800.png', iconSize: [20, 20], iconAnchor: [10, 20] }});
            L.marker([{moon_lat}, {moon_lng}], {{icon: window.moonMarker}}).addTo(map).bindPopup('Moon');
        """)

    def stop_tracking(self):
        self.status_label.setText("Stopped")
        self.status_label.setStyleSheet("QLabel { color: #F7931E; font-weight: bold; padding: 4px; }")
        
        if self.worker: 
            self.worker.stop()
            self.worker.wait(1000)  # Graceful shutdown
            self.worker = None
        
        self.clear_previous_satellite()
        self.start_btn.setText("▶ Start Tracking")
        self.start_btn.setEnabled(True)
        self.start_btn.setProperty("loading", "false")
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Ready")

    def show_error(self, message):
        cursor = self.error_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.tab_widget.setCurrentIndex(0)

    def update_log_display(self):
        try:
            with open(LOG_FILE, 'r') as f:
                self.log_display.setPlainText(f.read())
                self.log_display.moveCursor(QTextCursor.End)
        except: pass

    def create_tab_context_menu(self, pos):
        idx = self.tab_widget.tabBar().tabAt(pos)
        if idx >= 0:
            menu = QMenu(); clear = menu.addAction("Clear")
            clear.triggered.connect(lambda: self.tab_widget.widget(idx).clear())
            menu.exec_(self.tab_widget.mapToGlobal(pos))

    def update_celestial_positions(self):
        # Triggered by timer
        pass