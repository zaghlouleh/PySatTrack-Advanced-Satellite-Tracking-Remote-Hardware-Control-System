# -*- coding: utf-8 -*-
from typing import Optional, Tuple
from src.api.base_client import BaseAPIClient
from src.utils.logger import logger

class GeocodeClient(BaseAPIClient):
    """
    Client for interacting with the OpenCage Geocoding API 
    to convert city/location names into geographic coordinates.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(base_url="https://api.opencagedata.com/geocode/v1/json")
        self.api_key = api_key

    def get_coordinates(self, city: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Converts a city name into a (latitude, longitude) tuple.
        Returns (None, None) if lookup fails.
        """
        if not self.api_key:
            logger.error("Geocode: API key missing.")
            return None, None

        if not city:
            logger.warning("Geocode: City name cannot be empty.")
            return None, None

        params = {
            'q': city,
            'key': self.api_key,
            'no_annotations': 1,  # Reduces payload size
            'limit': 1           # We only need the top result
        }

        logger.info(f"Geocode: Querying coordinates for '{city}'")
        data = self._get("", params=params)

        if data and 'results' in data and data['results']:
            best_match = data['results'][0]
            geometry = best_match.get('geometry', {})
            
            lat = geometry.get('lat')
            lng = geometry.get('lng')
            
            if lat is not None and lng is not None:
                logger.info(f"Geocode: Found coordinates for '{city}': ({lat:.4f}, {lng:.4f})")
                return float(lat), float(lng)
                
        logger.warning(f"Geocode: No coordinates found for location '{city}'.")
        return None, None