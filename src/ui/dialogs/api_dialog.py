# -*- coding: utf-8 -*-
import webbrowser
from typing import Optional, Dict
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QDialogButtonBox, QGroupBox)
from src.utils.logger import logger

class ApiKeysDialog(QDialog):
    """
    A prompt for users to enter their personal API keys for N2YO and OpenCage.
    These are required for tracking and geocoding respectively.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Initial API Configuration")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        intro = QLabel(
            "This application requires free personal API keys to function.\n"
            "Please paste your keys below. They will be stored securely."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #64B5F6; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(intro)

        # --- N2YO Section ---
        n2yo_group = QGroupBox("N2YO (Satellite Tracking)")
        n2yo_layout = QVBoxLayout(n2yo_group)
        self.n2yo_input = QLineEdit()
        self.n2yo_input.setPlaceholderText("Paste N2YO API key here")
        
        n2yo_link = QPushButton("Get free N2YO Key")
        n2yo_link.setStyleSheet("text-align: left; color: #64B5F6; border: none; background: none; text-decoration: underline;")
        n2yo_link.clicked.connect(lambda: webbrowser.open("https://n2yo.com/register/"))
        
        n2yo_layout.addWidget(self.n2yo_input)
        n2yo_layout.addWidget(n2yo_link)
        layout.addWidget(n2yo_group)

        # --- OpenCage Section ---
        geo_group = QGroupBox("OpenCage (City Geocoding)")
        geo_layout = QVBoxLayout(geo_group)
        self.geo_input = QLineEdit()
        self.geo_input.setPlaceholderText("Paste OpenCage API key here")
        
        geo_link = QPushButton("Get free OpenCage Key")
        geo_link.setStyleSheet("text-align: left; color: #64B5F6; border: none; background: none; text-decoration: underline;")
        geo_link.clicked.connect(lambda: webbrowser.open("https://opencagedata.com/users/sign_up"))
        
        geo_layout.addWidget(self.geo_input)
        geo_layout.addWidget(geo_link)
        layout.addWidget(geo_group)
        
        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def get_keys(self) -> Optional[Dict[str, str]]:
        """Displays the dialog and returns the keys as a dictionary."""
        if self.exec_() == QDialog.Accepted:
            return {
                "n2yo": self.n2yo_input.text().strip(),
                "opencage": self.geo_input.text().strip()
            }
        return None