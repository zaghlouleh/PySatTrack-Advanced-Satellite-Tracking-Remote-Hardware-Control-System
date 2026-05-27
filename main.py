import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from src.ui.main_window import SatelliteUpdater
from src.config import setup_logging

def main():
    # Initialize logging configuration
    setup_logging()

    # Create the QApplication instance
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon('icon.ico'))
    
    # Create and show the main window
    window = SatelliteUpdater()
    window.show()
    
    # Start the GUI event loop
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()