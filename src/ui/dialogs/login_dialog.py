# -*- coding: utf-8 -*-
import webbrowser
from typing import Optional, Dict
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QHBoxLayout, QGroupBox, QCheckBox, QGridLayout)
from PyQt5.QtCore import Qt
from src.managers.background_manager import BackgroundManager
from src.utils.logger import logger

class LoginDialog(QDialog):
    """
    A beautiful, translucent login dialog for external services like Space-Track.org.
    Integrates with BackgroundManager for a modern aesthetic.
    """
    
    def __init__(self, service_name: str, registration_url: str, last_username: str = "", parent=None):
        super().__init__(parent)
        self.service_name = service_name
        self.registration_url = registration_url
        self.last_username = last_username
        
        self.setWindowTitle(f"Login to {service_name}")
        self.setModal(True)
        self.resize(600, 450)
        
        # Initialize background
        self.bg_manager = BackgroundManager()
        if self.bg_manager.setup_dialog_background(self, force_mode='video'):
            self.setup_ui()
        else:
            # Fallback if background manager fails
            self.content_layout = QVBoxLayout(self)
            self.setup_ui()

    def setup_ui(self):
        """Builds the form elements inside the content overlay."""
        layout = self.content_layout
        
        # Header
        title = QLabel(f"{self.service_name} Authentication")
        title.setStyleSheet("font-size: 18pt; color: #64B5F6; font-weight: bold; margin-bottom: 10px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Form Container
        form_group = QGroupBox("Account Details")
        form_layout = QGridLayout(form_group)
        
        form_layout.addWidget(QLabel("Username:"), 0, 0)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username or Email")
        if self.last_username:
            self.username_input.setText(self.last_username)
        form_layout.addWidget(self.username_input, 0, 1)
        
        form_layout.addWidget(QLabel("Password:"), 1, 0)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter Password")
        form_layout.addWidget(self.password_input, 1, 1)
        
        layout.addWidget(form_group)
        
        # Settings
        options_layout = QHBoxLayout()
        self.save_check = QCheckBox("Remember Credentials")
        self.save_check.setChecked(True)
        options_layout.addWidget(self.save_check)
        
        self.show_pass_check = QCheckBox("Show Password")
        self.show_pass_check.toggled.connect(
            lambda checked: self.password_input.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        options_layout.addWidget(self.show_pass_check)
        layout.addLayout(options_layout)
        
        # Registration Link
        reg_btn = QPushButton(f"Create {self.service_name} Account")
        reg_btn.setStyleSheet("background: transparent; color: #64B5F6; border: none; text-decoration: underline;")
        reg_btn.setCursor(Qt.PointingHandCursor)
        reg_btn.clicked.connect(lambda: webbrowser.open(self.registration_url))
        layout.addWidget(reg_btn)
        
        # Buttons
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("background: #444444;")
        
        login_btn = QPushButton("Login")
        login_btn.clicked.connect(self.accept)
        login_btn.setDefault(True)
        
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(login_btn)
        layout.addLayout(btn_layout)

    def get_credentials(self) -> Optional[Dict[str, str]]:
        """Executes the dialog and returns the entered data if accepted."""
        if self.exec_() == QDialog.Accepted:
            return {
                "username": self.username_input.text().strip(),
                "password": self.password_input.text(),
                "save": self.save_check.isChecked()
            }
        return None