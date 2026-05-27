# -*- coding: utf-8 -*-
import logging
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from src.utils.logger import logger

class MapBridge(QObject):
    """
    JavaScript Bridge for communication between Python and the Leaflet Map.
    This class is registered with QWebChannel.
    """
    
    # Signals emitted from Python to trigger JS functions in the map
    update_observer_position = pyqtSignal(float, float)
    update_satellite_position = pyqtSignal(float, float)
    update_celestial_position = pyqtSignal(str, float, float)
    add_satellite_track_point = pyqtSignal(float, float)
    clear_satellite_track = pyqtSignal()
    set_map_view = pyqtSignal(float, float, int)
    fit_map_bounds = pyqtSignal(list)

    @pyqtSlot(str)
    def js_log(self, message: str):
        """Receives log messages from the JavaScript console."""
        logger.info(f"JS Map Log: {message}")

    @pyqtSlot(float, float)
    def map_clicked(self, lat: float, lng: float):
        """Handles map click events from the JavaScript Leaflet map."""
        logger.info(f"Map clicked at Lat: {lat:.4f}, Lng: {lng:.4f}")