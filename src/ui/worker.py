# -*- coding: utf-8 -*-
import time
import math
import logging
from datetime import datetime, timezone
from PyQt5.QtCore import QThread, pyqtSignal
from src.core.calculations import SKYFIELD_AVAILABLE, load
from src.utils.logger import logger

class WorkerThread(QThread):
    """
    Background thread that handles periodic API polling and 
    coordinate calculations for a specific satellite.
    """
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, api, data_manager, config):
        super().__init__()
        self.api = api
        self.data_manager = data_manager
        self.config = config
        self.running = True
        self.setObjectName(f"Worker_{config.get('sat_name', 'Unknown')}")

    def calculate_lst(self, longitude: float, dt: datetime) -> float:
        """Calculates Local Sidereal Time using Skyfield if available."""
        if not SKYFIELD_AVAILABLE:
            return 0.0
        try:
            ts = load.timescale()
            t = ts.from_datetime(dt)
            gmst = t.gmst
            lst_hours = (gmst + longitude / 15.0) % 24.0
            return round(lst_hours, 4)
        except Exception:
            return 0.0

    def calculate_speed(self, positions):
        """Calculates satellite speed (km/s) between two points using Haversine."""
        if len(positions) < 2:
            return 0.0
        
        positions.sort(key=lambda p: p.get('timestamp', 0))
        p2 = positions[-1]
        p1 = positions[-2]
        
        try:
            lat1, lon1 = math.radians(p1['satlatitude']), math.radians(p1['satlongitude'])
            lat2, lon2 = math.radians(p2['satlatitude']), math.radians(p2['satlongitude'])
            
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance_km = 6371 * c
            
            time_diff_sec = p2['timestamp'] - p1['timestamp']
            if time_diff_sec <= 0:
                return 0.0
                
            return distance_km / time_diff_sec
        except (KeyError, TypeError, ZeroDivisionError):
            return 0.0

    def run(self):
        """Main execution loop for the worker thread."""
        logger.info(f"Worker thread started for {self.config.get('sat_name', 'Unknown')}")
        
        while self.running:
            start_time = time.time()
            try:
                # 1. Fetch Position Data from N2YO
                n2yo_response = self.api.get_satellite_position(
                    self.config['sat_id'],
                    self.config['obs_lat'],
                    self.config['obs_lng'],
                    self.config['obs_alt']
                )

                if n2yo_response is None:
                    self.error_occurred.emit("Failed to get satellite data from N2YO.")
                    time.sleep(10)
                    continue

                n2yo_positions = n2yo_response.get('positions', [])
                n2yo_info = n2yo_response.get('info', {})

                if not n2yo_positions:
                    self.error_occurred.emit("No position data received from N2YO.")
                    time.sleep(5)
                    continue

                # 2. Process Data
                latest_pos = n2yo_positions[0]
                speed_kms = self.calculate_speed(n2yo_positions) if len(n2yo_positions) >= 2 else 0.0
                pos_time_utc = datetime.fromtimestamp(latest_pos.get('timestamp', time.time()), tz=timezone.utc)
                lst = self.calculate_lst(self.config['obs_lng'], pos_time_utc)

                # 3. Merge Config (TLE/Frequencies) with Real-time API data
                full_data = self.config.copy()
                full_data.update({
                    'sat_id': n2yo_info.get('satid', self.config['sat_id']),
                    'sat_name': n2yo_info.get('satname', self.config['sat_name']),
                    'norad_id': n2yo_info.get('norad_cat_id', self.config['sat_id']),
                    'satlatitude': latest_pos.get('satlatitude'),
                    'satlongitude': latest_pos.get('satlongitude'),
                    'sataltitude': latest_pos.get('sataltitude'),
                    'azimuth': latest_pos.get('azimuth'),
                    'elevation': latest_pos.get('elevation'),
                    'ra': latest_pos.get('ra'),
                    'dec': latest_pos.get('dec'),
                    'timestamp': latest_pos.get('timestamp'),
                    'timestamp_iso': pos_time_utc.isoformat(),
                    'speed_kms': round(speed_kms, 3),
                    'speed_mis_s': round(speed_kms * 0.621371, 3),
                    'lst': lst,
                    'eclipsed': latest_pos.get('eclipsed', False),
                })

                # 4. Notify UI and Save to disk
                self.data_ready.emit(full_data)
                self.data_manager.save_satellite_data(full_data['sat_name'], full_data)

            except Exception as e:
                logger.exception("Error in worker thread:")
                self.error_occurred.emit(f"Worker error: {str(e)}")
                time.sleep(5)

            # Wait for the remainder of the interval
            elapsed = time.time() - start_time
            sleep_duration = max(0.1, self.config.get('interval', 10) - elapsed)
            time.sleep(sleep_duration)

        logger.info(f"Worker thread stopped for {self.config.get('sat_name', 'Unknown')}")

    def stop(self):
        self.running = False