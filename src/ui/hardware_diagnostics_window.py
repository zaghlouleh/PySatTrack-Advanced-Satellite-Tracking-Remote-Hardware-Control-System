# src/ui/hardware_diagnostics_window.py
# -*- coding: utf-8 -*-
"""
Professional Satellite Tracking Ground Station Diagnostics Dashboard.

Features:
- Unified single-view cockpit deck designed for 1080p and laptop viewports
- Vector-drawn Platform Attitude crosshair (stabilization/deflection feedback)
- Horizontal limit switches and time-sync safety lock indicator strip
- Core Positioning Motor diagnostics (Azimuth & Elevation feedback)
- 8:1 RF Switch visual schematic route
- Double-axis tracking error time-series plots
- RF Spectrum power plot
- Auto-collapsing layouts with strict vertical height bounds
"""

from __future__ import annotations

import math
import time
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None  # for local system metrics
from collections import deque
from typing import Dict, Deque, List, Any, Optional

import numpy as np
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QGroupBox, QFrame,
    QMessageBox, QTextEdit, QProgressBar, QComboBox, QTabWidget, QDoubleSpinBox,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize, QRect, QPoint
from PyQt5.QtGui import QFont, QColor, QPalette, QBrush, QPen, QTextCursor, QPainter, QPolygon

import pyqtgraph as pg
from pyqtgraph import PlotWidget

from src.managers.hardware_diagnostics_client import HardwareDiagnosticsClient
from src.utils.logger import logger
from src.utils.station_profile import (
    DEFAULT_RF_CHANNEL_COUNT,
    MAX_RF_CHANNEL_COUNT,
    validate_calibration,
)


# ----------------------------------------------------------------------
# Custom Circular Gauge (Optimized Modern Arc Dial)
# ----------------------------------------------------------------------
class CircularGauge(QWidget):
    def __init__(self, title: str, min_val: float = 0.0, max_val: float = 100.0,
                 units: str = "", warn_thresh: float = 70.0, crit_thresh: float = 90.0,
                 parent=None):
        super().__init__(parent)
        self.title = title
        self.min_val = min_val
        self.max_val = max_val
        self.units = units
        self.value = min_val
        self.warn_thresh = warn_thresh
        self.crit_thresh = crit_thresh
        self.setMinimumSize(100, 100)
        self.setMaximumSize(140, 140)

    def setValue(self, value: float):
        self.value = max(self.min_val, min(self.max_val, value))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        side = min(width, height) - 6
        x = int((width - side) // 2)
        y = int((height - side) // 2)

        # Draw structural track arc (270 degrees)
        start_angle = int(225 * 16)
        span_angle = int(-270 * 16)

        pen_bg = QPen(QColor(43, 43, 58), 6)
        pen_bg.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(x + 8, y + 8, side - 16, side - 16, start_angle, span_angle)

        # Draw active telemetry level path (with division guard)
        denom = max((self.max_val - self.min_val), 1e-5)
        frac = (self.value - self.min_val) / denom
        frac = max(0.0, min(1.0, frac))
        active_span = int(frac * -270 * 16)

        # Threshold assessment
        if self.warn_thresh > self.crit_thresh:
            if self.value >= self.warn_thresh:
                color = QColor(0, 230, 118)   # Green (Normal)
            elif self.value >= self.crit_thresh:
                color = QColor(255, 214, 0)   # Yellow (Warning)
            else:
                color = QColor(255, 82, 82)    # Red (Fault)
        else:
            if self.value <= self.warn_thresh:
                color = QColor(0, 230, 118)
            elif self.value <= self.crit_thresh:
                color = QColor(255, 214, 0)
            else:
                color = QColor(255, 82, 82)

        pen_fg = QPen(color, 6)
        pen_fg.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_fg)
        if active_span != 0:
            painter.drawArc(x + 8, y + 8, side - 16, side - 16, start_angle, active_span)

        # Draw internal labels
        painter.setPen(QColor(200, 200, 215))
        font_title = QFont("Segoe UI", 7, QFont.Bold)
        painter.setFont(font_title)
        title_rect = QRect(x, y + int(side * 0.28), side, 14)
        painter.drawText(title_rect, Qt.AlignCenter, self.title)

        font_val = QFont("Segoe UI", 11, QFont.Bold)
        painter.setFont(font_val)
        val_rect = QRect(x, y + int(side * 0.48), side, 18)
        val_str = f"{self.value:.1f}" if self.max_val - self.min_val < 500 else f"{int(self.value)}"
        if self.units:
            val_str += f" {self.units}"
        painter.drawText(val_rect, Qt.AlignCenter, val_str)


# ----------------------------------------------------------------------
# Platform Stabilization Crosshair (Pitch / Roll Attitude)
# ----------------------------------------------------------------------
class PlatformAttitudeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(120, 120)
        self.setMaximumSize(180, 180)
        self.roll = 0.0
        self.pitch = 0.0

    def set_attitude(self, roll: float, pitch: float):
        self.roll = max(-15.0, min(15.0, roll))
        self.pitch = max(-15.0, min(15.0, pitch))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        side = min(w, h) - 10
        center_x = w // 2
        center_y = h // 2
        radius = side // 2

        # Outer background
        painter.fillRect(self.rect(), QColor(22, 22, 32))
        painter.setPen(QPen(QColor(50, 50, 68), 1))
        painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)

        # Draw compass crosshairs
        painter.setPen(QPen(QColor(50, 50, 68, 120), 1, Qt.DashLine))
        painter.drawLine(center_x - radius, center_y, center_x + radius, center_y)
        painter.drawLine(center_x, center_y - radius, center_x, center_y + radius)

        # Static reference concentric ring (Safe 5-degree limit line)
        limit_r = int(radius * (5.0 / 15.0))
        painter.setPen(QPen(QColor(255, 214, 0, 80), 1, Qt.SolidLine))
        painter.drawEllipse(center_x - limit_r, center_y - limit_r, limit_r * 2, limit_r * 2)

        # Map dynamic Roll (X axis deviation) and Pitch (Y axis deviation)
        # Scale to max deflection of +/- 15 deg
        offset_x = int((self.roll / 15.0) * radius)
        offset_y = int((-self.pitch / 15.0) * radius)  # inverted for pitch-up display
        target_x = center_x + offset_x
        target_y = center_y + offset_y

        # Determine stability color based on deflection
        deviation = np.sqrt(self.roll**2 + self.pitch**2)
        if deviation < 3.0:
            pt_color = QColor(0, 230, 118)  # Stable green
        elif deviation < 8.0:
            pt_color = QColor(255, 214, 0)  # Deviating yellow
        else:
            pt_color = QColor(255, 82, 82)   # Fault red

        # Draw current tilt attitude point
        painter.setBrush(QBrush(pt_color))
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        painter.drawEllipse(target_x - 5, target_y - 5, 10, 10)

        # Crosshair reticle
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(pt_color, 1))
        painter.drawEllipse(target_x - 10, target_y - 10, 20, 20)

        # Text readouts
        painter.setPen(QColor(160, 160, 180))
        painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
        painter.drawText(QRect(6, h - 20, 80, 16), Qt.AlignLeft | Qt.AlignVCenter, f"R: {self.roll:+.1f}°")
        painter.drawText(QRect(w - 86, h - 20, 80, 16), Qt.AlignRight | Qt.AlignVCenter, f"P: {self.pitch:+.1f}°")


# ----------------------------------------------------------------------
# Dynamic Limit Switches & Signal Lock Annunciator Ribbon
# ----------------------------------------------------------------------
class LimitSwitchesWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self.pills: Dict[str, QLabel] = {}
        labels = [
            "AZ CCW LIM", "AZ CW LIM", "EL LOW LIM", "EL HIGH LIM", "GPS PPS LOCK",
            "OVR-CURR TRIP", "UV LOCKOUT", "STOW ACTIVE", "ENC SLIP DET"
        ]

        for label in labels:
            pill = QLabel(label)
            pill.setAlignment(Qt.AlignCenter)
            pill.setFont(QFont("Segoe UI", 7, QFont.Bold))
            pill.setStyleSheet("""
                color: #888899; 
                background-color: #1e1e2d; 
                border: 1px solid #3c3c4d; 
                border-radius: 3px; 
                padding: 3px;
            """)
            layout.addWidget(pill)
            self.pills[label] = pill

    def set_states(self, az_ccw: bool, az_cw: bool, el_low: bool, el_high: bool, pps_lock: bool,
                   overcurrent: bool, undervoltage: bool, stow_active: bool, enc_slip: bool):
        """Update display state of limit switches, GNSS sync status, and motor driver alarms."""
        def style_limit(tripped: bool):
            if tripped:
                return "color: #ff5252; background-color: #3d0000; border: 1px solid #ff5252; border-radius: 3px; padding: 3px;"
            return "color: #888899; background-color: #151522; border: 1px solid #2a2a38; border-radius: 3px; padding: 3px;"

        def style_lock(locked: bool):
            if locked:
                return "color: #00e676; background-color: #002d18; border: 1px solid #00e676; border-radius: 3px; padding: 3px;"
            return "color: #ffd600; background-color: #332a00; border: 1px solid #ffd600; border-radius: 3px; padding: 3px;"

        self.pills["AZ CCW LIM"].setStyleSheet(style_limit(az_ccw))
        self.pills["AZ CW LIM"].setStyleSheet(style_limit(az_cw))
        self.pills["EL LOW LIM"].setStyleSheet(style_limit(el_low))
        self.pills["EL HIGH LIM"].setStyleSheet(style_limit(el_high))
        self.pills["GPS PPS LOCK"].setStyleSheet(style_lock(pps_lock))
        
        self.pills["OVR-CURR TRIP"].setStyleSheet(style_limit(overcurrent))
        self.pills["UV LOCKOUT"].setStyleSheet(style_limit(undervoltage))
        self.pills["STOW ACTIVE"].setStyleSheet(style_lock(stow_active))
        self.pills["ENC SLIP DET"].setStyleSheet(style_limit(enc_slip))


# ----------------------------------------------------------------------
# Component Checklist Badge
# ----------------------------------------------------------------------
class HealthIndicator(QWidget):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(6)

        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("color: #d1d1e0; font-family: 'Segoe UI'; font-size: 11px;")

        self.status_pill = QLabel("UNKNOWN")
        self.status_pill.setAlignment(Qt.AlignCenter)
        self.status_pill.setFixedWidth(65)
        self.status_pill.setStyleSheet("""
            color: #888899; 
            background-color: #20202e; 
            border: 1px solid #3c3c4d; 
            border-radius: 3px; 
            font-family: 'Segoe UI'; 
            font-size: 8px; 
            font-weight: bold;
        """)

        layout.addWidget(self.name_label)
        layout.addStretch()
        layout.addWidget(self.status_pill)

    def set_status(self, status: str):
        style_map = {
            'ok': "color: #00e676; background-color: #002d18; border: 1px solid #00e676; border-radius: 3px; font-family: 'Segoe UI'; font-size: 8px; font-weight: bold;",
            'warning': "color: #ffd600; background-color: #332a00; border: 1px solid #ffd600; border-radius: 3px; font-family: 'Segoe UI'; font-size: 8px; font-weight: bold;",
            'error': "color: #ff5252; background-color: #3d0000; border: 1px solid #ff5252; border-radius: 3px; font-family: 'Segoe UI'; font-size: 8px; font-weight: bold;",
            'unknown': "color: #888899; background-color: #20202e; border: 1px solid #3c3c4d; border-radius: 3px; font-family: 'Segoe UI'; font-size: 8px; font-weight: bold;"
        }
        self.status_pill.setText(status.upper())
        self.status_pill.setStyleSheet(style_map.get(status, style_map['unknown']))


# ----------------------------------------------------------------------
# Local Resource Monitor Bar
# ----------------------------------------------------------------------
class ResourceBar(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(6)

        self.label = QLabel(label)
        self.label.setFixedWidth(80)
        self.label.setStyleSheet("color: #a0a0b0; font-family: 'Segoe UI'; font-size: 11px;")

        self.bar = QProgressBar()
        self.bar.setFixedHeight(6)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet("""
            QProgressBar {
                background-color: #1a1a26;
                border: 1px solid #2d2d3d;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: QLinearGradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #2979ff, stop: 1 #00e676);
                border-radius: 2px;
            }
        """)

        self.val_label = QLabel("0%")
        self.val_label.setFixedWidth(30)
        self.val_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.val_label.setStyleSheet("color: #d1d1e0; font-family: 'Segoe UI'; font-size: 10px; font-weight: bold;")

        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        layout.addWidget(self.val_label)

    def setValue(self, value: int):
        self.bar.setValue(value)
        self.val_label.setText(f"{value}%")


# ----------------------------------------------------------------------
# Physical RF Switch Path Visualizer (Vector Block Diagram)
# ----------------------------------------------------------------------
class RFSignalChainWidget(QWidget):
    def __init__(self, channel_count: int = DEFAULT_RF_CHANNEL_COUNT, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(115)
        self.setMaximumHeight(130)
        self.channel_count = max(1, min(int(channel_count), MAX_RF_CHANNEL_COUNT))
        self.active_channel = 1
        self.is_connected = False

    def set_channel_count(self, channel_count: int) -> None:
        self.channel_count = max(1, min(int(channel_count), MAX_RF_CHANNEL_COUNT))
        if self.active_channel > self.channel_count:
            self.active_channel = self.channel_count
        self.update()

    def set_channel(self, channel: int, connected: bool):
        self.active_channel = max(1, min(int(channel), self.channel_count))
        self.is_connected = connected
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # Canvas outline
        painter.fillRect(self.rect(), QColor(18, 18, 26))
        painter.setPen(QPen(QColor(40, 40, 56), 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        # Title block
        painter.setPen(QColor(120, 120, 140))
        painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
        painter.drawText(8, 14, "RF COUPLER SIGNAL SWITCH")

        ant_x = 25
        mux_x = w // 2 - 20
        rec_x = w - 55

        # Define 8:1 Mux frame dimensions
        mux_w = 40
        mux_h = 60
        mux_y = (h - mux_h) // 2 + 5

        painter.setPen(QPen(QColor(70, 70, 90), 1.2))
        painter.setBrush(QBrush(QColor(28, 28, 40)))
        painter.drawRoundedRect(int(mux_x), int(mux_y), int(mux_w), int(mux_h), 3, 3)

        painter.setPen(QColor(130, 130, 150))
        painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
        mux_label = f"{self.channel_count}:1 MUX"
        painter.drawText(QRect(int(mux_x), int(mux_y - 4), int(mux_w), 12), Qt.AlignCenter, mux_label)

        # Map channel wires
        slot_count = max(self.channel_count, 1)
        for ch in range(1, self.channel_count + 1):
            ch_y = int(mux_y + 5 + (ch - 1) * (mux_h - 10) // max(slot_count - 1, 1))
            start_x = int(ant_x + 12)

            is_active = self.is_connected and (ch == self.active_channel)
            if is_active:
                pen_wire = QPen(QColor(0, 230, 118), 1.8)
                brush_dot = QBrush(QColor(0, 230, 118))
            else:
                pen_wire = QPen(QColor(45, 45, 60), 0.8)
                brush_dot = QBrush(QColor(55, 55, 75))

            painter.setPen(pen_wire)
            painter.drawLine(int(start_x), int(ch_y), int(mux_x), int(ch_y))

            painter.setBrush(brush_dot)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(int(start_x) - 3, int(ch_y) - 3, 6, 6)

            if is_active:
                painter.setPen(QColor(0, 230, 118))
                painter.setFont(QFont("Segoe UI", 6, QFont.Bold))
                painter.drawText(QRect(int(start_x - 22), int(ch_y - 6), 16, 12), Qt.AlignRight | Qt.AlignVCenter, f"P{ch}")

            # Draw small channel label near each wire for clarity
            try:
                painter.setPen(QColor(160, 160, 180))
                painter.setFont(QFont("Segoe UI", 7))
                painter.drawText(QRect(int(start_x - 30), int(ch_y - 8), 28, 12), Qt.AlignLeft | Qt.AlignVCenter, f"CH {ch}")
            except Exception:
                pass

        # Antenna Visual Block
        painter.setPen(QPen(QColor(90, 90, 110), 1.2))
        painter.setBrush(QBrush(QColor(32, 32, 48)))
        painter.drawPolygon(QPolygon([
            QPoint(int(ant_x - 8), int(mux_y)),
            QPoint(int(ant_x + 8), int(mux_y)),
            QPoint(int(ant_x), int(mux_y + 12))
        ]))
        painter.drawLine(int(ant_x), int(mux_y + 12), int(ant_x), int(mux_y + mux_h))
        painter.setFont(QFont("Segoe UI", 6, QFont.Bold))
        painter.setPen(QColor(140, 140, 160))
        painter.drawText(QRect(int(ant_x - 20), int(mux_y + mux_h + 1), 40, 10), Qt.AlignCenter, "ANTENNA")

        # Active Output Wire to Receiver Block
        out_y = int(mux_y + mux_h // 2)
        receiver_y = int(out_y - 12)

        if self.is_connected:
            pen_out = QPen(QColor(0, 230, 118), 1.8)
            brush_rec = QColor(20, 90, 40)
            text_color = QColor(200, 250, 200)
        else:
            pen_out = QPen(QColor(45, 45, 60), 0.8)
            brush_rec = QColor(32, 32, 48)
            text_color = QColor(110, 110, 130)

        painter.setPen(pen_out)
        painter.drawLine(int(mux_x + mux_w), int(out_y), int(rec_x), int(out_y))

        # Label the active output path
        try:
            mid_x = int(mux_x + mux_w + (rec_x - (mux_x + mux_w)) // 2)
            painter.setPen(QColor(140, 140, 160))
            painter.setFont(QFont("Segoe UI", 7))
            painter.drawText(QRect(mid_x - 18, int(out_y) - 10, 36, 12), Qt.AlignCenter, "TO RX")
        except Exception:
            pass

        # Draw Demodulator Node
        painter.setPen(QPen(QColor(90, 90, 110), 1.2))
        painter.setBrush(QBrush(brush_rec))
        painter.drawRoundedRect(int(rec_x), int(receiver_y), 40, 24, 2, 2)

        painter.setPen(text_color)
        painter.setFont(QFont("Segoe UI", 6, QFont.Bold))
        painter.drawText(QRect(int(rec_x), int(receiver_y), 40, 24), Qt.AlignCenter, "RX\nSTAGE")


# ----------------------------------------------------------------------
# Integrated Ground Station Workstation
# ----------------------------------------------------------------------
class HardwareDiagnosticsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Satellite Ground Station Command Deck")
        self.setMinimumSize(1300, 800)

        # Strict styling with zero vertical excess
        self.setStyleSheet("""
            QMainWindow { background-color: #0c0c11; }
            QGroupBox { 
                color: #8c8ca2; 
                border: 1px solid #1f1f2e; 
                border-radius: 4px; 
                margin-top: 10px; 
                font-weight: bold;
                font-family: 'Segoe UI';
                font-size: 10px;
            }
            QGroupBox::title { 
                subcontrol-origin: margin; 
                left: 8px; 
                padding: 0 4px; 
            }
            QLabel { color: #c3c3d5; font-family: 'Segoe UI'; font-size: 10px; }
            QPushButton { 
                background-color: #1e222d; 
                color: #dddddd; 
                border: 1px solid #2e3347; 
                padding: 3px 8px; 
                border-radius: 2px; 
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2a2f42; border: 1px solid #3e455f; }
            QPushButton:pressed { background-color: #141720; }
            QLineEdit, QSpinBox, QDoubleSpinBox { 
                background-color: #11111a; 
                color: #eeeeee; 
                border: 1px solid #252538; 
                border-radius: 2px; 
                padding: 2px; 
                font-family: 'Segoe UI';
                font-size: 10px;
            }
            QComboBox {
                background-color: #11111a; 
                color: #eeeeee; 
                border: 1px solid #252538; 
                border-radius: 2px; 
                padding: 2px; 
                font-family: 'Segoe UI';
                font-size: 10px;
            }
            QTextEdit { 
                background-color: #060609; 
                color: #abb2bf; 
                border: 1px solid #1f1f2e; 
                font-family: 'Consolas', 'Courier New'; 
                font-size: 10px; 
            }
            QTabWidget::pane {
                border: 1px solid #1e1e2d;
                background-color: #0f0f16;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #161622;
                color: #a0a0b0;
                padding: 4px 10px;
                border-radius: 2px;
                margin-right: 2px;
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #1f1f2e;
                color: #64B5F6;
            }
        """)

        self.client = HardwareDiagnosticsClient(poll_interval_s=0.5, history_seconds=120.0)
        self.client.status_changed.connect(self._on_connection_status)
        self.client.telemetry_updated.connect(self._on_telemetry_update)

        # Non-blocking host core update timer
        self.system_timer = QTimer()
        self.system_timer.timeout.connect(self._update_system_health)
        self.system_timer.start(2000)

        self._setup_ui()
        self._init_dynamic_plots()
        self._connected = False
        self._set_data_widgets_enabled(False)
        self._refresh_local_calibration_banner()

        self._host = "127.0.0.1"
        self._port = 5000

    @staticmethod
    def _add_calibration_field(layout: QVBoxLayout, label_text: str, spinbox: QDoubleSpinBox) -> None:
        """Place label and control on one row for the calibration column."""
        row = QHBoxLayout()
        row.setSpacing(6)
        label = QLabel(label_text)
        label.setWordWrap(True)
        label.setMinimumWidth(1)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        spinbox.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        spinbox.setMinimumWidth(85)
        row.addWidget(label, 1)
        row.addWidget(spinbox, 0, Qt.AlignRight)
        layout.addLayout(row)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # ------------------------------------------------------------------
        # Top Panel: Connection Bridge Controls & System Safety Ribbon
        # ------------------------------------------------------------------
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        top_bar_layout.setSpacing(6)
        main_layout.addWidget(top_bar)

        conn_frame = QFrame()
        conn_frame.setStyleSheet("background-color: #11111a; border-radius: 3px; border: 1px solid #1f1f2e;")
        conn_layout = QHBoxLayout(conn_frame)
        conn_layout.setContentsMargins(6, 3, 6, 3)
        conn_layout.setSpacing(8)

        conn_layout.addWidget(QLabel("BRIDGE:"))
        self.ip_edit = QLineEdit("127.0.0.1")
        self.ip_edit.setMaximumWidth(90)
        conn_layout.addWidget(self.ip_edit)

        conn_layout.addWidget(QLabel("PORT:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(5000)
        self.port_spin.setMaximumWidth(60)
        conn_layout.addWidget(self.port_spin)

        # Operating Mode Selection Toggle
        conn_layout.addWidget(QLabel("MODE:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["[SIMULATION MODE]", "[DIRECT HARDWARE]"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        conn_layout.addWidget(self.mode_combo)

        self.connect_btn = QPushButton("Establish Link")
        self.connect_btn.setStyleSheet("background-color: #1b5e20; color: white;")
        self.connect_btn.clicked.connect(self._toggle_connection)
        conn_layout.addWidget(self.connect_btn)

        self.status_label = QLabel("DISCONNECTED")
        self.status_label.setStyleSheet("color: #ff5252; font-weight: bold; font-family: 'Segoe UI';")
        conn_layout.addWidget(self.status_label)
        top_bar_layout.addWidget(conn_frame)

        self.safety_ribbon = LimitSwitchesWidget()
        self.safety_ribbon.setStyleSheet("background-color: #11111a; border-radius: 3px; border: 1px solid #1f1f2e;")
        top_bar_layout.addWidget(self.safety_ribbon)

        self.sim_readiness_banner = QLabel(
            "SIMULATION: Complete Calibration (all tabs) and start SatTrack tracking before charts run."
        )
        self.sim_readiness_banner.setWordWrap(True)
        self.sim_readiness_banner.setStyleSheet(
            "color: #ffd600; background-color: #2a2200; border: 1px solid #665500; "
            "border-radius: 3px; padding: 4px 8px; font-family: 'Segoe UI'; font-size: 10px;"
        )
        main_layout.addWidget(self.sim_readiness_banner)

        # ------------------------------------------------------------------
        # Main Cockpit Workstation Layout
        # ------------------------------------------------------------------
        deck_layout = QHBoxLayout()
        deck_layout.setSpacing(4)
        main_layout.addLayout(deck_layout)

        # ---- COLUMN 1: System Command & Motion Health Panel (Left) ----
        col1 = QWidget()
        col1.setFixedWidth(290)
        col1_layout = QVBoxLayout(col1)
        col1_layout.setContentsMargins(0, 0, 0, 0)
        col1_layout.setSpacing(4)
        deck_layout.addWidget(col1)

        # Tab Widget for Left Pane Organisation
        self.left_tabs = QTabWidget()
        col1_layout.addWidget(self.left_tabs, 1)

        # Tab 1: Live Status & Hardware Interface Matrices
        tab_status = QWidget()
        tab_status_layout = QVBoxLayout(tab_status)
        tab_status_layout.setContentsMargins(2, 2, 2, 2)
        tab_status_layout.setSpacing(4)

        health_group = QGroupBox("STATION INTERFACE MATRIX")
        health_box = QVBoxLayout(health_group)
        health_box.setContentsMargins(6, 4, 6, 4)
        health_box.setSpacing(2)

        self.gps_health = HealthIndicator("GPS GNSS Subsystem")
        self.rf_health = HealthIndicator("RF Ant. Switch Matrix")
        self.antenna_health = HealthIndicator("Drive Motor Controllers")
        self.bridge_health = HealthIndicator("TCP Bridge Uplink")
        self.controller_health = HealthIndicator("Motion Controller")

        health_box.addWidget(self.gps_health)
        health_box.addWidget(self.rf_health)
        health_box.addWidget(self.antenna_health)
        health_box.addWidget(self.bridge_health)
        health_box.addWidget(self.controller_health)
        tab_status_layout.addWidget(health_group)

        sys_group = QGroupBox("HOST CONTROLLER MONITOR")
        sys_box = QVBoxLayout(sys_group)
        sys_box.setContentsMargins(6, 4, 6, 4)
        sys_box.setSpacing(2)

        self.cpu_bar = ResourceBar("Host CPU Load")
        self.ram_bar = ResourceBar("Host RAM Load")
        self.disk_bar = ResourceBar("Host Drive Cap")
        self.sys_temp_label = QLabel("Host Core Temp: -- °C")
        self.sys_temp_label.setStyleSheet("color: #8f8fa4; font-family: 'Segoe UI'; font-size: 9px; font-weight: bold;")

        sys_box.addWidget(self.cpu_bar)
        sys_box.addWidget(self.ram_bar)
        sys_box.addWidget(self.disk_bar)
        sys_box.addWidget(self.sys_temp_label)
        tab_status_layout.addWidget(sys_group)
        tab_status_layout.addStretch()

        self.left_tabs.addTab(tab_status, "Systems")

        # Tab 2: Calibration Specs & Overrides (sectioned sub-tabs)
        tab_calibration = QWidget()
        tab_cal_layout = QVBoxLayout(tab_calibration)
        tab_cal_layout.setContentsMargins(4, 4, 4, 4)
        tab_cal_layout.setSpacing(0)

        cal_sections = QTabWidget()
        cal_sections.setDocumentMode(True)
        cal_sections.tabBar().setExpanding(True)

        # --- Mechanical coefficients ---
        tab_mech = QWidget()
        mech_layout = QVBoxLayout(tab_mech)
        mech_layout.setContentsMargins(4, 6, 4, 4)
        mech_layout.setSpacing(6)

        spec_group = QGroupBox("MECHANICAL SPEC COEFFICIENTS")
        spec_col = QVBoxLayout(spec_group)
        spec_col.setContentsMargins(6, 8, 6, 6)
        spec_col.setSpacing(8)

        self.spin_mass = QDoubleSpinBox()
        self.spin_mass.setRange(0.1, 500.0)
        self.spin_mass.setValue(12.5)
        self.spin_mass.setSingleStep(0.5)
        self.spin_mass.valueChanged.connect(self._send_simulation_params)
        self._add_calibration_field(spec_col, "Dish Mass (kg)", self.spin_mass)

        self.spin_gearing = QDoubleSpinBox()
        self.spin_gearing.setRange(1.0, 1000.0)
        self.spin_gearing.setValue(120.0)
        self.spin_gearing.setSingleStep(1.0)
        self.spin_gearing.valueChanged.connect(self._send_simulation_params)
        self._add_calibration_field(spec_col, "Gearbox Ratio (N:1)", self.spin_gearing)

        self.spin_kt = QDoubleSpinBox()
        self.spin_kt.setRange(0.01, 10.0)
        self.spin_kt.setValue(0.15)
        self.spin_kt.setSingleStep(0.01)
        self.spin_kt.setDecimals(3)
        self.spin_kt.valueChanged.connect(self._send_simulation_params)
        self._add_calibration_field(spec_col, "Motor Const. Kt (Nm/A)", self.spin_kt)

        mech_layout.addWidget(spec_group)
        mech_layout.addStretch()
        cal_sections.addTab(tab_mech, "Mechanical")

        # --- Environment & power ---
        tab_env = QWidget()
        env_layout = QVBoxLayout(tab_env)
        env_layout.setContentsMargins(4, 6, 4, 4)
        env_layout.setSpacing(6)

        env_group = QGroupBox("ENVIRONMENT & POWER OVERRIDES")
        env_col = QVBoxLayout(env_group)
        env_col.setContentsMargins(6, 8, 6, 6)
        env_col.setSpacing(8)

        self.spin_wind = QDoubleSpinBox()
        self.spin_wind.setRange(0.0, 150.0)
        self.spin_wind.setValue(10.0)
        self.spin_wind.valueChanged.connect(self._send_simulation_params)
        self._add_calibration_field(env_col, "Manual Wind (km/h)", self.spin_wind)

        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(-50.0, 80.0)
        self.spin_temp.setValue(22.0)
        self.spin_temp.valueChanged.connect(self._send_simulation_params)
        self._add_calibration_field(env_col, "Ambient Temp (°C)", self.spin_temp)

        self.spin_voltage = QDoubleSpinBox()
        self.spin_voltage.setRange(3.3, 48.0)
        self.spin_voltage.setValue(12.0)
        self.spin_voltage.valueChanged.connect(self._send_simulation_params)
        self._add_calibration_field(env_col, "Supply Voltage (V)", self.spin_voltage)

        env_layout.addWidget(env_group)
        env_layout.addStretch()
        cal_sections.addTab(tab_env, "Environment")

        # --- Receiver & satellite RF ---
        tab_rf = QWidget()
        rf_layout = QVBoxLayout(tab_rf)
        rf_layout.setContentsMargins(4, 6, 4, 4)
        rf_layout.setSpacing(6)

        rf_spec_group = QGroupBox("RECEIVER & SATELLITE RF SPEC")
        rf_col = QVBoxLayout(rf_spec_group)
        rf_col.setContentsMargins(6, 8, 6, 6)
        rf_col.setSpacing(8)

        self.spin_sdr_center = QDoubleSpinBox()
        self.spin_sdr_center.setRange(10.0, 3000.0)
        self.spin_sdr_center.setValue(137.9100)
        self.spin_sdr_center.setSingleStep(0.01)
        self.spin_sdr_center.setDecimals(4)
        self.spin_sdr_center.valueChanged.connect(self._send_simulation_params)
        self._add_calibration_field(rf_col, "SDR Center (MHz)", self.spin_sdr_center)

        self.spin_sdr_span = QDoubleSpinBox()
        self.spin_sdr_span.setRange(1.0, 5000.0)
        self.spin_sdr_span.setValue(100.0)
        self.spin_sdr_span.setSingleStep(5.0)
        self.spin_sdr_span.valueChanged.connect(self._send_simulation_params)
        self._add_calibration_field(rf_col, "SDR Span (kHz)", self.spin_sdr_span)

        self.spin_manual_downlink = QDoubleSpinBox()
        self.spin_manual_downlink.setRange(10.0, 3000.0)
        self.spin_manual_downlink.setValue(137.9100)
        self.spin_manual_downlink.setSingleStep(0.01)
        self.spin_manual_downlink.setDecimals(4)
        self.spin_manual_downlink.valueChanged.connect(self._send_simulation_params)
        self._add_calibration_field(rf_col, "Manual Downlink (MHz)", self.spin_manual_downlink)

        self.spin_manual_bandwidth = QDoubleSpinBox()
        self.spin_manual_bandwidth.setRange(0.1, 500.0)
        self.spin_manual_bandwidth.setValue(30.0)
        self.spin_manual_bandwidth.setSingleStep(1.0)
        self.spin_manual_bandwidth.valueChanged.connect(self._send_simulation_params)
        self._add_calibration_field(rf_col, "Manual Bandwidth (kHz)", self.spin_manual_bandwidth)

        self.spin_rf_channels = QSpinBox()
        self.spin_rf_channels.setRange(1, MAX_RF_CHANNEL_COUNT)
        self.spin_rf_channels.setValue(DEFAULT_RF_CHANNEL_COUNT)
        self.spin_rf_channels.setToolTip(
            "Present hardware uses 8 channels. Increase when the RF coupler design supports more."
        )
        self.spin_rf_channels.valueChanged.connect(self._on_rf_channel_count_changed)
        rf_channels_row = QHBoxLayout()
        rf_channels_row.setSpacing(6)
        rf_ch_label = QLabel("RF Switch Channels")
        rf_ch_label.setWordWrap(True)
        rf_channels_row.addWidget(rf_ch_label, 1)
        rf_channels_row.addWidget(self.spin_rf_channels, 0, Qt.AlignRight)
        rf_col.addLayout(rf_channels_row)

        rf_layout.addWidget(rf_spec_group)
        rf_layout.addStretch()
        cal_sections.addTab(tab_rf, "RF")

        tab_cal_layout.addWidget(cal_sections)

        self.left_tabs.addTab(tab_calibration, "Calibration")

        # Core Visual modules
        stabilization_group = QGroupBox("PLATFORM STABILIZATION")
        stabilization_box = QHBoxLayout(stabilization_group)
        stabilization_box.setContentsMargins(6, 4, 6, 4)
        stabilization_box.setSpacing(8)

        self.attitude_widget = PlatformAttitudeWidget()
        stabilization_box.addWidget(self.attitude_widget)

        imu_txt_widget = QWidget()
        imu_txt_layout = QVBoxLayout(imu_txt_widget)
        imu_txt_layout.setContentsMargins(0, 0, 0, 0)
        imu_txt_layout.setSpacing(3)
        self.lbl_gyro_status = QLabel("ACCEL X: 0.00 G")
        self.lbl_gyro_status.setStyleSheet("color: #a0a0b0; font-size: 9px;")
        self.lbl_accel_y = QLabel("ACCEL Y: 0.00 G")
        self.lbl_accel_y.setStyleSheet("color: #a0a0b0; font-size: 9px;")
        self.lbl_accel_z = QLabel("ACCEL Z: 1.00 G")
        self.lbl_accel_z.setStyleSheet("color: #a0a0b0; font-size: 9px;")
        self.lbl_stabilized = QLabel("STABLE: YES")
        self.lbl_stabilized.setStyleSheet("color: #00e676; font-size: 9px; font-weight: bold;")
        imu_txt_layout.addWidget(self.lbl_gyro_status)
        imu_txt_layout.addWidget(self.lbl_accel_y)
        imu_txt_layout.addWidget(self.lbl_accel_z)
        imu_txt_layout.addWidget(self.lbl_stabilized)
        imu_txt_layout.addStretch()
        stabilization_box.addWidget(imu_txt_widget)
        col1_layout.addWidget(stabilization_group)

        # Advanced Link & GNSS Metrics Box
        link_group = QGroupBox("ADVANCED LINK & GNSS DECK")
        link_grid = QGridLayout(link_group)
        link_grid.setContentsMargins(6, 4, 6, 4)
        link_grid.setHorizontalSpacing(8)
        link_grid.setVerticalSpacing(2)

        self.lbl_doppler = QLabel("DOPPLER: 0.00 kHz")
        self.lbl_vco_locked = QLabel("PLL LOCK: YES")
        self.lbl_path_loss = QLabel("PATH LOSS: 120.0 dB")
        self.lbl_snr = QLabel("LINK SNR: 0.0 dB")
        self.lbl_margin = QLabel("MARGIN: 0.0 dB")
        self.lbl_sats_visible = QLabel("SATS VIS: 0")
        self.lbl_dop = QLabel("H/V DOP: 1.00 / 1.00")
        self.lbl_time_dev = QLabel("TIME DEV: 0 ns")
        self.lbl_torque = QLabel("AZ/EL TRQ: 0.0% / 0.0%")

        for lbl in [self.lbl_doppler, self.lbl_path_loss, self.lbl_snr, self.lbl_margin, 
                    self.lbl_sats_visible, self.lbl_dop, self.lbl_time_dev, self.lbl_torque]:
            lbl.setStyleSheet("color: #a0a0b0; font-size: 9px; font-family: 'Segoe UI'; font-weight: bold;")
        self.lbl_vco_locked.setStyleSheet("color: #00e676; font-size: 9px; font-family: 'Segoe UI'; font-weight: bold;")

        link_grid.addWidget(self.lbl_doppler, 0, 0)
        link_grid.addWidget(self.lbl_vco_locked, 0, 1)
        link_grid.addWidget(self.lbl_path_loss, 1, 0)
        link_grid.addWidget(self.lbl_snr, 1, 1)
        link_grid.addWidget(self.lbl_margin, 2, 0)
        link_grid.addWidget(self.lbl_sats_visible, 2, 1)
        link_grid.addWidget(self.lbl_dop, 3, 0)
        link_grid.addWidget(self.lbl_time_dev, 3, 1)
        link_grid.addWidget(self.lbl_torque, 4, 0, 1, 2)
        col1_layout.addWidget(link_group)

        rf_group = QGroupBox("PHYSICAL COUPLER DIAGRAM")
        rf_box = QVBoxLayout(rf_group)
        rf_box.setContentsMargins(4, 4, 4, 4)  # Low vertical margin
        self.rf_step_widget = RFSignalChainWidget()
        rf_box.addWidget(self.rf_step_widget)
        col1_layout.addWidget(rf_group)

        col1_layout.addStretch()

        # ---- COLUMN 2: Operations, Dials & Multi-trace Plots (Right/Expanding) ----
        col2 = QWidget()
        col2_layout = QVBoxLayout(col2)
        col2_layout.setContentsMargins(0, 0, 0, 0)
        col2_layout.setSpacing(4)
        deck_layout.addWidget(col2)

        gauge_group = QGroupBox("STATION CRITICAL BUSMETERS")
        gauge_layout = QHBoxLayout(gauge_group)
        gauge_layout.setContentsMargins(2, 4, 2, 2)  # Low vertical margin
        gauge_layout.setSpacing(2)

        self.gps_speed_gauge = CircularGauge("Wind Speed", 0, 120, "km/h", warn_thresh=60, crit_thresh=90)
        self.cpu_temp_gauge = CircularGauge("Motor Drive Temp", 0, 100, "°C", warn_thresh=65, crit_thresh=85)
        self.voltage_gauge = CircularGauge("Pwr Voltage", 4.5, 5.5, "V", warn_thresh=4.8, crit_thresh=4.6)
        self.signal_gauge = CircularGauge("Signal RSSI", 0, 100, "%", warn_thresh=45, crit_thresh=25)
        self.az_gauge = CircularGauge("Azimuth Head", 0, 360, "°")
        self.el_gauge = CircularGauge("Elevation Angle", -90, 90, "°")
        self.rf_channel_gauge = CircularGauge(
            "Active RF Ch", 1, float(DEFAULT_RF_CHANNEL_COUNT), ""
        )

        gauge_layout.addWidget(self.gps_speed_gauge)
        gauge_layout.addWidget(self.cpu_temp_gauge)
        gauge_layout.addWidget(self.voltage_gauge)
        gauge_layout.addWidget(self.signal_gauge)
        gauge_layout.addWidget(self.az_gauge)
        gauge_layout.addWidget(self.el_gauge)
        gauge_layout.addWidget(self.rf_channel_gauge)
        col2_layout.addWidget(gauge_group)

        lower_layout = QHBoxLayout()
        lower_layout.setSpacing(4)
        col2_layout.addLayout(lower_layout)

        # Plot Panel: Fluid height allocation matching available workspace height
        trends_group = QGroupBox("DIAGNOSTIC WAVEFORMS")
        trends_box = QVBoxLayout(trends_group)
        trends_box.setContentsMargins(4, 2, 4, 2)  # Tight padding to avoid top-edge gap
        trends_box.setSpacing(2)                  # Tight vertical gap between plots

        # Plot Widgets automatically expand symmetrically to eliminate blank spacing
        self.plot_signal = pg.PlotWidget(title="Drive Loops tracking error profile")
        self.plot_signal.setBackground('#0a0a0f')
        self.plot_signal.showGrid(x=True, y=True, alpha=0.3)
        self.plot_signal.getPlotItem().layout.setContentsMargins(2, 2, 2, 2)  
        self.plot_signal.getPlotItem().layout.setSpacing(2)
        self.curve_err_az = self.plot_signal.plot(pen=pg.mkPen(color='#00e676', width=1.5), name="Az Error")
        self.curve_err_el = self.plot_signal.plot(pen=pg.mkPen(color='#ffd600', width=1.5), name="El Error")
        # Show legend so each trace is clearly labeled on the plot
        try:
            self.plot_signal.addLegend(offset=(10, 10))
        except Exception:
            pass
        self.plot_signal.getAxis('left').setPen(pg.mkPen(color='#444455', width=1))
        self.plot_signal.getAxis('bottom').setPen(pg.mkPen(color='#444455', width=1))
        self.plot_signal.getAxis('left').setTextPen(QColor('#8f8fa4'))
        self.plot_signal.getAxis('bottom').setTextPen(QColor('#8f8fa4'))

        self.plot_dynamics = pg.PlotWidget(title="Motor Actuator Power Requirements")
        self.plot_dynamics.setBackground('#0a0a0f')
        self.plot_dynamics.showGrid(x=True, y=True, alpha=0.3)
        self.plot_dynamics.getPlotItem().layout.setContentsMargins(2, 2, 2, 2)  
        self.plot_dynamics.getPlotItem().layout.setSpacing(2)
        self.curve_motor_az_current = self.plot_dynamics.plot(pen=pg.mkPen(color='#2979ff', width=1.5), name="Az Motor (A)")
        self.curve_motor_el_current = self.plot_dynamics.plot(pen=pg.mkPen(color='#ff1744', width=1.5), name="El Motor (A)")
        # Show legend for motor current traces
        try:
            self.plot_dynamics.addLegend(offset=(10, 10))
        except Exception:
            pass
        self.plot_dynamics.getAxis('left').setPen(pg.mkPen(color='#444455', width=1))
        self.plot_dynamics.getAxis('bottom').setPen(pg.mkPen(color='#444455', width=1))
        self.plot_dynamics.getAxis('left').setTextPen(QColor('#8f8fa4'))
        self.plot_dynamics.getAxis('bottom').setTextPen(QColor('#8f8fa4'))

        trends_box.addWidget(self.plot_signal)
        trends_box.addWidget(self.plot_dynamics)
        lower_layout.addWidget(trends_group, 6)

        terminal_panel = QWidget()
        terminal_panel_layout = QVBoxLayout(terminal_panel)
        terminal_panel_layout.setContentsMargins(0, 0, 0, 0)
        terminal_panel_layout.setSpacing(4)

        spectrum_group = QGroupBox("RF POWER SPECTRUM")
        spectrum_box = QVBoxLayout(spectrum_group)
        spectrum_box.setContentsMargins(4, 2, 4, 2)  

        self.spectrum_plot = pg.PlotWidget()
        self.spectrum_plot.setBackground('#0a0a0f')
        self.spectrum_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spectrum_plot.getPlotItem().layout.setContentsMargins(2, 2, 2, 2)  
        self.spectrum_plot.getPlotItem().layout.setSpacing(2)
        self.spectrum_plot.setLabel('left', 'Power', units='dBm')
        self.spectrum_plot.setLabel('bottom', 'Freq Offset', units='kHz')
        self.spectrum_plot.getAxis('left').setPen(pg.mkPen(color='#444455', width=1))
        self.spectrum_plot.getAxis('bottom').setPen(pg.mkPen(color='#444455', width=1))
        self.spectrum_plot.getAxis('left').setTextPen(QColor('#8f8fa4'))
        self.spectrum_plot.getAxis('bottom').setTextPen(QColor('#8f8fa4'))

        # Name the spectrum trace and show a small legend label for clarity
        self.spectrum_curve = self.spectrum_plot.plot(pen=pg.mkPen(color='#00e676', width=1.5), name="RF Spectrum (dBm)")
        try:
            self.spectrum_plot.addLegend(offset=(10, 10))
        except Exception:
            pass
        spectrum_box.addWidget(self.spectrum_plot)
        terminal_panel_layout.addWidget(spectrum_group, 5)

        console_group = QGroupBox("STATION INTERFACE TERMINAL LOG")
        console_box = QVBoxLayout(console_group)
        console_box.setContentsMargins(4, 2, 4, 2)  

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.document().setMaximumBlockCount(200)
        console_box.addWidget(self.log_text)
        terminal_panel_layout.addWidget(console_group, 5)

        lower_layout.addWidget(terminal_panel, 5)

        self.statusBar().showMessage("Tracking System Deck operational.")

    def _clear_diagnostics_data(self):
        """Reset plot visuals and completely empty history deques for a clean, synchronized state."""
        # Flush all temporal buffers to ensure a fresh origin point
        self.plot_times.clear()
        self.err_az_history.clear()
        self.err_el_history.clear()
        self.motor_az_history.clear()
        self.motor_el_history.clear()

        # Clear curves to purge old tracing lines
        self.curve_err_az.clear()
        self.curve_err_el.clear()
        self.curve_motor_az_current.clear()
        self.curve_motor_el_current.clear()
        self.spectrum_curve.clear()
    
        # Reset gauges to neutral values
        for gauge in [self.gps_speed_gauge, self.cpu_temp_gauge, self.voltage_gauge,
                      self.signal_gauge, self.az_gauge, self.el_gauge, self.rf_channel_gauge]:
            gauge.setValue(gauge.min_val)
        self.rf_step_widget.set_channel(1, False)
        self.attitude_widget.set_attitude(0.0, 0.0)
        self.safety_ribbon.set_states(False, False, False, False, False, False, False, False, False)
        self._last_plot_sample_key = None

    def _update_hardware_health_indicators(self, payload: Dict[str, Any]) -> None:
        """Map bridge health fields to RF, motor, and motion-controller indicators."""
        simulated = bool(payload.get("hardware_simulated", False))
        motor_online = bool(
            payload.get("motor_controller_online", payload.get("arduino_online", False))
        )
        rf_ok = bool(payload.get("rf_switch_ok", False))
        board = (payload.get("controller_board") or "").strip()

        if simulated:
            self.rf_health.set_status('warning')
            self.antenna_health.set_status('warning')
            self.controller_health.set_status('warning')
            self.controller_health.name_label.setText(board or "Simulation")
            return

        self.rf_health.set_status('ok' if rf_ok else 'error')
        self.antenna_health.set_status('ok' if motor_online else 'error')

        if board:
            self.controller_health.name_label.setText(board)
        else:
            self.controller_health.name_label.setText("Motion Controller")
        self.controller_health.set_status('ok' if motor_online else 'error')

    def _on_telemetry_update(self, payload: Dict[str, Any]):
        if not self._connected:
            return
    
        current_sat = payload.get("sat_name", "UNKNOWN")
        last_sat = getattr(self, "_last_sat_name", None)
    
        # Detect satellite transition and cleanly purge old state history
        if last_sat is not None and current_sat != last_sat:
            self._add_log_entry(f"Satellite changed: {last_sat} → {current_sat}. Resetting diagnostics waveforms.", 'info')
            self._clear_diagnostics_data()
        self._last_sat_name = current_sat
    
        # Initialize default values to prevent UnboundLocalError in the offline branch
        err_az = 0.0
        err_el = 0.0
        mot_az = 0.0
        mot_el = 0.0
    
        is_simulation = self.client.simulation_mode
        hardware_online = bool(
            payload.get("motor_controller_online", payload.get("arduino_online", False))
        )

        err_az_val = payload.get("track_error_az")
        err_el_val = payload.get("track_error_el")
        mot_az_val = payload.get("motor_az_current")
        mot_el_val = payload.get("motor_el_current")
        err_az = float(err_az_val) if err_az_val is not None else 0.0
        err_el = float(err_el_val) if err_el_val is not None else 0.0
        mot_az = float(mot_az_val) if mot_az_val is not None else 0.0
        mot_el = float(mot_el_val) if mot_el_val is not None else 0.0

        plot_sample_key = (
            payload.get("tracking_sample_id"),
            payload.get("sim_params_revision"),
        )
        sim_plot_fresh = (
            not is_simulation
            or plot_sample_key != getattr(self, "_last_plot_sample_key", None)
        )
        
        # ------------------------------------------------------------------
        # Waveform Plotting Pipeline
        # ------------------------------------------------------------------
        if not is_simulation and not hardware_online:
            # Direct Hardware Mode is selected but the microcontroller is offline.
            self.plot_times.clear()
            self.err_az_history.clear()
            self.err_el_history.clear()
            self.motor_az_history.clear()
            self.motor_el_history.clear()
            self.curve_err_az.clear()
            self.curve_err_el.clear()
            self.curve_motor_az_current.clear()
            self.curve_motor_el_current.clear()
            self._last_plot_sample_key = None
        elif is_simulation and not payload.get("simulation_ready", False):
            # Simulation inputs incomplete or no valid SatTrack pass.
            self.plot_times.clear()
            self.err_az_history.clear()
            self.err_el_history.clear()
            self.motor_az_history.clear()
            self.motor_el_history.clear()
            self.curve_err_az.clear()
            self.curve_err_el.clear()
            self.curve_motor_az_current.clear()
            self.curve_motor_el_current.clear()
            self._last_plot_sample_key = None
        elif sim_plot_fresh:
            now = time.time()
            self.plot_times.append(now)
            self.err_az_history.append(err_az)
            self.err_el_history.append(err_el)
            self.motor_az_history.append(mot_az)
            self.motor_el_history.append(mot_el)
            self._last_plot_sample_key = plot_sample_key

            t_axis = [t - now for t in self.plot_times]

            def set_curve_data(curve, history):
                if not history:
                    curve.clear()
                    return
                min_len = min(len(t_axis), len(history))
                if min_len >= 2:
                    curve.setData(t_axis[-min_len:], list(history)[-min_len:])
                else:
                    curve.clear()

            set_curve_data(self.curve_err_az, self.err_az_history)
            set_curve_data(self.curve_err_el, self.err_el_history)
            set_curve_data(self.curve_motor_az_current, self.motor_az_history)
            set_curve_data(self.curve_motor_el_current, self.motor_el_history)

            if len(self.plot_times) >= 2:
                self.plot_signal.autoRange()
                self.plot_dynamics.autoRange()
    
        # ------------------------------------------------------------------
        # Update Dashboard Gauges (Standard payload mapping)
        # ------------------------------------------------------------------
        if "wind_speed" in payload:
            self.gps_speed_gauge.setValue(float(payload["wind_speed"]))
        elif "speed" in payload:
            self.gps_speed_gauge.setValue(float(payload["speed"]))
    
        if "motor_temp" in payload:
            self.cpu_temp_gauge.setValue(float(payload["motor_temp"]))
        elif "temperature" in payload:
            self.cpu_temp_gauge.setValue(float(payload["temperature"]))
    
        if "voltage" in payload:
            self.voltage_gauge.setValue(float(payload["voltage"]))
    
        if "signal_quality" in payload:
            self.signal_gauge.setValue(float(payload["signal_quality"]))
    
        if "azimuth" in payload:
            self.az_gauge.setValue(float(payload["azimuth"]))
        if "elevation" in payload:
            self.el_gauge.setValue(float(payload["elevation"]))
    
        if "rf_channel_count" in payload:
            ch_count = max(1, int(payload["rf_channel_count"]))
            self.rf_channel_gauge.max_val = float(ch_count)
            self.rf_step_widget.set_channel_count(ch_count)
            self.spin_rf_channels.blockSignals(True)
            self.spin_rf_channels.setValue(ch_count)
            self.spin_rf_channels.blockSignals(False)

        if "rf_channel" in payload:
            ch = int(payload["rf_channel"])
            self.rf_channel_gauge.setValue(ch)
            self.rf_step_widget.set_channel(ch, True)

        self._update_simulation_readiness_banner(payload)
    
        # ------------------------------------------------------------------
        # Update Link Deck Labels
        # ------------------------------------------------------------------
        self.lbl_doppler.setText(f"DOPPLER: {payload.get('doppler_offset_khz', 0.0):+.2f} kHz")
        locked = payload.get("vco_pll_locked", False)
        self.lbl_vco_locked.setText(f"PLL LOCK: {'YES' if locked else 'NO'}")
        self.lbl_vco_locked.setStyleSheet(f"color: {'#00e676' if locked else '#ff5252'}; font-size: 9px; font-weight: bold;")
        self.lbl_path_loss.setText(f"PATH LOSS: {payload.get('path_loss_db', 0.0):.1f} dB")
        self.lbl_snr.setText(f"LINK SNR: {payload.get('snr_db', 0.0):.1f} dB")
        margin = payload.get("link_margin_db", 0.0)
        self.lbl_margin.setText(f"MARGIN: {margin:.1f} dB")
        self.lbl_margin.setStyleSheet(f"color: {'#00e676' if margin > 6 else '#ffd600' if margin > 2 else '#ff5252'}; font-size: 9px; font-weight: bold;")
        self.lbl_sats_visible.setText(f"SATS VIS: {payload.get('gps_sats_visible', 0)}")
        self.lbl_dop.setText(
            f"H/V DOP: {payload.get('hdop', 0.0):.2f} / {payload.get('vdop', 0.0):.2f}"
        )
        self.lbl_time_dev.setText(f"TIME DEV: {payload.get('time_deviation_ns', 0):+d} ns")
        self.lbl_torque.setText(f"AZ/EL TRQ: {payload.get('motor_az_torque_pct', 0.0):.1f}% / {payload.get('motor_el_torque_pct', 0.0):.1f}%")
    
        # Attitude and acceleration from payload only
        roll = float(payload.get("roll", 0.0))
        pitch = float(payload.get("pitch", 0.0))
        self.attitude_widget.set_attitude(roll, pitch)
        ax = float(payload.get("accel_x", 0.0))
        ay = float(payload.get("accel_y", 0.0))
        az = float(payload.get("accel_z", 0.0))
        self.lbl_gyro_status.setText(f"ACCEL X: {ax:+.2f} G")
        self.lbl_accel_y.setText(f"ACCEL Y: {ay:+.2f} G")
        self.lbl_accel_z.setText(f"ACCEL Z: {az:+.2f} G")
        deviation = math.sqrt(roll**2 + pitch**2)
        if deviation < 4.0:
            self.lbl_stabilized.setText("STABILIZED: YES")
            self.lbl_stabilized.setStyleSheet("color: #00e676; font-size: 9px; font-weight: bold;")
        else:
            self.lbl_stabilized.setText("STABILIZED: DRIFT")
            self.lbl_stabilized.setStyleSheet("color: #ffd600; font-size: 9px; font-weight: bold;")
    
        # Limit switches and alarms
        self.safety_ribbon.set_states(
            bool(payload.get("limit_az_ccw", False)),
            bool(payload.get("limit_az_cw", False)),
            bool(payload.get("limit_el_low", False)),
            bool(payload.get("limit_el_high", False)),
            bool(payload.get("gps_lock", False)),
            bool(payload.get("overcurrent_trip", False)),
            bool(payload.get("undervoltage_lockout", False)),
            bool(payload.get("stow_active", False)),
            bool(payload.get("encoder_slip_detected", False))
        )
    
        # Health indicators (board-agnostic; reflects SatTrack HW selection)
        self.gps_health.set_status('ok' if payload.get("gps_fix", False) else 'warning')
        self._update_hardware_health_indicators(payload)
    
        # Log warnings if errors are high
        if abs(err_az) > 1.5 or abs(err_el) > 1.5:
            self._add_log_entry(f"High tracking error! AZ: {err_az:.2f}°, EL: {err_el:.2f}°", 'warning')
        if mot_az > 12.0 or mot_el > 12.0:
            self._add_log_entry("Motor overcurrent condition detected", 'error')
        if payload.get("wind_stow_alarm", False):
            self._add_log_entry(f"High wind ({payload.get('wind_speed', 0)} km/h) – stow active", 'warning')
    
        # Update spectrum plot
        spectrum = payload.get("spectrum")
        if isinstance(spectrum, list) and len(spectrum) == 100:
            self.spectrum_curve.setData(spectrum)
            self.spectrum_plot.autoRange()
            

    def _on_mode_changed(self, index: int):
        """Notifies the bridge and switches operating states."""
        is_sim = (index == 0)
        try:
            self._add_log_entry(f"Switched platform path to: {'SIMULATION' if is_sim else 'DIRECT HARDWARE'}", 'warning')
            
            # Immediately flush visual trace history to prevent old data retention
            self._clear_diagnostics_data()
            
            # Update client operating state so that subsequent polls are correctly flagged
            self.client.simulation_mode = is_sim
            self._refresh_local_calibration_banner()
            
            if self._connected:
                # Explicitly notify bridge server of mode change immediately to prevent spikes
                cmd = {
                    "type": "SET_OPERATION_MODE",
                    "payload": {"simulation_mode": is_sim}
                }
                self.client.bridge_client._send_command(cmd)
                
                if is_sim:
                    # Synchronize settings upon returning to simulation
                    self._send_simulation_params()
        except Exception as e:
            logger.debug(f"Diagnostics: mode toggle error: {e}")


    def _update_plots(self):
        """Update the diagnostic waveform plots using the current history."""
        # Ensure we clear curves completely if not connected or when history is too small to form a line
        if not self._connected or len(self.plot_times) < 2:
            self.curve_err_az.clear()
            self.curve_err_el.clear()
            self.curve_motor_az_current.clear()
            self.curve_motor_el_current.clear()
            return
    
        now = self.plot_times[-1]
        t_axis = [t - now for t in self.plot_times]
    
        # Helper to safely set data with matching lengths
        def set_curve_data(curve, history):
            if not history:
                curve.clear()
                return
            min_len = min(len(t_axis), len(history))
            if min_len >= 2:
                curve.setData(t_axis[-min_len:], list(history)[-min_len:])
            else:
                curve.clear()
    
        set_curve_data(self.curve_err_az, self.err_az_history)
        set_curve_data(self.curve_err_el, self.err_el_history)
        set_curve_data(self.curve_motor_az_current, self.motor_az_history)
        set_curve_data(self.curve_motor_el_current, self.motor_el_history)

        # Force PyQtGraph ViewBox to recalculate viewport bounds safely,
        # ensuring the curves are positioned correctly on the grid.
        self.plot_signal.autoRange()
        self.plot_dynamics.autoRange()
        

    def _collect_calibration_params(self) -> Dict[str, Any]:
        return {
            "mass": self.spin_mass.value(),
            "gearing": self.spin_gearing.value(),
            "kt": self.spin_kt.value(),
            "wind_speed": self.spin_wind.value(),
            "ambient_temp": self.spin_temp.value(),
            "voltage": self.spin_voltage.value(),
            "sdr_center_mhz": self.spin_sdr_center.value(),
            "sdr_span_khz": self.spin_sdr_span.value(),
            "manual_downlink_mhz": self.spin_manual_downlink.value(),
            "manual_bandwidth_khz": self.spin_manual_bandwidth.value(),
            "rf_channel_count": self.spin_rf_channels.value(),
        }

    def _on_rf_channel_count_changed(self, _value: int) -> None:
        count = self.spin_rf_channels.value()
        self.rf_channel_gauge.max_val = float(count)
        self.rf_step_widget.set_channel_count(count)
        self._send_simulation_params()
        self._refresh_local_calibration_banner()

    def _refresh_local_calibration_banner(self) -> None:
        if not self.client.simulation_mode:
            return
        ok, missing = validate_calibration(self._collect_calibration_params())
        if ok:
            self.sim_readiness_banner.setText(
                "SIMULATION: Calibration complete. Start / maintain SatTrack tracking for live charts."
            )
            self.sim_readiness_banner.setStyleSheet(
                "color: #a0e0b0; background-color: #0d2618; border: 1px solid #2e7d4e; "
                "border-radius: 3px; padding: 4px 8px; font-family: 'Segoe UI'; font-size: 10px;"
            )
        else:
            self.sim_readiness_banner.setText(
                "SIMULATION: Enter required calibration — missing: " + ", ".join(missing)
            )
            self.sim_readiness_banner.setStyleSheet(
                "color: #ffd600; background-color: #2a2200; border: 1px solid #665500; "
                "border-radius: 3px; padding: 4px 8px; font-family: 'Segoe UI'; font-size: 10px;"
            )

    def _update_simulation_readiness_banner(self, payload: Dict[str, Any]) -> None:
        if not self.client.simulation_mode:
            self.sim_readiness_banner.setVisible(False)
            return
        self.sim_readiness_banner.setVisible(True)
        if payload.get("simulation_ready"):
            self.sim_readiness_banner.setText(
                f"SIMULATION READY — RF matrix {int(payload.get('rf_channel_count', 8))} ch | "
                f"Sat: {payload.get('sat_name', '—')} | El {float(payload.get('elevation', 0)):.1f}°"
            )
            self.sim_readiness_banner.setStyleSheet(
                "color: #00e676; background-color: #0d2618; border: 1px solid #2e7d4e; "
                "border-radius: 3px; padding: 4px 8px; font-family: 'Segoe UI'; font-size: 10px; font-weight: bold;"
            )
            return
        missing = payload.get("simulation_missing") or []
        if missing:
            text = "SIMULATION INCOMPLETE — " + "; ".join(str(m) for m in missing[:4])
            if len(missing) > 4:
                text += f" (+{len(missing) - 4} more)"
        else:
            text = "SIMULATION INCOMPLETE — complete Calibration and SatTrack tracking."
        self.sim_readiness_banner.setText(text)
        self.sim_readiness_banner.setStyleSheet(
            "color: #ffd600; background-color: #2a2200; border: 1px solid #665500; "
            "border-radius: 3px; padding: 4px 8px; font-family: 'Segoe UI'; font-size: 10px;"
        )

    def _send_simulation_params(self):
        """Asynchronous calibration dispatch transmitting dynamic physical spec modifications."""
        self._refresh_local_calibration_banner()
        if not self._connected:
            return
        params = self._collect_calibration_params()
        cmd = {
            "type": "UPDATE_SIMULATION_PARAMETERS",
            "payload": params
        }
        try:
            self.client.bridge_client._send_command(cmd)
        except Exception as e:
            logger.debug(f"Diagnostics: Failed to dispatch mechanical calibrations: {e}")
            

    def _init_dynamic_plots(self):
        """Initialize double-axis plot data deques with temporal maximum limits."""
        self.plot_times: Deque[float] = deque(maxlen=240)
        self.err_az_history: Deque[float] = deque(maxlen=240)
        self.err_el_history: Deque[float] = deque(maxlen=240)
        self.motor_az_history: Deque[float] = deque(maxlen=240)
        self.motor_el_history: Deque[float] = deque(maxlen=240)

    def _set_data_widgets_enabled(self, enabled: bool):
        if not enabled:
            self._clear_diagnostics_data()
            for health in [self.gps_health, self.rf_health, self.antenna_health,
                           self.bridge_health, self.controller_health]:
                health.set_status('unknown')
            self.controller_health.name_label.setText("Motion Controller")
            
            # Reset link deck
            self.lbl_doppler.setText("DOPPLER: 0.00 kHz")
            self.lbl_vco_locked.setText("PLL LOCK: NO")
            self.lbl_vco_locked.setStyleSheet("color: #ff5252; font-size: 9px; font-weight: bold;")
            self.lbl_path_loss.setText("PATH LOSS: 0.0 dB")
            self.lbl_snr.setText("LINK SNR: 0.0 dB")
            self.lbl_margin.setText("MARGIN: 0.0 dB")
            self.lbl_margin.setStyleSheet("color: #ff5252; font-size: 9px; font-weight: bold;")
            self.lbl_sats_visible.setText("SATS VIS: 0")
            self.lbl_dop.setText("H/V DOP: 0.00 / 0.00")
            self.lbl_time_dev.setText("TIME DEV: 0 ns")
            self.lbl_torque.setText("AZ/EL TRQ: 0.0% / 0.0%")
        else:
            self.bridge_health.set_status('ok')
            self.rf_step_widget.set_channel(1, True)
            
            # Auto-sync specifications on successful bridge handshake
            self._send_simulation_params()

    def _toggle_connection(self):
        if self._connected:
            self.client.disconnect()
            self._clear_diagnostics_data()
        else:
            host = self.ip_edit.text().strip()
            port = self.port_spin.value()
            ok, msg = self.client.connect(host, port)
            if ok:
                self._host = host
                self._port = port
                self.client.start()
                self._add_log_entry(f"Secure handshake link at {host}:{port}", 'info')
            else:
                QMessageBox.warning(self, "Link Connection Error", msg)
                self._add_log_entry(f"Link connection failure: {msg}", 'error')

    def _on_connection_status(self, connected: bool, msg: str):
        self._connected = connected
        if connected:
            self.connect_btn.setText("Close Link")
            self.connect_btn.setStyleSheet("background-color: #c62828; color: white;")
            self.status_label.setText(f"ONLINE")
            self.status_label.setStyleSheet("color: #00e676; font-weight: bold; font-family: 'Segoe UI';")
            self._set_data_widgets_enabled(True)
            self._add_log_entry("Secure data handshake established with tracking controller", 'info')
        else:
            self.connect_btn.setText("Establish Link")
            self.connect_btn.setStyleSheet("background-color: #1b5e20; color: white;")
            self.status_label.setText("OFFLINE")
            self.status_label.setStyleSheet("color: #ff5252; font-weight: bold; font-family: 'Segoe UI';")
            self._set_data_widgets_enabled(False)
            self._add_log_entry("Tracking communications link disconnected", 'error')

    def _add_log_entry(self, text: str, level: str = 'info'):
        timestamp = time.strftime("%H:%M:%S")
        color = {'info': '#aaddff', 'warning': '#ffd600', 'error': '#ff5252'}.get(level, '#dddddd')
        self.log_text.append(f'<span style="color:{color};">[{timestamp}] {text}</span>')
        self.log_text.moveCursor(QTextCursor.End)


    def _update_system_health(self):
        """Monitor host hardware system resource metrics."""
        if not PSUTIL_AVAILABLE:
            self.cpu_bar.setValue(0)
            self.ram_bar.setValue(0)
            self.disk_bar.setValue(0)
            return
        try:
            # Explicit interval=None ensures immediate non-blocking CPU load evaluation
            cpu_percent = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            self.cpu_bar.setValue(int(cpu_percent or 0))
            self.ram_bar.setValue(int(ram.percent))
            self.disk_bar.setValue(int(disk.percent))

            temp = self._get_cpu_temperature()
            if temp is not None:
                self.sys_temp_label.setText(f"Host Core Temp: {temp:.1f} °C")
                if temp > 75.0:
                    self._add_log_entry(f"Host thermal load threshold exceeded: {temp:.1f}°C", 'warning')
            else:
                self.sys_temp_label.setText("Host Core Temp: N/A")
        except Exception as e:
            logger.debug(f"Host tracking parse error: {e}")

    def _get_cpu_temperature(self) -> Optional[float]:
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                return float(f.read()) / 1000.0
        except Exception:
            return None

    def closeEvent(self, event):
        """Cleanly terminate polling services and window context upon closing."""
        self.client.stop()
        self.client.disconnect()
        self.system_timer.stop()
        event.accept()