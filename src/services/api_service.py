import requests
import logging
from src.config import OPENCAGE_API_KEY, N2YO_API_KEY

def fetch_geolocation_data(city_name):
    """Fetches latitude and longitude for a given city name using OpenCage API."""
    opencage_api_endpoint = f"https://api.opencagedata.com/geocode/v1/json?q={city_name}&key={OPENCAGE_API_KEY}"
    
    try:
        response = requests.get(opencage_api_endpoint)
        response.raise_for_status()
        
        geolocation_data = response.json()
        
        if 'results' in geolocation_data and geolocation_data['results']:
            result = geolocation_data['results'][0]
            lat = result['geometry']['lat']
            lng = result['geometry']['lng']
            return lat, lng
        else:
            logging.error(f"No geolocation data found for city: {city_name}")
            return None, None
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching geolocation data: {str(e)}")
        return None, None

def fetch_satellite_position(observer_lat, observer_lng, observer_alt, seconds, satellite_id):
    """Fetches real-time satellite position using N2YO API."""
    n2yo_api_endpoint = f"https://api.n2yo.com/rest/v1/satellite/positions/{satellite_id}/{observer_lat}/{observer_lng}/{observer_alt}/{seconds}/&apiKey={N2YO_API_KEY}"
    
    try:
        response = requests.get(n2yo_api_endpoint)
        response.raise_for_status()
        
        position_data = response.json()
        positions = position_data.get('positions', [])
        
        if not positions:
            logging.error(f"No position data found for satellite ID: {satellite_id}")
            return None
        
        # Extract the latest position data
        latest_position = positions[-1]
        return {
            'satlatitude': latest_position.get('satlatitude'),
            'satlongitude': latest_position.get('satlongitude'),
            'sataltitude': latest_position.get('sataltitude'),
            'azimuth': latest_position.get('azimuth'),
            'elevation': latest_position.get('elevation')
        }
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching satellite position: {str(e)}")
        return None