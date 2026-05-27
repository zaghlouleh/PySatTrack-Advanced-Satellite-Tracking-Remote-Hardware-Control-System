import sys
import logging
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from src.utils.logger import setup_logging
from src.ui.main_window import SatelliteTracker

def main():
    # 1. Initialize the logging system and get the log file path
    log_file = setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Application starting...")

    # 2. Create the Qt Application
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon('icon.ico'))

    # 3. Apply the global Dark Theme stylesheet (from the original code)
    app.setStyleSheet("""
        QWidget {
            background-color: #1E1E1E;
            color: #D4D4D4;
            font-family: Consolas, Monaco, monospace;
            font-size: 12px;
        }
        QLineEdit, QTextEdit, QListWidget {
            background-color: #252526;
            color: #D4D4D4;
            border: 1px solid #333333;
            border-radius: 4px;
            padding: 6px;
        }
        QLineEdit:focus {
            border: 2px solid #0e639c;
            background-color: #2d2d30;
        }
        QPushButton {
            background-color: #3F3F3F;
            color: #D4D4D4;
            border: 1px solid #555555;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #0e639c;
        }
        QPushButton:pressed {
            background-color: #094771;
        }
        QPushButton:disabled {
            background-color: #2d2d2d;
            color: #666;
        }
        QListWidget::item {
            background-color: #1E1E1E;
            color: #D4D4D4;
            padding: 6px;
        }
        QListWidget::item:hover {
            background-color: #2d2d30;
        }
        QListWidget::item:selected {
            background-color: #0e639c;
        }
        QLabel {
            color: #D4D4D4;
        }
        QGroupBox {
            border: 2px solid #404040;
            border-radius: 8px;
            margin: 12px;
            padding: 16px;
            font-weight: 600;
            font-size: 13px;
        }
        QGroupBox:title {
            subcontrol-origin: margin;
            left: 15px;
            padding: 0 8px 0 8px;
            color: #ffffff;
        }
        QTabWidget::pane {
            border: 1px solid #404040;
            background: #252526;
            border-radius: 6px;
        }
        QTabBar::tab {
            background: #2d2d30;
            color: #D4D4D4;
            padding: 12px 20px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            border: 1px solid #404040;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background: #0e639c;
            color: #ffffff;
        }
    """)

    # 4. Initialize and show the main window
    # Note: We pass the log_file path so the UI can read/display logs
    tracker = SatelliteTracker(log_file)
    tracker.show()

    # 5. Execute the application
    try:
        sys.exit(app.exec_())
    except Exception as e:
        logger.critical(f"Application crashed: {e}", exc_info=True)

if __name__ == "__main__":
    main()