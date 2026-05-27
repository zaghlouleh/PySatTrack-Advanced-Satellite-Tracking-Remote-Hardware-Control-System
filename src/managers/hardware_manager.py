# src/managers/hardware_manager.py
# -*- coding: utf-8 -*-
import sys
import glob
import platform
import time
import serial
import socket
import threading
import json
import math
from typing import Tuple, List, Optional, Any
from PyQt5.QtCore import QObject, pyqtSignal
from src.managers.hardware_bridge import ArduinoReader, SerialDevice, GpioRfSwitch, GPIO
from src.managers.hardware_bridge_client import HardwareBridgeClient
from src.utils.logger import logger
from src.utils.station_profile import (
    DEFAULT_RF_CHANNEL_COUNT,
    MAX_RF_CHANNEL_COUNT,
    clamp_rf_channel,
    validate_calibration,
    validate_tracking_context,
)

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


def _coerce_float(value: Any, default: float = 0.0) -> float:
    """Parse numeric telemetry; treat missing or '---' as default."""
    if value is None:
        return default
    if isinstance(value, str) and value.strip() in ("", "---"):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(_coerce_float(value, float(default)))
    except (ValueError, TypeError):
        return default


class HardwareBridgeServer:
    """Multi-threaded background TCP server that responds to diagnostics clients."""

    def __init__(self, hw_manager: "HardwareManager", host: str, port: int):
        self.hw_manager = hw_manager
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.clients: List[socket.socket] = []
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None

    def start(self) -> Tuple[bool, str]:
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.thread.start()
            logger.info(f"TCP Bridge Server listening on {self.host}:{self.port}")
            return True, "Server started successfully."
        except Exception as e:
            self.running = False
            if self.server_socket:
                self.server_socket.close()
            return False, str(e)

    def _listen_loop(self):
        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                client_sock, addr = self.server_socket.accept()
                logger.info(f"TCP Bridge: Accepted connection from {addr}")
                client_thread = threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True)
                client_thread.start()
                with self.lock:
                    self.clients.append(client_sock)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"TCP Bridge listen error: {e}")
                break

    def _handle_client(self, client_sock: socket.socket):
        client_sock.settimeout(5.0)
        buffer = ""
        while self.running:
            try:
                data = client_sock.recv(4096)
                if not data:
                    break
                buffer += data.decode('utf-8')
                while buffer:
                    start = buffer.find('{')
                    if start == -1:
                        buffer = ""
                        break
                    
                    depth = 0
                    end = -1
                    for idx in range(start, len(buffer)):
                        if buffer[idx] == '{':
                            depth += 1
                        elif buffer[idx] == '}':
                            depth -= 1
                            if depth == 0:
                                end = idx
                                break
                    if end != -1:
                        json_str = buffer[start:end+1]
                        buffer = buffer[end+1:]
                        try:
                            req = json.loads(json_str)
                            self._process_request(client_sock, req)
                        except Exception as e:
                            logger.error(f"Failed to process client request: {e}")
                    else:
                        break
            except socket.timeout:
                continue
            except Exception:
                break
        with self.lock:
            if client_sock in self.clients:
                self.clients.remove(client_sock)
        try:
            client_sock.close()
        except Exception:
            pass

    def _process_request(self, sock: socket.socket, req: dict):
        req_type = req.get("type")
        if req_type == "GET_GPS_STATUS":
            payload = req.get("payload", {})
            if isinstance(payload, dict) and "simulation_mode" in payload:
                self.hw_manager.simulation_mode = bool(payload["simulation_mode"])

            sim_time = time.time()
            health = self.hw_manager.get_hardware_health_status()

            with self.hw_manager._data_lock:
                tracking_data = self.hw_manager.live_tracking_data.copy()

            # Detect satellite change and reset internal dynamics
            current_sat = tracking_data.get("sat_name", "UNKNOWN")
            if hasattr(self, "_last_sat_name") and self._last_sat_name != current_sat:
                logger.info(f"Bridge: Satellite changed from {self._last_sat_name} to {current_sat}. Resetting dynamics.")
                self._last_sim_time = sim_time
                self._last_az = 0.0
                self._last_el = 0.0
                # Reset hardware manager's last positions to avoid huge delta
                self.hw_manager.last_az = 0.0
                self.hw_manager.last_el = 0.0
            self._last_sat_name = current_sat

            if self.hw_manager.simulation_mode:
                response = self.hw_manager.build_simulation_diagnostics_payload(
                    tracking_data, current_sat, health
                )
            else:
                response = self.hw_manager.build_hardware_diagnostics_payload(
                    tracking_data, current_sat, health
                )

            try:
                sock.sendall(json.dumps(response).encode('utf-8'))
            except Exception as e:
                logger.error(f"Error sending GPS status: {e}")

        elif req_type == "SET_RF_CHANNEL":
            payload = req.get("payload", {})
            channel = payload.get("channel", 1)
            self.hw_manager.select_rf_channel(channel)

        elif req_type == "SET_ANTENNA_POSITION":
            payload = req.get("payload", {})
            az = payload.get("azimuth", 0.0)
            el = payload.get("elevation", 0.0)
            self.hw_manager.send_telemetry(az, el)

        elif req_type == "UPDATE_SIMULATION_PARAMETERS":
            payload = req.get("payload", {})
            self.hw_manager.sim_params.update(payload)
            self.hw_manager._sim_params_revision += 1
            logger.info(f"TCP: Simulation physics parameters updated: {self.hw_manager.sim_params}")

        elif req_type == "SET_OPERATION_MODE":
            payload = req.get("payload", {})
            is_sim = bool(payload.get("simulation_mode", True))
            
            # Reset internal dynamics to avoid jumps if the mode has changed
            if self.hw_manager.simulation_mode != is_sim:
                logger.info(f"Bridge: Operating mode changed to {'SIMULATION' if is_sim else 'DIRECT HARDWARE'}. Resetting dynamics.")
                self._last_sim_time = time.time()
                self._last_az = 0.0
                self._last_el = 0.0
                self.hw_manager.last_az = 0.0
                self.hw_manager.last_el = 0.0
                
            self.hw_manager.simulation_mode = is_sim
            logger.info(f"TCP: Set operation mode state to: {'SIMULATION' if is_sim else 'DIRECT HARDWARE'}")
                
            
    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        with self.lock:
            for sock in self.clients:
                try:
                    sock.close()
                except Exception:
                    pass
            self.clients.clear()


class HardwareManager(QObject):
    """
    Handles hardware communication via UART, I2C, and SPI.
    Manages client/server states and input port conversions.
    """
    connection_changed = pyqtSignal(bool, str)
    arduino_data_received = pyqtSignal(dict)

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
        "Raspberry Pi": {"protocol": "UART", "command": b"uname -a\n", "response_contains": "Linux"},
        "ESP32 RF Switch": {"protocol": "GPIO", "pins": {"s0": 22, "s1": 23, "s2": 24, "override": 27}}
    }

    def __init__(self):
        super().__init__()
        self.connection = None
        self.device = None
        self.arduino_reader = None
        self.ap_mode_enabled = False
        self.bridge_server_running = False
        self.protocol = None
        self.current_board = None
        self.current_port = None
        self._data_lock = threading.RLock()

        # Operation modes
        self.simulation_mode = True
        self.live_tracking_data: dict = {}
        
        # Rigorous Physics Engine Specs defaults
        self.sim_params: dict = {
            "mass": 12.5,
            "gearing": 120.0,
            "kt": 0.15,
            "wind_speed": 10.0,
            "ambient_temp": 22.0,
            "voltage": 12.0,
            "sdr_center_mhz": 137.9100,
            "sdr_span_khz": 100.0,
            "manual_downlink_mhz": 137.9100,
            "manual_bandwidth_khz": 30.0,
            "rf_channel_count": DEFAULT_RF_CHANNEL_COUNT,
        }

        # Physical Input Port State Registers (zeroed until hardware or SatTrack provides data)
        self.last_gps_lat = 0.0
        self.last_gps_lon = 0.0
        self.last_gps_alt = 0.0
        self.last_gps_speed = 0.0
        self.last_gps_fix = False
        self.last_az = 0.0
        self.last_el = 0.0
        self.last_channel = 1

        self.last_voltage = 0.0
        self.last_motor_az_current = 0.0
        self.last_motor_el_current = 0.0
        self.last_track_error_az = 0.0
        self.last_track_error_el = 0.0
        self.last_motor_az_torque_pct = 0.0
        self.last_motor_el_torque_pct = 0.0
        self.last_roll = 0.0
        self.last_pitch = 0.0
        self.last_accel_x = 0.0
        self.last_accel_y = 0.0
        self.last_accel_z = 0.0
        self.last_signal_quality = 0.0
        self.last_path_loss_db = 0.0
        self.last_snr_db = 0.0
        self.last_link_margin_db = 0.0
        self.last_doppler_offset_khz = 0.0
        self.last_frequency_correction_hz_s = 0.0
        self.last_gps_sats_visible = 0
        self.last_hdop = 0.0
        self.last_vdop = 0.0
        self.last_time_deviation_ns = 0
        self.last_vco_pll_locked = False
        self.last_wind_speed = 0.0
        self.last_spectrum: List[float] = []

        self.last_limit_az_ccw = False
        self.last_limit_az_cw = False
        self.last_limit_el_low = False
        self.last_limit_el_high = False
        self.last_overcurrent_trip = False
        self.last_undervoltage_lockout = False
        self.last_encoder_slip = False
        self.last_wind_stow_alarm = False
        self.last_stow_active = False

        # SatTrack sample sequencing (drives simulation waveform plots)
        self._tracking_sample_id = 0
        self._sim_params_revision = 0
        self._track_prev_az: Optional[float] = None
        self._track_prev_el: Optional[float] = None
        self._track_prev_timestamp: Optional[float] = None
        self._track_prev_wall_time: Optional[float] = None

        self.bridge_server: Optional[HardwareBridgeServer] = None

    def _reset_tracking_derivatives(self) -> None:
        self._track_prev_az = None
        self._track_prev_el = None
        self._track_prev_timestamp = None
        self._track_prev_wall_time = None
        self.last_track_error_az = 0.0
        self.last_track_error_el = 0.0

    def update_tracking_telemetry(self, data: dict):
        """Thread-safe update of live tracking data from SatTrack."""
        with self._data_lock:
            current_name = data.get("sat_name")
            prev_name = self.live_tracking_data.get("sat_name")
            if current_name and prev_name and current_name != prev_name:
                logger.info(f"HardwareManager: Target changed from {prev_name} to {current_name}. Flushing.")
                self.live_tracking_data.clear()
                self._reset_tracking_derivatives()
            self.live_tracking_data.update(data)
            self._tracking_sample_id += 1

            az = _coerce_float(data.get("azimuth"), None) if "azimuth" in data else None
            el = _coerce_float(data.get("elevation"), None) if "elevation" in data else None
            if az is not None and el is not None:
                now = time.time()
                ts = data.get("timestamp")
                dt: Optional[float] = None
                if ts is not None and self._track_prev_timestamp is not None:
                    dt = max(_coerce_float(ts) - _coerce_float(self._track_prev_timestamp), 1e-3)
                elif self._track_prev_wall_time is not None:
                    dt = max(now - self._track_prev_wall_time, 1e-3)

                if (
                    dt is not None
                    and self._track_prev_az is not None
                    and self._track_prev_el is not None
                ):
                    self.last_track_error_az = round((az - self._track_prev_az) / dt, 3)
                    self.last_track_error_el = round((el - self._track_prev_el) / dt, 3)

                self._track_prev_az = az
                self._track_prev_el = el
                self._track_prev_timestamp = _coerce_float(ts) if ts is not None else None
                self._track_prev_wall_time = now
                self.last_az = az
                self.last_el = el

    def get_rf_channel_count(self) -> int:
        try:
            count = int(self.sim_params.get("rf_channel_count", DEFAULT_RF_CHANNEL_COUNT))
        except (TypeError, ValueError):
            count = DEFAULT_RF_CHANNEL_COUNT
        return max(1, min(count, MAX_RF_CHANNEL_COUNT))

    def evaluate_simulation_readiness(self, tracking_data: dict) -> dict:
        """Check calibration + SatTrack inputs required for engineering simulation."""
        cal_ok, cal_missing = validate_calibration(self.sim_params)
        track_ok, track_missing = validate_tracking_context(tracking_data)

        downlink = tracking_data.get("downlink_mhz")
        has_sattrack_rf = (
            downlink is not None
            and str(downlink).strip() not in ("", "---")
        )
        has_manual_rf = _coerce_float(self.sim_params.get("manual_downlink_mhz"), 0.0) > 0.0
        rf_ok = has_sattrack_rf or has_manual_rf
        rf_missing: List[str] = []
        if not rf_ok:
            rf_missing.append("Downlink frequency (SatTrack SatNOGS or Manual Downlink MHz)")

        ready = cal_ok and track_ok and rf_ok
        missing = cal_missing + track_missing + rf_missing
        return {
            "simulation_ready": ready,
            "calibration_complete": cal_ok,
            "tracking_complete": track_ok,
            "rf_frequency_available": rf_ok,
            "simulation_missing": missing,
            "rf_channel_count": self.get_rf_channel_count(),
        }

    def get_available_ports(self) -> List[str]:
        return self._safe_port_detection()

    def _safe_port_detection(self) -> List[str]:
        ports = []
        system = platform.system()
        try:
            if system == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
                for i in range(1024):
                    try:
                        _, port = winreg.EnumValue(key, i)
                        ports.append(port)
                    except OSError:
                        break
            elif system == "Linux":
                ports = glob.glob('/dev/ttyS*') + glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
            elif system == "Darwin":
                ports = glob.glob('/dev/cu.*') + glob.glob('/dev/tty.*')
        except Exception as e:
            logger.error(f"Hardware: Port scan failed: {e}")
        return sorted(ports)

    def connect(self, port: str, board_type: str, model: str = None, baud: int = 9600) -> Tuple[bool, str]:
        self.disconnect()
        
        info = self.BOARDS.get(board_type)
        if not info: return False, "Unknown board type."
        
        self.protocol = info["protocol"]
        self.current_board = board_type
        self.current_port = port

        try:
            if self.protocol == "UART":
                return self._connect_uart(port, baud, info, board_type)
            elif self.protocol == "I2C":
                return self._connect_i2c(port, info, model)
            elif self.protocol == "SPI":
                return self._connect_spi(port, info, model)
            elif self.protocol == "GPIO":
                return self._connect_gpio(info)
        except Exception as e:
            error_msg = f"Connection failed: {str(e)}"
            logger.error(f"Hardware: {error_msg}")
            return False, error_msg

        return False, "Unsupported protocol."

    def _connect_uart(self, port: str, baud: int, info: dict, board_type: str) -> Tuple[bool, str]:
        try:
            if board_type == "Arduino":
                self.device = SerialDevice(port, baud)
                if self.device.connection and self.device.connection.is_open:
                    self._start_arduino_reader()
                    self.connection_changed.emit(True, f"Connected to {self.current_board}")
                    return True, "Connected successfully."
                return False, "Failed to open Arduino serial port."

            self.connection = serial.Serial(port, baudrate=baud, timeout=2)
            if self.connection.is_open:
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
            self.connection.read_byte(addr)
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

    def _connect_gpio(self, info: dict) -> Tuple[bool, str]:
        if GPIO is None:
            return False, "GPIO is not available on this platform."
        try:
            self.device = GpioRfSwitch(
                s0=info["pins"]["s0"],
                s1=info["pins"]["s1"],
                s2=info["pins"]["s2"],
                override_pin=info["pins"]["override"],
                max_channels=self.get_rf_channel_count(),
            )
            self.connection_changed.emit(True, "GPIO RF switch configured.")
            return True, "GPIO RF switch ready."
        except Exception as e:
            return False, f"GPIO Error: {e}"

    def _start_arduino_reader(self):
        if self.arduino_reader and self.arduino_reader.is_alive():
            self.arduino_reader.stop()
            self.arduino_reader.join(timeout=1)
        self.arduino_reader = ArduinoReader(self.device, callback=self._handle_arduino_message)
        self.arduino_reader.start()

    def _ingest_hardware_telemetry(self, data: dict) -> None:
        """Update hardware registers from any connected controller telemetry frame."""
        if "voltage" in data:
            self.last_voltage = _coerce_float(data.get("voltage"), self.last_voltage)
        if "motor_az_current" in data:
            self.last_motor_az_current = _coerce_float(data.get("motor_az_current"), 0.0)
        if "motor_el_current" in data:
            self.last_motor_el_current = _coerce_float(data.get("motor_el_current"), 0.0)
        if "track_error_az" in data:
            self.last_track_error_az = _coerce_float(data.get("track_error_az"), 0.0)
        if "track_error_el" in data:
            self.last_track_error_el = _coerce_float(data.get("track_error_el"), 0.0)
        if "motor_az_torque_pct" in data:
            self.last_motor_az_torque_pct = _coerce_float(data.get("motor_az_torque_pct"), 0.0)
        if "motor_el_torque_pct" in data:
            self.last_motor_el_torque_pct = _coerce_float(data.get("motor_el_torque_pct"), 0.0)
        if "azimuth" in data:
            self.last_az = _coerce_float(data.get("azimuth"), self.last_az)
        if "elevation" in data:
            self.last_el = _coerce_float(data.get("elevation"), self.last_el)
        if "roll" in data:
            self.last_roll = _coerce_float(data.get("roll"), 0.0)
        if "pitch" in data:
            self.last_pitch = _coerce_float(data.get("pitch"), 0.0)
        if "accel_x" in data:
            self.last_accel_x = _coerce_float(data.get("accel_x"), 0.0)
        if "accel_y" in data:
            self.last_accel_y = _coerce_float(data.get("accel_y"), 0.0)
        if "accel_z" in data:
            self.last_accel_z = _coerce_float(data.get("accel_z"), 0.0)
        if "signal_quality" in data:
            self.last_signal_quality = _coerce_float(data.get("signal_quality"), 0.0)
        if "path_loss_db" in data:
            self.last_path_loss_db = _coerce_float(data.get("path_loss_db"), 0.0)
        if "snr_db" in data:
            self.last_snr_db = _coerce_float(data.get("snr_db"), 0.0)
        if "link_margin_db" in data:
            self.last_link_margin_db = _coerce_float(data.get("link_margin_db"), 0.0)
        if "doppler_offset_khz" in data:
            self.last_doppler_offset_khz = _coerce_float(data.get("doppler_offset_khz"), 0.0)
        if "frequency_correction_hz_s" in data:
            self.last_frequency_correction_hz_s = _coerce_float(
                data.get("frequency_correction_hz_s"), 0.0
            )
        if "gps_sats_visible" in data:
            self.last_gps_sats_visible = _coerce_int(data.get("gps_sats_visible"), 0)
        if "hdop" in data:
            self.last_hdop = _coerce_float(data.get("hdop"), 0.0)
        if "vdop" in data:
            self.last_vdop = _coerce_float(data.get("vdop"), 0.0)
        if "time_deviation_ns" in data:
            self.last_time_deviation_ns = _coerce_int(data.get("time_deviation_ns"), 0)
        if "wind_speed" in data:
            self.last_wind_speed = _coerce_float(data.get("wind_speed"), 0.0)
        if "spectrum" in data and isinstance(data.get("spectrum"), list):
            self.last_spectrum = list(data["spectrum"])

        for key, attr in (
            ("limit_az_ccw", "last_limit_az_ccw"),
            ("limit_az_cw", "last_limit_az_cw"),
            ("limit_el_low", "last_limit_el_low"),
            ("limit_el_high", "last_limit_el_high"),
            ("overcurrent_trip", "last_overcurrent_trip"),
            ("undervoltage_lockout", "last_undervoltage_lockout"),
            ("encoder_slip_detected", "last_encoder_slip"),
            ("wind_stow_alarm", "last_wind_stow_alarm"),
            ("stow_active", "last_stow_active"),
            ("vco_pll_locked", "last_vco_pll_locked"),
        ):
            if key in data:
                setattr(self, attr, bool(data.get(key)))

        if "gps_lat" in data:
            self.last_gps_lat = _coerce_float(data.get("gps_lat"), self.last_gps_lat)
        if "gps_lon" in data:
            self.last_gps_lon = _coerce_float(data.get("gps_lon"), self.last_gps_lon)
        if "gps_alt" in data:
            self.last_gps_alt = _coerce_float(data.get("gps_alt"), self.last_gps_alt)
        if "gps_speed" in data:
            self.last_gps_speed = _coerce_float(data.get("gps_speed"), self.last_gps_speed)
        if "gps_fix" in data:
            self.last_gps_fix = bool(data.get("gps_fix"))

    def _handle_arduino_message(self, data: dict):
        """Microcontroller Input Port: decodes raw analog and digital states."""
        logger.debug(f"Controller telemetry parsed: {data}")
        self._ingest_hardware_telemetry(data)
        self.arduino_data_received.emit(data)

    def select_rf_channel(self, channel: int) -> Tuple[bool, str]:
        """Select a specific RF switch channel (1..rf_channel_count)."""
        channel = clamp_rf_channel(channel, self.get_rf_channel_count())
        self.last_channel = channel
        if isinstance(self.device, GpioRfSwitch):
            try:
                ok = self.device.select_channel(channel)
                if ok:
                    return True, f"RF channel {channel} selected."
                return False, f"RF channel {channel} selection returned False."
            except Exception as e:
                return False, f"RF channel error: {e}"
        return True, f"RF channel {channel} selected (Virtual Mode)."

    def auto_select_rf_channel(
        self,
        channels: Optional[List[int]] = None,
        max_attempts_per_channel: int = 1,
        pause_s: float = 0.05,
    ) -> Tuple[bool, str, Optional[int]]:
        if channels is None:
            channels = list(range(1, self.get_rf_channel_count() + 1))

        seen = set()
        candidates: List[int] = []
        for ch in channels:
            if ch not in seen:
                seen.add(ch)
                candidates.append(ch)

        for ch in candidates:
            for _ in range(max_attempts_per_channel):
                try:
                    ok, msg = self.select_rf_channel(ch)
                    if ok:
                        return True, msg, ch
                except Exception as e:
                    logger.debug(f"Auto-select RF channel: exception on ch={ch}: {e}")

                time.sleep(pause_s)

        return False, "Auto RF channel selection failed for all candidates.", None

    def start_ap_mode(self) -> Tuple[bool, str]:
        try:
            self.ap_mode_enabled = True
            logger.info("Hardware: AP mode enabled (placeholder).")
            return True, "AP mode enabled."
        except Exception as e:
            return False, str(e)

    def stop_ap_mode(self) -> Tuple[bool, str]:
        try:
            self.ap_mode_enabled = False
            logger.info("Hardware: AP mode disabled (placeholder).")
            return True, "AP mode disabled."
        except Exception as e:
            return False, str(e)

    def start_bridge_server(self, ip: str, port: int) -> Tuple[bool, str]:
        if self.bridge_server_running:
            return False, "Bridge server already running."

        if not isinstance(port, int) or port < 1 or port > 65535:
            return False, "Invalid port. Must be between 1 and 65535."

        try:
            self.bridge_ip = ip
            self.bridge_port = port

            # Start background functional socket server
            self.bridge_server = HardwareBridgeServer(self, ip, port)
            success, msg = self.bridge_server.start()
            if not success:
                return False, f"Failed to start Bridge Server: {msg}"

            self.bridge_server_running = True
            logger.info(f"Hardware: Bridge server started on {ip}:{port}.")
            return True, f"Bridge server started on {ip}:{port}."
        except Exception as e:
            return False, str(e)

    def stop_bridge_server(self) -> Tuple[bool, str]:
        if not self.bridge_server_running:
            return False, "Bridge server not running."
        try:
            if self.bridge_server:
                self.bridge_server.stop()
                self.bridge_server = None
            self.bridge_server_running = False
            logger.info("Hardware: Bridge server stopped.")
            return True, "Bridge server stopped."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _diagnostics_health_fields(health: dict) -> dict:
        return {
            "arduino_online": health["motor_controller_online"],
            "motor_controller_online": health["motor_controller_online"],
            "rf_switch_ok": health["rf_switch_ok"],
            "controller_board": health["controller_board"],
            "controller_protocol": health["controller_protocol"],
            "hardware_simulated": health["hardware_simulated"],
        }

    def _resolve_downlink_mhz(self, tracking_data: dict) -> float:
        downlink = tracking_data.get("downlink_mhz")
        if downlink is not None and str(downlink).strip() not in ("", "---"):
            return _coerce_float(downlink, self.sim_params.get("manual_downlink_mhz", 0.0))
        return _coerce_float(self.sim_params.get("manual_downlink_mhz"), 0.0)

    def _resolve_bandwidth_khz(self, tracking_data: dict) -> float:
        bandwidth = tracking_data.get("bandwidth_khz")
        if bandwidth is not None and str(bandwidth).strip() not in ("", "---"):
            return _coerce_float(bandwidth, self.sim_params.get("manual_bandwidth_khz", 0.0))
        return _coerce_float(self.sim_params.get("manual_bandwidth_khz"), 0.0)

    def _build_spectrum_from_link(
        self,
        downlink_mhz: float,
        bandwidth_khz: float,
        doppler_offset_khz: float,
        snr_db: float,
        ambient_temp_c: float,
    ) -> List[float]:
        """Gaussian spectrum model using manual RF calibration and SatTrack link inputs."""
        f_center = _coerce_float(self.sim_params.get("sdr_center_mhz"), 0.0)
        span_khz = max(1.0, _coerce_float(self.sim_params.get("sdr_span_khz"), 1.0))
        T_kelvin = max(1.0, ambient_temp_c + 273.15)
        k_B = 1.3806e-23
        bin_bw_hz = (span_khz / 100.0) * 1000.0
        thermal_noise_dbm = 10.0 * math.log10(max(k_B * T_kelvin * bin_bw_hz * 1000.0, 1e-25))

        spectrum_data: List[float] = []
        f_signal = downlink_mhz + (doppler_offset_khz / 1000.0)
        sigma_mhz = max(
            1e-6,
            (bandwidth_khz / 1000.0) / (2.0 * math.sqrt(2.0 * math.log(2.0)))
            if bandwidth_khz > 0
            else 0.05,
        )

        for i in range(100):
            delta_f_khz = -(span_khz / 2.0) + i * (span_khz / 100.0)
            f_bin = f_center + (delta_f_khz / 1000.0)
            sig_dist = (f_bin - f_signal) ** 2
            power_ratio = math.exp(-sig_dist / (2 * (sigma_mhz ** 2)))
            signal_power_db = snr_db * power_ratio
            spectrum_data.append(round(thermal_noise_dbm + signal_power_db, 2))
        return spectrum_data

    def build_simulation_diagnostics_payload(
        self, tracking_data: dict, sat_name: str, health: dict
    ) -> dict:
        """Simulation deck: SatTrack telemetry + user calibration only (no wall-clock synthesis)."""
        az = _coerce_float(tracking_data.get("azimuth"), self.last_az)
        el = _coerce_float(tracking_data.get("elevation"), self.last_el)
        speed = _coerce_float(tracking_data.get("speed_kms"), 0.0)
        alt_km = _coerce_float(tracking_data.get("sataltitude"), 0.0)

        period_min = _coerce_float(tracking_data.get("period_tle_calculated_min"), 0.0)
        period_sec = period_min * 60.0 if period_min > 0 else 0.0
        orbital_rate_deg_per_sec = (360.0 / period_sec) if period_sec > 0 else 0.0

        track_err_az = self.last_track_error_az
        track_err_el = self.last_track_error_el

        doppler_offset = 0.0
        if speed > 0 and el != 0.0:
            doppler_offset = round(4.5 * (speed / 7.8) * (1 - abs(el) / 90.0), 2)

        downlink_mhz = self._resolve_downlink_mhz(tracking_data)
        bandwidth_khz = self._resolve_bandwidth_khz(tracking_data)

        path_loss_db = 0.0
        if downlink_mhz > 0 and alt_km > 0 and el != 0.0:
            freq_mhz = max(0.1, downlink_mhz)
            distance_km = max(0.1, alt_km / max(0.01, abs(math.sin(math.radians(el)))))
            path_loss_db = round(32.4 + 20 * math.log10(distance_km) + 20 * math.log10(freq_mhz), 1)

        readiness = self.evaluate_simulation_readiness(tracking_data)
        simulation_ready = readiness["simulation_ready"]
        tracking_active = simulation_ready
        eclipsed = bool(tracking_data.get("eclipsed", False))
        signal_quality = round(max(0.0, min(100.0, el)), 1) if simulation_ready else 0.0
        snr_db = round(10 + (signal_quality / 100.0) * 30, 1) if simulation_ready else 0.0
        link_margin = round(snr_db - 4.0, 1) if simulation_ready else 0.0
        gps_fix = simulation_ready and not eclipsed
        rf_channel_count = readiness["rf_channel_count"]
        active_channel = clamp_rf_channel(self.last_channel, rf_channel_count)

        mass = max(0.1, _coerce_float(self.sim_params.get("mass"), 0.0))
        gearing = max(1.0, _coerce_float(self.sim_params.get("gearing"), 1.0))
        wind_speed = _coerce_float(self.sim_params.get("wind_speed"), 0.0)
        voltage = _coerce_float(self.sim_params.get("voltage"), 0.0)
        kt = max(1e-6, _coerce_float(self.sim_params.get("kt"), 0.15))
        ambient_temp = _coerce_float(self.sim_params.get("ambient_temp"), 0.0)

        wind_pressure = (wind_speed / 50.0) ** 2 if wind_speed > 0 else 0.0
        wind_torque_nm = 0.12 * wind_pressure * mass
        reflected_inertia = 0.0015 * mass * (gearing ** 2)
        if orbital_rate_deg_per_sec > 0:
            slew_torque_nm = reflected_inertia * math.radians(orbital_rate_deg_per_sec) * 120.0
        elif speed > 0:
            slew_torque_nm = 0.002 * mass * gearing * (speed / 7.8)
        else:
            slew_torque_nm = 0.0
        total_torque_nm = wind_torque_nm + slew_torque_nm
        az_torque = min(100.0, total_torque_nm * 28.0)
        el_torque = min(100.0, total_torque_nm * 22.0)
        shaft_torque_nm = total_torque_nm / gearing
        motor_current = (shaft_torque_nm / kt) if kt > 0 else 0.0
        motor_az_current = round(motor_current, 2) if voltage > 0 else 0.0
        motor_el_current = round(motor_current * 0.85, 2) if voltage > 0 else 0.0

        wind_stow_alarm = wind_speed > 32.0
        observer_lat = _coerce_float(tracking_data.get("lat"), 0.0)
        observer_lon = _coerce_float(tracking_data.get("lng"), 0.0)
        observer_alt = _coerce_float(tracking_data.get("alt"), 0.0)

        spectrum_data = (
            self._build_spectrum_from_link(downlink_mhz, bandwidth_khz, doppler_offset, snr_db, ambient_temp)
            if tracking_active and downlink_mhz > 0
            else [0.0] * 100
        )

        response = {
            "sat_name": sat_name,
            "gpsLock": gps_fix,
            "lat": observer_lat,
            "lon": observer_lon,
            "alt": observer_alt,
            "speed": speed,
            "voltage": voltage,
            "signal_quality": signal_quality,
            "azimuth": az,
            "elevation": el,
            "rf_channel": active_channel,
            "rf_channel_count": rf_channel_count,
            "gps_fix": gps_fix,
            "doppler_offset_khz": doppler_offset,
            "vco_pll_locked": tracking_active and not eclipsed,
            "frequency_correction_hz_s": round(25.0 * doppler_offset, 1),
            "path_loss_db": path_loss_db,
            "snr_db": snr_db,
            "link_margin_db": link_margin,
            "gps_sats_visible": _coerce_int(tracking_data.get("gps_sats_visible"), 0),
            "hdop": _coerce_float(tracking_data.get("hdop"), 0.0),
            "vdop": _coerce_float(tracking_data.get("vdop"), 0.0),
            "time_deviation_ns": _coerce_int(tracking_data.get("time_deviation_ns"), 0),
            "motor_az_torque_pct": az_torque,
            "motor_el_torque_pct": el_torque,
            "encoder_slip_detected": False,
            "overcurrent_trip": motor_az_current > 12.0 or motor_el_current > 12.0,
            "undervoltage_lockout": voltage > 0 and voltage < 10.5,
            "tracking_timeout": False,
            "stow_active": wind_stow_alarm,
            "wind_stow_alarm": wind_stow_alarm,
            "wind_speed": wind_speed,
            "spectrum": spectrum_data,
            "track_error_az": track_err_az,
            "track_error_el": track_err_el,
            "motor_az_current": motor_az_current,
            "motor_el_current": motor_el_current,
            "roll": 0.0,
            "pitch": 0.0,
            "accel_x": 0.0,
            "accel_y": 0.0,
            "accel_z": 0.0,
            "limit_az_ccw": az < -180,
            "limit_az_cw": az > 180,
            "limit_el_low": el < -10,
            "limit_el_high": el > 90,
            "gps_lock": gps_fix,
            "tracking_active": tracking_active,
            "simulation_ready": simulation_ready,
            "calibration_complete": readiness["calibration_complete"],
            "tracking_complete": readiness["tracking_complete"],
            "simulation_missing": readiness["simulation_missing"],
            "tracking_sample_id": self._tracking_sample_id,
            "sim_params_revision": self._sim_params_revision,
        }
        response.update(self._diagnostics_health_fields(health))
        return response

    def build_hardware_diagnostics_payload(
        self, tracking_data: dict, sat_name: str, health: dict
    ) -> dict:
        """Direct hardware deck: values from the active controller connection only."""
        spectrum = self.last_spectrum if len(self.last_spectrum) == 100 else [0.0] * 100
        rf_channel_count = self.get_rf_channel_count()
        active_channel = clamp_rf_channel(self.last_channel, rf_channel_count)

        response = {
            "sat_name": sat_name,
            "gpsLock": self.last_gps_fix,
            "lat": self.last_gps_lat,
            "lon": self.last_gps_lon,
            "alt": self.last_gps_alt,
            "speed": self.last_gps_speed,
            "voltage": self.last_voltage,
            "signal_quality": self.last_signal_quality,
            "azimuth": self.last_az,
            "elevation": self.last_el,
            "rf_channel": active_channel,
            "rf_channel_count": rf_channel_count,
            "gps_fix": self.last_gps_fix,
            "doppler_offset_khz": self.last_doppler_offset_khz,
            "vco_pll_locked": self.last_vco_pll_locked,
            "frequency_correction_hz_s": self.last_frequency_correction_hz_s,
            "path_loss_db": self.last_path_loss_db,
            "snr_db": self.last_snr_db,
            "link_margin_db": self.last_link_margin_db,
            "gps_sats_visible": self.last_gps_sats_visible,
            "hdop": self.last_hdop,
            "vdop": self.last_vdop,
            "time_deviation_ns": self.last_time_deviation_ns,
            "motor_az_torque_pct": self.last_motor_az_torque_pct,
            "motor_el_torque_pct": self.last_motor_el_torque_pct,
            "encoder_slip_detected": self.last_encoder_slip,
            "overcurrent_trip": self.last_overcurrent_trip,
            "undervoltage_lockout": self.last_undervoltage_lockout,
            "tracking_timeout": False,
            "stow_active": self.last_stow_active,
            "wind_stow_alarm": self.last_wind_stow_alarm,
            "wind_speed": self.last_wind_speed,
            "spectrum": spectrum,
            "track_error_az": self.last_track_error_az,
            "track_error_el": self.last_track_error_el,
            "motor_az_current": self.last_motor_az_current,
            "motor_el_current": self.last_motor_el_current,
            "roll": self.last_roll,
            "pitch": self.last_pitch,
            "accel_x": self.last_accel_x,
            "accel_y": self.last_accel_y,
            "accel_z": self.last_accel_z,
            "limit_az_ccw": self.last_limit_az_ccw,
            "limit_az_cw": self.last_limit_az_cw,
            "limit_el_low": self.last_limit_el_low,
            "limit_el_high": self.last_limit_el_high,
            "gps_lock": self.last_gps_fix,
        }
        response.update(self._diagnostics_health_fields(health))
        return response

    def is_motor_controller_board(self) -> bool:
        """True when the active SatTrack connection targets antenna/motor control."""
        if isinstance(self.device, GpioRfSwitch):
            return False
        if isinstance(self.device, SerialDevice):
            return True
        if self.protocol in ("I2C", "SPI") and self.connection is not None:
            return True
        if self.protocol == "UART" and self.connection is not None:
            return getattr(self.connection, "is_open", False)
        return False

    def is_motor_controller_online(self) -> bool:
        """True when the configured motion controller link is active."""
        if not self.is_motor_controller_board():
            return False
        if isinstance(self.device, SerialDevice):
            if not self.device.connection or not self.device.connection.is_open:
                return False
            if self.current_board == "Arduino":
                return (
                    self.arduino_reader is not None
                    and self.arduino_reader.is_alive()
                )
            return True
        if self.protocol == "UART" and self.connection is not None:
            return getattr(self.connection, "is_open", False)
        if self.protocol in ("I2C", "SPI"):
            return self.connection is not None
        return False

    def is_rf_switch_online(self) -> bool:
        """True when an GPIO RF switch device is configured and available."""
        return isinstance(self.device, GpioRfSwitch)

    def get_hardware_health_status(self) -> dict:
        """Snapshot for diagnostics: motion controller, RF matrix, and board identity."""
        board = self.current_board or ""
        protocol = self.protocol or ""

        if self.simulation_mode:
            return {
                "hardware_simulated": True,
                "controller_board": board or "Simulation",
                "controller_protocol": protocol or "SIM",
                "motor_controller_online": True,
                "rf_switch_ok": True,
            }

        motor_online = self.is_motor_controller_online()
        return {
            "hardware_simulated": False,
            "controller_board": board,
            "controller_protocol": protocol,
            "motor_controller_online": motor_online,
            "rf_switch_ok": self.is_rf_switch_online(),
        }

    def send_telemetry(self, az: float, el: float) -> bool:
        """Sends Azimuth and Elevation to the hardware."""
        self.last_az = az
        self.last_el = el
        if self.device and isinstance(self.device, SerialDevice):
            return self.device.send_position(az, el)

        if not self.connection:
            return True
        
        try:
            if self.protocol == "UART":
                vis = 1 if el > 0 else 0
                cmd = f"AZ:{az:.2f},EL:{el:.2f},VIS:{vis}\n"
                self.connection.write(cmd.encode('ascii'))
                return True
        except Exception as e:
            logger.error(f"Hardware: Data send failed: {e}")
            self.disconnect()
            return False

    def disconnect(self):
        if self.arduino_reader and self.arduino_reader.is_alive():
            self.arduino_reader.stop()
            self.arduino_reader.join(timeout=1)
            self.arduino_reader = None

        if self.device:
            try:
                self.device.cleanup()
            except Exception:
                pass
            self.device = None

        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None

        self.connection_changed.emit(False, "Disconnected")
        logger.info("Hardware: Connection closed.")