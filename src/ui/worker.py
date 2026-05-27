import time
import math
import logging
from datetime import datetime, timezone
from PyQt5.QtCore import QThread, pyqtSignal
from src.services.api_client import APIClient
from src.services.data_manager import DataManager

class WorkerThread(QThread):
    """Background thread for fetching and processing satellite data"""
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, api: APIClient, data_manager: DataManager, config: dict):
        super().__init__()
        self.api = api
        self.data_manager = data_manager
        self.config = config
        self.running = True

    def calculate_lst(self, longitude: float, dt: datetime) -> float:
        """Calculate Local Sidereal Time"""
        jd = (dt - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400 + 2451545
        gmst = 18.697374558 + 24.06570982441908 * (jd - 2451545)
        lst = (gmst + longitude/15) % 24
        return round(lst, 4)

    def calculate_speed(self, positions):
        """Calculate speed using Haversine formula between two points"""
        if len(positions) < 2:
            return 0.0
        
        # Get first two positions
        p1 = positions[0]
        p2 = positions[1]
        
        # Convert degrees to radians
        lat1 = math.radians(p1['satlatitude'])
        lon1 = math.radians(p1['satlongitude'])
        lat2 = math.radians(p2['satlatitude'])
        lon2 = math.radians(p2['satlongitude'])
        
        # Haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance_km = 6371 * c  # Earth radius in km
        
        # Time difference in hours
        time_diff = (p2['timestamp'] - p1['timestamp']) / 3600
        return distance_km / time_diff if time_diff != 0 else 0.0

    def run(self):
        while self.running:
            try:
                response = self.api.get_satellite_position(
                    self.config['sat_id'],
                    self.config['obs_lat'],
                    self.config['obs_lng'],
                    self.config['obs_alt']
                )
                
                if response and 'positions' in response and len(response['positions']) >= 2:
                    positions = response['positions']
                    first_pos = positions[0]
                    
                    # Calculate orbital period using Kepler's third law
                    altitude_km = first_pos.get('sataltitude')
                    period_minutes = None
                    if altitude_km is not None:
                        earth_radius_km = 6371.0  # Average Earth radius
                        mu = 398600.4418          # Earth's gravitational parameter (km³/s²)
                        a = earth_radius_km + altitude_km
                        T_seconds = 2 * math.pi * math.sqrt(a**3 / mu)
                        period_minutes = round(T_seconds / 60, 2)
                    
                    # Calculate speed
                    speed_kms = self.calculate_speed(positions)
                    speed_mis = speed_kms * 0.621371
                    
                    # Calculate LST
                    now = datetime.now(timezone.utc)
                    lst = self.calculate_lst(self.config['obs_lng'], now)
                    
                    full_data = {
                        'satlatitude': first_pos.get('satlatitude'),
                        'satlongitude': first_pos.get('satlongitude'),
                        'sataltitude': first_pos.get('sataltitude'),
                        'azimuth': first_pos.get('azimuth'),
                        'elevation': first_pos.get('elevation'),
                        'ra': first_pos.get('ra'),
                        'dec': first_pos.get('dec'),
                        'lst': lst,
                        'speed_kms': speed_kms,
                        'speed_mis': speed_mis,
                        'period': period_minutes or response.get('info', {}).get('period'),
                        'eclipsed': first_pos.get('eclipsed', False),
                        'timestamp': now.isoformat(),
                        'observer': {
                            'latitude': self.config['obs_lat'],
                            'longitude': self.config['obs_lng'],
                            'altitude': self.config['obs_alt']
                        }
                    }
                    
                    self.data_manager.save_satellite_data(self.config['sat_name'], full_data)
                    self.data_ready.emit(full_data)
                else:
                    self.error_occurred.emit("No position data received")
                
                time.sleep(self.config['interval'])
                
            except Exception as e:
                self.error_occurred.emit(str(e))
                time.sleep(5)
                
    def stop(self):
        self.running = False