"""Data models for satellite tracking application"""

from dataclasses import dataclass
from typing import Optional, List, Dict

@dataclass
class SatellitePosition:
    """Represents a satellite's position and orientation"""
    latitude: float
    longitude: float
    altitude: float
    azimuth: float
    elevation: float

@dataclass
class SatellitePass:
    """Represents a single pass of a satellite"""
    start_time: float
    max_time: float
    end_time: float
    max_elevation: float
    
@dataclass
class Observer:
    """Represents an observer's location"""
    latitude: float
    longitude: float
    altitude: float
    city_name: str