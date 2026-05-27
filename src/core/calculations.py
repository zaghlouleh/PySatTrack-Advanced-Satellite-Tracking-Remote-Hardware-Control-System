# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timezone
from src.utils.logger import logger

# --- Skyfield Import and Fallbacks ---
try:
    from skyfield.api import load, wgs84
    from skyfield.sgp4lib import EarthSatellite
    SKYFIELD_AVAILABLE = True
except ImportError:
    logger.critical("Skyfield library not found. Calculations will be disabled.")
    SKYFIELD_AVAILABLE = False
    
    # Dummy classes to prevent NameErrors
    class EarthSatellite:
        def __init__(self, l1, l2, n): 
            self.model = type('model', (object,), {'satnum': 0})()
    
    class DummyTimescale:
        def from_datetime(self, dt): return None
        def now(self): return None
    
    class DummyLoad:
        def timescale(self): return DummyTimescale()
        def ephemeris(self, name): return None
    
    class DummyWGS84:
         def subpoint(self, pos): 
             return type('subpoint', (object,), {
                 'latitude': type('lat', (object,), {'degrees': 0.0})(), 
                 'longitude': type('lon', (object,), {'degrees': 0.0})()
             })()
    
    load = DummyLoad()
    wgs84 = DummyWGS84()

class CelestialCalculator:
    @staticmethod
    def sun_position(dt):
        if not SKYFIELD_AVAILABLE: 
            return 0.0, 0.0
        try:
            ts = load.timescale()
            eph = load('de421.bsp')
            sun = eph['sun']
            earth = eph['earth']
            t = ts.from_datetime(dt.astimezone(timezone.utc))
            astrometric = earth.at(t).observe(sun)
            subsolar_point = wgs84.subpoint(astrometric)
            return subsolar_point.latitude.degrees, subsolar_point.longitude.degrees
        except Exception as e:
            logger.error(f"Error calculating sun position: {e}")
            return 0.0, 0.0

    @staticmethod
    def moon_position(dt):
        if not SKYFIELD_AVAILABLE: 
            return 0.0, 0.0
        try:
            ts = load.timescale()
            eph = load('de421.bsp')
            moon = eph['moon']
            earth = eph['earth']
            t = ts.from_datetime(dt.astimezone(timezone.utc))
            astrometric = earth.at(t).observe(moon)
            sublunar_point = wgs84.subpoint(astrometric)
            return sublunar_point.latitude.degrees, sublunar_point.longitude.degrees
        except Exception as e:
            logger.error(f"Error calculating moon position: {e}")
            return 0.0, 0.0