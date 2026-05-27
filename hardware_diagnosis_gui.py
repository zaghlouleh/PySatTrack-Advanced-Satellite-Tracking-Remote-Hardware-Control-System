# -*- coding: utf-8 -*-
"""Entry point for the standalone hardware diagnostics GUI.

Run concurrently with the main app:
    python hardware_diagnosis_gui.py

It will connect to the TCP bridge (host/port) and poll GET_GPS_STATUS.
"""

import os
import sys
import platform

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from src.ui.hardware_diagnostics_window import HardwareDiagnosticsWindow

# Best-effort Qt tweaks for RPi
if hasattr(Qt, 'AA_EnableHighDpiScaling'):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


def main():
    # If QtWebEngine exists elsewhere, keep env clean; this GUI is pure widgets+pyqtgraph.
    app = QApplication(sys.argv)
    try:
        # Optional: nicer font rendering
        app.setStyle('Fusion')
    except Exception:
        pass

    win = HardwareDiagnosticsWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

