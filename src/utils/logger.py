# -*- coding: utf-8 -*-
import os
import sys
import logging
from datetime import datetime

# Get the root directory of the project
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "satellite_tracker.log")

class ImmediateFlushFileHandler(logging.FileHandler):
    """A custom log handler that flushes to disk immediately after every write."""
    def __init__(self, filename):
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            super().__init__(filename, encoding='utf-8')
        except Exception as e:
            print(f"CRITICAL: Failed to initialize logger directory: {str(e)}")
            raise

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except Exception as e:
            print(f"LOGGER ERROR: {str(e)}")

def setup_logger(name=__name__):
    """Configures and returns a logger instance."""
    logger = logging.getLogger(name)
    
    # If the logger already has handlers, don't add more (prevents duplicate logs)
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Create formatters
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(threadName)s - %(message)s')

    # File Handler
    try:
        file_handler = ImmediateFlushFileHandler(LOG_FILE)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        print("WARNING: Could not initialize file logging.")

    # Stream (Console) Handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger

# Global instance for the main application
logger = setup_logger("PySatTrack")