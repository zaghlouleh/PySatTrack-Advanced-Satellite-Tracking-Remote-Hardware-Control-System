import os

# API Configurations
N2YO_API_KEY = "Add_Your_N2YO_API_KEY"
N2YO_BASE_URL = "https://api.n2yo.com/rest/v1/satellite/tle"

# API Limits
MAX_RETRIES = 3
RETRY_DELAY = 20  # seconds
TIMEOUT = 50      # seconds

# Database Configurations
DB_FILENAME = "namesat+idsat.json"

# UI Configurations
THEME_NAME = "arc"
WINDOW_TITLE = "Satellite Tracker & Arduino Exporter"
WINDOW_GEOMETRY = "450x600"

# Styling Constants
FONT_FAMILY = "Helvetica"
FONT_MONO = "Courier New"

COLOR_BG = "#f2f2f2"
COLOR_SUCCESS = "green"
COLOR_ERROR = "red"

STYLE_LABEL = {"font": (FONT_FAMILY, 11), "bg": COLOR_BG}
STYLE_ENTRY = {
    "font": (FONT_FAMILY, 11), 
    "relief": "flat", 
    "highlightthickness": 1, 
    "highlightbackground": "#cccccc",
    "highlightcolor": "#4caf50"
}
STYLE_BUTTON = {
    "font": (FONT_FAMILY, 11, "bold"), 
    "bg": "#4caf50", 
    "fg": "white", 
    "activebackground": "#45a049", 
    "relief": "raised"
}
STYLE_TEXT = {
    "font": (FONT_MONO, 10), 
    "bg": "#ffffff", 
    "highlightthickness": 1, 
    "highlightbackground": "#cccccc"
}