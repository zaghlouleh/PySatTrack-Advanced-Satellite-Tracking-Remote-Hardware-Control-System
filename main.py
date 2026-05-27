# -*- coding: utf-8 -*-
import sys
import os
import platform
from dotenv import load_dotenv

# --- CRITICAL: QtWebEngine Deployment Fix ---
# This ensures Qt can find its browser engine process and resources on Windows.
if platform.system() == "Windows":
    try:
        from PyQt5 import QtCore
        pyqt_dir = os.path.dirname(QtCore.__file__)
        bin_path = os.path.join(pyqt_dir, "Qt5", "bin")
        plugin_path = os.path.join(pyqt_dir, "Qt5", "plugins")
        resources_path = os.path.join(pyqt_dir, "Qt5", "resources")
        
        os.environ["QTWEBENGINE_PROCESS_PATH"] = os.path.join(bin_path, "QtWebEngineProcess.exe")
        os.environ["QTWEBENGINE_RESOURCES_PATH"] = resources_path
        os.environ["QT_PLUGIN_PATH"] = plugin_path
        if hasattr(os, 'add_dll_directory') and os.path.isdir(bin_path):
            os.add_dll_directory(bin_path)
        os.environ['PATH'] = bin_path + os.pathsep + os.environ['PATH']
    except Exception as e:
        print(f"WARNING: Qt path configuration failed: {e}")

# Ensure the 'src' directory is in the path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
from src.ui.main_window import MainWindow
from src.ui.styles import CYBER_DARK_THEME
from src.utils.logger import logger

def global_exception_hook(exctype, value, tb):
    logger.critical("UNHANDLED EXCEPTION:", exc_info=(exctype, value, tb))
    if QApplication.instance():
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("System Failure")
        msg.setText("A critical error occurred.")
        msg.setInformativeText(f"{exctype.__name__}: {value}")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()
    sys.exit(1)

def main():
    load_dotenv()
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # Disable GPU for better stability in virtualized environments
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-gpu'
    os.environ['QT_MULTIMEDIA_PREFERRED_PLUGINS'] = 'windowsmediafoundation'

    app = QApplication(sys.argv)
    app.setStyleSheet(CYBER_DARK_THEME)
    sys.excepthook = global_exception_hook
    
    logger.info("Main: Starting Satellite Tracker with Full Parity...")
    
    try:
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        logger.exception("Main: Initialization failed:")
        sys.exit(1)

if __name__ == "__main__":
    main()