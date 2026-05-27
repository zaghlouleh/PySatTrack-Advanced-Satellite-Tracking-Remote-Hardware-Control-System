# -*- coding: utf-8 -*-
import os
import json
import time
from typing import Optional, Dict, Any
from src.api.base_client import BaseAPIClient
from src.utils.logger import logger

# Get project root for cache directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class N2YOClient(BaseAPIClient):
    """
    Client for fetching real-time satellite positions from N2YO 
    and radio frequency data from SatNOGS.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(base_url="https://api.n2yo.com/rest/v1/satellite")
        self.api_key = api_key
        self.cache_dir = os.path.join(PROJECT_ROOT, "satnogs_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_satellite_position(self, 
                               norad_id: int, 
                               obs_lat: float, 
                               obs_lng: float, 
                               obs_alt: float, 
                               seconds: int = 1) -> Optional[Dict]:
        """
        Fetches the real-time position of a satellite relative to an observer.
        """
        if not self.api_key:
            logger.error("N2YO: API key missing.")
            return None

        # N2YO format: /positions/{id}/{obs_lat}/{obs_lng}/{obs_alt}/{seconds}/&apiKey={key}
        endpoint = f"/positions/{norad_id}/{obs_lat}/{obs_lng}/{obs_alt}/{seconds}/&apiKey={self.api_key}"
        
        data = self._get(endpoint)
        if data and 'positions' in data:
            return data
        
        logger.warning(f"N2YO: Failed to retrieve positions for NORAD {norad_id}")
        return None

    def get_frequency_data(self, norad_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches satellite radio frequencies from SatNOGS DB with 2-day local caching.
        """
        cache_file = os.path.join(self.cache_dir, f"{norad_id}.json")
        cache_age_limit = 2 * 86400  # 48 hours

        # 1. Try to load from local cache
        if os.path.exists(cache_file):
            try:
                if (time.time() - os.path.getmtime(cache_file)) < cache_age_limit:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        logger.debug(f"SatNOGS: Loaded cache for {norad_id}")
                        return json.load(f)
            except Exception as e:
                logger.warning(f"SatNOGS: Cache read error for {norad_id}: {e}")

        # 2. Fetch from SatNOGS API
        url = f"https://db.satnogs.org/api/transmitters/?satellite__norad_cat_id={norad_id}"
        logger.info(f"SatNOGS: Fetching transmitter data for {norad_id}")
        
        try:
            # Note: We use the base session from BaseAPIClient for retries/headers
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            transmitters = resp.json()
            
            if not transmitters:
                # Cache an empty result to avoid hitting the API again immediately
                with open(cache_file, 'w') as f: json.dump({}, f)
                return None

            # Process the transmitter data (picking the most likely downlink)
            processed = {}
            primary = next((t for t in transmitters if t.get('downlink_low')), None)
            
            if primary:
                processed = {
                    'downlink_mhz': f"{primary.get('downlink_low', 0) / 1e6:.4f}",
                    'mode': primary.get('mode') or primary.get('description'),
                    'status': "Alive" if primary.get('alive') else "Inactive",
                    'bandwidth_khz': f"{primary.get('bandwidth', 0) / 1e3:.2f}" if primary.get('bandwidth') else "---",
                    'service': primary.get('service') or "N/A"
                }
            
            # Save to cache
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(processed, f, indent=2)
                
            return processed if processed else None
        
        except Exception as e:
            logger.error(f"SatNOGS: Network error for {norad_id}: {e}")
            return None