# -*- coding: utf-8 -*-
import os
import logging
import sys
import time
from datetime import datetime
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton

# Determine the base directory (one level up from src/utils)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_FILE = os.path.join(BASE_DIR, 'satellite_tracker.log')

class ImmediateFlushFileHandler(logging.FileHandler):
    def __init__(self, filename):
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            super().__init__(filename, encoding='utf-8')
        except Exception as e:
            print(f"CRITICAL: Failed to initialize logger: {str(e)}")
            raise

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except Exception as e:
            print(f"LOGGER ERROR: {str(e)}")

def setup_logger():
    """Configures and returns the application logger."""
    logger = logging.getLogger("satellite_tracker")
    logger.propagate = False
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        file_handler = ImmediateFlushFileHandler(LOG_FILE)
        stream_handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
        
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
    
    return logger

logger = setup_logger()

class LogMonitor(QThread):
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
                        logger.info("Log file rotation detected by monitor.")
                        self.update_status.emit("ROTATED")
                    else:
                        self.update_status.emit("ACTIVE")
                    self._last_stat = current_stat
                else:
                    self.update_status.emit("STALLED")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Log monitor error: {str(e)}")
                self.update_status.emit(f"ERROR")
                time.sleep(5)

    def stop(self):
        self.running = False

class LoggingVerificationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Logging Diagnostics")
        layout = QVBoxLayout()
        self.results = QTextEdit()
        self.results.setReadOnly(True)
        test_btn = QPushButton("Run Comprehensive Test")
        test_btn.clicked.connect(self.run_full_test)
        layout.addWidget(self.results)
        layout.addWidget(test_btn)
        self.setLayout(layout)

    def run_full_test(self):
        tests = [('DEBUG', 'Debug test'), ('INFO', 'Info test'), 
                 ('WARNING', 'Warning test'), ('ERROR', 'Error test')]
        results = []
        for level, msg in tests:
            try:
                getattr(logger, level.lower())(msg)
                results.append(f"✓ {level} test passed")
            except Exception as e:
                results.append(f"✗ {level} test failed: {str(e)}")
        
        log_exists = os.path.exists(LOG_FILE)
        results.append(f"Log file exists: {'✓' if log_exists else '✗'}")
        self.results.setPlainText("\n".join(results))