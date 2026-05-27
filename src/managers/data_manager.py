# -*- coding: utf-8 -*-
import os
import json
from threading import Lock
from typing import Dict, Optional, Any
from src.utils.logger import logger

# Get project root for data storage
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class DataManager:
    """
    Handles local persistence of satellite telemetry and management of TLE files.
    Ensures thread-safe access to JSON data stores.
    """
    
    def __init__(self):
        self._lock = Lock()
        self._cache = {}
        
        # Directory for satellite telemetry JSON files
        self.telemetry_dir = os.path.join(PROJECT_ROOT, "satellite_data")
        # Directory for raw TLE text files
        self.tle_dir = os.path.join(PROJECT_ROOT, "tle_data")
        
        os.makedirs(self.telemetry_dir, exist_ok=True)
        os.makedirs(self.tle_dir, exist_ok=True)

    def _get_telemetry_path(self, satellite_name: str) -> str:
        """Generates a safe filesystem path for a satellite's JSON data."""
        # Sanitize name: remove non-alphanumeric except underscores/hyphens
        safe_name = "".join(c for c in satellite_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
        safe_name = safe_name.replace(' ', '_')
        return os.path.join(self.telemetry_dir, f"{safe_name}.json")

    def save_satellite_telemetry(self, satellite_name: str, data: Dict[str, Any]) -> None:
        """Saves combined N2YO and internal telemetry to a local JSON file."""
        if not satellite_name:
            logger.error("DataManager: Attempted to save data with empty satellite name.")
            return

        filepath = self._get_telemetry_path(satellite_name)
        with self._lock:
            try:
                with open(filepath, "w", encoding='utf-8') as outfile:
                    json.dump(data, outfile, indent=2, ensure_ascii=False)
                self._cache[satellite_name] = data
                logger.debug(f"DataManager: Saved telemetry for '{satellite_name}'")
            except Exception as e:
                logger.error(f"DataManager: Error saving telemetry for {satellite_name}: {e}")

    def load_satellite_telemetry(self, satellite_name: str) -> Optional[Dict[str, Any]]:
        """Loads satellite telemetry from local storage, checking cache first."""
        if not satellite_name:
            return None

        with self._lock:
            if satellite_name in self._cache:
                return self._cache[satellite_name]

            filepath = self._get_telemetry_path(satellite_name)
            try:
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding='utf-8') as infile:
                        data = json.load(infile)
                    self._cache[satellite_name] = data
                    logger.debug(f"DataManager: Loaded telemetry for '{satellite_name}' from disk.")
                    return data
            except Exception as e:
                logger.error(f"DataManager: Error loading telemetry for {satellite_name}: {e}")
        return None

    def get_tle_path(self, filename: str) -> str:
        """Returns the full path for a TLE source file."""
        return os.path.join(self.tle_dir, filename)

    def list_downloaded_tles(self) -> list:
        """Lists all TLE files currently available in the tle_data folder."""
        if not os.path.exists(self.tle_dir):
            return []
        return [f for f in os.listdir(self.tle_dir) if f.endswith('.txt')]