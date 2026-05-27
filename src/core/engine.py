# -*- coding: utf-8 -*-
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from skyfield.api import load, wgs84, EarthSatellite
from src.utils.logger import logger

class OrbitEngine:
    """
    Mathematical heart of SatTrack. 
    Handles high-volume TLE parsing for 65,000+ objects.
    """
    def __init__(self):
        self.ts = load.timescale()
        try:
            self.eph = load('de421.bsp')
            self.ready = True
        except:
            self.ready = False

    def parse_tle_file(self, filepath: str) -> Dict[str, Dict[str, Any]]:
        """
        Robust TLE Parser. Supports 2-line and 3-line formats.
        Prioritizes specific IDs for 65,000+ object database parity.
        """
        satellites = {}
        if not os.path.exists(filepath):
            return satellites

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f if line.strip()]

            i = 0
            while i < len(lines):
                line = lines[i]
                
                # Check if this is Line 1 of a TLE
                if line.startswith('1 '):
                    line1 = line
                    line2 = lines[i+1] if i+1 < len(lines) else None
                    
                    if line2 and line2.startswith('2 '):
                        # Parse NORAD ID as integer first, then store as string key
                        try:
                            norad_id_int = int(line1[2:7])
                            norad_id = str(norad_id_int)
                        except (ValueError, IndexError):
                            # If NORAD ID is malformed, skip this entry
                            i += 1
                            continue
                        
                        # Look for name on previous line (3-line format)
                        name = f"OBJECT {norad_id}"
                        if i > 0:
                            prev_line = lines[i-1]
                            if not prev_line.startswith('1 ') and not prev_line.startswith('2 '):
                                name = prev_line
                        
                        try:
                            # Epoch calculation for merging logic
                            epoch_yr = int(line1[18:20])
                            epoch_day = float(line1[20:32])
                            year = 2000 + epoch_yr if epoch_yr < 57 else 1900 + epoch_yr
                            epoch = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=epoch_day - 1)

                            satellites[norad_id] = {
                                'name': name,
                                'norad_id': norad_id_int,
                                'line1': line1,
                                'line2': line2,
                                'epoch': epoch
                            }
                        except: 
                            pass
                        i += 2
                        continue
                i += 1
            return satellites
        except Exception as e:
            logger.error(f"Engine: Bulk parse error: {e}")
            return {}

    def get_sun_position(self, dt):
        if not self.ready: return 0, 0
        t = self.ts.from_datetime(dt.astimezone(timezone.utc))
        subpoint = wgs84.subpoint(self.eph['earth'].at(t).observe(self.eph['sun']))
        return subpoint.latitude.degrees, subpoint.longitude.degrees

    def get_moon_position(self, dt):
        if not self.ready: return 0, 0
        t = self.ts.from_datetime(dt.astimezone(timezone.utc))
        subpoint = wgs84.subpoint(self.eph['earth'].at(t).observe(self.eph['moon']))
        return subpoint.latitude.degrees, subpoint.longitude.degrees

