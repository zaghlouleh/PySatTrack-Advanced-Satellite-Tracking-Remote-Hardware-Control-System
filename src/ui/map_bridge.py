from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class MapBridge(QObject):
    """Bridge for JavaScript-Python communication within the QWebEngineView"""
    update_map = pyqtSignal(float, float)

    @pyqtSlot(float, float)
    def update_position(self, lat: float, lng: float):
        """Receive updates from the Leaflet JavaScript map"""
        self.update_map.emit(lat, lng)