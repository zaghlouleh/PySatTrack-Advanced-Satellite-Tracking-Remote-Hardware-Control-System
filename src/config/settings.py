# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Base Directory (Project Root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# TLE Data Directory
TLE_DATA_DIR = os.path.join(BASE_DIR, "tle_data")
os.makedirs(TLE_DATA_DIR, exist_ok=True)

# SatNOGS Cache Directory
SATNOGS_CACHE_DIR = os.path.join(BASE_DIR, "satnogs_cache")
os.makedirs(SATNOGS_CACHE_DIR, exist_ok=True)

# API Keys and Credentials
OPENCAGE_API_KEY = os.getenv('OPENCAGE_API_KEY', 'Add_Your_OPENCAGE_API_KEY')
N2YO_API_KEY = os.getenv('N2YO_API_KEY', 'Add_Your_N2YO_API_KEY')
SPACE_TRACK_USER = os.getenv('SPACE_TRACK_USER', "Add_Your_SPACE_TRACK_USER")
SPACE_TRACK_PASSWORD = os.getenv('SPACE_TRACK_PASSWORD', "Add_Your_SPACE_TRACK_PASSWORD")

DEFAULT_TLE_SOURCES = {
    # --- Navigation Systems ---
    "gps": {"url": "https://celestrak.org/NORAD/elements/gps-ops.txt", "filename": "tle_gps-ops.txt", "cache_days": 1},
    "glonass": {"url": "https://celestrak.org/NORAD/elements/glonass-ops.txt", "filename": "tle_glonass-ops.txt", "cache_days": 1},
    "galileo": {"url": "https://celestrak.org/NORAD/elements/galileo.txt", "filename": "tle_galileo.txt", "cache_days": 1},
    "beidou": {"url": "https://celestrak.org/NORAD/elements/beidou.txt", "filename": "tle_beidou.txt", "cache_days": 1},
    "sbas": {"url": "https://celestrak.org/NORAD/elements/sbas.txt", "filename": "tle_sbas.txt", "cache_days": 1},
    "nnss": {"url": "https://celestrak.org/NORAD/elements/nnss.txt", "filename": "tle_nnss.txt", "cache_days": 2},
    "russian-leo": {"url": "https://celestrak.org/NORAD/elements/russian-leo.txt", "filename": "tle_russian-leo.txt", "cache_days": 1},

    # --- Weather & Earth Observation ---
    "weather": {"url": "https://celestrak.org/NORAD/elements/weather.txt", "filename": "tle_weather.txt", "cache_days": 1},
    "noaa": {"url": "https://celestrak.org/NORAD/elements/noaa.txt", "filename": "tle_noaa.txt", "cache_days": 1},
    "goes": {"url": "https://celestrak.org/NORAD/elements/goes.txt", "filename": "tle_goes.txt", "cache_days": 1},
    "earth-resources": {"url": "https://celestrak.org/NORAD/elements/resource.txt", "filename": "tle_resource.txt", "cache_days": 1},
    "sarsat": {"url": "https://celestrak.org/NORAD/elements/sarsat.txt", "filename": "tle_sarsat.txt", "cache_days": 1},
    "disaster-monitoring": {"url": "https://celestrak.org/NORAD/elements/dmc.txt", "filename": "tle_dmc.txt", "cache_days": 1},
    "tdrss": {"url": "https://celestrak.org/NORAD/elements/tdrss.txt", "filename": "tle_tdrss.txt", "cache_days": 1},
    "argos": {"url": "https://celestrak.org/NORAD/elements/argos.txt", "filename": "tle_argos.txt", "cache_days": 1},
    "planet": {"url": "https://celestrak.org/NORAD/elements/planet.txt", "filename": "tle_planet.txt", "cache_days": 1},
    "spire": {"url": "https://celestrak.org/NORAD/elements/spire.txt", "filename": "tle_spire.txt", "cache_days": 1},

    # --- Communications Satellites ---
    "intelsat": {"url": "https://celestrak.org/NORAD/elements/intelsat.txt", "filename": "tle_intelsat.txt", "cache_days": 2},
    "ses": {"url": "https://celestrak.org/NORAD/elements/ses.txt", "filename": "tle_ses.txt", "cache_days": 2},
    "iridium": {"url": "https://celestrak.org/NORAD/elements/iridium.txt", "filename": "tle_iridium.txt", "cache_days": 1},
    "iridium-next": {"url": "https://celestrak.org/NORAD/elements/iridium-NEXT.txt", "filename": "tle_iridium-NEXT.txt", "cache_days": 1},
    "starlink": {"url": "https://celestrak.org/NORAD/elements/starlink.txt", "filename": "tle_starlink.txt", "cache_days": 1},
    "oneweb": {"url": "https://celestrak.org/NORAD/elements/oneweb.txt", "filename": "tle_oneweb.txt", "cache_days": 1},
    "orbcomm": {"url": "https://celestrak.org/NORAD/elements/orbcomm.txt", "filename": "tle_orbcomm.txt", "cache_days": 1},
    "globalstar": {"url": "https://celestrak.org/NORAD/elements/globalstar.txt", "filename": "tle_globalstar.txt", "cache_days": 1},
    "swarm": {"url": "https://celestrak.org/NORAD/elements/swarm.txt", "filename": "tle_swarm.txt", "cache_days": 1},
    "other-comm": {"url": "https://celestrak.org/NORAD/elements/other-comm.txt", "filename": "tle_other-comm.txt", "cache_days": 2},
    "gorizont": {"url": "https://celestrak.org/NORAD/elements/gorizont.txt", "filename": "tle_gorizont.txt", "cache_days": 2},
    "raduga": {"url": "https://celestrak.org/NORAD/elements/raduga.txt", "filename": "tle_raduga.txt", "cache_days": 2},
    "molniya": {"url": "https://celestrak.org/NORAD/elements/molniya.txt", "filename": "tle_molniya.txt", "cache_days": 1},

    # --- Amateur, Experimental, Educational, Scientific ---
    "amateur": { "url": "https://celestrak.org/NORAD/elements/amateur.txt", "filename": "tle_amateur.txt", "cache_days": 1 },
    "satnogs": {"url": "https://celestrak.org/NORAD/elements/satnogs.txt", "filename": "tle_satnogs.txt", "cache_days": 1},
    "experimental": {"url": "https://celestrak.org/NORAD/elements/experimental.txt", "filename": "tle_experimental.txt", "cache_days": 1},
    "education": {"url": "https://celestrak.org/NORAD/elements/education.txt", "filename": "tle_education.txt", "cache_days": 2},
    "science": {"url": "https://celestrak.org/NORAD/elements/science.txt", "filename": "tle_science.txt", "cache_days": 2},
    "geodetic": {"url": "https://celestrak.org/NORAD/elements/geodetic.txt", "filename": "tle_geodetic.txt", "cache_days": 2},
    "engineering": {"url": "https://celestrak.org/NORAD/elements/engineering.txt", "filename": "tle_engineering.txt", "cache_days": 2},
    "cubesat": {"url": "https://celestrak.org/NORAD/elements/cubesat.txt", "filename": "tle_cubesat.txt", "cache_days": 1},
    "other-misc": {"url": "https://celestrak.org/NORAD/elements/other.txt", "filename": "tle_other.txt", "cache_days": 1},

    # --- Military & Radar ---
    "military": {"url": "https://celestrak.org/NORAD/elements/military.txt", "filename": "tle_military.txt", "cache_days": 1},
    "radar": {"url": "https://celestrak.org/NORAD/elements/radar.txt", "filename": "tle_radar.txt", "cache_days": 1},
    "musson": {"url": "https://celestrak.org/NORAD/elements/musson.txt", "filename": "tle_musson.txt", "cache_days": 2 },

    # --- Recent Launches & Active ---
    "active": {"url": "https://celestrak.org/NORAD/elements/active.txt", "filename": "tle_active.txt", "cache_days": 1},
    "last-30-days": {"url": "https://celestrak.org/NORAD/elements/last-30-days.txt", "filename": "tle_last-30-days.txt", "cache_days": 1},
    "tle-new": { "url": "https://celestrak.org/NORAD/elements/tle-new.txt", "filename": "tle_tle-new.txt", "cache_days": 1 },

    # --- Geostationary & Special ---
    "geo": {"url": "https://celestrak.org/NORAD/elements/geo.txt", "filename": "tle_geo.txt", "cache_days": 2},

    # --- Visual ---
    "stations": { "url": "https://celestrak.org/NORAD/elements/stations.txt", "filename": "tle_stations.txt", "cache_days": 1 },
    "visual": { "url": "https://celestrak.org/NORAD/elements/visual.txt", "filename": "tle_visual.txt", "cache_days": 1 },

    # --- Third-Party Sources ---
    "amsat": {"url": "https://www.amsat.org/tle/current/nasabare.txt", "filename": "tle_nasabare.txt", "cache_days": 1},

    # --- Debris & Special Cases ---
    "asat-debris": {"url": "https://celestrak.org/NORAD/elements/asat.txt", "filename": "tle_asat.txt", "cache_days": 1},
    "classified": {"url": "https://celestrak.org/NORAD/elements/classified.txt", "filename": "tle_classified.txt", "cache_days": 1},

    # --- Sources Requiring Space-Track Login ---
    "geo-protected": {
        "url": "https://celestrak.org/NORAD/elements/geo-protected.txt",
        "filename": "tle_geo-protected.txt",
        "cache_days": 1,
        "auth_required": "space-track"
    },
    "geo-protected-plus": {
         "url": "https://celestrak.org/NORAD/elements/geo-protected-plus.txt",
         "filename": "tle_geo-protected-plus.txt",
         "cache_days": 1,
         "auth_required": "space-track"
    },
}