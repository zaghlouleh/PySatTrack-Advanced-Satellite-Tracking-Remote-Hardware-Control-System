# -*- coding: utf-8 -*-
import os
import sys
import platform
import logging
import glob

# Try to import Windows-specific registry access
if platform.system() == "Windows":
    try:
        import winreg
    except ImportError:
        winreg = None
else:
    winreg = None

logger = logging.getLogger(__name__)

def setup_qt_environment():
    """Addresses QtWebEngine deployment issues on Windows."""
    if platform.system() == "Windows":
        try:
            from PyQt5 import QtCore
            pyqt_dir = os.path.dirname(QtCore.__file__)
            bin_path = os.path.join(pyqt_dir, "Qt5", "bin")
            plugin_path = os.path.join(pyqt_dir, "Qt5", "plugins")
            resources_path = os.path.join(pyqt_dir, "Qt5", "resources")

            web_engine_process_path = os.path.join(bin_path, "QtWebEngineProcess.exe")
            if os.path.exists(web_engine_process_path):
                os.environ["QTWEBENGINE_PROCESS_PATH"] = web_engine_process_path

            if os.path.isdir(resources_path):
                os.environ["QTWEBENGINE_RESOURCES_PATH"] = resources_path

            if hasattr(os, 'add_dll_directory') and os.path.isdir(bin_path):
                os.add_dll_directory(bin_path)

            if os.path.isdir(bin_path):
                os.environ['PATH'] = bin_path + os.pathsep + os.environ['PATH']

            if os.path.isdir(plugin_path):
                os.environ['QT_PLUGIN_PATH'] = plugin_path
        except ImportError:
            pass
        except Exception as e:
            print(f"WARNING: An error occurred while setting Qt paths: {e}")

# --- Hardware Library Wrappers ---

def get_i2c_smbus():
    """Returns smbus2 or a mock object based on the platform."""
    if sys.platform.startswith('linux'):
        try:
            import smbus2
            return smbus2
        except ImportError:
            logger.error("smbus2 module not found, I2C functionality disabled.")
    
    class MockSMBus:
        def __init__(self, bus_number): self.bus_number = bus_number
        def write_i2c_block_data(self, addr, cmd, data): pass
        def read_byte(self, addr): return 0
        def close(self): pass
    
    mock_smbus_module = type('smbus2', (), {'SMBus': MockSMBus})()
    return mock_smbus_module

def get_spidev():
    """Returns spidev or a mock object based on the platform."""
    if platform.system() == 'Linux':
        try:
            import spidev
            return spidev
        except ImportError:
            logger.error("spidev module not found, SPI functionality disabled.")
    
    class SpiDevMock:
        def open(self, bus, device): pass
        def xfer2(self, data): return [0x00] * len(data)
        def close(self): pass
    
    return SpiDevMock()

# --- Port Detection Logic ---

def _windows_board_check():
    ports = []
    if not winreg: return ports
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
        i = 0
        while True:
            try:
                device, port = winreg.EnumValue(key, i)
                ports.append(port)
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass
    return sorted(ports)

def _linux_board_check():
    return sorted(glob.glob('/dev/ttyS*') + glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*'))

def _macos_board_check():
    return sorted(glob.glob('/dev/cu.*') + glob.glob('/dev/tty.*'))

def safe_port_detection():
    """Detects available serial ports across Windows, Linux, and macOS."""
    os_type = platform.system()
    try:
        if os_type == "Windows":
            return _windows_board_check()
        elif os_type == "Linux":
            return _linux_board_check()
        elif os_type == "Darwin":
            return _macos_board_check()
        return []
    except Exception as e:
        logger.error(f"Error during port detection: {e}")
        return []