import os
import time
import logging
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTextEdit, QPushButton, 
                             QLabel, QWidget, QGridLayout)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

logger = logging.getLogger(__name__)

class LoggingVerificationDialog(QDialog):
    """Execute and display comprehensive logging system checks."""
    def __init__(self, log_file_path, parent=None):
        super().__init__(parent)
        self.log_file = log_file_path
        self.setWindowTitle("Logging Diagnostics")
        self.setMinimumSize(400, 300)
        
        layout = QVBoxLayout()
        self.results = QTextEdit()
        self.results.setReadOnly(True)
        self.results.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas;")
        
        test_btn = QPushButton("Run Comprehensive Test")
        test_btn.clicked.connect(self.run_full_test)
        
        layout.addWidget(self.results)
        layout.addWidget(test_btn)
        self.setLayout(layout)

    def run_full_test(self):
        tests = [
            ('DEBUG', 'Debug test message'),
            ('INFO', 'Info test message'),
            ('WARNING', 'Warning test message'),
            ('ERROR', 'Error test message')
        ]
        
        results = []
        for level, msg in tests:
            try:
                getattr(logging, level.lower())(msg)
                results.append(f"✓ {level} test passed")
            except Exception as e:
                results.append(f"✗ {level} test failed: {str(e)}")
        
        log_exists = os.path.exists(self.log_file)
        results.append(f"Log file exists: {'✓' if log_exists else '✗'}")
        
        try:
            with open(self.log_file, 'a') as f:
                f.write("=== Permissions test ===\n")
            results.append("✓ Direct write permissions confirmed")
        except Exception as e:
            results.append(f"✗ Direct write failed: {str(e)}")
        
        self.results.setPlainText("\n".join(results))


class LogMonitor(QThread):
    """Monitors the log file size to detect if logging has stalled."""
    update_status = pyqtSignal(str)
    
    def __init__(self, log_file):
        super().__init__()
        self.log_file = log_file
        self.running = True
    
    def run(self):
        last_size = -1
        while self.running:
            try:
                if os.path.exists(self.log_file):
                    current_size = os.path.getsize(self.log_file)
                    if current_size != last_size:
                        self.update_status.emit("ACTIVE")
                        last_size = current_size
                    else:
                        self.update_status.emit("STALLED")
                else:
                    self.update_status.emit("MISSING")
                time.sleep(2)
            except Exception as e:
                self.update_status.emit(f"ERROR: {str(e)}")
                time.sleep(5)

    def stop(self):
        self.running = False