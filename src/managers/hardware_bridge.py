# -*- coding: utf-8 -*-
import json
import logging
import threading
import time
from typing import Callable, Optional

import serial

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    GPIO = None
    logger.warning("GPIO library not available; GPIO-based RF switch support will be disabled.")


class ArduinoReader(threading.Thread):
    """Continuously reads JSON telemetry from an Arduino serial device."""

    def __init__(self, serial_device: "SerialDevice", callback: Optional[Callable[[dict], None]] = None):
        super().__init__(name="ArduinoReaderThread")
        self.serial_device = serial_device
        self.callback = callback
        self.running = True
        self.daemon = True

    def run(self):
        logger.info("Arduino reader thread started.")
        while self.running:
            if not self.serial_device or not self.serial_device.connection or not self.serial_device.connection.is_open:
                time.sleep(1)
                continue
            try:
                line = self.serial_device.connection.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                if line.startswith("{") and line.endswith("}"):
                    data = json.loads(line)
                    logger.debug(f"Received Arduino telemetry: {data}")
                    if self.callback:
                        try:
                            self.callback(data)
                        except Exception as exc:
                            logger.error(f"Arduino reader callback error: {exc}")
            except serial.SerialException as e:
                logger.error(f"Arduino serial error: {e}")
                time.sleep(2)
            except json.JSONDecodeError:
                logger.warning(f"Malformed JSON from Arduino: {line}")
            except Exception as e:
                logger.exception(f"Unexpected error in Arduino reader: {e}")
                time.sleep(2)
        logger.info("Arduino reader thread stopped.")

    def stop(self):
        self.running = False


class SerialDevice:
    """Handles a serial device connection for Arduino-style command interfaces."""

    def __init__(self, port: str, baud_rate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.connection: Optional[serial.Serial] = None
        self.connect()

    def connect(self) -> bool:
        try:
            self.connection = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
            time.sleep(2)
            if self.connection.is_open:
                logger.info(f"Serial device connected on {self.port}.")
                return True
        except Exception as e:
            logger.error(f"Failed to open serial device {self.port}: {e}")
            self.connection = None
        return False

    def send_position(self, az: float, el: float):
        if not self.connection or not self.connection.is_open:
            logger.warning("SerialDevice: not connected, cannot send position.")
            return False
        vis = 1 if el > 0 else 0
        command = f"AZ:{az:.2f},EL:{el:.2f},VIS:{vis}\n"
        try:
            self.connection.write(command.encode("ascii"))
            logger.debug(f"SerialDevice: sent {command.strip()}")
            return True
        except Exception as e:
            logger.error(f"SerialDevice write failed: {e}")
            self.close()
            return False

    def close(self):
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None
            logger.info(f"Serial device on {self.port} closed.")

    def cleanup(self):
        self.close()


class GpioRfSwitch:
    """Controls an N-channel GPIO RF switch using digital outputs (3-bit address, up to 8 lines)."""

    def __init__(self, s0: int, s1: int, s2: int, override_pin: int, max_channels: int = 8):
        if GPIO is None:
            raise RuntimeError("GPIO is not available on this platform.")
        self.max_channels = max(1, min(int(max_channels), 8))
        self.pins = {"s0": s0, "s1": s1, "s2": s2, "override": override_pin}
        self._setup_gpio()

    def _setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in self.pins.values():
            GPIO.setup(pin, GPIO.OUT)
        self.release_control()
        logger.info(f"RF switch GPIO configured: {self.pins}")

    def select_channel(self, channel: int):
        if channel < 1 or channel > self.max_channels:
            logger.error(f"Invalid RF channel: {channel} (max {self.max_channels})")
            return False
        GPIO.output(self.pins["override"], GPIO.LOW)
        time.sleep(0.1)
        code = channel - 1
        GPIO.output(self.pins["s0"], (code >> 0) & 1)
        GPIO.output(self.pins["s1"], (code >> 1) & 1)
        GPIO.output(self.pins["s2"], (code >> 2) & 1)
        logger.info(f"RF switch channel selected: {channel}")
        return True

    def release_control(self):
        GPIO.output(self.pins["override"], GPIO.HIGH)

    def cleanup(self):
        self.release_control()
        logger.info("RF switch GPIO cleaned up.")
