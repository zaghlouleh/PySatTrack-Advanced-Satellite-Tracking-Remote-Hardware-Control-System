# -*- coding: utf-8 -*-
import os
import json
import time
import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, Optional
from src.config.settings import (
    OPENCAGE_API_KEY, N2YO_API_KEY, SPACE_TRACK_USER, 
    SPACE_TRACK_PASSWORD, SATNOGS_CACHE_DIR
)
from src.utils.logger import logger

class APIClient:
    def __init__(self):
        self.opencage_key = OPENCAGE_API_KEY
        self.n2yo_key = N2YO_API_KEY
        
        # Space-Track Session
        self.space_track_session: Optional[requests.Session] = None
        self.space_track_logged_in: bool = False
        self._setup_space_track_session()

    def _setup_space_track_session(self):
        """Initializes the requests session and attempts Space-Track login."""
        if not SPACE_TRACK_USER or not SPACE_TRACK_PASSWORD:
            logger.warning("Space-Track credentials missing. Protected TLEs will be unavailable.")
            return

        if self.space_track_session is None:
            self.space_track_session = requests.Session()
            retry_strategy = Retry(
                total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self.space_track_session.mount("https://", adapter)
            self.space_track_session.mount("http://", adapter)
            self.space_track_session.headers.update({'User-Agent': 'SatelliteTrackerApp/1.0'})

        login_url = "https://www.space-track.org/ajaxauth/login"
        login_data = {'identity': SPACE_TRACK_USER, 'password': SPACE_TRACK_PASSWORD}

        try:
            logger.info(f"Attempting Space-Track login as {SPACE_TRACK_USER}...")
            response = self.space_track_session.post(login_url, data=login_data, timeout=25)
            response.raise_for_status()

            if response.status_code == 200 and len(response.text) < 100 and '</html>' not in response.text.lower():
                logger.info("Space-Track login successful.")
                self.space_track_logged_in = True
            else:
                logger.error(f"Space-Track login failed. Status: {response.status_code}")
                self.space_track_logged_in = False
        except Exception as e:
            logger.error(f"Network error during Space-Track login: {e}")
            self.space_track_logged_in = False

    def get_authenticated_session(self) -> Optional[requests.Session]:
        if self.space_track_logged_in and self.space_track_session:
            return self.space_track_session
        return None

    def get_geolocation(self, city):
        if not self.opencage_key: return None, None
        url = f"https://api.opencagedata.com/geocode/v1/json?q={city}&key={self.opencage_key}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if not data.get('results'): return None, None
            res = data['results'][0]
            return res['geometry']['lat'], res['geometry']['lng']
        except Exception as e:
            logger.error(f"Geo Err: {e}")
            return None, None

    def get_satellite_position(self, sat_id, lat, lng, alt):
        if not self.n2yo_key: return None
        url = f"https://api.n2yo.com/rest/v1/satellite/positions/{sat_id}/{lat}/{lng}/{alt}/2/&apiKey={self.n2yo_key}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"N2YO Err: {e}")
            return None

    def get_satnogs_frequencies(self, norad_id: int) -> Optional[Dict]:
        cache_file = os.path.join(SATNOGS_CACHE_DIR, f"{norad_id}.json")
        cache_age_sec = 172800 # 2 days
        
        if os.path.exists(cache_file) and (time.time() - os.path.getmtime(cache_file)) < cache_age_sec:
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass

        url = f"https://db.satnogs.org/api/transmitters/?satellite__norad_cat_id={norad_id}"
        headers = {'User-Agent': 'SatTracker/1.0'}
        processed = {'downlink_mhz': None, 'uplink_mhz': None, 'mode': None, 'beacon_mhz': None, 
                     'status': None, 'bandwidth_khz': None, 'baud': None, 'service': None, 'source': 'SatNOGS DB'}
        
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            transmitters = resp.json()
            if not transmitters: return None
            
            p = next((t for t in transmitters if t.get('downlink_low') and t.get('alive')), transmitters[0])
            if p:
                processed['downlink_mhz'] = f"{p.get('downlink_low', 0)/1e6:.4f}" if p.get('downlink_low') else None
                processed['mode'] = p.get('mode') or p.get('description')
                processed['status'] = "Alive" if p.get('alive') else "Inactive"
                processed['bandwidth_khz'] = f"{p.get('bandwidth', 0)/1e3:.1f}" if p.get('bandwidth') else None
                processed['baud'] = p.get('baud')
                processed['service'] = p.get('service')
            
            final = {k: v for k, v in processed.items() if v is not None}
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(final, f, indent=2)
            return final
        except Exception as e:
            logger.error(f"SatNOGS Err {norad_id}: {e}")
            return None