# -*- coding: utf-8 -*-

DEFAULT_TLE_SOURCES = {
    # =================================================================================
    # === A. SPACE-TRACK SOURCES (With DESIRED Filters)                            ===
    # =================================================================================
    "space-track-main-catalog": {
        "name": "Space-Track Full Catalog (GP)",
        "description": "The main, high-fidelity catalog from Space-Track. Requires login.",
        "group": "Space-Track (Login Required)",
        "filename": "tle_space-track-gp-main.txt", 
        "cache_days": 1, 
        "auth_required": "space-track",
        "query_class": "gp",
        "query_filters": {
            "DECAYED": "false",
            "NORAD_CAT_ID": "< 90000",
            "orderby": "NORAD_CAT_ID"
        }
    },
    "space-track-supplemental-catalog": {
        "name": "Space-Track Supplemental (Analyst/Debris)",
        "description": "Supplemental data for analyst objects and other debris. Requires login.",
        "group": "Space-Track (Login Required)",
        "filename": "tle_space-track-gp-supplemental.txt", 
        "cache_days": 1, 
        "auth_required": "space-track",
        "query_class": "gp",
        "query_filters": {
            "DECAYED": "false",
            "NORAD_CAT_ID": ">= 90000",
            "orderby": "NORAD_CAT_ID"
        }
    },

    # =================================================================================
    # === B. CORE PUBLIC CATALOGS (The Essential Fallback)                          ===
    # =================================================================================
    "active": {
        "name": "All Active Satellites (CelesTrak)",
        "description": "A comprehensive public list of all currently active satellites.",
        "group": "Core Public Catalogs",
        "url": [
            "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle", 
            "https://celestrak.com/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"
        ],
        "filename": "tle_active.txt", 
        "cache_days": 1
    },
    "last-30-days": {
        "name": "Last 30 Days' Launches", 
        "group": "Core Public Catalogs", 
        "url": [
            "https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=tle", 
            "https://celestrak.com/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=tle"
        ], 
        "filename": "tle_last-30-days.txt", 
        "cache_days": 1
    },
    "stations": {
        "name": "Space Stations", 
        "group": "Specialized Public Catalogs", 
        "url": [
            "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle", 
            "https://celestrak.com/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle"
        ], 
        "filename": "tle_stations.txt", 
        "cache_days": 1
    },
    "visual": {
        "name": "100 Brightest", 
        "group": "Specialized Public Catalogs", 
        "url": [
            "https://celestrak.org/NORAD/elements/gp.php?GROUP=visual&FORMAT=tle", 
            "https://celestrak.com/NORAD/elements/gp.php?GROUP=visual&FORMAT=tle"
        ], 
        "filename": "tle_visual.txt", 
        "cache_days": 1
    },
    "amsat": {
        "name": "Amateur Radio", 
        "group": "Specialized Public Catalogs", 
        "url": "https://www.amsat.org/tle/current/nasabare.txt", 
        "filename": "tle_nasabare.txt", 
        "cache_days": 1
    },
    "weather": {
        "name": "Weather Satellites",
        "description": "Satellites used for weather forecasting and meteorology.",
        "group": "Weather & Earth Resources",
        "url": [
            "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle", 
            "https://celestrak.com/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle"
        ],
        "filename": "tle_weather.txt", 
        "cache_days": 1
    },
    "noaa": {
        "name": "NOAA Constellation",
        "description": "Satellites from the National Oceanic and Atmospheric Administration.",
        "group": "Weather & Earth Resources",
        "url": [
            "https://celestrak.org/NORAD/elements/gp.php?GROUP=noaa&FORMAT=tle", 
            "https://celestrak.com/NORAD/elements/gp.php?GROUP=noaa&FORMAT=tle"
        ],
        "filename": "tle_noaa.txt", 
        "cache_days": 1
    },
    "goes": {
        "name": "GOES Constellation",
        "description": "Geostationary Operational Environmental Satellites.",
        "group": "Weather & Earth Resources",
        "url": [
            "https://celestrak.org/NORAD/elements/gp.php?GROUP=goes&FORMAT=tle", 
            "https://celestrak.com/NORAD/elements/gp.php?GROUP=goes&FORMAT=tle"
        ],
        "filename": "tle_goes.txt", 
        "cache_days": 1
    },
    "earth-resources": {
        "name": "Earth Resources",
        "description": "Satellites for observing Earth's environment and resources.",
        "group": "Weather & Earth Resources",
        "url": [
            "https://celestrak.org/NORAD/elements/gp.php?GROUP=resource&FORMAT=tle", 
            "https://celestrak.com/NORAD/elements/gp.php?GROUP=resource&FORMAT=tle"
        ],
        "filename": "tle_earth-resources.txt", 
        "cache_days": 1
    },
    "science": {
        "name": "Science Satellites",
        "description": "Satellites dedicated to scientific research missions.",
        "group": "Specialized Public Catalogs",
        "url": [
            "https://celestrak.org/NORAD/elements/gp.php?GROUP=science&FORMAT=tle", 
            "https://celestrak.com/NORAD/elements/gp.php?GROUP=science&FORMAT=tle"
        ],
        "filename": "tle_science.txt", 
        "cache_days": 1
    }
}