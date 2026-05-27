# -*- coding: utf-8 -*-
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# Internal Imports
from src.ui.main_window import SatelliteTracker
from src.utils.platform_utils import setup_qt_environment
from src.utils.logger import logger

def main():
    # 1. Setup Windows-specific Qt environment variables
    setup_qt_environment()

    # 2. Enable High DPI Scaling (Exact attributes from original)
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    
    # 3. Apply EXACT Stylesheet from original monolithic script
    app.setStyleSheet("""
        QWidget { 
            background-color: #2B2B2B; 
            color: #D4D4D4; 
            font-family: Consolas, Monaco, 'Andale Mono', 'Ubuntu Mono', monospace; 
            font-size: 10pt; 
            border: none; 
        }
        QGroupBox { 
            border: 1px solid #4A4A4A; 
            border-radius: 4px; 
            margin-top: 10px; 
            padding: 10px 5px 5px 5px; 
            font-weight: bold; 
            color: #CCCCCC; 
        }
        QGroupBox::title { 
            subcontrol-origin: margin; 
            subcontrol-position: top left; 
            left: 10px; 
            padding: 0px 5px 2px 5px; 
            background-color: #2B2B2B; 
        }
        QLabel { background-color: transparent; padding: 1px; color: #D4D4D4; }
        QLineEdit, QTextEdit, QListWidget, QComboBox { 
            background-color: #3C3C3C; 
            color: #F0F0F0; 
            border: 1px solid #555555; 
            border-radius: 3px; 
            padding: 4px; 
        }
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #007ACC; }
        QPushButton { 
            background-color: #555555; 
            color: #F0F0F0; 
            border: 1px solid #666666; 
            padding: 5px 12px; 
            border-radius: 3px; 
        } 
        QPushButton:hover { background-color: #666666; } 
        QPushButton:pressed { background-color: #444444; }
        QListWidget::item:selected { background-color: #007ACC; color: white; }
        QScrollBar:vertical { border: none; background: #3C3C3C; width: 10px; margin: 0px; } 
        QScrollBar::handle:vertical { background: #666666; min-height: 20px; border-radius: 5px; } 
        QTabWidget::pane { border-top: 1px solid #4A4A4A; background: #2B2B2B; } 
        QTabBar::tab { 
            background: #3C3C3C; color: #CCCCCC; border: 1px solid #4A4A4A; 
            border-bottom: none; padding: 6px 10px; margin-right: 1px; 
        }
        QTabBar::tab:selected { background: #555555; color: #FFFFFF; border-color: #555555; }
    """)

    # 4. Exception Handling
    def global_except_hook(exctype, value, tb):
        logger.critical("Unhandled exception caught!", exc_info=(exctype, value, tb))
        sys.exit(1)
    sys.excepthook = global_except_hook

    try:
        window = SatelliteTracker()
        window.show()
        logger.info("Application started with original design.")
    except Exception as e:
        logger.exception("Startup failed:")
        sys.exit(1)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()