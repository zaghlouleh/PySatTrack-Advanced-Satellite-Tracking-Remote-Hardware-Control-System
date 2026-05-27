import logging
import requests
from typing import Dict, Optional, Tuple
from src.config.settings import OPENCAGE_KEY, N2YO_KEY

logger = logging.getLogger(__name__)

class APIClient:
    """Handles all API communications for geolocation and satellite data."""

    def get_geolocation(self, city: str) -> Tuple[Optional[float], Optional[float]]:
        """Fetches latitude and longitude for a given city string."""
        logging.info(f"Fetching geolocation data for city: {city}")
        endpoint = f"https://api.opencagedata.com/geocode/v1/json?q={city}&key={OPENCAGE_KEY}"
    
        try:
            response = requests.get(endpoint, timeout=10)
            
            if response.status_code == 401:
                logging.error("Authentication failed for OpenCage API. Check your API key.")
                return None, None
            elif response.status_code != 200:
                logging.error(f"Failed to fetch geolocation: HTTP {response.status_code}")
                return None, None
            
            data = response.json()
            if 'results' in data and data['results']:
                result = data['results'][0]
                lat = result['geometry']['lat']
                lng = result['geometry']['lng']
                logging.info(f"Geolocation found: {lat}, {lng}")
                return lat, lng
            else:
                logging.error(f"No results found for city: {city}")
                return None, None
    
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during geolocation: {str(e)}")
            return None, None
        except Exception as e:
            logger.error(f"Unexpected geolocation error: {str(e)}", exc_info=True)
            return None, None

    def get_satellite_position(self, sat_id: int, lat: float, lng: float, alt: float) -> Optional[Dict]:
        """Fetches current and future satellite positions from N2YO."""
        try:
            # Request 2 positions to allow speed calculation between timestamps
            url = f"https://api.n2yo.com/rest/v1/satellite/positions/{sat_id}/{lat}/{lng}/{alt}/2/&apiKey={N2YO_KEY}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                logging.error(f"N2YO API returned status code {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Satellite position API error: {str(e)}", exc_info=True)
            return None