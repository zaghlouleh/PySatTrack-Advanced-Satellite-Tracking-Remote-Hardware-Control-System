import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from src.ui.main_window import SatelliteTracker
from src.ui.styles import APP_STYLESHEET

def main():
    # Initialize the application
    app = QApplication(sys.argv)
    app.setApplicationName("Satellite Tracker v2")
    app.setOrganizationName("SatTrack")
    app.setWindowIcon(QIcon("icon.ico"))  # App icon
    
    # Apply the global VS Code-like dark theme
    app.setStyleSheet(APP_STYLESHEET)
    
    # Create and show the main window
    tracker = SatelliteTracker()
    tracker.showMaximized()  # Start maximized
    
    # Execute the application loop
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()