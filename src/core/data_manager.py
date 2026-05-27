# -*- coding: utf-8 -*-
import os
import json
from threading import Lock
from typing import Dict, Optional
from src.config.settings import BASE_DIR
from src.utils.logger import logger

class DataManager:
    """Manages saving and loading of satellite data to/from JSON files."""
    
    def __init__(self):
        self._lock = Lock()
        self._cache = {}
        # In the original script, data was saved in the same directory as the script.
        # We use BASE_DIR (the project root) to maintain this behavior.
        self.data_dir = BASE_DIR
        os.makedirs(self.data_dir, exist_ok=True)

    def _get_filepath(self, satellite_name: str) -> str:
        """Generates a safe filename for a given satellite name."""
        safe_name = "".join(c for c in satellite_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
        safe_name = safe_name.replace(' ', '_')
        return os.path.join(self.data_dir, f"{safe_name}.json")

    def save_satellite_data(self, satellite_name: str, data: Dict) -> None:
        """Saves satellite dictionary to a JSON file thread-safely."""
        if not satellite_name:
            logger.error("Attempted save with empty satellite name.")
            return
        
        filepath = self._get_filepath(satellite_name)
        with self._lock:
            try:
                with open(filepath, "w", encoding='utf-8') as outfile:
                    json.dump(data, outfile, indent=2, ensure_ascii=False)
                self._cache[satellite_name] = data
                logger.debug(f"Saved data for '{satellite_name}'")
            except Exception as e:
                logger.error(f"Error saving {satellite_name}: {e}")

    def load_satellite_data(self, satellite_name: str) -> Optional[Dict]:
        """Loads satellite dictionary from a JSON file if it exists."""
        if not satellite_name:
            return None
        
        filepath = self._get_filepath(satellite_name)
        with self._lock:
            if satellite_name in self._cache:
                return self._cache[satellite_name]
            try:
                if not os.path.exists(filepath):
                    return None
                with open(filepath, "r", encoding='utf-8') as infile:
                    data = json.load(infile)
                self._cache[satellite_name] = data
                logger.debug(f"Loaded data for '{satellite_name}'")
                return data
            except Exception as e:
                logger.error(f"Error loading {satellite_name}: {e}")
                return None