"""
predictive_maintenance.py
===========================
Two things: disk SMART health (if a reader is available) so failing
drives get flagged before they fail, and a simple linear-trend
forecast of "at this rate, drive X fills up in N days" from repeated
disk_usage() samples logged over time.

Dependencies: pip install psutil
Optional (for real SMART data): pip install pySMART  (needs smartctl
installed and admin rights; falls back gracefully without it)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import psutil

logger = logging.getLogger("ultron.predictive_maintenance")

try:
    from pySMART import DeviceList

    _SMART_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SMART_AVAILABLE = False


@dataclass
class DiskHealth:
    device: str
    model: Optional[str]
    smart_available: bool
    assessment: str  # "PASS" | "FAIL" | "UNKNOWN"
    temperature_c: Optional[int] = None


@dataclass
class SpaceForecast:
    path: str
    percent_used_now: float
    gb_free_now: float
    days_until_full: Optional[float]  # None if usage isn't trending up


class PredictiveMaintenance:
    def __init__(self, history_path: str = "./ultron_disk_history.json"):
        self.history_path = Path(history_path)
        self._history = self._load_history()

    def _load_history(self) -> dict:
        if self.history_path.exists():
            try:
                return json.loads(self.history_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Corrupt history file, starting fresh")
        return {}

    def _save_history(self):
        self.history_path.write_text(json.dumps(self._history, indent=2), encoding="utf-8")

    # ------------------------------------------------------------- health
    def disk_health(self) -> List[DiskHealth]:
        if not _SMART_AVAILABLE:
            logger.info("pySMART not available - install pySMART + smartctl for real SMART data")
            return [
                DiskHealth(device=p.device, model=None, smart_available=False, assessment="UNKNOWN")
                for p in psutil.disk_partitions(all=False)
            ]

        results = []
        try:
            for dev in DeviceList().devices:
                results.append(
                    DiskHealth(
                        device=dev.name,
                        model=dev.model,
                        smart_available=True,
                        assessment=dev.assessment or "UNKNOWN",
                        temperature_c=dev.temperature,
                    )
                )
        except Exception as e:
            logger.error("SMART read failed: %s", e)
        return results

    # ------------------------------------------------------------ forecast
    def record_sample(self, path: str = "/"):
        """Call this periodically (e.g. once a day via a scheduler) to
        build up the trend history used by forecast()."""
        usage = psutil.disk_usage(path)
        self._history.setdefault(path, []).append(
            {
                "timestamp": time.time(),
                "used_gb": usage.used / (1024**3),
            }
        )
        # keep at most 90 samples per path
        self._history[path] = self._history[path][-90:]
        self._save_history()

    def forecast(self, path: str = "/") -> SpaceForecast:
        usage = psutil.disk_usage(path)
        samples = self._history.get(path, [])

        days_until_full = None
        if len(samples) >= 2:
            first, last = samples[0], samples[-1]
            days_elapsed = (last["timestamp"] - first["timestamp"]) / 86400
            gb_growth = last["used_gb"] - first["used_gb"]
            if days_elapsed > 0 and gb_growth > 0:
                growth_per_day = gb_growth / days_elapsed
                free_gb = usage.free / (1024**3)
                days_until_full = round(free_gb / growth_per_day, 1)

        return SpaceForecast(
            path=path,
            percent_used_now=usage.percent,
            gb_free_now=round(usage.free / (1024**3), 2),
            days_until_full=days_until_full,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pm = PredictiveMaintenance()
    for h in pm.disk_health():
        print(h)
    pm.record_sample("/")
    print(pm.forecast("/"))
