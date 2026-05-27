import sys
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QTextEdit, 
    QScrollArea, QListWidget, QVBoxLayout, QProgressBar, QHBoxLayout
)
from PyQt5.QtGui import QTextCursor, QColor, QFont, QIcon
from PyQt5.QtCore import Qt, QTimer

from src.models.data_manager import load_satellite_names
from src.hardware.arduino import get_arduino_ports
from src.services.tracking_service import fetch_satellite_data_threaded

# Styles
WINDOW_STYLE = "background-color: #f0f2f5;"
LABEL_STYLE = "font-size: 13px; font-weight: bold; color: #1c1e21; margin-top: 5px;"
ENTRY_STYLE = """
    QLineEdit { font-size: 12px; background-color: #ffffff; border: 1px solid #ccd0d5; border-radius: 4px; padding: 5px; color: #000000; }
    QLineEdit:focus { border: 1px solid #1877f2; }
"""
LIST_STYLE = "background-color: #ffffff; border: 1px solid #ccd0d5; color: #000000;"
TEXT_STYLE = "font: 10pt 'Courier New'; background-color: #ffffff; border: 1px solid #ccd0d5; color: #1c1e21; padding: 5px;"
BUTTON_STYLE = """
    QPushButton { font: bold 12pt Helvetica; background-color: #42b72a; color: white; border-radius: 6px; padding: 10px; margin-top: 10px; }
    QPushButton:hover { background-color: #36a420; }
    QPushButton:pressed { background-color: #2b9217; }
"""
PROGRESS_STYLE = "QProgressBar { border: 1px solid #ccd0d5; border-radius: 4px; text-align: center; } QProgressBar::chunk { background-color: #42b72a; }"

class SatelliteUpdater(QWidget):
    def __init__(self):
        super().__init__()
        self.satellite_names = load_satellite_names()
        self.init_ui()
        self.check_initial_arduino()

    def init_ui(self):
        self.setStyleSheet(WINDOW_STYLE)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(5)

        # Theme toggle improvement
        theme_layout = QHBoxLayout()
        # self.theme_btn = QPushButton("🌙 Dark Theme")
        # self.theme_btn.clicked.connect(self.toggle_theme)
        # theme_layout.addWidget(self.theme_btn)
        layout.addLayout(theme_layout)

        # Satellite Name
        self.add_styled_label(layout, "Satellite Name:")
        self.satellite_name_entry = QLineEdit(self)
        self.satellite_name_entry.setStyleSheet(ENTRY_STYLE)
        self.satellite_name_entry.textChanged.connect(self.update_suggestions)
        layout.addWidget(self.satellite_name_entry)

        # Suggestion Listbox
        self.suggestion_listbox = QListWidget(self)
        self.suggestion_listbox.setStyleSheet(LIST_STYLE)
        self.suggestion_listbox.setVisible(False)
        layout.addWidget(self.suggestion_listbox)

        # Arduino inputs
        self.add_styled_label(layout, "Arduino Port:")
        self.arduino_port_entry = QLineEdit(self)
        self.arduino_port_entry.setStyleSheet(ENTRY_STYLE)
        layout.addWidget(self.arduino_port_entry)

        self.add_styled_label(layout, "Baud Rate:")
        self.baud_rate_entry = QLineEdit(self, text="9600")
        self.baud_rate_entry.setStyleSheet(ENTRY_STYLE)
        layout.addWidget(self.baud_rate_entry)

        self.add_styled_label(layout, "Arduino Description:")
        self.arduino_description_entry = QLineEdit(self)
        self.arduino_description_entry.setStyleSheet(ENTRY_STYLE)
        layout.addWidget(self.arduino_description_entry)

        # Observer
        self.add_styled_label(layout, "City Name:")
        self.city_name_entry = QLineEdit(self)
        self.city_name_entry.setStyleSheet(ENTRY_STYLE)
        layout.addWidget(self.city_name_entry)

        self.add_styled_label(layout, "Observer Altitude (meters):")
        self.observer_alt_entry = QLineEdit(self)
        self.observer_alt_entry.setStyleSheet(ENTRY_STYLE)
        layout.addWidget(self.observer_alt_entry)

        self.add_styled_label(layout, "Future Positions (max 300):")
        self.seconds_entry = QLineEdit(self)
        self.seconds_entry.setStyleSheet(ENTRY_STYLE)
        layout.addWidget(self.seconds_entry)

        # Fetch with progress (improvement)
        fetch_layout = QHBoxLayout()
        self.fetch_button = QPushButton("Fetch Data", self)
        self.fetch_button.setStyleSheet(BUTTON_STYLE)
        self.fetch_button.clicked.connect(self.on_fetch_clicked)
        fetch_layout.addWidget(self.fetch_button)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(PROGRESS_STYLE)
        self.progress_bar.setVisible(False)
        fetch_layout.addWidget(self.progress_bar)
        layout.addLayout(fetch_layout)

        # Logs
        self.add_styled_label(layout, "Logs & Status:")
        self.error_text = QTextEdit(self)
        self.error_text.setStyleSheet(TEXT_STYLE)
        self.error_text.setReadOnly(True)
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.error_text)
        scroll_area.setStyleSheet("border: none;")
        layout.addWidget(scroll_area)

        self.suggestion_listbox.itemClicked.connect(self.on_suggestion_select)

        self.setLayout(layout)
        self.setWindowTitle("Satellite Tracker v2.0 - Improved")
        self.setWindowIcon(QIcon("/home/ghaith/Downloads/Programing/SatTrack/satellite_tracker_Version_1/icon.ico"))
        self.resize(500, 850)

    # def toggle_theme(self):
    #     self.is_dark = not hasattr(self, 'is_dark') or not self.is_dark
    #     if self.is_dark:
    #         self.setStyleSheet(WINDOW_STYLE.replace('#f0f2f5', '#2c3e50').replace('#1c1e21', '#ecf0f1'))
    #         self.theme_btn.setText("☀️ Light Theme")
    #     else:
    #         self.setStyleSheet(WINDOW_STYLE)
    #         self.theme_btn.setText("🌙 Dark Theme")

    def add_styled_label(self, layout, text):
        label = QLabel(text)
        label.setStyleSheet(LABEL_STYLE)
        layout.addWidget(label)

    def append_log(self, message, color_name="black"):
        self.error_text.moveCursor(QTextCursor.End)
        self.error_text.setTextColor(QColor(color_name))
        self.error_text.insertPlainText(message)
        self.error_text.setTextColor(QColor("#1c1e21"))

    def update_suggestions(self):
        current_input = self.satellite_name_entry.text().lower()
        self.suggestion_listbox.clear()
        if not current_input:
            self.suggestion_listbox.hide()
            return
        filtered_names = [name for name in self.satellite_names if current_input in name.lower()]
        if filtered_names:
            self.suggestion_listbox.addItems(filtered_names[:5])
            self.suggestion_listbox.show()
        else:
            self.suggestion_listbox.hide()

    def on_suggestion_select(self, item):
        self.satellite_name_entry.setText(item.text())
        self.suggestion_listbox.hide()

    def check_initial_arduino(self):
        desc = self.arduino_description_entry.text()
        ports = get_arduino_ports(desc)
        color = "#28a745" if ports else "#dc3545"
        msg = "Arduino found:\n" + "\n".join(ports) if ports else "No Arduino."
        self.append_log(msg, color)

    def on_fetch_clicked(self):
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.fetch_button.setEnabled(False)
        QTimer.singleShot(3000, self.on_fetch_complete)  # Simulate
        self.append_log("Fetching...", "#1877f2")
        fetch_satellite_data_threaded(
            self.satellite_name_entry.text(),
            self.city_name_entry.text(),
            self.observer_alt_entry.text(),
            self.seconds_entry.text(),
            self.arduino_port_entry.text(),
            self.baud_rate_entry.text(),
            self.arduino_description_entry.text(),
            self.append_log
        )

    def on_fetch_complete(self):
        self.progress_bar.setVisible(False)
        self.fetch_button.setEnabled(True)
        self.append_log("Fetch complete!", "green")

