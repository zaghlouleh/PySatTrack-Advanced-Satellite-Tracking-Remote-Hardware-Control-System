import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys (Defaults provided from original code, but can be overridden by .env)
OPENCAGE_KEY = os.getenv('OPENCAGE_KEY', 'Add_Your_OPENCAGE_KEY')
N2YO_KEY = os.getenv('N2YO_KEY', 'Add_Your_N2YO_KEY')

# Physical Constants
EARTH_RADIUS_KM = 6371.0
MU_EARTH = 398600.4418  # Earth's gravitational parameter (km³/s²)

# Application Defaults
DEFAULT_INTERVAL = 60
DEFAULT_ALTITUDE = 0

# Protocol Settings
DEFAULT_BAUD_RATE = 9600