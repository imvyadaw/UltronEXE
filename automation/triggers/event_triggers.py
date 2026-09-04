"""
Event triggers skill (Phase 5 facade)
========================================
Combines the three existing trigger modules - automation/triggers/
time_trigger.py (TimeTrigger: recurring wall-clock times / intervals),
file_watcher.py (FileWatcher: filesystem change events), and
system_trigger.py (SystemTrigger: CPU/RAM/battery thresholds, process
start/stop) - behind one BaseSkill interface, so "fire a tool call when
X happens" is a single skill regardless of what X is.
"""

from typing import Dict

from skills.base_skill import BaseSkill
from automation.triggers.time_trigger import TimeTrigger
from automation.triggers.file_watcher import FileWatcher
from automation.triggers.system_trigger import SystemTrigger


class EventTriggersSkill(BaseSkill):
    """Register/manage time-based, filesystem-based, and system-state-based triggers."""

    name = "event_triggers"
    description = "Fire a tool call on a schedule, a file change, or a system-state threshold."
    category = "automation"

    def __init__(self):
        self._time = TimeTrigger()
        self._files = FileWatcher()
        self._system = SystemTrigger()
        super().__init__()

    def list_all_triggers(self) -> Dict:
        """Aggregate view across all three trigger types."""
        return {
            "time_triggers": self._time.list_triggers(),
            "file_watches": self._files.list_watches(),
            "system_triggers": self._system.list_triggers(),
        }

    def stop_all(self) -> Dict:
        self._time.stop()
        self._system.stop()
        return {"success": True, "message": "Stopped time and system trigger background loops."}

    def register_actions(self) -> None:
        t, f, s = self._time, self._files, self._system
        self._actions = {
            # time
            "add_daily": t.add_daily_trigger,
            "add_interval": t.add_interval_trigger,
            "remove_time_trigger": t.remove_trigger,
            "enable_time_trigger": t.enable_trigger,
            "list_time_triggers": t.list_triggers,
            # filesystem
            "watch_file": f.watch,
            "stop_watch": f.stop_watching,
            "list_watches": f.list_watches,
            # system state
            "on_cpu_threshold": s.on_cpu_threshold,
            "on_ram_threshold": s.on_ram_threshold,
            "on_battery_threshold": s.on_battery_threshold,
            "on_process_start": s.on_process_start,
            "on_process_stop": s.on_process_stop,
            "remove_system_trigger": s.remove_trigger,
            "list_system_triggers": s.list_triggers,
            # aggregate
            "list_all": self.list_all_triggers,
            "stop_all": self.stop_all,
        }

    def health_check(self) -> Dict:
        from automation.triggers.file_watcher import HAS_WATCHDOG
        from automation.triggers.system_trigger import HAS_PSUTIL

        return {
            "success": True,
            "skill": self.name,
            "configured": True,
            "watchdog_available": HAS_WATCHDOG,
            "psutil_available": HAS_PSUTIL,
        }
