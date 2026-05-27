# -*- coding: utf-8 -*-
from typing import Dict
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QGroupBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from src.utils.logger import logger

class TelemetryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels: Dict[str, QLabel] = {}
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # 1. GROUND STATION (Mirroring original 'observer_fields')
        obs_group = QGroupBox("Ground Station (Observer)")
        obs_grid = QGridLayout(obs_group)
        self._add_row(obs_grid, "Local Time:", "local_time", 0)
        self._add_row(obs_grid, "UTC Time:", "utc", 1)
        self._add_row(obs_grid, "Latitude:", "latitude", 2)
        self._add_row(obs_grid, "Longitude:", "longitude", 3)
        self._add_row(obs_grid, "Altitude [km]:", "altitude_km_obs", 4)
        self._add_row(obs_grid, "Altitude [mi]:", "altitude_mi_obs", 5)
        self._add_row(obs_grid, "Timezone:", "timezone", 6)
        layout.addWidget(obs_group)

        # 2. SATELLITE TELEMETRY (Mirroring original 'satellite_fields')
        sat_group = QGroupBox("Satellite Telemetry")
        sat_grid = QGridLayout(sat_group)
        self._add_row(sat_grid, "Speed [km/s]:", "speed_kms", 0)
        self._add_row(sat_grid, "Speed [mi/s]:", "speed_mis_s", 1)
        self._add_row(sat_grid, "Altitude [km]:", "altitude_km_sat", 2)
        self._add_row(sat_grid, "Altitude [mi]:", "altitude_mi_sat", 3)
        self._add_row(sat_grid, "Azimuth:", "azimuth", 4)
        self._add_row(sat_grid, "Elevation:", "elevation", 5)
        self._add_row(sat_grid, "RA (Topo):", "ra", 6)
        self._add_row(sat_grid, "Dec (Topo):", "dec", 7)
        self._add_row(sat_grid, "LST:", "lst", 8)
        self._add_row(sat_grid, "Period [min]:", "period", 9)
        self._add_row(sat_grid, "Eclipsed:", "eclipsed", 10)
        layout.addWidget(sat_group)

        # 3. FREQUENCY INFORMATION (Mirroring original 'frequency_fields')
        freq_group = QGroupBox("Frequency Information")
        freq_grid = QGridLayout(freq_group)
        self._add_row(freq_grid, "Downlink [MHz]:", "downlink_mhz", 0)
        self._add_row(freq_grid, "Uplink [MHz]:", "uplink_mhz", 1)
        self._add_row(freq_grid, "Mode:", "mode", 2)
        self._add_row(freq_grid, "Beacon [MHz]:", "beacon_mhz", 3)
        self._add_row(freq_grid, "Status:", "status", 4)
        self._add_row(freq_grid, "Bandwidth [kHz]:", "bandwidth_khz", 5)
        self._add_row(freq_grid, "Baud Rate:", "baud", 6)
        self._add_row(freq_grid, "Service:", "service", 7)
        layout.addWidget(freq_group)

        layout.addStretch(1)

    def _add_row(self, grid, label_text, key, row):
        name_lbl = QLabel(label_text)
        name_lbl.setStyleSheet("color: #AAA;")
        val_lbl = QLabel("---")
        val_lbl.setFont(QFont("Consolas", 10))
        val_lbl.setAlignment(Qt.AlignRight)
        val_lbl.setStyleSheet("color: #00E676; font-weight: bold;")
        grid.addWidget(name_lbl, row, 0)
        grid.addWidget(val_lbl, row, 1)
        self.labels[key] = val_lbl

    def update_telemetry(self, data: Dict):
        """Original mapping logic: formats floats to 2 decimal places, preserves strings."""
        # Standard Keys Mapping
        mapping = {
            'speed_kms': 'speed_kms',
            'speed_mis_s': 'speed_mis_s',
            'sataltitude': 'altitude_km_sat',
            'azimuth': 'azimuth',
            'elevation': 'elevation',
            'ra': 'ra',
            'dec': 'dec',
            'lst': 'lst',
            'period_tle_calculated_min': 'period',
            'downlink_mhz': 'downlink_mhz',
            'uplink_mhz': 'uplink_mhz',
            'mode': 'mode',
            'beacon_mhz': 'beacon_mhz',
            'status': 'status',
            'bandwidth_khz': 'bandwidth_khz',
            'baud': 'baud',
            'service': 'service'
        }
        
        updated = 0
        for dict_key, ui_key in mapping.items():
            if ui_key in self.labels and dict_key in data:
                val = data[dict_key]
                if val is not None:
                    updated += 1
                    if isinstance(val, float):
                        self.labels[ui_key].setText(f"{val:.2f}")
                    else:
                        self.labels[ui_key].setText(str(val))
        logger.info(f"TelemetryPanel updated {updated} labels from {len(data)} keys")

        # Original logic for altitude in miles
        if 'sataltitude' in data and data['sataltitude'] is not None:
            self.labels['altitude_mi_sat'].setText(f"{float(data['sataltitude']) * 0.621371:.2f}")

        if 'eclipsed' in data:
            self.labels['eclipsed'].setText("YES" if data['eclipsed'] else "NO")

    def update_observer(self, lat, lng, alt, tz):
        self.labels['latitude'].setText(f"{lat:.4f}°")
        self.labels['longitude'].setText(f"{lng:.4f}°")
        self.labels['altitude_km_obs'].setText(f"{alt/1000:.2f}")
        self.labels['altitude_mi_obs'].setText(f"{alt*0.000621:.2f}")
        self.labels['timezone'].setText(tz)

    def update_time(self, local_str, utc_str):
        self.labels['local_time'].setText(local_str)
        self.labels['utc'].setText(utc_str)


