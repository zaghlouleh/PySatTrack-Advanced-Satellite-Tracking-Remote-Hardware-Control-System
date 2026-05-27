# -*- coding: utf-8 -*-
import os
from typing import Optional, Dict, Any

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QGroupBox, QGridLayout,
    QSizePolicy, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from src.utils.logger import logger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class StartScreen(QDialog):
    """
    Initial launch screen for satellite selection and ground station configuration.
    Appears on application startup before the main tracking interface is shown.
    """

    def __init__(self, satellites: Dict[str, Dict], parent=None):
        super().__init__(parent)
        self.satellites = satellites
        self.selected_sat_name: Optional[str] = None
        self.result_data: Optional[Dict[str, Any]] = None

        self.setWindowTitle("SatTrack Terminal v5.0 - Launch")
        self.resize(900, 700)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

        self.setup_ui()
        self.populate_sat_list()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("SATELLITE TRACKING SYSTEM")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont("Segoe UI", 20, QFont.Bold)
        title.setFont(title_font)
        title.setStyleSheet("color: #64B5F6; margin-bottom: 10px;")
        main_layout.addWidget(title)

        subtitle = QLabel("Select a satellite and configure your ground station to begin.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #888888; margin-bottom: 20px;")
        main_layout.addWidget(subtitle)

        # --- SATELLITE SELECTION GROUP ---
        sat_group = QGroupBox("Target Acquisition")
        sat_layout = QVBoxLayout(sat_group)

        # Search
        search_layout = QHBoxLayout()
        self.sat_search = QLineEdit()
        self.sat_search.setPlaceholderText("Filter by Name or NORAD ID...")
        self.sat_search.textChanged.connect(self.filter_sat_list)
        search_layout.addWidget(QLabel("Search:"))
        search_layout.addWidget(self.sat_search)
        sat_layout.addLayout(search_layout)

        # Satellite list
        self.sat_list = QListWidget()
        self.sat_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.sat_list.itemClicked.connect(self.on_sat_selected)
        sat_layout.addWidget(self.sat_list)

        # Count label
        self.sat_count_label = QLabel(f"Available satellites: {len(self.satellites)}")
        self.sat_count_label.setStyleSheet("color: #64B5F6; font-weight: bold;")
        sat_layout.addWidget(self.sat_count_label)

        main_layout.addWidget(sat_group, 3)

        # --- GROUND STATION CONFIG GROUP ---
        obs_group = QGroupBox("Ground Station Config")
        obs_grid = QGridLayout(obs_group)

        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("Damascus, London, NYC...")
        self.alt_input = QLineEdit("0")

        obs_grid.addWidget(QLabel("City:"), 0, 0)
        obs_grid.addWidget(self.city_input, 0, 1)
        obs_grid.addWidget(QLabel("Altitude (m):"), 1, 0)
        obs_grid.addWidget(self.alt_input, 1, 1)

        main_layout.addWidget(obs_group)

        # --- ACTION BUTTONS ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.launch_btn = QPushButton("Launch Tracking")
        self.launch_btn.setStyleSheet(
            "background-color: #1B5E20; color: white; height: 45px; "
            "font-weight: bold; font-size: 12pt; padding: 8px 24px;"
        )
        self.launch_btn.setEnabled(False)
        self.launch_btn.clicked.connect(self.on_launch)

        btn_layout.addWidget(self.launch_btn)
        main_layout.addLayout(btn_layout)

    def populate_sat_list(self):
        """Populate the list with all available satellites."""
        self.sat_list.clear()
        names = sorted([s['name'] for s in self.satellites.values()])
        self.sat_list.addItems(names)
        self.sat_count_label.setText(f"Available satellites: {len(names)}")

    def filter_sat_list(self):
        """Filter the satellite list based on search query."""
        self.sat_list.clear()
        query = self.sat_search.text().lower().strip()

        if not query:
            self.populate_sat_list()
            return

        matches = [
            s['name'] for s in self.satellites.values()
            if query in s['name'].lower() or query in str(s['norad_id'])
        ]

        if matches:
            self.sat_list.addItems(sorted(list(set(matches))))

    def on_sat_selected(self, item):
        """Handle satellite selection from the list."""
        self.selected_sat_name = item.text()
        self.sat_search.setText(self.selected_sat_name)
        self.launch_btn.setEnabled(True)
        logger.info(f"StartScreen: Selected {self.selected_sat_name}")

    def on_launch(self):
        """Validate inputs and return the result data."""
        if not self.selected_sat_name:
            QMessageBox.warning(self, "No Satellite Selected", "Please select a satellite from the list.")
            return

        sat_info = next(
            (v for v in self.satellites.values() if v['name'] == self.selected_sat_name),
            None
        )
        if not sat_info:
            QMessageBox.critical(self, "Error", "Selected satellite data not found.")
            return

        try:
            altitude = float(self.alt_input.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid Altitude", "Please enter a valid numeric altitude.")
            return

        self.result_data = {
            'satellite': sat_info,
            'city': self.city_input.text().strip(),
            'altitude': altitude,
        }
        self.accept()

    def get_result(self) -> Optional[Dict[str, Any]]:
        """Return the result data if the dialog was accepted."""
        return self.result_data

