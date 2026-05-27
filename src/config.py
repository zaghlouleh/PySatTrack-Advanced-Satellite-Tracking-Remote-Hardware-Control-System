import os
import logging

# API Keys
OPENCAGE_API_KEY = "Add_Your_OPENCAGE_API_KEY"
N2YO_API_KEY = "Add_Your_N2YO_API_KEY"

# File Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOG_DIR = os.path.join(BASE_DIR, 'logs')

SATELLITE_DATA_FILE = os.path.join(DATA_DIR, 'namesat+idsat.json')
LOG_FILE = os.path.join(LOG_DIR, 'script.log')

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Logging Configuration
def setup_logging():
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )