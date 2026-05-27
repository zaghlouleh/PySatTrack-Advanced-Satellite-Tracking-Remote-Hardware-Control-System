from skyfield.api import load, wgs84
from datetime import timezone
import math

class CelestialCalculator:
    """Handles astronomical calculations for Sun and Moon positions"""
    
    @staticmethod
    def sun_position(dt):
        """Calculate subsolar point using Skyfield"""
        # Load ephemeris and timescale
        ts = load.timescale()
        eph = load('de421.bsp')
        
        # Get astronomical objects
        sun = eph['sun']
        earth = eph['earth']
        
        # Convert to UTC and create Skyfield time object
        dt_utc = dt.astimezone(timezone.utc)
        t = ts.from_datetime(dt_utc)
        
        # Calculate Sun's position relative to Earth's center
        astrometric = earth.at(t).observe(sun)
        ra, dec, distance = astrometric.radec()
        
        # Greenwich Sidereal Time in hours
        gst = t.gmst
        
        # Longitude is RA - GST converted to degrees
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
        
        # Get moon's geocentric position
        astrometric = earth.at(t).observe(moon)
        ra, dec, _ = astrometric.radec()
        
        # Convert to geographic coordinates
        lat = dec.degrees
        lng = -(ra.hours * 15 - 180) % 360 - 180  # Convert RA to longitude
        
        return lat, lng