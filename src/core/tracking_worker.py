# -*- coding: utf-8 -*-
import math
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from PyQt5.QtCore import QThread, pyqtSignal
from src.api.n2yo_client import N2YOClient
from src.managers.data_manager import DataManager
from src.core.engine import OrbitEngine
from src.utils.logger import logger

class TrackingWorker(QThread):
    """
    Continuous background worker that polls N2YO for real-time 
    satellite telemetry and emits processed data to the UI.
    """
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, api: N2YOClient, data_manager: DataManager, config: Dict[str, Any]):
        super().__init__()
        self.api = api
        self.data_manager = data_manager
        self.config = config
        self.running = True
        self.engine = OrbitEngine()
        self.previous_pos: Optional[Dict[str, float]] = None
        self.setObjectName(f"Tracking_{config.get('sat_name', 'Unknown')}")

    def calculate_lst(self, longitude: float, dt: datetime) -> float:
        """Calculates Local Sidereal Time (LST) in hours."""
        try:
            t = self.engine.ts.from_datetime(dt)
            gmst = t.gmst
            lst_hours = (gmst + longitude / 15.0) % 24.0
            return round(lst_hours, 4)
        except Exception:
            return 0.0

    def calculate_speed(self, current_pos: Dict[str, Any]) -> float:
        """Calculates instantaneous speed (km/s) based on the distance from the previous point."""
        if not self.previous_pos:
            self.previous_pos = current_pos
            return 0.0

        p1 = self.previous_pos
        p2 = current_pos
        
        try:
            lat1, lon1 = math.radians(p1['satlatitude']), math.radians(p1['satlongitude'])
            lat2, lon2 = math.radians(p2['satlatitude']), math.radians(p2['satlongitude'])
            
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance_km = 6371 * c 
            
            time_diff = p2['timestamp'] - p1['timestamp']
            
            if time_diff <= 0: return 0.0
            
            self.previous_pos = p2
            return distance_km / time_diff
        except Exception as e:
            logger.error(f"TrackingWorker: Speed calculation error: {e}")
            return 0.0

    def run(self):
        """Main loop for polling telemetry."""
        logger.info(f"TrackingWorker: Started for {self.config.get('sat_name')}")
        
        # Use the interval from config, fallback to 10 seconds
        interval = self.config.get('interval', 10)
        
        while self.running:
            start_time = time.time()
            try:
                # FIXED: Standardized configuration keys to match MainWindow.start_tracking()
                # obs_lat -> lat, obs_lng -> lng, obs_alt -> alt
                response = self.api.get_satellite_position(
                    self.config['sat_id'],
                    self.config['lat'],
                    self.config['lng'],
                    self.config['alt']
                )
                logger.info(f"TrackingWorker N2YO resp ({len(response) if response else 0} keys): positions={len(response.get('positions', [])) if response else 0} | keys={list(response.keys()) if response else 'None'}")

                if response and 'positions' in response and response['positions']:
                    latest_pos = response['positions'][0]
                    info = response.get('info', {})
                    
                    # Process and Enrich Data
                    pos_dt = datetime.fromtimestamp(latest_pos['timestamp'], tz=timezone.utc)
                    speed_kms = self.calculate_speed(latest_pos)
                    lst = self.calculate_lst(self.config['lng'], pos_dt)
                    
                    # Merge with configuration
                    full_data = self.config.copy()
                    full_data.update({
                        'sat_name': info.get('satname', self.config['sat_name']),
                        'norad_id': info.get('norad_cat_id', self.config['sat_id']),
                        'satlatitude': latest_pos['satlatitude'],
                        'satlongitude': latest_pos['satlongitude'],
                        'sataltitude': latest_pos['sataltitude'],
                        'azimuth': latest_pos['azimuth'],
                        'elevation': latest_pos['elevation'],
                        'ra': latest_pos.get('ra', 0),
                        'dec': latest_pos.get('dec', 0),
                        'timestamp': latest_pos['timestamp'],
                        'speed_kms': round(speed_kms, 3),
                        'speed_mis_s': round(speed_kms * 0.621371, 3),
                        'lst': lst,
                        'eclipsed': latest_pos.get('eclipsed', False)
                    })

                    logger.info(f"TrackingWorker EMIT ({len(full_data)} keys): {sorted(full_data.keys())} | ex: lat={full_data['satlatitude']:.3f}, alt={full_data['sataltitude']:.0f}")
                    self.data_ready.emit(full_data)
                    self.data_manager.save_satellite_telemetry(full_data['sat_name'], full_data)
                else:
                    msg = "N2YO API Error: No position data returned."
                    logger.error(msg)
                    self.error_occurred.emit(msg)

            except Exception as e:
                err_msg = f"Tracking Error: {str(e)}"
                logger.exception(err_msg)
                self.error_occurred.emit(err_msg)

            # Controlled sleep
            elapsed = time.time() - start_time
            sleep_time = max(0.5, interval - elapsed)
            time.sleep(sleep_time)

    def stop(self):
        """Signals the loop to terminate."""
        self.running = False
        logger.info(f"TrackingWorker: Stop signal received for {self.config.get('sat_name')}")