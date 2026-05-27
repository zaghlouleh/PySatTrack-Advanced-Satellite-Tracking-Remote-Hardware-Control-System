import os
import json
import logging
from datetime import datetime, timezone
from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit, QTabWidget,
                            QPushButton, QTextEdit, QVBoxLayout, QMenu, QComboBox,
                            QHBoxLayout, QListWidget, QGridLayout, QGroupBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QTextCursor, QColor, QTextCharFormat, QIcon

from src.core.calculator import CelestialCalculator
from src.core.data_manager import satellite_data_manager
from src.services.api_client import APIClient
from src.services.board_manager import BoardManager
from src.workers.tracking_worker import TrackingWorker
from src.ui.components import LoggingVerificationDialog

logger = logging.getLogger(__name__)

class SatelliteTracker(QWidget):
    """Main application window with exact icon URLs and layout from the original file."""
    def __init__(self, log_file):
        super().__init__()
        self.log_file = log_file
        self.api = APIClient()
        self.data_manager = satellite_data_manager
        self.board_manager = BoardManager()
        self.worker = None
        self.satellites = self.load_satellites()
        
        self.observer_values = {}
        self.satellite_values = {}
        self.memory_labels = {}

        self.init_ui()
        self.init_map()
        
        self.log_timer = QTimer()
        self.log_timer.timeout.connect(self.update_log_display)
        self.log_timer.start(1000)
        
        self.mem_display_timer = QTimer()
        self.mem_display_timer.timeout.connect(self.update_memory_display)
        self.mem_display_timer.start(1000)

    def load_satellites(self):
        try:
            with open('namesat+idsat.json', 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load satellite database: {e}")
            return {}

    def init_ui(self):
        self.setWindowTitle("Satellite Tracker")
        self.setGeometry(100, 100, 1400, 900)
        self.setWindowIcon(QIcon('icon.ico'))
        main_layout = QHBoxLayout()
        
        left_panel = QVBoxLayout()
        self.create_input_fields(left_panel)
        
        self.map_view = QWebEngineView()
        self.map_view.setMinimumSize(700, 600)
        
        right_panel = QVBoxLayout()
        self.create_info_displays(right_panel)
    
        main_layout.addLayout(left_panel, 30)
        main_layout.addWidget(self.map_view, 50)
        main_layout.addLayout(right_panel, 20)
        self.setLayout(main_layout)

    def create_input_fields(self, layout):
        sat_group = QGroupBox("🌐 Satellite Tracking")
        sat_group.setFixedHeight(120)
        sat_layout = QVBoxLayout(sat_group)
        sat_layout.setContentsMargins(1, 1, 1, 1)
        self.sat_name_input = QLineEdit()
        self.sat_name_input.setPlaceholderText("e.g., ISS, Starlink...")
        self.sat_name_input.setToolTip("Type satellite name or ID to search database")
        self.sat_name_input.textChanged.connect(self.filter_satellites)
        self.sat_list = QListWidget()
        self.sat_list.setMinimumHeight(80)
        self.sat_list.setStyleSheet("""
            QListWidget { border: 1px solid #404040; border-radius: 4px; }
            QListWidget::item { padding: 8px; }
        """)
        self.sat_list.setVisible(False)
        self.sat_list.itemClicked.connect(self.select_satellite)
        sat_layout.addWidget(QLabel("Satellite Name:"))
        sat_layout.addWidget(self.sat_name_input)
        sat_layout.addWidget(self.sat_list)
        layout.addWidget(sat_group)

        # --- NEW TABBED SECTION FOR SETTINGS ---
        self.settings_tabs = QTabWidget()
        
        # Tab 1: Location & Updates
        loc_tab = QWidget()
        loc_tab_layout = QVBoxLayout(loc_tab)
        loc_tab_layout.setContentsMargins(0, 5, 0, 0)

        loc_group = QGroupBox("📍 Observer Location")
        loc_group.setFixedHeight(170)
        loc_layout = QVBoxLayout(loc_group)
        loc_layout.setContentsMargins(1, 1, 1, 1)
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("e.g., New York")
        self.city_input.setToolTip("Enter city name for geolocation lookup")
        self.alt_input = QLineEdit("0")
        self.alt_input.setToolTip("Observer altitude above sea level (meters)")
        loc_layout.addWidget(QLabel("City:"))
        loc_layout.addWidget(self.city_input)
        loc_layout.addWidget(QLabel("Altitude (meters):"))
        loc_layout.addWidget(self.alt_input)

        interval_group = QGroupBox("⏱️ Update Settings")
        interval_group.setFixedHeight(110)
        interval_layout = QVBoxLayout(interval_group)
        interval_layout.setContentsMargins(1, 1, 1, 1)
        self.interval_input = QLineEdit("60")
        self.interval_input.setToolTip("Tracking update interval (1-300 seconds)")
        interval_layout.addWidget(QLabel("Update Interval (1-300 seconds):"))
        interval_layout.addWidget(self.interval_input)
        
        loc_tab_layout.addWidget(loc_group)
        loc_tab_layout.addWidget(interval_group)
        loc_tab_layout.addStretch()

        # Tab 2: Board Configuration
        board_tab = QWidget()
        board_tab_layout = QVBoxLayout(board_tab)
        board_tab_layout.setContentsMargins(0, 5, 0, 0)

        board_group = QGroupBox("🖥️ Board Configuration")
        board_group.setFixedHeight(280)
        board_layout = QVBoxLayout(board_group)
        board_layout.setContentsMargins(1, 1, 1, 1)
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Board Type:"))
        self.board_type_combo = QComboBox()
        self.board_type_combo.addItems(sorted(self.board_manager.boards.keys()))
        self.board_type_combo.currentTextChanged.connect(self._update_board_ui)
        type_layout.addWidget(self.board_type_combo)
        board_layout.addLayout(type_layout)
        
        self.port_label = QLabel("Port:")
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("/dev/ttyUSB0 or COM3")
        self.port_input.setToolTip("Board serial port or protocol address")
        self.baud_rate_label = QLabel("Baud Rate:")
        self.baud_rate_input = QLineEdit("9600")
        self.baud_rate_input.setToolTip("UART baud rate (common: 9600, 115200)")
        board_layout.addWidget(self.port_label)
        board_layout.addWidget(self.port_input)
        board_layout.addWidget(self.baud_rate_label)
        board_layout.addWidget(self.baud_rate_input)
        
        status_layout = QHBoxLayout()
        self.connection_status = QLabel()
        self.connection_status.setFixedSize(24, 24)
        self.connection_status.setStyleSheet("border-radius: 12px; background-color: #666; border: 2px solid #404040;")
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self.test_board_connection)
        status_layout.addWidget(self.connection_status)
        status_layout.addWidget(self.test_btn)
        status_layout.addStretch()
        board_layout.addLayout(status_layout)

        diag_btn = QPushButton("Logging Diagnostics")
        diag_btn.clicked.connect(self.show_logging_diagnostics)
        board_layout.addWidget(diag_btn)
        
        board_tab_layout.addWidget(board_group)
        board_tab_layout.addStretch()

        self.settings_tabs.addTab(loc_tab, "Configuration")
        self.settings_tabs.addTab(board_tab, "Hardware")
        layout.addWidget(self.settings_tabs)

        # --- REST OF THE UI AS ORIGINALLY DEFINED ---
        self.start_btn = QPushButton("▶️ Start Tracking")
        self.start_btn.setStyleSheet("QPushButton { background-color: #0e639c; font-weight: bold; }")
        self.stop_btn = QPushButton("⏹️ Stop Tracking")
        self.stop_btn.setStyleSheet("QPushButton { background-color: #cd3131; font-weight: bold; }")
        self.start_btn.clicked.connect(self.start_tracking)
        self.stop_btn.clicked.connect(self.stop_tracking)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)
        layout.addWidget(self.create_tab_widget())

    def create_tab_widget(self):
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabBar::tab { font-weight: 500; min-width: 100px; }
        """)
        self.error_display = QTextEdit()
        self.error_display.setReadOnly(True)
        self.error_display.setStyleSheet("background-color: #1e1e1e; color: #f48771; font-family: Consolas; border: none;")
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas; border: none;")
        
        self.tab_widget.addTab(self.error_display, "Problems")
        self.tab_widget.addTab(self.log_display, "Output")
        
        mem_tab = QWidget()
        mem_layout = QGridLayout(mem_tab)
        mem_layout.setVerticalSpacing(8)
        mem_layout.setHorizontalSpacing(12)
        self.memory_labels = {
            'process_rss': QLabel("Process Memory (RSS): N/A"),
            'process_percent': QLabel("Process Memory (%): N/A"),
            'system_available': QLabel("System Available: N/A"),
            'system_used': QLabel("System Used: N/A")
        }
        for i, label in enumerate(self.memory_labels.values()):
            label.setStyleSheet("font-family: Consolas; padding: 4px; border: none;")
            mem_layout.addWidget(label, i, 0)
        self.tab_widget.addTab(mem_tab, "💾 Memory Info")
        
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3d3d3d; background: #1e1e1e; }
            QTabBar::tab { background: #252526; color: #ffffff; padding: 8px 12px; border: 1px solid #3d3d3d; border-bottom: none; }
            QTabBar::tab:selected { background: #2d2d2d; }
        """)
        return self.tab_widget

    def create_info_displays(self, layout):
        obs_container = QGroupBox("Your Current Location")
        obs_container.setFixedHeight(300) 
        obs_layout = QVBoxLayout(obs_container)
        obs_grid = QGridLayout()
        obs_fields = [
            ("Local Time:", "local_time"), ("UTC:", "utc"),
            ("Latitude:", "latitude"), ("Longitude:", "longitude"),
            ("Altitude [km]:", "altitude_km"), ("Altitude [mi]:", "altitude_mi"),
            ("Timezone:", "timezone")
        ]
        for i, (label, key) in enumerate(obs_fields):
            obs_grid.addWidget(QLabel(label), i, 0)
            self.observer_values[key] = QLabel("N/A")
            obs_grid.addWidget(self.observer_values[key], i, 1)
        obs_grid.setVerticalSpacing(6)
        obs_grid.setHorizontalSpacing(12)
        obs_layout.addLayout(obs_grid)
        
        sat_container = QGroupBox("Satellite Telemetry")
        sat_container.setFixedHeight(380)
        sat_layout = QVBoxLayout(sat_container)
        sat_grid = QGridLayout()
        sat_fields = [
            ("Speed [km/s]:", "speed_kms"), ("Speed [mi/s]:", "speed_mis"),
            ("Azimuth:", "azimuth"), ("Elevation:", "elevation"),
            ("Right Ascension:", "ra"), ("Declination:", "dec"),
            ("Local Sidereal Time:", "lst"), ("Satellite Period:", "period"),
            ("In Earth's Shadow:", "eclipsed"), ("Altitude [km]:", "sat_alt_km"),
            ("Altitude [mi]:", "sat_alt_mi")
        ]
        for i, (label, key) in enumerate(sat_fields):
            sat_grid.addWidget(QLabel(label), i, 0)
            self.satellite_values[key] = QLabel("N/A")
            sat_grid.addWidget(self.satellite_values[key], i, 1)
        sat_grid.setVerticalSpacing(4)
        sat_grid.setHorizontalSpacing(12)
        sat_layout.addLayout(sat_grid)
        
        layout.addWidget(obs_container)
        layout.addWidget(sat_container)
        layout.addStretch()

    def init_map(self):
        self.map_view.setHtml("""
            <!DOCTYPE html>
            <html>
            <head>
                <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css"/>
                <style>#map{position:absolute;top:0;bottom:0;left:0;right:0;}</style>
            </head>
            <body>
                <div id="map"></div>
                <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
                <script>
                    var map = L.map('map', {worldCopyJump: true}).setView([0, 0], 2);
                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
                    
                    var observerMarker = null;
                    var satelliteMarker = null;
                    var sunMarker = null;
                    var moonMarker = null;
                    var satellitePath = L.polyline([], {color: 'red'}).addTo(map);
                </script>
            </body>
            </html>
        """)

    def _update_board_ui(self):
        current_board = self.board_type_combo.currentText()
        board_info = self.board_manager.boards.get(current_board, {})
        protocol = board_info.get("protocol", "UART")
        if protocol == "UART":
            self.port_label.setText("Serial Port:")
            self.baud_rate_input.show()
            self.baud_rate_label.show()
        else:
            self.port_label.setText(f"{protocol} Address/Bus:")
            self.baud_rate_input.hide()
            self.baud_rate_label.hide()

    def test_board_connection(self):
        try:
            port = self.port_input.text().strip()
            if not port:
                raise ValueError("Please enter a port (e.g., /dev/ttyUSB0 or COM3)")

            board_key = self.board_type_combo.currentText()
            if board_key not in self.board_manager.boards:
                raise KeyError(f"Invalid board type: {board_key}")


            baud_text = self.baud_rate_input.text().strip()
            baud = int(baud_text) if self.baud_rate_input.isVisible() and baud_text else 9600
            if baud <= 0 or baud > 500000:
                raise ValueError(f"Invalid baud rate: {baud_text} (must be 1-500000)")

            success = self.board_manager.connect(port, {'baud_rate': baud}, board_key)
            color = "#28a745" if success else "#dc3545"
            self.connection_status.setStyleSheet(f"border-radius: 12px; background-color: {color}; border: 2px solid #404040;")
            
            if not success:
                self.show_error(f"Connection failed to {port} at {baud} baud (board: {board_key}). Check device connection.")

        except (KeyError, ValueError) as e:
            error_msg = str(e)
            self.show_error(error_msg)
            self.connection_status.setStyleSheet("border-radius: 12px; background-color: #dc3545; border: 2px solid #404040;")
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.show_error(error_msg)
            self.connection_status.setStyleSheet("border-radius: 12px; background-color: #dc3545; border: 2px solid #404040;")
            logger.error(f"Test connection error: {error_msg}")

    def start_tracking(self):
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        try:
            city = self.city_input.text().strip()
            if not city: raise ValueError("Please enter a city")
            sat_name = self.sat_name_input.text().strip()
            if not sat_name: raise ValueError("Please select a satellite")
            if sat_name not in self.satellites: raise ValueError("Satellite not found")
            lat, lng = self.api.get_geolocation(city)
            if lat is None: raise ValueError("Invalid city - check spelling")
            alt = float(self.alt_input.text() or 0)
            
            self.observer_values['latitude'].setText(f"{lat:.4f}°")
            self.observer_values['longitude'].setText(f"{lng:.4f}°")
            self.observer_values['altitude_km'].setText(f"{alt/1000:.2f}")
            self.observer_values['altitude_mi'].setText(f"{alt*0.000621371:.2f}")
            self.observer_values['local_time'].setText(datetime.now().strftime("%H:%M:%S"))

            self.worker = TrackingWorker(self.api, self.data_manager, {
                'sat_id': self.satellites[sat_name], 'sat_name': sat_name,
                'obs_lat': lat, 'obs_lng': lng, 'obs_alt': alt,
                'interval': int(self.interval_input.text())
            })
            self.worker.data_ready.connect(self.update_satellite_data)
            self.worker.error_occurred.connect(self.show_error)
            self.worker.start()
            
            # Initial Observer Marker placement
            self.map_view.page().runJavaScript(f"""
                if (observerMarker) map.removeLayer(observerMarker);
                observerMarker = L.marker([{lat}, {lng}], {{
                    icon: L.icon({{
                        iconUrl: 'https://cdn-icons-png.flaticon.com/512/447/447031.png',
                        iconSize: [22, 22]
                    }})
                }}).addTo(map);
                map.setView([{lat}, {lng}], 4);
            """)
        except Exception as e:
            self.show_error(str(e))

    def update_satellite_data(self, data):
        # Update Text Labels
        self.satellite_values['azimuth'].setText(f"{data['azimuth']}°")
        self.satellite_values['elevation'].setText(f"{data['elevation']}°")
        self.satellite_values['speed_kms'].setText(f"{data['speed_kms']:.2f}")
        self.satellite_values['speed_mis'].setText(f"{data['speed_mis']:.2f}")
        self.satellite_values['sat_alt_km'].setText(f"{data['sataltitude']:.2f}")
        self.satellite_values['sat_alt_mi'].setText(f"{data['sataltitude']*0.621:.2f}")
        self.satellite_values['ra'].setText(f"{data['ra']}°")
        self.satellite_values['dec'].setText(f"{data['dec']}°")
        self.satellite_values['lst'].setText(f"{data['lst']}h")
        self.satellite_values['period'].setText(f"{data['period']}")
        self.satellite_values['eclipsed'].setText("Yes" if data['eclipsed'] else "No")
        
        now = datetime.now()
        self.observer_values['local_time'].setText(now.strftime("%H:%M:%S"))
        self.observer_values['utc'].setText(datetime.now(timezone.utc).strftime("%H:%M:%S"))
        self.observer_values['timezone'].setText(str(datetime.now().astimezone().tzname()))

        sun_lat, sun_lng = CelestialCalculator.sun_position(datetime.now(timezone.utc))
        moon_lat, moon_lng = CelestialCalculator.moon_position(datetime.now(timezone.utc))
        
        # Update Map Markers using exact icons from original file
        self.map_view.page().runJavaScript(f"""
            if (satelliteMarker) map.removeLayer(satelliteMarker);
            satelliteMarker = L.marker([{data['satlatitude']}, {data['satlongitude']}], {{
                icon: L.icon({{
                    iconUrl: 'https://cdn-icons-png.flaticon.com/512/1062/1062195.png',
                    iconSize: [32, 32]
                }})
            }}).addTo(map);
            satellitePath.addLatLng([{data['satlatitude']}, {data['satlongitude']}]);
            
            if (sunMarker) map.removeLayer(sunMarker);
            sunMarker = L.marker([{sun_lat}, {sun_lng}], {{
                icon: L.icon({{
                    iconUrl: 'https://cdn-icons-png.flaticon.com/512/979/979534.png',
                    iconSize: [32, 32]
                }})
            }}).addTo(map);
            
            if (moonMarker) map.removeLayer(moonMarker);
            moonMarker = L.marker([{moon_lat}, {moon_lng}], {{
                icon: L.icon({{
                    iconUrl: 'https://cdn-icons-png.flaticon.com/512/9689/9689800.png',
                    iconSize: [32, 32]
                }})
            }}).addTo(map);
        """)
        self.board_manager.send_data(data)

    def stop_tracking(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self.worker:
            self.worker.stop()
            self.worker = None

    def filter_satellites(self):
        text = self.sat_name_input.text().lower()
        self.sat_list.clear()
        if text:
            self.sat_list.setVisible(True)
            for name in self.satellites:
                if text in name.lower(): self.sat_list.addItem(name)
        else:
            self.sat_list.setVisible(False)

    def select_satellite(self, item):
        self.sat_name_input.setText(item.text())
        self.sat_list.setVisible(False)

    def show_error(self, message):
        cursor = self.error_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.tab_widget.setCurrentIndex(0)

    def show_logging_diagnostics(self):
        dialog = LoggingVerificationDialog(self.log_file, self)
        dialog.exec_()

    def update_log_display(self):
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if content != self.log_display.toPlainText():
                    self.log_display.setPlainText(content)
                    self.log_display.moveCursor(QTextCursor.End)
        except: pass

    def update_memory_display(self):
        try:
            import psutil
            process = psutil.Process(os.getpid())
            sys_mem = psutil.virtual_memory()
            self.memory_labels['process_rss'].setText(f"Process Memory (RSS): {process.memory_info().rss/1024/1024:.1f} MB")
            self.memory_labels['process_percent'].setText(f"Process Memory (%): {process.memory_percent():.1f}%")
            self.memory_labels['system_available'].setText(f"System Available: {sys_mem.available/1024/1024:.1f} MB")
            self.memory_labels['system_used'].setText(f"System Used: {sys_mem.used/1024/1024:.1f} MB")
        except: pass