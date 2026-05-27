import json
import logging
import os
from src.config import DATA_DIR, SATELLITE_DATA_FILE

def load_all_satellite_mappings():
    """Loads the main name-to-ID mapping file."""
    try:
        if not os.path.exists(SATELLITE_DATA_FILE):
            logging.error(f"Satellite mapping file not found: {SATELLITE_DATA_FILE}")
            return {}
        with open(SATELLITE_DATA_FILE, 'r') as infile:
            return json.load(infile)
    except Exception as e:
        logging.error(f"Failed to load satellite mapping data: {str(e)}")
        return {}

def load_satellite_names():
    """Returns a list of all satellite names from the mapping file."""
    data = load_all_satellite_mappings()
    return list(data.keys())

def get_satellite_id(satellite_name, mapping_data):
    """Retrieves the ID for a specific satellite name."""
    return mapping_data.get(satellite_name, None)

def save_satellite_tracking_info(satellite_name, data):
    """Saves specific tracking coordinates to a JSON file."""
    filename = os.path.join(DATA_DIR, f"{satellite_name}.json")
    try:
        with open(filename, "w") as outfile:
            json.dump(data, outfile)
        return filename
    except Exception as e:
        logging.error(f"Failed to save tracking info for {satellite_name}: {e}")
        return None