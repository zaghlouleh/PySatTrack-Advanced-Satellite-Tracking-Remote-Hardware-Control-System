# -*- coding: utf-8 -*-
from typing import List, Optional, Dict, Any
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton, 
                             QHBoxLayout, QGroupBox, QCheckBox, QScrollArea, QWidget)
from PyQt5.QtCore import Qt
from src.managers.background_manager import BackgroundManager
from src.utils.logger import logger

class SourceSelectionDialog(QDialog):
    """
    A categorized dialog for selecting TLE data sources.
    Organizes sources into groups and handles batch selection logic.
    """
    
    def __init__(self, sources_dict: Dict[str, Any], last_selection: List[str], parent=None):
        super().__init__(parent)
        self.sources = sources_dict
        self.last_selection = last_selection
        self.checkboxes = {}
        self.user_response = None
        
        self.setWindowTitle("Select TLE Sources")
        self.resize(850, 750)
        
        # Initialize the cyber-dark background
        self.bg_manager = BackgroundManager()
        if self.bg_manager.setup_dialog_background(self, force_mode='video'):
            self.setup_ui()
        else:
            self.content_layout = QVBoxLayout(self)
            self.setup_ui()

    def setup_ui(self):
        """Constructs the scrollable source list with group categorization."""
        layout = self.content_layout
        
        title = QLabel("TLE Source Selection")
        title.setStyleSheet("font-size: 18pt; color: #64B5F6; font-weight: bold; margin-bottom: 5px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Batch Control Buttons
        control_layout = QHBoxLayout()
        all_btn = QPushButton("Select All")
        all_btn.clicked.connect(self.select_all)
        none_btn = QPushButton("Deselect All")
        none_btn.clicked.connect(self.deselect_all)
        
        control_layout.addWidget(all_btn)
        control_layout.addWidget(none_btn)
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # Source groups without scrolling
        sources_layout = QVBoxLayout()
        sources_layout.addStretch(1)

        # Group sources by their 'group' property
        grouped = {}
        for key, info in self.sources.items():
            grp = info.get("group", "Miscellaneous")
            if grp not in grouped: grouped[grp] = []
            grouped[grp].append((key, info))
        
        for group_name in sorted(grouped.keys()):
            group_box = QGroupBox(group_name)
            group_layout = QVBoxLayout(group_box)
            
            for key, info in grouped[group_name]:
                cb = QCheckBox(info.get("name", key))
                cb.setToolTip(info.get("description", ""))
                if key in self.last_selection:
                    cb.setChecked(True)
                self.checkboxes[key] = cb
                group_layout.addWidget(cb)
            
            sources_layout.addWidget(group_box)
        
        sources_layout.addStretch(1)
        layout.addLayout(sources_layout, 1)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("background: #444444;")
        
        ok_btn = QPushButton("Update and Download")
        ok_btn.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def select_all(self):
        for cb in self.checkboxes.values(): cb.setChecked(True)

    def deselect_all(self):
        for cb in self.checkboxes.values(): cb.setChecked(False)

    def get_selected_sources(self) -> Optional[List[str]]:
        """Executes the dialog and returns the list of selected keys."""
        if self.exec_() == QDialog.Accepted:
            return [key for key, cb in self.checkboxes.items() if cb.isChecked()]
        return None