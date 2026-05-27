import requests
import logging
from typing import Optional, Dict, Tuple
from src.config import OPENCAGE_API_KEY, N2YO_API_KEY

class APIClient:
    """Handles all API communications for Geolocation and Satellite data"""

    def get_geolocation(self, city: str) -> Tuple[Optional[float], Optional[float]]:
        """Fetch latitude and longitude for a given city string using OpenCage API"""
        logging.info(f"Fetching geolocation data for city: {city}")
        url = f"https://api.opencagedata.com/geocode/v1/json?q={city}&key={OPENCAGE_API_KEY}"

        try:
            response = requests.get(url)
            
            # Check for authentication failure
            if response.status_code == 401:
                logging.error("Authentication failed for OpenCage API. Please check your API key.")
                return None, None
            elif response.status_code != 200:
                logging.error(f"Failed to fetch geolocation data: {response.status_code}")
                return None, None
            
            data = response.json()
            if 'results' in data and data['results']:
                result = data['results'][0]
                lat = result['geometry']['lat']
                lng = result['geometry']['lng']
                return lat, lng
            else:
                logging.error("No geolocation data found in the API response.")
                return None, None

        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching geolocation data: {str(e)}")
            return None, None

    def get_satellite_position(self, sat_id: int, lat: float, lng: float, alt: float) -> Optional[Dict]:
        """Fetch current and next satellite positions from N2YO API"""
        try:
            # Request 2 positions to calculate speed (matching original logic)
            url = f"https://api.n2yo.com/rest/v1/satellite/positions/{sat_id}/{lat}/{lng}/{alt}/2/&apiKey={N2YO_API_KEY}"
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                logging.error(f"N2YO API error: Status {response.status_code}")
                return None
        except Exception as e:
            logging.error(f"Satellite position request failed: {str(e)}")
            return None