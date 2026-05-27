import json
import logging
from threading import Lock
from typing import Dict, Optional

class DataManager:
    """Thread-safe manager for satellite data operations with caching."""
    def __init__(self):
        self._lock = Lock()
        self._cache: Dict[str, Dict] = {}
        logging.info("DataManager initialized.")

    def save_satellite_data(self, satellite_name: str, data: Dict) -> None:
        """Saves satellite data to a JSON file and updates the cache."""
        with self._lock:
            filename = f"{satellite_name}.json"
            try:
                with open(filename, "w", encoding='utf-8') as outfile:
                    json.dump(data, outfile, indent=2, ensure_ascii=False)
                self._cache[satellite_name] = data
                logging.info(f"Saved satellite data for {satellite_name} to {filename}")
            except Exception as e:
                logging.error(f"Failed to save data for {satellite_name}: {str(e)}", exc_info=True)

    def load_satellite_data(self, satellite_name: str) -> Optional[Dict]:
        """Loads satellite data from cache or file, thread-safely."""
        with self._lock:
            if satellite_name in self._cache:
                logging.debug(f"Loading {satellite_name} from cache.")
                return self._cache[satellite_name]
                
            filename = f"{satellite_name}.json"
            try:
                with open(filename, "r", encoding='utf-8') as infile:
                    data = json.load(infile)
                self._cache[satellite_name] = data
                logging.info(f"Loaded satellite data for {satellite_name} from {filename}")
                return data
            except FileNotFoundError:
                logging.warning(f"Data file not found for {satellite_name}: {filename}")
                return None
            except Exception as e:
                logging.error(f"Failed to load data for {satellite_name}: {str(e)}", exc_info=True)
                return None

# Global instance to be used across the application
satellite_data_manager = DataManager()