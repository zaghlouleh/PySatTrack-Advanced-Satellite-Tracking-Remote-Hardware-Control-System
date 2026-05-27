# -*- coding: utf-8 -*-

CYBER_DARK_THEME = """
    QWidget { 
        background-color: #1E1E1E; 
        color: #D4D4D4; 
        font-family: 'Segoe UI', 'Roboto', sans-serif; 
        font-size: 10pt; 
    }
    QGroupBox { 
        border: 1px solid #333333; 
        border-radius: 6px; 
        margin-top: 2px; 
        padding-top: 2px; 
        font-weight: bold; 
        color: #64B5F6; 
    }
    QGroupBox::title { 
        subcontrol-origin: margin; 
        left: 10px; 
        padding: 0px 3px; 
    }
    QLineEdit, QComboBox, QListWidget { 
        background-color: #2D2D2D; 
        color: #F0F0F0; 
        border: 1px solid #444444; 
        border-radius: 4px; 
        padding: 4px; 
    }
    /* Fixed Button Sizes */
    QPushButton { 
        background-color: #333333; 
        color: #FFFFFF; 
        border: 1px solid #444444; 
        padding: 4px 8px; 
        border-radius: 4px; 
        min-height: 24px;
    } 
    QPushButton:hover { background-color: #444444; border-color: #64B5F6; } 
    QTabWidget::pane { border-top: 1px solid #333333; background: #1E1E1E; } 
    QTabBar::tab { 
        background: #252525; 
        padding: 6px 12px; 
        margin-right: 2px; 
    }
    QTabBar::tab:selected { background: #333333; color: #64B5F6; border-bottom: 2px solid #64B5F6; }
"""