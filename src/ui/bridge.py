# -*- coding: utf-8 -*-
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from src.utils.logger import logger

class MapBridge(QObject):
    """
    Handles two-way communication between Python and the JavaScript Leaflet map.
    Signals are emitted by Python to update the map.
    Slots are called by JavaScript to notify Python of user interactions.
    """
    
    # --- Signals for real-time updates (Python -> JS) ---
    js_ready_signal = pyqtSignal()
    update_satellite_position = pyqtSignal(float, float, float, float, float, float)
    update_observer_position = pyqtSignal(float, float)
    update_celestial_position = pyqtSignal(str, float, float)

    # --- Signals for controlling map view and drawings ---
    set_map_view = pyqtSignal(float, float, int)
    clear_satellite_data = pyqtSignal()
    draw_orbit_path = pyqtSignal(list)
    highlight_visible_pass = pyqtSignal(list)
    
    # --- Signals for tracking history ---
    update_satellite_range = pyqtSignal(float, float, float)  # lat, lng, range_km
    add_track_step = pyqtSignal(float, float)  # lat, lng for trail history
    clear_track_steps = pyqtSignal()
    
    # --- Satellite position ---
    update_satellite_position = pyqtSignal(float, float, float, float, float, float)  # lat,lng,alt,spd,az,el

    # --- Signals for the map's info panels ---
    update_pass_info = pyqtSignal(str)
    update_traffic_info = pyqtSignal(str)  # JSON str for JS parse

    def __init__(self, parent=None):
        super().__init__(parent)
        self._js_ready = False

    @pyqtSlot()
    def on_js_ready(self):
        """Called by JavaScript via the WebChannel when the map is fully initialized."""
        logger.info("*** BRIDGE on_js_ready(): JS -> Python READY! ***")
        self._js_ready = True
        self.js_ready_signal.emit()

    @pyqtSlot(str)
    def js_log(self, message: str):
        """Allows the JavaScript console to log directly into our Python logging system."""
        logger.info(f"MapBridge (JS): {message}")

    @pyqtSlot(float, float)
    def map_clicked(self, lat: float, lng: float):
        """Called when the user clicks on the map."""
        logger.info(f"MapBridge: User clicked at Lat: {lat:.4f}, Lng: {lng:.4f}")

    def is_ready(self) -> bool:
        """Returns True if the JS/Python bridge is established."""
        return self._js_ready