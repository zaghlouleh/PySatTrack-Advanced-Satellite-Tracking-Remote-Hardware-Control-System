# -*- coding: utf-8 -*-
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from PyQt5.QtCore import QThread, pyqtSignal
from skyfield.api import wgs84, EarthSatellite
from src.core.engine import OrbitEngine
from src.utils.logger import logger

class PredictionWorker(QThread):
    """
    Background worker that calculates the future orbit path 
    and predicts the next pass for a selected satellite.
    """
    prediction_ready = pyqtSignal(dict)
    
    def __init__(self, sat_info: Dict[str, Any], obs_lat: float, obs_lng: float, obs_alt: float):
        super().__init__()
        self.sat_info = sat_info
        self.obs_lat = obs_lat
        self.obs_lng = obs_lng
        self.obs_alt = obs_alt
        self.engine = OrbitEngine()
        self.observer_location = wgs84.latlon(obs_lat, obs_lng, elevation_m=obs_alt)

    def run(self):
        """Executes the skyfield calculations and emits results."""
        try:
            sat_name = self.sat_info.get('name', 'UNKNOWN')
            satellite = EarthSatellite(
                self.sat_info['line1'], 
                self.sat_info['line2'], 
                sat_name, 
                self.engine.ts
            )
            
            logger.info(f"PredictionWorker: Calculating orbit for {sat_name}")
            
            # 1. Calculate the ground track for the next 95 minutes
            # FIXED: Python 3.13 does not allow timedelta * range. 
            # Using list comprehension for cross-version compatibility.
            now = self.engine.ts.now().utc_datetime()
            times_list = [now + timedelta(minutes=i) for i in range(95)]
            times = self.engine.ts.from_datetimes(times_list)
            
            geocentric = satellite.at(times)
            subpoints = wgs84.subpoint_of(geocentric)
            
            orbit_points = []
            lats = subpoints.latitude.degrees
            longs = subpoints.longitude.degrees
            
            for lat, lon in zip(lats, longs):
                orbit_points.append([float(lat), float(lon)])

            # 2. Predict next pass within a 2-day window
            t0 = self.engine.ts.now()
            t1 = self.engine.ts.utc(t0.utc_datetime() + timedelta(days=2))
            
            times_events, events = satellite.find_events(self.observer_location, t0, t1, altitude_degrees=0.1)
            
            pass_data = {}
            next_pass_events = {}
            
            for ti, event in zip(times_events, events):
                if event == 0 and 'rise' not in next_pass_events: 
                    next_pass_events['rise'] = ti
                elif event == 1 and 'rise' in next_pass_events and 'max' not in next_pass_events: 
                    next_pass_events['max'] = ti
                elif event == 2 and 'max' in next_pass_events and 'set' not in next_pass_events: 
                    next_pass_events['set'] = ti
                    break 

            pass_path_points = []
            if 'set' in next_pass_events:
                pass_data['rise_time_utc'] = next_pass_events['rise'].utc_datetime()
                pass_data['set_time_utc'] = next_pass_events['set'].utc_datetime()
                
                difference = satellite - self.observer_location
                alt, _, _ = difference.at(next_pass_events['max']).altaz()
                pass_data['max_el'] = f"{alt.degrees:.1f}°"
                
                # Generate pass ground track
                pass_times = self.engine.ts.linspace(next_pass_events['rise'], next_pass_events['set'], 50)
                pass_subpoints = wgs84.subpoint_of(satellite.at(pass_times))
                
                for lat, lon in zip(pass_subpoints.latitude.degrees, pass_subpoints.longitude.degrees):
                    pass_path_points.append([float(lat), float(lon)])

            result = {
                "orbit_path": orbit_points,
                "pass_details": pass_data,
                "pass_path": pass_path_points
            }
            
            self.prediction_ready.emit(result)
            
        except Exception as e:
            logger.exception(f"PredictionWorker: Error during calculation: {e}")
            self.prediction_ready.emit({})