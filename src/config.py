"""Configuration settings for the satellite tracking application"""

import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys loaded from environment variables with fallbacks (from original code)
N2YO_API_KEY = os.getenv('N2YO_API_KEY', 'Add_Your_N2YO_API_KEY')
OPENCAGE_API_KEY = os.getenv('OPENCAGE_API_KEY', 'Add_Your_OPENCAGE_API_KEY')

# Default constraints and settings
DEFAULT_BAUD_RATE = 9600
MAX_SECONDS = 300
MAX_DAYS = 10

# Logging Configuration
LOG_FILE = 'satellite_tracker.log'

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_logger():
    return logging.getLogger('satellite_tracker')