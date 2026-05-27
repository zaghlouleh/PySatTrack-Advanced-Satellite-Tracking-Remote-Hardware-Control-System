import os
import logging
import sys

# Global log file path accessible by other modules
LOG_FILE = os.path.abspath('satellite_tracker.log')

class ImmediateFlushFileHandler(logging.FileHandler):
    """Custom handler to ensure logs are written to disk immediately."""
    def __init__(self, filename):
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            # Force UTF-8 encoding for cross-platform compatibility
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

def setup_logging():
    """Initializes the global logging configuration."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Clear existing handlers to prevent duplicate logs during refactoring/reloads
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add our custom handlers
    file_handler = ImmediateFlushFileHandler(LOG_FILE)
    stream_handler = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    logging.info("===== Logging System Initialized =====")
    logging.info(f"Log file path: {LOG_FILE}")
    logging.info(f"Write test: {os.access(os.path.dirname(LOG_FILE), os.W_OK)}")
    
    return LOG_FILE