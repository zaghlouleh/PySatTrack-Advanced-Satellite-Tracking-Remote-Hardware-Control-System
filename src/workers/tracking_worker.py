import time
import logging
import math
from datetime import datetime, timezone
from PyQt5.QtCore import QThread, pyqtSignal
from src.core.calculator import CelestialCalculator
from src.services.api_client import APIClient
from src.core.data_manager import DataManager

logger = logging.getLogger(__name__)

class TrackingWorker(QThread):
    """Background thread for periodic satellite position updates and calculations."""
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, api: APIClient, data_manager: DataManager, config: dict):
        super().__init__()
        self.api = api
        self.data_manager = data_manager
        self.config = config
        self.running = True

    def run(self):
        """Main loop for the background worker."""
        while self.running:
            try:
                # 1. Fetch data from API
                response = self.api.get_satellite_position(
                    self.config['sat_id'],
                    self.config['obs_lat'],
                    self.config['obs_lng'],
                    self.config['obs_alt']
                )
                
                if not response or 'positions' not in response:
                    self.error_occurred.emit("Invalid API response from N2YO")
                    time.sleep(5)
                    continue
    
                positions = response.get('positions', [])
                if len(positions) < 2:
                    self.error_occurred.emit("Insufficient position data for calculations")
                    time.sleep(5)
                    continue
            
                # 2. Extract primary position
                first_pos = positions[0]
                
                # 3. Perform Orbital and Celestial Calculations
                altitude_km = first_pos.get('sataltitude')
                period_minutes = CelestialCalculator.calculate_orbital_period(altitude_km)
                
                speed_kms = CelestialCalculator.calculate_speed(positions)
                speed_mis = speed_kms * 0.621371
                
                now = datetime.now(timezone.utc)
                lst = CelestialCalculator.calculate_lst(self.config['obs_lng'], now)
                
                # 4. Construct the full data package
                full_data = {
                    'satlatitude': first_pos.get('satlatitude'),
                    'satlongitude': first_pos.get('satlongitude'),
                    'sataltitude': altitude_km,
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
                
                # 5. Save and Emit
                self.data_manager.save_satellite_data(
                    self.config['sat_name'],
                    full_data
                )
            
                self.data_ready.emit(full_data)
                
                # Sleep for the configured interval
                time.sleep(self.config['interval'])
                
            except Exception as e:
                logger.error(f"Worker Error: {str(e)}", exc_info=True)
                self.error_occurred.emit(f"Tracking Error: {str(e)}")
                time.sleep(5)
                
    def stop(self):
        """Gracefully stop the thread loop."""
        self.running = False