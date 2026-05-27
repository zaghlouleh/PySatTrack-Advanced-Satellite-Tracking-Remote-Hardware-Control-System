# -*- coding: utf-8 -*-
import os
import psutil
from datetime import datetime
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QTextEdit, QLabel, QGridLayout, QPushButton, QMenu
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QTextCursor, QFont
from src.utils.logger import logger, LOG_FILE
from src.ui.dialogs.diagnostics_dialog import LoggingVerificationDialog

class LogPanel(QTabWidget):
    """
    Restores the 'Problems', 'Output', and 'Memory Info' tabs from the original code.
    Includes real-time memory tracking and log file synchronization.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_log_stat = None
        self.setup_ui()
        
        # Timers for log and memory updates
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self._check_log_file_update)
        self.log_timer.start(1500)
        
        self.mem_timer = QTimer(self)
        self.mem_timer.timeout.connect(self.update_memory_display)
        self.mem_timer.start(2000)

    def setup_ui(self):
        log_font = QFont("Consolas", 9)
        
        # 1. Problems Tab (Red Text for Errors)
        self.error_display = QTextEdit()
        self.error_display.setReadOnly(True)
        self.error_display.setFont(log_font)
        self.error_display.setStyleSheet("color: #FF6347; background-color: #1A1A1A;")
        self.addTab(self.error_display, "Problems")
        
        # 2. Output Tab (App Log)
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(log_font)
        self.log_display.setStyleSheet("background-color: #1A1A1A;")
        self.addTab(self.log_display, "Output")
        
        # 3. Memory Info Tab (psutil integration)
        self.mem_tab = QWidget()
        mem_layout = QGridLayout(self.mem_tab)
        self.mem_labels = {
            'proc_rss': QLabel("---"),
            'proc_perc': QLabel("---"),
            'sys_avail': QLabel("---"),
            'sys_total': QLabel("---"),
            'sys_perc': QLabel("---")
        }
        
        rows = [
            ("App Memory (RSS):", 'proc_rss'),
            ("App Memory (%):", 'proc_perc'),
            ("Sys Available:", 'sys_avail'),
            ("Sys Total:", 'sys_total'),
            ("Sys Used (%):", 'sys_perc')
        ]
        
        for i, (label, key) in enumerate(rows):
            mem_layout.addWidget(QLabel(label), i, 0)
            mem_layout.addWidget(self.mem_labels[key], i, 1)
            
        diag_btn = QPushButton("Run Logging Diagnostics")
        diag_btn.clicked.connect(self.show_diagnostics)
        mem_layout.addWidget(diag_btn, len(rows), 0, 1, 2)
        
        self.addTab(self.mem_tab, "Memory Info")
        
        # Context menu for clearing logs
        self.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabBar().customContextMenuRequested.connect(self.show_context_menu)

    def append_error(self, message: str):
        """Thread-safe error reporting to the Problems tab."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.error_display.append(f"[{ts}] ERROR: {message}")
        self.setCurrentIndex(0)  # Switch to Problems tab

    def append_success(self, message: str):
        """Thread-safe success reporting to the Problems tab."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.error_display.append(f"[{ts}] SUCCESS: {message}")
        self.setCurrentIndex(0)  # Switch to Problems tab


    def update_memory_display(self):
        """Updates the memory tab labels using psutil."""
        try:
            process = psutil.Process(os.getpid())
            mem = process.memory_info()
            sys_mem = psutil.virtual_memory()
            mb = 1024 * 1024
            
            self.mem_labels['proc_rss'].setText(f"{mem.rss / mb:.1f} MB")
            self.mem_labels['proc_perc'].setText(f"{process.memory_percent():.1f}%")
            self.mem_labels['sys_avail'].setText(f"{sys_mem.available / mb:.0f} MB")
            self.mem_labels['sys_total'].setText(f"{sys_mem.total / mb:.0f} MB")
            self.mem_labels['sys_perc'].setText(f"{sys_mem.percent:.1f}%")
        except Exception:
            pass

    def _check_log_file_update(self):
        """Polls the log file for new content."""
        try:
            if not os.path.exists(LOG_FILE): return
            curr_stat = os.stat(LOG_FILE)
            stat_val = (curr_stat.st_size, curr_stat.st_ino)
            
            if self.last_log_stat is None:
                self.last_log_stat = stat_val
                self._read_logs(from_start=True)
            elif stat_val != self.last_log_stat:
                self._read_logs(from_start=(stat_val[1] != self.last_log_stat[1]))
                self.last_log_stat = stat_val
        except Exception:
            pass

    def _read_logs(self, from_start=False):
        try:
            with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                if not from_start and self.last_log_stat:
                    f.seek(self.last_log_stat[0])
                content = f.read()
                if content:
                    self.log_display.append(content.strip())
                    self.log_display.moveCursor(QTextCursor.End)
        except Exception:
            pass

    def show_diagnostics(self):
        diag = LoggingVerificationDialog(self)
        diag.exec_()

    def show_context_menu(self, pos):
        idx = self.tabBar().tabAt(pos)
        if idx < 0: return
        menu = QMenu(self)
        clear_act = menu.addAction("Clear Tab Content")
        if menu.exec_(self.tabBar().mapToGlobal(pos)):
            widget = self.widget(idx)
            if isinstance(widget, QTextEdit): widget.clear()