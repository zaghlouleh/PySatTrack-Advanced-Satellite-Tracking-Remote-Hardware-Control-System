# -*- coding: utf-8 -*-
import webbrowser
from typing import Optional, Dict
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QWidget, 
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
        # Used by BackgroundManager to apply login-specific sizing/styling.
        self.service_display_name = service_name


        self.registration_url = registration_url
        self.last_username = last_username
        
        self.setWindowTitle(f"Login to {service_name}")
        self.setModal(True)
        # Slightly smaller dialog size to reduce how much the background image shows.
        self.resize(520, 350)


        
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
        # BackgroundManager should inject content_layout, but keep a hard fallback.
        if not hasattr(self, "content_layout") or self.content_layout is None:
            self.content_layout = QVBoxLayout(self)

        layout = self.content_layout
        layout.setSpacing(10)

        # Header
        header_wrap = QWidget()
        header_wrap.setAttribute(Qt.WA_TranslucentBackground, True)
        header_wrap.setStyleSheet("background: transparent;")

        header_layout = QHBoxLayout(header_wrap)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_col = QVBoxLayout()
        title = QLabel(f"{self.service_name}")
        title.setObjectName("loginHeaderTitle")
        title.setAlignment(Qt.AlignLeft)
        title.setStyleSheet(
            "font-size: 22pt; color: #64B5F6; font-weight: bold; margin: 0; background: transparent;"
        )


        subtitle = QLabel("Authentication")
        subtitle.setObjectName("loginHeaderSubtitle")
        subtitle.setAlignment(Qt.AlignLeft)
        subtitle.setStyleSheet("color: #B0BEC5; margin: 0; background: transparent;")



        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_col.setSpacing(0)

        header_layout.addLayout(title_col)
        header_layout.addStretch(1)
        layout.addWidget(header_wrap)

        # Why login
        why = QLabel(
            "This login is required to unlock authenticated Space-Track TLE catalogs."
        )
        why.setWordWrap(True)
        layout.addWidget(why)

        # Form Container
        # Add a stretch above the form so the credential inputs sit higher in the dialog.
        layout.addStretch(1)

        form_group = QGroupBox("Account Details")
        form_layout = QGridLayout(form_group)
        form_layout.setContentsMargins(12, 18, 12, 12)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)


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

        # Security / help note
        help_hint = QLabel("Tip: enable 'Show Password' only when needed.")
        help_hint.setWordWrap(True)
        help_hint.setStyleSheet("color: #90A4AE; font-weight: normal;")
        form_layout.addWidget(help_hint, 2, 0, 1, 2)

        layout.addWidget(form_group)

        # Inline validation / status
        self.inline_error = QLabel("")
        self.inline_error.setStyleSheet("color: #EF5350; font-weight: bold;")
        self.inline_error.setVisible(False)
        layout.addWidget(self.inline_error)

        self.login_status_label = QLabel("")
        self.login_status_label.setStyleSheet("color: #64B5F6; font-weight: bold;")
        self.login_status_label.setVisible(False)
        layout.addWidget(self.login_status_label)

        # Settings row
        options_layout = QHBoxLayout()
        self.save_check = QCheckBox("Remember Credentials")
        self.save_check.setChecked(False)
        options_layout.addWidget(self.save_check)

        self.show_pass_check = QCheckBox("Show Password")
        self.show_pass_check.toggled.connect(
            lambda checked: self.password_input.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        options_layout.addWidget(self.show_pass_check)
        layout.addLayout(options_layout)

        # Links row
        links_layout = QHBoxLayout()

        reg_btn = QPushButton(f"Create {self.service_name} Account")
        reg_btn.setStyleSheet(
            "background: transparent; color: #64B5F6; border: none; text-decoration: underline;"
        )
        reg_btn.setCursor(Qt.PointingHandCursor)
        reg_btn.clicked.connect(lambda: webbrowser.open(self.registration_url))
        links_layout.addWidget(reg_btn)

        help_btn = QPushButton("Need help?")
        help_btn.setStyleSheet(
            "background: transparent; color: #B0BEC5; border: none; text-decoration: underline;"
        )
        help_btn.setCursor(Qt.PointingHandCursor)
        help_btn.clicked.connect(lambda: webbrowser.open(self.registration_url))
        links_layout.addWidget(help_btn)

        layout.addLayout(links_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 5, 0, 0)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("background: #444444;")

        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self._on_login_clicked)
        self.login_btn.setDefault(True)
        self.login_btn.setEnabled(False)

        btn_layout.addStretch(1)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.login_btn)
        layout.addLayout(btn_layout)

        # Live validation wiring
        self.username_input.textChanged.connect(self._sync_validation_state)
        self.password_input.textChanged.connect(self._sync_validation_state)
        self._sync_validation_state()

    def _sync_validation_state(self):
        username = (self.username_input.text() or "").strip()
        password = self.password_input.text() or ""
        if not username and not password:
            self.inline_error.setVisible(False)
            self.login_btn.setEnabled(False)
            return

        # Only require both values
        if not username:
            self._set_inline_error("Username is required.")
            self.login_btn.setEnabled(False)
            return
        if not password:
            self._set_inline_error("Password is required.")
            self.login_btn.setEnabled(False)
            return

        self.inline_error.setVisible(False)
        self.login_btn.setEnabled(True)

    def _set_inline_error(self, msg: str):
        self.inline_error.setText(msg)
        self.inline_error.setVisible(True)

    def _on_login_clicked(self):
        # Final client-side check
        username = (self.username_input.text() or "").strip()
        password = self.password_input.text() or ""
        if not username:
            self._set_inline_error("Username is required.")
            return
        if not password:
            self._set_inline_error("Password is required.")
            return

        # UX: show status while dialog submits
        self.inline_error.setVisible(False)
        self.login_status_label.setText("Logging in…")
        self.login_status_label.setVisible(True)
        self.login_btn.setEnabled(False)
        self.username_input.setEnabled(False)
        self.password_input.setEnabled(False)
        self.show_pass_check.setEnabled(False)
        self.save_check.setEnabled(False)

        # Accept dialog - actual auth is performed in main thread after get_credentials()
        self.accept()

    def reject(self):
        # Reset inline state when user cancels
        if hasattr(self, "inline_error") and self.inline_error is not None:
            self.inline_error.setVisible(False)
        if hasattr(self, "login_status_label") and self.login_status_label is not None:
            self.login_status_label.setVisible(False)

        # Restore enabled state if we disabled inputs while submitting.
        if hasattr(self, "username_input") and self.username_input is not None:
            self.username_input.setEnabled(True)
        if hasattr(self, "password_input") and self.password_input is not None:
            self.password_input.setEnabled(True)
        if hasattr(self, "show_pass_check") and self.show_pass_check is not None:
            self.show_pass_check.setEnabled(True)
        if hasattr(self, "save_check") and self.save_check is not None:
            self.save_check.setEnabled(True)

        # Re-run validation to decide whether the Login button should be enabled.
        try:
            self._sync_validation_state()
        except Exception:
            pass

        super().reject()


    def get_credentials(self) -> Optional[Dict[str, str]]:
        """Executes the dialog and returns the entered data if accepted."""
        if self.exec_() == QDialog.Accepted:
            return {
                "username": self.username_input.text().strip(),
                "password": self.password_input.text(),
                "save": self.save_check.isChecked(),
            }
        return None


