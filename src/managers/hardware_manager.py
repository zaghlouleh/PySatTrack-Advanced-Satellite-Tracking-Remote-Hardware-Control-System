# -*- coding: utf-8 -*-
import sys
import platform
import time
import serial
from typing import Tuple, List, Optional, Any
from PyQt5.QtCore import QObject, pyqtSignal
from src.utils.logger import logger

# Platform-specific hardware imports with graceful fallbacks
try:
    if platform.system() == 'Linux':
        import smbus2
        import spidev
    else:
        smbus2 = None
        spidev = None
except ImportError:
    smbus2 = None
    spidev = None
    logger.warning("Hardware: smbus2 or spidev not found. Using Mocks for I2C/SPI.")

class HardwareManager(QObject):
    """
    Handles hardware communication via UART, I2C, and SPI.
    Includes platform-specific logic and auto-detection.
    """
    connection_changed = pyqtSignal(bool, str)

    # Database of supported hardware profiles
    BOARDS = {
        "Arduino": {"protocol": "UART", "command": b"*IDN?\n", "response_contains": "Arduino"},
        "Adafruit Feather": {
            "protocol": "I2C",
            "models": {
                "Feather M0": {"address": 0x12},
                "Feather M4": {"address": 0x34}
            }
        },
        "SparkFun": {
            "protocol": "SPI",
            "models": {
                "Pro Micro": {"bus": 0, "device": 0},
                "ESP32 Thing": {"bus": 1, "device": 0}
            }
        },
        "ESP32/NodeMCU": {"protocol": "UART", "command": b"info\n", "response_contains": "ESP32"},
        "Raspberry Pi": {"protocol": "UART", "command": b"uname -a\n", "response_contains": "Linux"}
    }

    def __init__(self):
        super().__init__()
        self.connection = None
        self.protocol = None
        self.current_board = None
        self.current_port = None

    def get_available_ports(self) -> List[str]:
        """Lists available serial ports across Windows, Linux, and macOS."""
        import glob
        system = platform.system()
        ports = []
        
        try:
            if system == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
                for i in range(1024):
                    try:
                        _, port = winreg.EnumValue(key, i)
                        ports.append(port)
                    except OSError: break
            elif system == "Linux":
                ports = glob.glob('/dev/ttyS*') + glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
            elif system == "Darwin":  # macOS
                ports = glob.glob('/dev/cu.*') + glob.glob('/dev/tty.*')
        except Exception as e:
            logger.error(f"Hardware: Port scan failed: {e}")
            
        return sorted(ports)

    def connect(self, port: str, board_type: str, model: str = None, baud: int = 9600) -> Tuple[bool, str]:
        """Initiates a connection to the specified hardware."""
        self.disconnect()
        
        info = self.BOARDS.get(board_type)
        if not info: return False, "Unknown board type."
        
        self.protocol = info["protocol"]
        self.current_board = board_type
        self.current_port = port

        try:
            if self.protocol == "UART":
                return self._connect_uart(port, baud, info)
            elif self.protocol == "I2C":
                return self._connect_i2c(port, info, model)
            elif self.protocol == "SPI":
                return self._connect_spi(port, info, model)
        except Exception as e:
            error_msg = f"Connection failed: {str(e)}"
            logger.error(f"Hardware: {error_msg}")
            return False, error_msg

        return False, "Unsupported protocol."

    def _connect_uart(self, port: str, baud: int, info: dict) -> Tuple[bool, str]:
        try:
            self.connection = serial.Serial(port, baudrate=baud, timeout=2)
            if self.connection.is_open:
                # Optional handshake
                if "command" in info:
                    self.connection.write(info["command"])
                    time.sleep(0.5)
                    resp = self.connection.read_all().decode(errors='ignore')
                    if info["response_contains"] not in resp:
                        logger.warning(f"Hardware: Handshake mismatch on {port}. Expected {info['response_contains']}")
                
                self.connection_changed.emit(True, f"Connected to {self.current_board}")
                return True, "Connected successfully."
        except Exception as e:
            return False, str(e)

    def _connect_i2c(self, bus_num: str, info: dict, model: str) -> Tuple[bool, str]:
        if not smbus2: return False, "smbus2 not available on this platform."
        try:
            addr = info["models"][model]["address"]
            self.connection = smbus2.SMBus(int(bus_num))
            self.connection.read_byte(addr) # Ping device
            self.connection_changed.emit(True, f"I2C Active on addr {hex(addr)}")
            return True, "I2C device detected."
        except Exception as e:
            return False, f"I2C Error: {e}"

    def _connect_spi(self, port: str, info: dict, model: str) -> Tuple[bool, str]:
        if not spidev: return False, "spidev not available on this platform."
        try:
            bus = info["models"][model]["bus"]
            dev = info["models"][model]["device"]
            self.connection = spidev.SpiDev()
            self.connection.open(bus, dev)
            self.connection_changed.emit(True, "SPI Bus Open")
            return True, "SPI Ready."
        except Exception as e:
            return False, f"SPI Error: {e}"

    def send_telemetry(self, az: float, el: float) -> bool:
        """Sends Azimuth and Elevation to the hardware."""
        if not self.connection: return False
        
        try:
            if self.protocol == "UART":
                # Standard ASCII protocol: AZ:180.00,EL:45.00,VIS:1\n
                vis = 1 if el > 0 else 0
                cmd = f"AZ:{az:.2f},EL:{el:.2f},VIS:{vis}\n"
                self.connection.write(cmd.encode('ascii'))
                return True
            
            # Add I2C/SPI binary packet logic here if needed for specific firmwares
            
        except Exception as e:
            logger.error(f"Hardware: Data send failed: {e}")
            self.disconnect()
            return False

    def disconnect(self):
        if self.connection:
            try:
                self.connection.close()
            except: pass
            self.connection = None
            self.connection_changed.emit(False, "Disconnected")
            logger.info("Hardware: Connection closed.")