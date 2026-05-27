import json
import logging
from threading import Lock
from typing import Dict, Optional

class DataManager:
    """Thread-safe manager for satellite data operations"""
    def __init__(self):
        self._lock = Lock()
        self._cache = {}

    def save_satellite_data(self, satellite_name: str, data: Dict) -> None:
        """Thread-safe satellite data saving to JSON and memory cache""" 
        with self._lock: 
            try:
                filename = f"{satellite_name}.json"
                with open(filename, "w") as outfile:
                    json.dump(data, outfile, indent=2)
                self._cache[satellite_name] = data
                logging.info(f"Saved satellite data for {satellite_name}")
            except Exception as e:
                logging.error(f"Failed to save data for {satellite_name}: {str(e)}")
                
    def load_satellite_data(self, satellite_name: str) -> Optional[Dict]:
        """Thread-safe satellite data loading from cache or file"""
        with self._lock:
            if satellite_name in self._cache:
                return self._cache[satellite_name]
                
            try:
                filename = f"{satellite_name}.json"
                with open(filename, "r") as infile:
                    data = json.load(infile)
                self._cache[satellite_name] = data
                return data
            except FileNotFoundError:
                return None
            except Exception as e:
                logging.error(f"Failed to load data for {satellite_name}: {str(e)}")
                return None

# Global instance of the data manager to be used across the app
satellite_data_manager = DataManager()