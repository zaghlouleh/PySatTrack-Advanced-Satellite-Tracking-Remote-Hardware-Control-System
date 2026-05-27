# -*- coding: utf-8 -*-
"""TCP JSON client for the Raspberry Pi hardware bridge."""

from __future__ import annotations

import json
import socket
import threading
from typing import Optional, Tuple, Any

from PyQt5.QtCore import QObject, pyqtSignal

from src.utils.logger import logger


class HardwareBridgeClient(QObject):
    """Manages a TCP client connection to the hardware bridge server."""

    connection_changed = pyqtSignal(bool, str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.sock: Optional[socket.socket] = None
        self.is_connected: bool = False
        self._lock = threading.Lock()

    def connect(self, host: str, port: int) -> Tuple[bool, str]:
        """Connects to the hardware bridge server."""
        self.disconnect()
        try:
            with self._lock:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)
                self.sock.connect((host, port))
                self.sock.settimeout(None)

            self.is_connected = True
            msg = f"Connected to bridge at {host}:{port}"
            logger.info(msg)
            self.connection_changed.emit(True, msg)
            return True, msg
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            msg = f"Failed to connect: {e}"
            logger.error(msg)
            self.connection_changed.emit(False, msg)
            self.is_connected = False
            self.sock = None
            return False, msg

    def disconnect(self) -> None:
        """Disconnects from the hardware bridge server."""
        with self._lock:
            if self.sock is not None:
                try:
                    try:
                        self.sock.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
                    self.sock.close()
                except Exception as e:
                    logger.warning(f"Error while closing bridge socket: {e}")
            self.sock = None

        if self.is_connected:
            self.is_connected = False
            self.connection_changed.emit(False, "Disconnected")
            logger.info("Disconnected from hardware bridge.")

    def _send_command(self, command_obj: dict) -> bool:
        """Sends a JSON-formatted command to the bridge."""
        if not self.is_connected or self.sock is None:
            logger.warning("Cannot send command: bridge not connected")
            return False

        try:
            json_data = json.dumps(command_obj)
            with self._lock:
                self.sock.sendall(json_data.encode("utf-8"))
            logger.debug(f"Bridge sent command: {json_data}")
            return True
        except (socket.error, BrokenPipeError) as e:
            logger.error(f"Bridge socket error on send: {e}. Disconnecting.")
            self.disconnect()
            return False

    def get_gps_status(self, simulation_mode: bool = True) -> Optional[dict]:
        """Requests the latest GPS status from the hardware bridge with active mode flag."""
        command = {
            "type": "GET_GPS_STATUS",
            "payload": {"simulation_mode": simulation_mode}
        }
        if not self._send_command(command):
            return None

        try:
            with self._lock:
                if self.sock is None:
                    return None
                self.sock.settimeout(2.0)
                response_data = self.sock.recv(4096)

            if not response_data:
                return None

            status = json.loads(response_data.decode("utf-8"))
            logger.debug(f"Received GPS status from bridge: {status}")
            return status
        except (socket.timeout, json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to receive GPS status from bridge: {e}")
            return None
        finally:
            try:
                if self.sock is not None:
                    self.sock.settimeout(None)
            except Exception:
                pass

    def send_rf_channel(self, device_id: str, channel: int) -> bool:
        """Convenience method to send RF switch channel command."""
        command = {
            "type": "SET_RF_CHANNEL",
            "device_id": device_id,
            "payload": {"channel": int(channel)},
        }
        return self._send_command(command)

    def send_antenna_position(self, device_id: str, az: float, el: float) -> bool:
        """Convenience method to send antenna steering command."""
        command = {
            "type": "SET_ANTENNA_POSITION",
            "device_id": device_id,
            "payload": {"azimuth": float(az), "elevation": float(el)},
        }
        return self._send_command(command)