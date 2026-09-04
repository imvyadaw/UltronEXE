"""
System Listener (Phase 22 - Perception)
========================================
The environment-awareness sense: how loaded is the machine
(monitoring/resource_monitor.py) and are we online
(core/internet_monitor.py). Neither of those modules emits on the
event bus by itself on every reading (resource_monitor is pull-only;
internet_monitor only emits on actual state transitions) - this module
adds the missing piece for resources: a polling loop that emits
"perception.system" on every reading and "perception.system_alert"
only when a threshold is crossed, so autonomous_engine can treat "the
machine is under heavy load" as a first-class signal (lowering
consciousness confidence, same way a repeated action failure does)
instead of something only a human watching monitoring/alerts.py would
notice.

monitoring/alerts.py already owns full alert *policy* (thresholds,
notification channels) for the dashboard - this module's alert
threshold is intentionally a single simple default, only meant to
gate the event_bus emission here, not a replacement for that system.
"""

import threading
import time
from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.perception.system_listener")

DEFAULT_POLL_SECONDS = 30.0
DEFAULT_CPU_ALERT_PERCENT = 90.0
DEFAULT_MEMORY_ALERT_PERCENT = 90.0


class SystemListener:
    def __init__(self):
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()

    def snapshot(self) -> Dict:
        """One-off reading: CPU/RAM/disk plus online status."""
        resources = self._resource_snapshot()
        online = self._online_status()
        data = {**resources, "online": online}
        return self._emit(data)

    def _resource_snapshot(self) -> Dict:
        try:
            from monitoring.resource_monitor import ResourceMonitor

            return ResourceMonitor().snapshot()
        except Exception as exc:
            logger.debug(f"system_listener: resource snapshot unavailable: {exc}")
            return {}

    def _online_status(self) -> Optional[bool]:
        try:
            from core.internet_monitor import is_online

            return is_online()
        except Exception as exc:
            logger.debug(f"system_listener: internet status unavailable: {exc}")
            return None

    # -- polling ---------------------------------------------------------
    def start_polling(
        self,
        interval_seconds: float = DEFAULT_POLL_SECONDS,
        cpu_alert_percent: float = DEFAULT_CPU_ALERT_PERCENT,
        memory_alert_percent: float = DEFAULT_MEMORY_ALERT_PERCENT,
    ) -> None:
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._stop_flag.clear()

        def _loop():
            while not self._stop_flag.is_set():
                try:
                    event = self.snapshot()
                    self._check_alert(event["data"], cpu_alert_percent, memory_alert_percent)
                except Exception:
                    logger.exception("system_listener: poll iteration failed")
                self._stop_flag.wait(interval_seconds)

        self._poll_thread = threading.Thread(target=_loop, daemon=True, name="system-listener-poll")
        self._poll_thread.start()

    def stop_polling(self) -> None:
        self._stop_flag.set()

    def _check_alert(self, data: Dict, cpu_alert_percent: float, memory_alert_percent: float) -> None:
        cpu = data.get("cpu_percent")
        mem = data.get("memory_percent")
        breached = []
        if cpu is not None and cpu >= cpu_alert_percent:
            breached.append(f"cpu={cpu}%")
        if mem is not None and mem >= memory_alert_percent:
            breached.append(f"memory={mem}%")
        if not breached:
            return
        try:
            from core.event_bus import get_event_bus

            get_event_bus().emit(
                "perception.system_alert", reason=", ".join(breached), data=data, timestamp=time.time()
            )
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("perception.system_listener._check_alert")
        try:
            from core.consciousness import get_consciousness

            get_consciousness().note_outcome(False, detail=f"system under load: {', '.join(breached)}")
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("perception.system_listener._check_alert")

    # -- emit ----------------------------------------------------------
    def _emit(self, data: Dict) -> Dict:
        event = {"modality": "system", "timestamp": time.time(), "data": data, "source": "system_listener"}
        try:
            from core.event_bus import get_event_bus

            get_event_bus().emit("perception.system", **event)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("perception.system_listener._emit")
        return event


_listener: Optional[SystemListener] = None


def get_system_listener() -> SystemListener:
    global _listener
    if _listener is None:
        _listener = SystemListener()
    return _listener
