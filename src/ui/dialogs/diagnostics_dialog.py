# -*- coding: utf-8 -*-
import os
import time
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QLabel
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from src.utils.logger import logger, LOG_FILE

class LogMonitor(QThread):
    """Thread-safe monitor for the application log file (Parity Feature)."""
    update_status = pyqtSignal(str)
    
    def __init__(self, log_file_path):
        super().__init__()
        self.log_file_path = log_file_path
        self.running = True
        self._last_stat = None

    def run(self):
        while self.running:
            try:
                if not os.path.exists(self.log_file_path):
                    self.update_status.emit("ERROR: Log file not found")
                    time.sleep(5)
                    continue
                
                current_stat_result = os.stat(self.log_file_path)
                current_stat = (current_stat_result.st_size, current_stat_result.st_ino)
                
                if self._last_stat is None:
                    self._last_stat = current_stat
                    self.update_status.emit("MONITORING")
                elif current_stat != self._last_stat:
                    if current_stat[1] != self._last_stat[1]:
                        self.update_status.emit("ROTATED")
                    else:
                        self.update_status.emit("ACTIVE")
                    self._last_stat = current_stat
                else:
                    self.update_status.emit("STALLED")
                time.sleep(2)
            except Exception as e:
                self.update_status.emit(f"ERROR: {str(e)[:30]}")
                time.sleep(5)

    def stop(self):
        self.running = False

class LoggingVerificationDialog(QDialog):
    """Restores the original 'Logging Diagnostics' feature for system integrity."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Logging Diagnostics")
        self.resize(500, 400)
        
        layout = QVBoxLayout(self)
        self.status_label = QLabel("Monitor: Initializing...")
        layout.addWidget(self.status_label)
        
        self.results = QTextEdit()
        self.results.setReadOnly(True)
        self.results.setStyleSheet("background-color: #000; color: #00FF00; font-family: Consolas;")
        layout.addWidget(self.results)
        
        test_btn = QPushButton("Run Comprehensive Test")
        test_btn.clicked.connect(self.run_full_test)
        layout.addWidget(test_btn)
        
        # Start the monitor thread
        self.monitor = LogMonitor(LOG_FILE)
        self.monitor.update_status.connect(self.status_label.setText)
        self.monitor.start()

    def run_full_test(self):
        tests = [
            ('DEBUG', 'Debug test message'),
            ('INFO', 'Info test message'),
            ('WARNING', 'Warning test message'),
            ('ERROR', 'Error test message')
        ]
        
        output = []
        for level, msg in tests:
            try:
                getattr(logger, level.lower())(f"DIAGNOSTIC: {msg}")
                output.append(f"✓ {level} test passed")
            except Exception as e:
                output.append(f"✗ {level} test failed: {str(e)}")
        
        output.append(f"Log path: {LOG_FILE}")
        output.append(f"Writable: {os.access(os.path.dirname(LOG_FILE), os.W_OK)}")
        
        self.results.setPlainText("\n".join(output))

    def closeEvent(self, event):
        self.monitor.stop()
        self.monitor.wait()
        super().closeEvent(event)