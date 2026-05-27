import sys
import os
import platform
import logging
import glob
from PyQt5.QtCore import QObject, pyqtSignal

# Platform-specific imports for Serial/UART
try:
    import serial
except ImportError:
    logging.error("pyserial not found. Serial communication will be unavailable.")

# Platform-specific imports for Windows Registry
if sys.platform.startswith('win'):
    import winreg

# Hardware Protocol Imports with Mocking for non-Linux platforms
if sys.platform.startswith('linux'):
    try:
        import smbus2
        import spidev
    except ImportError:
        logging.warning("Linux hardware libraries (smbus2/spidev) not found.")
else:
    # Create mock SMBus for Windows/macOS
    class SMBus:
        def __init__(self, bus_number): self.bus_number = bus_number
        def read_byte(self, addr): return 0x00
        def write_i2c_block_data(self, addr, cmd, data): pass
        def close(self): pass
    
    # Create mock SpiDev for Windows/macOS
    class SpiDevMock:
        def open(self, bus, device): pass
        def xfer2(self, data): return [0x00] * len(data)
        def close(self): pass

    smbus2 = type('smbus2', (), {'SMBus': SMBus})()
    spidev = type('spidev', (), {'SpiDev': SpiDevMock})()

class BoardManager(QObject):
    """Manages connections to external hardware boards via UART, I2C, or SPI."""
    connection_changed = pyqtSignal(bool)
    
    boards = {
        "Arduino": {"protocol": "UART"},
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
        "RedBoard": {"protocol": "UART"},
        "NodeMCU": {"protocol": "UART"},
        "ESP32": {"protocol": "UART"},
        "Raspberry Pi": {"protocol": "UART"}
    }

    def __init__(self):
        super().__init__()
        self.serial = None
        self.current_board = None
        self.current_model = None

    def detect_os_specific_ports(self):
        """Return a list of available serial ports based on the OS."""
        ports = []
        try:
            os_type = platform.system()
            if os_type == "Windows":
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
                    i = 0
                    while True:
                        ports.append(winreg.EnumValue(key, i)[1])
                        i += 1
                except (OSError, EnvironmentError): pass
            elif os_type == "Linux":
                ports = glob.glob('/dev/tty[A-Za-z]*')
            elif os_type == "Darwin":
                ports = glob.glob('/dev/cu.*') + glob.glob('/dev/tty.*')
            return sorted(ports)
        except Exception as e:
            logging.error(f"Port detection failed: {str(e)}")
            return []

    def connect(self, port: str, config: dict, board_type: str, model: str = None) -> bool:
        """Main connection entry point."""
        self.disconnect()  # Close previous connection if any
        self.current_board = board_type
        self.current_model = model
        protocol = self.boards.get(board_type, {}).get("protocol", "UART")
        
        try:
            if protocol == "UART":
                return self._connect_uart(port, config.get('baud_rate', 9600))
            elif protocol == "I2C":
                return self._connect_i2c(port)
            elif protocol == "SPI":
                return self._connect_spi(port)
            return False
        except Exception as e:
            logging.error(f"Connection error: {str(e)}")
            self.connection_changed.emit(False)
            return False

    def disconnect(self):
        """Safely disconnect current board."""
        try:
            if hasattr(self, 'serial') and self.serial and self.serial.is_open:
                self.serial.close()
            self.serial = None
            self.current_board = None
            self.connection_changed.emit(False)
            logging.info("Board disconnected")
        except Exception as e:
            logging.error(f"Disconnect error: {str(e)}")

    def _connect_uart(self, port: str, baud_rate: int) -> bool:
        try:
            self.serial = serial.Serial(port, baudrate=baud_rate, timeout=2)
            if self.serial.is_open:
                logging.info(f"UART connected to {port}")
                self.connection_changed.emit(True)
                return True
            return False
        except Exception as e:
            logging.error(f"UART connection failed: {str(e)}")
            return False

    def _connect_i2c(self, bus_num: str) -> bool:
        if not sys.platform.startswith('linux'):
            logging.warning("I2C hardware check skipped (Non-Linux platform)")
            return True # Assume success for UI purposes on mock
        try:
            bus = smbus2.SMBus(int(bus_num))
            bus.close()
            self.connection_changed.emit(True)
            return True
        except Exception as e:
            logging.error(f"I2C connection failed: {str(e)}")
            return False

    def _connect_spi(self, port: str) -> bool:
        try:
            bus, device = map(int, port.split(','))
            spi = spidev.SpiDev()
            spi.open(bus, device)
            spi.close()
            self.connection_changed.emit(True)
            return True
        except Exception as e:
            logging.error(f"SPI connection failed: {str(e)}")
            return False

    def send_data(self, data: dict) -> bool:
        """Send formatted tracking data to the connected board."""
        if self.current_board and self.boards[self.current_board]["protocol"] == "UART":
            try:
                if self.serial and self.serial.is_open:
                    command = f"{data['azimuth']},{data['elevation']}\n"
                    self.serial.write(command.encode())
                    return True
            except Exception as e:
                logging.error(f"Failed to send UART data: {str(e)}")
        return False