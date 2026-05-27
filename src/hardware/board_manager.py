# -*- coding: utf-8 -*-
import time
import serial
import platform
from PyQt5.QtCore import QObject, pyqtSignal
from src.utils.platform_utils import safe_port_detection, get_i2c_smbus, get_spidev
from src.utils.logger import logger

# Initialize platform-aware hardware modules
smbus2 = get_i2c_smbus()
spidev = get_spidev()

class BoardManager(QObject):
    """
    Hardware Interface for communicating with various microcontrollers.
    Supports UART, I2C, and SPI protocols.
    """
    connection_changed = pyqtSignal(bool, str)

    # Hardware definitions dictionary
    boards = {
        "Arduino": {"protocol": "UART", "command": b"*IDN?\n", "response_contains": "Arduino"},
        "Adafruit Feather": {
            "protocol": "I2C",
            "models": {
                "Feather M0": {"address": 0x12, "command": b"\x01\x02\x03"},
                "Feather M4": {"address": 0x34, "command": b"\x04\x05\x06"}
            }
        },
        "SparkFun": {
            "protocol": "SPI",
            "models": {
                "SparkFun Pro Micro": {"bus": 0, "device": 0, "command": [0x07, 0x08, 0x09]},
                "SparkFun ESP32 Thing": {"bus": 1, "device": 0, "command": [0x0A, 0x0B, 0x0C]}
            }
        },
        "RedBoard": {"protocol": "UART", "command": b"*IDN?\n", "response_contains": "RedBoard"},
        "NodeMCU": {"protocol": "UART", "command": b"get_board_info\n", "response_contains": "NodeMCU"},
        "ESP32": {"protocol": "UART", "command": b"get_board_info\n", "response_contains": "ESP32"},
        "Raspberry Pi": {"protocol": "UART", "command": b"uname -a\n", "response_contains": "Linux"},
        "PanelModel1": {
            "protocol": "I2C",
            "models": {
                "Panel1 Model A": {"address": 0x56, "command": b"\x0D\x0E\x0F"},
                "Panel1 Model B": {"address": 0x78, "command": b"\x10\x11\x12"}
            }
        },
        "PanelModel2": {
            "protocol": "SPI",
            "models": {
                "Panel2 Model X": {"bus": 2, "device": 1, "command": [0x13, 0x14, 0x15]},
                "Panel2 Model Y": {"bus": 3, "device": 1, "command": [0x16, 0x17, 0x18]}
            }
        }
    }

    def __init__(self):
        super().__init__()
        self.connection = None
        self.current_board = None
        self.current_model = None
        self.current_port = None
        self.protocol = None

    def get_available_ports(self):
        """Returns detected serial/comm ports using platform-specific logic."""
        return safe_port_detection()

    def connect(self, port, config, board_type, model=None):
        """Main entry point to establish hardware connection."""
        self.disconnect()
        self.current_board = board_type
        self.current_model = model
        self.current_port = port
        
        board_info = self.boards.get(board_type)
        if not board_info:
            msg = f"Unsupported board type: {board_type}"
            logger.error(msg)
            return False, msg
            
        self.protocol = board_info.get("protocol", "UART")
        try:
            if self.protocol == "UART":
                success, message = self._connect_uart(port, config.get('baud_rate', 9600), board_info)
            elif self.protocol == "I2C":
                success, message = self._connect_i2c(port, board_info)
            elif self.protocol == "SPI":
                success, message = self._connect_spi(port, board_info)
            else:
                success, message = False, f"Unknown protocol: {self.protocol}"
            
            if success:
                logger.info(f"Connected to {board_type} via {self.protocol}")
                self.connection_changed.emit(True, f"Connected to {board_type} at {port}")
            else:
                logger.error(f"Connection failed: {message}")
                self.connection_changed.emit(False, f"Connection failed: {message}")
            return success, message

        except Exception as e:
            error_msg = f"Unexpected connection error: {str(e)}"
            logger.exception(error_msg)
            self.disconnect()
            self.connection_changed.emit(False, error_msg)
            return False, error_msg

    def _connect_uart(self, port, baud_rate, board_info):
        try:
            self.connection = serial.Serial(port, baudrate=baud_rate, timeout=2, write_timeout=2)
            if self.connection.is_open:
                id_cmd = board_info.get("command")
                expected_response = board_info.get("response_contains")
                if id_cmd:
                    self.connection.write(id_cmd)
                    time.sleep(0.5)
                    response = self.connection.read_until().decode(errors='ignore').strip()
                    if expected_response and expected_response not in response:
                        self.disconnect()
                        return False, f"ID mismatch. Got: {response}"
                return True, "Board identified."
            return False, "Port could not be opened."
        except Exception as e:
            self.disconnect()
            return False, str(e)

    def _connect_i2c(self, bus_num_str, board_info):
        if platform.system() != "Linux":
            return False, "I2C requires Linux platform."
        try:
            model_info = board_info.get("models", {}).get(self.current_model)
            if not model_info: return False, "Invalid model for I2C."
            address = model_info.get("address")
            bus_num = int(bus_num_str)
            self.connection = smbus2.SMBus(bus_num)
            self.connection.read_byte(address) # Probe device
            return True, f"Device found at 0x{address:02X}"
        except Exception as e:
            self.disconnect()
            return False, f"I2C Probe failed: {str(e)}"

    def _connect_spi(self, port, board_info):
        if platform.system() != "Linux":
            return False, "SPI requires Linux platform."
        try:
            model_info = board_info.get("models", {}).get(self.current_model)
            if not model_info: return False, "Invalid model for SPI."
            bus, device = map(int, port.split(','))
            self.connection = spidev.SpiDev()
            self.connection.open(bus, device)
            return True, f"SPI Bus {bus} Device {device} ready."
        except Exception as e:
            self.disconnect()
            return False, f"SPI Setup failed: {str(e)}"

    def disconnect(self):
        if self.connection:
            try:
                self.connection.close()
                logger.info("Hardware connection closed.")
            except:
                pass
        self.connection = None
        self.protocol = None
        self.current_port = None

    def send_data(self, data):
        """Sends satellite coordinates to the connected hardware."""
        if not self.connection or not self.protocol:
            return False
        try:
            if self.protocol == "UART":
                return self._send_uart(data)
            elif self.protocol == "I2C":
                return self._send_i2c(data)
            elif self.protocol == "SPI":
                return self._send_spi(data)
            return False
        except Exception as e:
            logger.error(f"Hardware transmit error: {e}")
            return False

    def _send_uart(self, data):
        try:
            az = float(data.get('azimuth', 0))
            el = float(data.get('elevation', 0))
            is_visible = 1 if el > 0 else 0
            command = f"AZ:{az:.2f},EL:{el:.2f},VIS:{is_visible}\n"
            self.connection.write(command.encode('ascii'))
            return True
        except Exception:
            return False

    def _send_i2c(self, data):
        try:
            model_info = self.boards.get(self.current_board, {}).get("models", {}).get(self.current_model)
            address = model_info.get('address')
            az = int(float(data.get('azimuth', 0)))
            el = int(float(data.get('elevation', 0)) + 90)
            cmd_byte = 0x01
            payload = [(az >> 8) & 0xFF, az & 0xFF, el & 0xFF]
            self.connection.write_i2c_block_data(address, cmd_byte, payload)
            return True
        except Exception:
            return False

    def _send_spi(self, data):
        try:
            az = int(float(data.get('azimuth', 0)))
            el = int(float(data.get('elevation', 0)) + 90)
            cmd_byte = 0x02
            spi_command = [cmd_byte, (az >> 8) & 0xFF, az & 0xFF, el & 0xFF]
            self.connection.xfer2(spi_command)
            return True
        except Exception:
            return False