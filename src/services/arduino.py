import serial
import logging
from PyQt5.QtCore import QObject, pyqtSignal
from typing import Dict

class ArduinoManager(QObject):
    """Handles Arduino communication via Serial"""
    connection_changed = pyqtSignal(bool)
    
    def __init__(self):
        super().__init__()
        self.serial = None

    def connect(self, port: str, baud_rate: int) -> bool:
        """Establish serial connection to the Arduino"""
        try:
            self.serial = serial.Serial(
                port=port,
                baudrate=baud_rate,
                timeout=2,  # 2 second timeout
                write_timeout=2
            )
            if self.serial.is_open:
                logging.info(f"Successfully connected to Arduino on {port}")
                self.connection_changed.emit(True)
                return True
            logging.error(f"Failed to open connection to Arduino on {port}")
            return False
        except Exception as e:
            logging.error(f"Arduino connection error: {str(e)}")
            return False
        
    def send_data(self, data: Dict) -> bool:
        """Send azimuth and elevation to Arduino in 'azimuth,elevation\n' format"""
        try:
            if self.serial and self.serial.is_open:
                # Azimuth and Elevation are expected in the data dictionary
                command = f"{data.get('azimuth', 0)},{data.get('elevation', 0)}\n"
                self.serial.write(command.encode())
                return True
            return False
        except Exception as e:
            logging.error(f"Data send failed: {str(e)}")
            return False