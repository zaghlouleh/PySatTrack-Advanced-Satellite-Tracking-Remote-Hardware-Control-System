import math
from datetime import datetime, timezone
from skyfield.api import load
from src.config.settings import EARTH_RADIUS_KM, MU_EARTH

class CelestialCalculator:
    """Handles all astronomical and orbital mathematics."""

    @staticmethod
    def sun_position(dt):
        """Calculate subsolar point using Skyfield"""
        ts = load.timescale()
        eph = load('de421.bsp')
        
        sun = eph['sun']
        earth = eph['earth']
        
        dt_utc = dt.astimezone(timezone.utc)
        t = ts.from_datetime(dt_utc)
        
        astrometric = earth.at(t).observe(sun)
        ra, dec, distance = astrometric.radec()
        
        gst = t.gmst
        lon_deg = (ra.hours - gst) * 15
        lon_deg = (lon_deg + 180) % 360 - 180  # Wrap to -180..180
        return dec.degrees, lon_deg

    @staticmethod
    def moon_position(dt):
        """Calculate actual geographic position of the moon using Skyfield"""
        ts = load.timescale()
        eph = load('de421.bsp')
        
        t = ts.from_datetime(dt.astimezone(timezone.utc))
        moon = eph['moon']
        earth = eph['earth']
        
        astrometric = earth.at(t).observe(moon)
        ra, dec, _ = astrometric.radec()
        
        lat = dec.degrees
        lng = -(ra.hours * 15 - 180) % 360 - 180 
        
        return lat, lng

    @staticmethod
    def calculate_lst(longitude: float, dt: datetime) -> float:
        """Calculate Local Sidereal Time"""
        jd = (dt - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400 + 2451545
        gmst = 18.697374558 + 24.06570982441908 * (jd - 2451545)
        lst = (gmst + longitude/15) % 24
        return round(lst, 4)

    @staticmethod
    def calculate_speed(positions):
        """Calculate speed using Haversine formula between two points"""
        if len(positions) < 2:
            return 0.0
        
        p1, p2 = positions[0], positions[1]
        
        lat1, lon1 = math.radians(p1['satlatitude']), math.radians(p1['satlongitude'])
        lat2, lon2 = math.radians(p2['satlatitude']), math.radians(p2['satlongitude'])
        
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance_km = EARTH_RADIUS_KM * c
        
        time_diff = (p2['timestamp'] - p1['timestamp']) / 3600
        return distance_km / time_diff if time_diff != 0 else 0.0

    @staticmethod
    def calculate_orbital_period(altitude_km):
        """Calculate orbital period using Kepler's third law"""
        if altitude_km is None:
            return None
        # Semi-major axis
        a = EARTH_RADIUS_KM + altitude_km  
        T_seconds = 2 * math.pi * math.sqrt(a**3 / MU_EARTH)
        return round(T_seconds / 60, 2)