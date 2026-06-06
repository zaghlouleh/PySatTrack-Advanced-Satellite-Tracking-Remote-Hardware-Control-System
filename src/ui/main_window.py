# -*- coding: utf-8 -*-
import os
import json
import socket
import time
import requests
import math
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
                             QSplitter, QLineEdit, QPushButton,
                             QGroupBox, QComboBox, QLabel, QApplication, QMessageBox,
                             QSizePolicy, QCompleter, QTextEdit, QTabWidget)

from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QUrl, QMetaObject, Q_ARG, pyqtSignal, QStringListModel
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from PyQt5.QtWebChannel import QWebChannel

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
from src.managers.hardware_bridge_client import HardwareBridgeClient


import ipaddress
from src.managers.background_manager import BackgroundManager
from src.managers.tle_sync_manager import TleSyncManager
from src.core.engine import OrbitEngine
from src.core.tracking_worker import TrackingWorker
from src.core.prediction_worker import PredictionWorker

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MainWindow(QMainWindow):
    sig_update_sat_list = pyqtSignal(dict)

    def create_board_config_fields(self, parent_layout: QVBoxLayout, title: str,
                                     temp_manager: Any = None,
                                     default_board: Optional[str] = None) -> None:
        """Create UI fields for a board profile.

        This project (v5 UI) previously had RF/Sensor controls embedded directly.
        These fields are a lightweight, functional replacement that wires into
        HardwareManager where possible.
        """
        container = QGroupBox(title)
        container_layout = QGridLayout(container)
        # Increase spacing *below the title* (inside the group box).
        # Margins push the first row away from the title.
        container_layout.setContentsMargins(12, 18, 12, 12)
        # Extra spacing between the grid items
        container_layout.setHorizontalSpacing(12)
        container_layout.setVerticalSpacing(10)


        board_combo = QComboBox()
        board_combo.addItems(["Select Board..."] + sorted(self.hw_manager.BOARDS.keys()))
        if default_board and default_board in self.hw_manager.BOARDS:
            board_combo.setCurrentText(default_board)

        port_combo = QComboBox()
        port_combo.addItems(self.hw_manager.get_available_ports())

        baud_input = QLineEdit("115200")
        baud_input.setMaximumWidth(140)

        # Bottom control button: explicitly checks current connection state.
        btn_check_connection = QPushButton("Check Connection")
        btn_check_connection.setEnabled(True)
        btn_check_connection.setMinimumWidth(180)
        btn_check_connection.setStyleSheet(
            "QPushButton { background-color: #1B5E20; color: white; font-weight: bold; border-radius: 6px; }"
            "QPushButton:disabled { background-color: #555; color: #ddd; }"
        )

        def _refresh_ports():
            port_combo.clear()
            port_combo.addItems(self.hw_manager.get_available_ports())

        def _toggle_buttons(connected: bool):
            # Keep LED + label + toggle in sync
            # Keep UI professional: do NOT display the literal word "disconnect".
            # Toggle button shows current state + the available action.
            # LED + status text updated by _set_tab_led.
            _set_tab_led(connected)


        btn_refresh_ports = QPushButton("Refresh")
        btn_refresh_ports.clicked.connect(_refresh_ports)

        def _check_connection_clicked():
            # If already connected, just refresh the UI indicators.
            if bool(getattr(self.hw_manager, "connection", None)):
                _toggle_buttons(True)
                return

            # Otherwise attempt to connect using current selections.
            board = board_combo.currentText()
            port = port_combo.currentText()
            if not port or board.startswith("Select"):
                self.log_panel.append_error(f"{title}: Select a board and a port first.")
                return

            ok, msg = self.hw_manager.connect(
                port, board, baud=int(baud_input.text() or "115200"))
            if ok:
                self.log_panel.append_success(f"{title}: {msg}")
            else:
                self.log_panel.append_error(f"{title}: {msg}")
            _toggle_buttons(ok)


        btn_check_connection.clicked.connect(_check_connection_clicked)

        container_layout.addWidget(QLabel("Board:"), 0, 0)
        container_layout.addWidget(board_combo, 0, 1, 1, 2)
        container_layout.addWidget(QLabel("Port:"), 1, 0)
        container_layout.addWidget(port_combo, 1, 1)
        container_layout.addWidget(btn_refresh_ports, 1, 2)
        container_layout.addWidget(QLabel("Baud:"), 2, 0)
        container_layout.addWidget(baud_input, 2, 1)
        container_layout.addWidget(QLabel(""), 2, 2)

        # --- Per-tab connection status indicator (LED) + embedded control ---
        status_led = QLabel()

        status_led.setFixedSize(20, 20)
        status_led.setStyleSheet("border-radius: 10px; background-color: gray;")

        status_led_label = QLabel("")
        status_led_label.setMinimumWidth(140)

        def _set_tab_led(connected: bool):
            color = "#00cc00" if connected else "#cc0000"  # Green/Red
            status_led.setStyleSheet(
                f"border-radius: 10px; background-color: {color};")
            status_led_label.setText("Connected" if connected else "Disconnected")


        # Initialize based on current HW state
        _set_tab_led(bool(getattr(self.hw_manager, "connection", None)))

        # Status label uses Connected vs blank for disconnected (LED logic retained).


        # Keep references for MainWindow to update independently
        if "SENSOR" in title.upper():
            self.sensor_status_led = status_led
            self.sensor_status_led_label = status_led_label
        elif "RF" in title.upper():
            self.rf_status_led = status_led
            self.rf_status_led_label = status_led_label

        # Render inside the tab group (LED + status text alongside it)
        container_layout.addWidget(QLabel("Status:"), 6, 0)
        container_layout.addWidget(status_led, 6, 1, Qt.AlignLeft)
        container_layout.addWidget(status_led_label, 6, 2)

        # Bottom: single button to check current connection
        container_layout.addWidget(btn_check_connection, 7, 0, 1, 4, Qt.AlignBottom)


        # RF switch: no manual channel selection. Channel selection is automated
        # in controller code via HardwareManager.auto_select_rf_channel.

        if "RF" in title.upper():

            def _auto_select_now():
                # Prevent UI blocking: run selection in a background thread.
                def task():
                    try:
                        ok, msg, ch = self.hw_manager.auto_select_rf_channel()
                        text = msg
                        if ok and ch is not None:
                            text = f"RF switch: auto-selected channel {ch}."
                        QMetaObject.invokeMethod(
                            self,
                            "_update_rf_auto_status",
                            Qt.QueuedConnection,
                            Q_ARG(str, text),
                        )
                        if ok:
                            self.log_panel.append_success(text)
                        else:
                            self.log_panel.append_error(msg)
                    except Exception as exc:
                        err_text = f"RF auto-select failed: {exc}"
                        QMetaObject.invokeMethod(
                            self,
                            "_update_rf_auto_status",
                            Qt.QueuedConnection,
                            Q_ARG(str, err_text),
                        )
                        self.log_panel.append_error(f"RF auto-select exception: {exc}")

                threading.Thread(target=task, daemon=True).start()


            # Store function for later triggers (connect/start)
            self._rf_auto_select_now = _auto_select_now

            # Kick off once on UI creation if already connected
            if bool(getattr(self.hw_manager, "connection", None)):
                _auto_select_now()

            # When hardware connects later, re-run auto-selection.
            try:
                self.hw_manager.connection_changed.connect(
                    lambda connected, _msg: self._rf_auto_select_now() if connected else None
                )
            except Exception:
                pass

        parent_layout.addWidget(container)

    def create_bridge_config_fields(self, parent_layout: QVBoxLayout) -> None:
        """Create UI fields for controlling the hardware bridge server."""
        container = QGroupBox("Bridge")
        layout = QGridLayout(container)

        btn_start = QPushButton("Start Bridge Server")
        btn_stop = QPushButton("Stop Bridge Server")
        btn_stop.setEnabled(False)


        # --- Bridge tab independent status indicator (LED) ---
        self.bridge_status_led = QLabel()
        self.bridge_status_led.setFixedSize(20, 20)
        self.bridge_status_label = QLabel("")

        self.bridge_status_led.setStyleSheet("border-radius: 10px; background-color: gray;")

        def _update_bridge_status_ui(connected: bool, message: str):
            self.bridge_status_label.setText(message)
            if connected:
                color = "#00cc00"  # Green
                btn_start.setEnabled(False)
                btn_stop.setEnabled(True)
            else:
                color = "#cc0000"  # Red
                btn_start.setEnabled(True)
                btn_stop.setEnabled(False)
            self.bridge_status_led.setStyleSheet(
                f"border-radius: 10px; background-color: {color};")

        def _set_status(running: bool):
            # Keep the old text status too (doesn't affect LED behavior)
            _update_bridge_status_ui(running, "Connected" if running else "Offline")


        # --- Bridge server network inputs (IP + Port) ---
        self.bridge_ip_input = QLineEdit("127.0.0.1")
        self.bridge_ip_input.setMaximumWidth(160)

        self.bridge_port_input = QLineEdit("5000")
        self.bridge_port_input.setMaximumWidth(100)

        layout.addWidget(QLabel("IP:"), 1, 0)
        layout.addWidget(self.bridge_ip_input, 1, 1)
        layout.addWidget(QLabel("Port:"), 2, 0)
        layout.addWidget(self.bridge_port_input, 2, 1)

        def _validated_bridge_endpoint() -> tuple[bool, str, str, int]:
            ip_str = (self.bridge_ip_input.text() or "").strip()
            port_raw = (self.bridge_port_input.text() or "").strip()

            if not ip_str:
                return False, "Bridge IP is required.", "", 0

            try:
                ipaddress.ip_address(ip_str)
            except ValueError:
                return False, f"Invalid Bridge IP: {ip_str}", "", 0

            if not port_raw.isdigit():
                return False, "Bridge port must be a number.", "", 0

            port = int(port_raw)
            if port < 1 or port > 65535:
                return False, "Bridge port must be between 1 and 65535.", "", 0

            return True, "", ip_str, port

        def _start():
            ok_ep, ep_msg, ip_str, port = _validated_bridge_endpoint()
            if not ok_ep:
                self.log_panel.append_error(f"Bridge: {ep_msg}")
                _set_status(False)
                return

            # Start local socket server background thread inside HardwareManager
            ok_srv, srv_msg = self.hw_manager.start_bridge_server(ip_str, port)
            if ok_srv:
                self.log_panel.append_success(f"Bridge Server: {srv_msg}")
            else:
                self.log_panel.append_error(f"Bridge Server error: {srv_msg}")

            # Connect client directly to server loopback
            ok, msg = self.hardware_bridge_client.connect(ip_str, port)
            if ok:
                self.hardware_bridge_connected = True
                self.log_panel.append_success(f"TCP Bridge Client: {msg}")
                _set_status(True)
            else:
                self.hardware_bridge_connected = False
                self.log_panel.append_error(f"TCP Bridge Client: {msg}")
                _set_status(False)


        def _stop():
            self.hardware_bridge_client.disconnect()
            self.hw_manager.stop_bridge_server()
            self.hardware_bridge_connected = False
            _set_status(False)
            self.log_panel.append_success("TCP Bridge: Client and Server Stopped.")


        btn_start.clicked.connect(_start)
        btn_stop.clicked.connect(_stop)

        layout.addWidget(btn_start, 4, 0)
        layout.addWidget(btn_stop, 4, 1)

        # LED shown directly within the Bridge tab group
        layout.addWidget(QLabel("Status:"), 3, 0)
        layout.addWidget(self.bridge_status_led, 3, 1, Qt.AlignLeft)
        layout.addWidget(self.bridge_status_label, 3, 1, 1, 1, Qt.AlignCenter)

        # Connect launcher command button to setup layout
        btn_diagnostics = QPushButton("Open Diagnostics Dashboard")
        btn_diagnostics.setStyleSheet(
            "QPushButton { background-color: #0D47A1; color: white; font-weight: bold; border-radius: 6px; min-height: 28px; }"
            "QPushButton:hover { background-color: #1565C0; }"
        )
        btn_diagnostics.clicked.connect(self.open_diagnostics_window)
        layout.addWidget(btn_diagnostics, 5, 0, 1, 2)

        parent_layout.addWidget(container)

    def open_diagnostics_window(self):
        """Dynamic launcher for diagnostics window (avoids circular imports)."""
        try:
            from src.ui.hardware_diagnostics_window import HardwareDiagnosticsWindow
            if not hasattr(self, "_diagnostics_win") or self._diagnostics_win is None:
                self._diagnostics_win = HardwareDiagnosticsWindow()
            self._diagnostics_win.show()
            self._diagnostics_win.raise_()
            self._diagnostics_win.activateWindow()
            self.log_panel.append_success("Opened Hardware Diagnostics Dashboard.")
        except Exception as e:
            self.log_panel.append_error(f"Failed to open Hardware Diagnostics: {e}")
            logger.exception("Error opening Hardware Diagnostics:")

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
        self.hardware_bridge_client = HardwareBridgeClient()
        self.hardware_bridge_connected = False

        self.bg_manager = BackgroundManager()
        self.engine = OrbitEngine()
        self.tle_sync_manager = None

        # 3. UI Construction
        self.setup_ui()
        self.setup_clients()

        if self.st_client:
            self.tle_sync_manager = TleSyncManager(self.data_manager, self.st_client)

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
        self.obs_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

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
        self.hw_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Build left panel: Observer view on top with a nested row of tabs
        self.left_tabs = QTabWidget()

        # Observer tab (top) containing the observer controls.
        # Hardware controls now live in the dedicated control_tab_widget below.
        self.obs_group.setMaximumHeight(160)
        obs_tab = QWidget()
        obs_tab_layout = QVBoxLayout(obs_tab)
        obs_tab_layout.setContentsMargins(4, 4, 4, 4)
        obs_tab_layout.setSpacing(8)
        obs_tab_layout.addWidget(self.obs_group)

        # Add top-level tabs
        self.left_tabs.addTab(obs_tab, "Observer")


        # ---------- Additional Hardware Config Tabs (per requested layout) ----------
        self.control_tab_widget = QTabWidget()

        # Container for sensor/antenna hardware config
        antenna_hw_widget = QWidget()
        antenna_hw_layout = QVBoxLayout(antenna_hw_widget)

        # Temperature manager placeholder: in this v5 UI we don't have a dedicated one.
        # Keeping signature compatibility for the requested layout.
        temp_manager = None

        antenna_hw_layout.addStretch(1)
        self.control_tab_widget.addTab(antenna_hw_widget, "Sensor HW")
        self.create_board_config_fields(
            antenna_hw_layout,
            "Sensor Controller",
            temp_manager,
            default_board="Arduino",
        )
        
        # RF Switch tab (layout fix: pass layout, not widget)
        rf_switch_hw_widget = QWidget()
        rf_switch_hw_layout = QVBoxLayout(rf_switch_hw_widget)
        self.create_board_config_fields(
            rf_switch_hw_layout,
            "RF Switch",
            temp_manager,
            default_board="ESP32/NodeMCU",
        )
        rf_switch_hw_layout.addStretch(1)
        self.control_tab_widget.addTab(rf_switch_hw_widget, "RF Switch HW")

        # Bridge tab
        bridge_widget = QWidget()
        bridge_layout = QVBoxLayout(bridge_widget)
        self.create_bridge_config_fields(bridge_layout)

        # Compatibility: sensor telemetry + RF status references used elsewhere in v5
        # (signals expect these attrs to exist).
        self.sensor_status_label = QLabel("No sensor telemetry.")
        self.rf_status_label = QLabel("Channel control idle.")
        self.rf_status_label.setStyleSheet("color: #FFD54F;")

        # Network references for refresh_network_info()
        self.network_status_label = QLabel("Network status unavailable.")
        self.network_ip_label = QLabel("IP: --")

        bridge_layout.addStretch(1)
        self.control_tab_widget.addTab(bridge_widget, "Bridge")

        # Add the control tabs under observer tab (stacked vertically)
        top_controls_layout = QVBoxLayout()
        top_controls_layout.addWidget(self.control_tab_widget)

        # Replace left tabs with a vertical container: keep Observer + controls.
        observer_controls_container = QWidget()
        observer_controls_layout = QVBoxLayout(observer_controls_container)
        observer_controls_layout.setContentsMargins(0, 0, 0, 0)
        observer_controls_layout.setSpacing(6)
        observer_controls_layout.addWidget(self.left_tabs)
        observer_controls_layout.addLayout(top_controls_layout)

        # Remove the old direct add and add the new container
        left_layout.addWidget(observer_controls_container)


        # 8. Engagement Buttons
        self.start_btn = QPushButton("Start Tracking")
        self.start_btn.setStyleSheet(
            "background-color: #1B5E20; color: white; height: 50px; font-weight: bold;")
        self.start_btn.clicked.connect(self.start_tracking)
        self.stop_btn = QPushButton("Stop Tracking")
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
        self._bind_hw_signals()
        self.refresh_network_info()

    def _update_rf_auto_status(self, text: str):
        if hasattr(self, "_rf_status_label") and self._rf_status_label is not None:
            self._rf_status_label.setText(text)

    def _bind_hw_signals(self):
        self.hw_manager.arduino_data_received.connect(self._update_sensor_data)
        self.hw_manager.connection_changed.connect(self._set_hardware_status)


        # Update per-tab LEDs independently (Sensor HW / RF Switch HW)
        def _update_tab_leds(connected: bool, _message: str):
            if hasattr(self, "sensor_status_led"):
                self.sensor_status_led.setStyleSheet(
                    f"border-radius: 10px; background-color: {'#00cc00' if connected else '#cc0000'};")
            if hasattr(self, "sensor_status_led_label"):
                self.sensor_status_led_label.setText(
                    "Connected" if connected else "Disconnected")


            if hasattr(self, "rf_status_led"):
                self.rf_status_led.setStyleSheet(
                    f"border-radius: 10px; background-color: {'#00cc00' if connected else '#cc0000'};")
                if hasattr(self, "rf_status_led_label"):
                    self.rf_status_led_label.setText(
                        "Connected" if connected else "Disconnected")



        self.hw_manager.connection_changed.connect(_update_tab_leds)


    def _set_hardware_status(self, connected: bool, message: str):
        if connected:
            self.sensor_status_label.setText(f"Hardware connected: {message}")
            self.rf_status_label.setText("Ready for RF channel selection.")
        else:
            self.sensor_status_label.setText("Hardware disconnected.")
            self.rf_status_label.setText("Channel control idle.")

    def refresh_network_info(self):
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            self.network_status_label.setText("Network interface active.")
            self.network_ip_label.setText(f"IP: {ip}")
        except Exception as exc:
            self.network_status_label.setText("Network lookup failed.")
            self.network_ip_label.setText("IP: --")
            self.log_panel.append_error(f"Network error: {exc}")

    def _update_sensor_data(self, data: dict):
        self.sensor_status_label.setText("Arduino telemetry received.")
        self.sensor_data_display.append(json.dumps(data, indent=2))
        self.sensor_data_display.moveCursor(QTextCursor.End)

    def set_rf_channel(self):
        channel = int(self.rf_channel_selector.currentText())
        success, msg = self.hw_manager.select_rf_channel(channel)
        self.rf_status_label.setText(msg)
        if not success:
            self.log_panel.append_error(f"RF Error: {msg}")

    def _toggle_ap_mode(self):
        # Toggle AP mode via HardwareManager placeholder
        if self.btn_toggle_ap.text().startswith("Enable"):
            ok, msg = self.hw_manager.start_ap_mode()
            if ok:
                self.adv_ap_status.setText(f"AP Mode: enabled")
                self.btn_toggle_ap.setText("Disable AP Mode")
            else:
                self.log_panel.append_error(f"AP Error: {msg}")
        else:
            ok, msg = self.hw_manager.stop_ap_mode()
            if ok:
                self.adv_ap_status.setText(f"AP Mode: disabled")
                self.btn_toggle_ap.setText("Enable AP Mode")
            else:
                self.log_panel.append_error(f"AP Error: {msg}")

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
            self.log_panel.append_error("Geocode: City name is required.")
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
            try:
                alt_m = float(self.alt_input.text())
            except Exception:
                self.log_panel.append_error(
                    f"Observer Error: Invalid altitude '{self.alt_input.text()}'.");
                alt_m = 0.0

            tz = datetime.now().astimezone().tzname() or "UTC"
            self.telemetry_panel.update_observer(lat, lng, alt_m, tz)

            if self.map_js_ready:
                self.map_bridge.update_observer_position.emit(lat, lng)
                self.map_bridge.set_map_view.emit(lat, lng, 4)
                self.update_celestial_positions()

            self.log_panel.append_success(f"Observer established for '{city}'.")
            logger.info(f"Station established at {city}.")
        else:
            self.log_panel.append_error(
                f"Geocode Error: Could not resolve '{city}'. Check spelling or enable network.")

    def show_source_dialog(self):
        last = self.load_source_settings()
        dialog = SourceSelectionDialog(DEFAULT_TLE_SOURCES, last, self)
        selected = dialog.get_selected_sources()
        if selected:
            # Login Gatekeeper on Main Thread (Thread Safety)
            if any(DEFAULT_TLE_SOURCES[s].get('auth_required') == 'space-track' for s in selected):
                if not self.st_client._client:
                    login = LoginDialog(
                        "Space Track", "https://www.space-track.org/auth/createAccount", parent=self)
                    creds = login.get_credentials()
                    if creds:
                        ok = self.st_client.authenticate(
                            creds['username'],
                            creds['password'],
                        )
                        if not ok:
                            self.log_panel.append_error(
                                "Space-Track login failed (invalid credentials or blocked request)."
                            )
                            QMessageBox.warning(
                                self,
                                "Space-Track Login Failed",
                                "Login failed. Verify your username/password and try again.",
                            )
                            return
                    else:
                        return


            self.save_source_settings(selected)
            self.sync_btn.setEnabled(False)
            threading.Thread(target=self._run_sync,
                             args=(selected,), daemon=True).start()

    def _run_sync(self, sources):
        new_data = {}
        if self.tle_sync_manager:
            filepaths = self.tle_sync_manager.download_sources(sources)
            for save_path in filepaths:
                self._merge_satellite_data(new_data, self.engine.parse_tle_file(save_path))
        else:
            for key in sources:
                info = DEFAULT_TLE_SOURCES[key]
                save_path = self.data_manager.get_tle_path(info['filename'])
                if info.get('auth_required') == 'space-track':
                    lines = self.st_client.get_gp_data(
                        info['query_class'], info.get('query_filters', {}))
                    if lines:
                        with open(save_path, 'w', encoding='utf-8') as f:
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
                        except Exception:
                            continue
        self.sig_update_sat_list.emit(new_data)

    @pyqtSlot(dict)
    def _finalize_sync(self, new_sats):
        self.satellites.update(new_sats)
        self.load_tles_from_disk()
        self.sync_btn.setEnabled(True)
        self.log_panel.append_success(
            f"Sync Complete: Database updated with {len(new_sats):,} objects.")
        # QMessageBox retained for visibility, but Problems tab is the primary UX.
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

    def _run_js(self, command: str):
        """Safely executes a JavaScript instruction within the map's WebEngine layout."""
        if (hasattr(self, 'map_js_ready') and self.map_js_ready and 
                hasattr(self, 'map_view') and isinstance(self.map_view, QWebEngineView)):
            try:
                self.map_view.page().runJavaScript(command)
            except Exception as e:
                logger.error(f"MainWindow: JS execution failed: {e}")

    def clear_all_satellite_visuals(self):
        """Clears all map and UI visual indicators from previous tracking sessions."""
        logger.info("MainWindow: Clearing previous tracking visual indicators.")
        
        # 1. Clear Map Elements via Bridge Signals
        if self.map_js_ready and hasattr(self, 'map_bridge'):
            # Clear the satellite marker and visibility footprint
            self.map_bridge.clear_satellite_data.emit()
            # Clear the live tracking ground trail
            self.map_bridge.clear_track_steps.emit()
            # Clear future orbit segments (red dashed line)
            self.map_bridge.draw_orbit_path.emit([])
            # Clear upcoming pass segments (solid blue line)
            self.map_bridge.highlight_visible_pass.emit([])
        
        # 2. Reset Telemetry Labels on the Right Panel
        self.telemetry_panel.update_telemetry({
            'speed_kms': '---',
            'speed_mis_s': '---',
            'sataltitude': '---',
            'azimuth': '---',
            'elevation': '---',
            'ra': '---',
            'dec': '---',
            'lst': '---',
            'period_tle_calculated_min': '---',
            'eclipsed': False
        })
        
        # 3. Reset Local Pass Data
        self.last_pass_data = {}

    def start_tracking(self):
        if not self.selected_sat_name:
            self.log_panel.append_error("Start Tracking: Select a satellite first.")
            return

        sat = next((s for s in self.satellites.values()
                   if s['name'] == self.selected_sat_name), None)
        if not sat:
            self.log_panel.append_error(
                f"Start Tracking: Satellite '{self.selected_sat_name}' not found in database.")
            return

        # 1. Observer Altitude & Interval Validation
        try:
            alt_m = float(self.alt_input.text())
        except Exception:
            self.log_panel.append_error(
                f"Start Tracking: Invalid altitude '{self.alt_input.text()}'.")
            return

        try:
            interval_s = int(self.poll_rate.currentText())
        except Exception:
            self.log_panel.append_error("Start Tracking: Poll rate must be a number.")
            return

        # 2. Automated GPS Telemetry Check (TCP Hardware Bridge Parity)
        if (hasattr(self, "hardware_bridge_client") and 
                self.hardware_bridge_client is not None and 
                getattr(self.hardware_bridge_client, "is_connected", False)):
            
            gps_status = self.hardware_bridge_client.get_gps_status()
            if gps_status and gps_status.get("gpsLock"):
                try:
                    self.lat_station = float(gps_status.get("lat"))
                    self.lng_station = float(gps_status.get("lon"))
                    alt_m = float(gps_status.get("alt", alt_m))
                    tz = datetime.now().astimezone().tzname() or "UTC"
                    
                    self.telemetry_panel.update_observer(self.lat_station, self.lng_station, alt_m, tz)
                    if self.map_js_ready:
                        self.map_bridge.update_observer_position.emit(self.lat_station, self.lng_station)
                        self.map_bridge.set_map_view.emit(self.lat_station, self.lng_station, 4)
                        
                    self.log_panel.append_success("Observer updated automatically via GPS Lock.")
                except Exception as exc:
                    self.log_panel.append_error(f"GPS status parsing failed, falling back to manual: {exc}")

        # 3. Observer Location Verification
        if self.lat_station == 0.0 and self.lng_station == 0.0:
            self.log_panel.append_error("Start Tracking: Establish the observer (city) first.")
            return

        obs = {'lat': self.lat_station, 'lng': self.lng_station,
               'alt': alt_m, 'interval': interval_s}

        # 4. Map & Celestial Refresh
        if self.map_js_ready:
            self.map_bridge.clear_satellite_data.emit()
            self.update_celestial_positions()

        # 5. Terminate Previous Prediction Tasks
        if self.active_prediction_worker:
            self.active_prediction_worker.terminate()
            self.active_prediction_worker.wait()

        self.active_prediction_worker = PredictionWorker(
            sat, obs['lat'], obs['lng'], obs['alt'])
        self.active_prediction_worker.prediction_ready.connect(
            self.on_prediction_complete)
        self.active_prediction_worker.start()

        # 6. Terminate Previous Live Polling Tasks
        if self.active_tracking_worker:
            self.active_tracking_worker.stop()
            self.active_tracking_worker.wait()

        # 7. Dynamic RF Switch Channel Selection (Accounting for Variable Capacities)
        channel_count = self.hw_manager.get_rf_channel_count()
        target_channel = channel_count  # Default fallback to Aux/Test (last channel)
        
        upper_sat_name = sat['name'].upper()
        if 'NOAA' in upper_sat_name:
            target_channel = 1
        elif 'ISS (ZARYA)' in upper_sat_name:
            target_channel = 2
        elif 'GOES' in upper_sat_name:
            target_channel = 7

        # Dynamically clamp target channel to current physical switch capacity
        target_channel = max(1, min(target_channel, channel_count))

        # A. Command RF Switch via TCP Bridge Client
        if self.hardware_bridge_connected:
            try:
                self.hardware_bridge_client.send_rf_channel(device_id='RFSwitch', channel=target_channel)
                self.log_panel.append_success(f"Bridge RF Switch: Routing to channel {target_channel} of {channel_count}")
            except Exception as exc:
                self.log_panel.append_error(f"TCP RF channel command failed: {exc}")

        # B. Fallback to Local Hardware Manager (Serial/GPIO)
        if self.hw_manager.is_rf_switch_online() or self.hw_manager.connection:
            try:
                success, msg = self.hw_manager.select_rf_channel(target_channel)
                if success:
                    self.log_panel.append_success(f"Local RF Switch: Routed to channel {target_channel} of {channel_count}")
                else:
                    self.log_panel.append_error(f"Local RF Switch Error: {msg}")
            except Exception as exc:
                self.log_panel.append_error(f"Local RF Switch execution failed: {exc}")

        # 8. Start Telemetry Collector Thread
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
        
        self.log_panel.append_success(
            f"Start Tracking: '{sat['name']}' tracking started successfully.")

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_tracking(self):
        if self.active_tracking_worker:
            try:
                self.active_tracking_worker.stop()
                self.log_panel.append_success("Stop Tracking: Tracking stopped.")
            except Exception as exc:
                self.log_panel.append_error(f"Stop Tracking: {exc}")
        else:
            self.log_panel.append_error("Stop Tracking: Tracking is not running.")

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def on_telemetry(self, data):
        self.telemetry_panel.update_telemetry(data)
        
        # Forward live SGP4 & SatNOGS frequency telemetry to the HardwareManager
        if hasattr(self, "hw_manager") and self.hw_manager is not None:
            self.hw_manager.update_tracking_telemetry(data)
            
        # Sync real-time metrics to the Leaflet map's floating UI card
        if self.map_js_ready:
            live_data_payload = {
                "elevation": data.get('elevation', 0.0),
                "azimuth": data.get('azimuth', 0.0),
                "altitude": data.get('sataltitude', 0.0),
                "speed": data.get('speed_kms', 0.0),
                "visibility": "Visible" if data.get('elevation', 0.0) > 0 else "Not Visible"
            }
            self._run_js(f"updateLiveData({json.dumps(live_data_payload)})")
                
        # Optional parity with legacy PySatTrack.py:
        if self.hardware_bridge_connected:
            try:
                self.hardware_bridge_client.send_antenna_position(
                    device_id='AntennaController',
                    az=float(data['azimuth']),
                    el=float(data['elevation']),
                )
            except Exception as exc:
                self.log_panel.append_error(f"TCP antenna position send failed: {exc}")

        # Existing local hardware fallback (serial/GPIO)
        if self.hw_manager.connection:
            ok = self.hw_manager.send_telemetry(data['azimuth'], data['elevation'])
            if ok is False:
                self.log_panel.append_error("Hardware telemetry send failed.")


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
        
        # Center initially
        self.map_bridge.set_map_view.emit(0, 0, 2)
        
        # Restore Parity: If ground station coordinates are set, render them
        if self.lat_station != 0.0 or self.lng_station != 0.0:
            logger.info(f"Main: Syncing startup station coordinates to map: {self.lat_station}, {self.lng_station}")
            self.map_bridge.update_observer_position.emit(self.lat_station, self.lng_station)
            self.map_bridge.set_map_view.emit(self.lat_station, self.lng_station, 4)
            
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
        get_time = datetime.now()
        lt, ut = get_time.strftime("%H:%M:%S"), datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        self.telemetry_panel.update_time(lt, ut)

    def load_source_settings(self):
        p = os.path.join(PROJECT_ROOT, "tle_source_settings.json")
        return json.load(open(p)) if os.path.exists(p) else ["active", "visual"]

    def save_source_settings(self, settings):
        json.dump(settings, open(os.path.join(
            PROJECT_ROOT, "tle_source_settings.json"), 'w'))

    def closeEvent(self, event):
        """Cleanly terminates and joins active threads and sockets during application exit."""
        logger.info("MainWindow: Initiating graceful shutdown sequence...")
        
        # 1. Stop and wait for the live tracking thread
        if self.active_tracking_worker and self.active_tracking_worker.isRunning():
            logger.info("MainWindow: Stopping active tracking worker...")
            self.active_tracking_worker.stop()
            self.active_tracking_worker.wait(1000)  # Wait up to 1 second
            
        # 2. Terminate the path prediction thread
        if self.active_prediction_worker and self.active_prediction_worker.isRunning():
            logger.info("MainWindow: Terminating prediction worker...")
            self.active_prediction_worker.terminate()
            self.active_prediction_worker.wait(500)

        # 3. Shut down diagnostic loops and disconnect hardware
        try:
            self.hw_manager.disconnect()
        except Exception as e:
            logger.debug(f"MainWindow: HW disconnect issue on exit: {e}")

        # 4. Disconnect from the local/remote hardware TCP bridge
        try:
            self.hardware_bridge_client.disconnect()
        except Exception as e:
            logger.debug(f"MainWindow: Bridge client disconnect issue on exit: {e}")

        # 5. Stop local server sockets if they are active
        try:
            self.hw_manager.stop_bridge_server()
        except Exception:
            pass

        logger.info("MainWindow: Shutdown complete.")
        event.accept()
