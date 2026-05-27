"""UI Stylesheets and Visual Constants for the application"""

APP_STYLESHEET = """
    QWidget {
        background-color: #1E1E1E;
        color: #D4D4D4;
        font-family: 'Segoe UI', Consolas, monospace;
        font-size: 12px;
    }
    
    /* Enhanced inputs with validation states */
    QLineEdit, QTextEdit {
        background-color: #252526;
        color: #D4D4D4;
        border: 1px solid #404040;
        border-radius: 4px;
        padding: 6px;
        min-height: 24px;
    }
    QLineEdit:focus {
        border-color: #0E639C;
        box-shadow: 0 0 0 2px rgba(14,99,156,0.2);
    }
    QLineEdit[valid=true] {
        border-color: #3DDC84;
        box-shadow: 0 0 0 2px rgba(61,220,132,0.2);
    }
    QLineEdit[valid=false] {
        border-color: #F14C4C;
        box-shadow: 0 0 0 2px rgba(241,76,76,0.2);
    }
    
    /* Modern buttons with loading states */
    QPushButton {
        background: linear-gradient(145deg, #3F3F3F, #2D2D2D);
        color: #D4D4D4;
        border: 1px solid #555;
        border-radius: 6px;
        padding: 8px 16px;
        font-weight: 500;
        min-height: 32px;
    }
    QPushButton:hover {
        background: linear-gradient(145deg, #4A4A4A, #3F3F3F);
        border-color: #666;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    QPushButton:pressed {
        background: linear-gradient(145deg, #2D2D2D, #1E1E1E);
    }
    QPushButton:disabled {
        background: #2A2A2A;
        color: #606060;
        border-color: #404040;
    }
    
    /* Loading spinner */
    QPushButton[loading=true]::before {
        content: '';
        background: url(:/icons/spinner.gif) no-repeat center;
        width: 16px;
        height: 16px;
        position: absolute;
        left: 8px;
    }
    
    QListWidget {
        background-color: #252526;
        color: #D4D4D4;
        border: 1px solid #404040;
        border-radius: 4px;
    }
    QListWidget::item {
        padding: 8px;
        border-bottom: 1px solid #303030;
    }
    QListWidget::item:hover {
        background-color: #0E639C20;
    }
    QListWidget::item:selected {
        background-color: #0E639C;
        color: white;
    }
    
    /* Telemetry labels with color coding */
    QLabel[role=telemetry] {
        font-weight: 600;
        padding: 4px 8px;
        border-radius: 3px;
        min-height: 20px;
    }
    QLabel[elevation-green] {
        background: rgba(61,220,132,0.2);
        color: #3DDC84;
    }
    QLabel[elevation-red] {
        background: rgba(241,76,76,0.2);
        color: #F14C4C;
    }
    QLabel[speed-high] {
        background: linear-gradient(90deg, #FF6B35, #F7931E);
        color: white;
    }
    
    /* Group boxes */
    QGroupBox {
        font-weight: 600;
        border: 1px solid #404040;
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 12px;
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #252526, stop:1 #1E1E1E);
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 8px;
        color: #CCCCCC;
    }
    
    /* Map container */
    QWebEngineView {
        background: #0D1117;
        border-radius: 8px;
        border: 1px solid #30363D;
    }
    
    QLabel {
        color: #CCCCCC;
    }
"""


TAB_WIDGET_STYLE = """
    QTabWidget::pane {
        border: 1px solid #3d3d3d;
        background: #1e1e1e;
        margin: 0;
        padding: 0;
    }
    QTabBar::tab {
        background: #252526;
        color: #ffffff;
        padding: 8px 12px;
        border: 1px solid #3d3d3d;
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        margin-right: 2px;
    }
    QTabBar::tab:selected {
        background: #2d2d2d;
        border-color: #3d3d3d;
        color: #ffffff;
    }
    QTabBar::tab:hover {
        background: #353535;
    }
    QTabBar::close-button {
        image: url(none);
    }
"""

ERROR_DISPLAY_STYLE = """
    QTextEdit {
        background-color: #1e1e1e;
        color: #f48771;
        font-family: Consolas;
        font-size: 12px;
    }
"""

LOG_DISPLAY_STYLE = """
    QTextEdit {
        background-color: #1e1e1e;
        color: #d4d4d4;
        font-family: Consolas;
        font-size: 12px;
    }
"""