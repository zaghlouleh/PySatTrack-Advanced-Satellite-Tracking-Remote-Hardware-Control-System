# -*- coding: utf-8 -*-
"""Hardware diagnostics data source client."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, Deque, Optional, Tuple

from PyQt5.QtCore import QObject, pyqtSignal

from src.managers.hardware_bridge_client import HardwareBridgeClient


def _is_number(x: Any) -> bool:
    if isinstance(x, bool):
        return False
    return isinstance(x, (int, float))


@dataclass
class TelemetryPoint:
    t: float
    v: float


class HardwareDiagnosticsClient(QObject):
    """Polls the bridge and emits telemetry updates with safe thread lifecycle guards."""

    status_changed = pyqtSignal(bool, str)
    telemetry_updated = pyqtSignal(dict)

    def __init__(
        self,
        parent: Optional[QObject] = None,
        poll_interval_s: float = 0.5,
        history_seconds: float = 60.0,
    ):
        super().__init__(parent)
        self.bridge_client = HardwareBridgeClient()
        self.poll_interval_s = float(poll_interval_s)
        self.history_seconds = float(history_seconds)

        self._thread: Optional[threading.Thread] = None
        self._running = False

        self.latest: Dict[str, Any] = {}
        self._history: Dict[str, Deque[TelemetryPoint]] = defaultdict(deque)
        
        # UI-bound state tracking
        self.simulation_mode = True

    @property
    def history(self) -> Dict[str, Deque[TelemetryPoint]]:
        return self._history

    def connect(self, host: str, port: int) -> Tuple[bool, str]:
        ok, msg = self.bridge_client.connect(host, port)
        if ok:
            try:
                self.status_changed.emit(True, msg)
            except RuntimeError:
                pass
        else:
            try:
                self.status_changed.emit(False, msg)
            except RuntimeError:
                pass
        return ok, msg

    def disconnect(self) -> None:
        self.stop()
        self.bridge_client.disconnect()
        try:
            self.status_changed.emit(False, "Disconnected")
        except RuntimeError:
            pass

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _prune_history(self, now: float) -> None:
        cutoff = now - self.history_seconds
        for k, dq in list(self._history.items()):
            while dq and dq[0].t < cutoff:
                dq.popleft()
            if not dq:
                self._history.pop(k, None)

    def _poll_loop(self) -> None:
        while self._running:
            try:
                # -------------------------------------------------------------
                # Deletion Guard Step 1: Pre-access checks
                # -------------------------------------------------------------
                try:
                    sim_mode = self.simulation_mode
                    poll_interval = self.poll_interval_s
                except RuntimeError:
                    # The underlying C++ QObject was deleted. Stop the loop.
                    self._running = False
                    break

                payload = self.bridge_client.get_gps_status(simulation_mode=sim_mode)
                if isinstance(payload, dict):
                    now = time.time()
                    self.latest = payload

                    for key, val in payload.items():
                        if _is_number(val):
                            self._history[key].append(TelemetryPoint(t=now, v=float(val)))

                    self._prune_history(now)

                    # ---------------------------------------------------------
                    # Deletion Guard Step 2: Signal emission
                    # ---------------------------------------------------------
                    try:
                        self.telemetry_updated.emit(payload)
                    except RuntimeError:
                        self._running = False
                        break

            except Exception as exc:
                # If a socket error causes a RuntimeError matching a deletion state, break
                if isinstance(exc, RuntimeError) and "deleted" in str(exc):
                    self._running = False
                    break
                try:
                    self.status_changed.emit(False, f"Poll error: {exc}")
                except RuntimeError:
                    self._running = False
                    break

            # Granular sleep checking. Improves responsiveness during UI shutdown
            # and prevents thread-locking behind a slow sleep interval.
            sleep_step = 0.05
            elapsed = 0.0
            while elapsed < poll_interval:
                if not self._running:
                    break
                time.sleep(sleep_step)
                elapsed += sleep_step