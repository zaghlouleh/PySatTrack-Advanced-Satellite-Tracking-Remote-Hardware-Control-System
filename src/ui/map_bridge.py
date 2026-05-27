from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class MapBridge(QObject):
    """
    Bridge for JavaScript-Python communication. 
    Allows the QWebEngineView to send data back to Python if needed.
    """
    update_map = pyqtSignal(float, float)

    @pyqtSlot(float, float)
    def update_position(self, lat: float, lng: float):
        """Receive position updates from JavaScript."""
        self.update_map.emit(lat, lng)