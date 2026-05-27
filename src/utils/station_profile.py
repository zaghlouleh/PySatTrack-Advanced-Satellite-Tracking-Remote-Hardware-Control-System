# -*- coding: utf-8 -*-
"""Ground-station profile constants and simulation input requirements."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Present hardware: 8-channel RF switch. Increase when the coupler design changes.
DEFAULT_RF_CHANNEL_COUNT = 8
MAX_RF_CHANNEL_COUNT = 64

# Minimum calibration fields required for engineering simulation (all must be > 0).
CALIBRATION_NUMERIC_KEYS: Tuple[str, ...] = (
    "mass",
    "gearing",
    "kt",
    "wind_speed",
    "ambient_temp",
    "voltage",
    "sdr_center_mhz",
    "sdr_span_khz",
    "manual_downlink_mhz",
    "manual_bandwidth_khz",
    "rf_channel_count",
)

CALIBRATION_LABELS: Dict[str, str] = {
    "mass": "Dish mass (kg)",
    "gearing": "Gearbox ratio (N:1)",
    "kt": "Motor Kt (Nm/A)",
    "wind_speed": "Manual wind (km/h)",
    "ambient_temp": "Ambient temp (°C)",
    "voltage": "Supply voltage (V)",
    "sdr_center_mhz": "SDR center (MHz)",
    "sdr_span_khz": "SDR span (kHz)",
    "manual_downlink_mhz": "Manual downlink (MHz)",
    "manual_bandwidth_khz": "Manual bandwidth (kHz)",
    "rf_channel_count": "RF switch channels",
}


def clamp_rf_channel(channel: int, channel_count: int) -> int:
    count = max(1, min(int(channel_count), MAX_RF_CHANNEL_COUNT))
    return max(1, min(int(channel), count))


def _is_positive_number(value: Any) -> bool:
    try:
        return float(value) > 0.0
    except (TypeError, ValueError):
        return False


def validate_calibration(sim_params: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Return (ok, list of human-readable missing/invalid fields)."""
    missing: List[str] = []
    for key in CALIBRATION_NUMERIC_KEYS:
        if key not in sim_params:
            missing.append(CALIBRATION_LABELS.get(key, key))
            continue
        val = sim_params[key]
        if key == "wind_speed":
            try:
                if float(val) < 0.0:
                    missing.append(CALIBRATION_LABELS[key])
            except (TypeError, ValueError):
                missing.append(CALIBRATION_LABELS[key])
            continue
        if not _is_positive_number(val):
            missing.append(CALIBRATION_LABELS.get(key, key))

    try:
        count = int(sim_params.get("rf_channel_count", DEFAULT_RF_CHANNEL_COUNT))
        if count < 1 or count > MAX_RF_CHANNEL_COUNT:
            missing.append(CALIBRATION_LABELS["rf_channel_count"])
    except (TypeError, ValueError):
        missing.append(CALIBRATION_LABELS["rf_channel_count"])

    return (len(missing) == 0, missing)


def validate_tracking_context(tracking_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """SatTrack must supply observer geometry and a live pass."""
    missing: List[str] = []
    lat = tracking_data.get("lat")
    lng = tracking_data.get("lng")
    try:
        if abs(float(lat or 0.0)) < 1e-6 and abs(float(lng or 0.0)) < 1e-6:
            missing.append("Observer position (set city / observer in SatTrack)")
    except (TypeError, ValueError):
        missing.append("Observer position (set city / observer in SatTrack)")

    sat_name = (tracking_data.get("sat_name") or "").strip()
    if not sat_name or sat_name.upper() == "UNKNOWN":
        missing.append("Active satellite pass (Start Tracking in SatTrack)")

    try:
        el = float(tracking_data.get("elevation", 0.0))
        if el <= 0.0:
            missing.append("Satellite above horizon (elevation > 0°)")
    except (TypeError, ValueError):
        missing.append("Satellite elevation from SatTrack")

    for key, label in (
        ("azimuth", "Azimuth from SatTrack"),
        ("elevation", "Elevation from SatTrack"),
        ("sataltitude", "Satellite altitude from SatTrack"),
        ("speed_kms", "Orbital speed from SatTrack"),
        ("timestamp", "Pass timestamp from SatTrack"),
    ):
        if key not in tracking_data or tracking_data.get(key) is None:
            missing.append(label)

    return (len(missing) == 0, missing)
