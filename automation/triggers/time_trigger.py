"""Time trigger
============
Fire a Ultron tool call at a specific clock time (daily, or on chosen
weekdays) or on a fixed interval. Built on the same background-thread
TaskScheduler used by core/scheduler.py, but adds the "every day at
09:00" / "every Monday and Friday at 18:30" scheduling shape that
scheduler.py's schedule_at()/schedule_every() don't offer directly
(they work in relative seconds / one-shot ISO datetimes, not recurring
wall-clock times).
"""

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

TRIGGERS_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "triggers"
TRIGGERS_FILE = TRIGGERS_DIR / "time_triggers.json"

_WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class TimeTrigger:
    """Schedule recurring or one-off actions at specific wall-clock times."""

    def __init__(self):
        TRIGGERS_DIR.mkdir(parents=True, exist_ok=True)
        self._triggers: Dict[str, Dict] = self._load()
        self._stop_flag = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._last_fired: Dict[str, str] = {}
        self._thread.start()

    def _load(self) -> Dict[str, Dict]:
        if TRIGGERS_FILE.exists():
            try:
                with open(TRIGGERS_FILE) as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        with open(TRIGGERS_FILE, "w") as f:
            json.dump(self._triggers, f, indent=2)

    def add_daily_trigger(
        self,
        hour: int,
        minute: int,
        tool_name: str,
        arguments: Dict = None,
        days: Optional[List[str]] = None,
        label: str = "",
    ) -> Dict:
        """Fire tool_name(arguments) every day at hour:minute, or only on the
        given weekdays (e.g. ['mon', 'wed', 'fri'])."""
        trigger_id = str(uuid.uuid4())[:8]
        self._triggers[trigger_id] = {
            "type": "daily",
            "hour": hour,
            "minute": minute,
            "days": [d.lower()[:3] for d in days] if days else None,
            "tool": tool_name,
            "arguments": arguments or {},
            "label": label,
            "enabled": True,
        }
        self._save()
        return {"success": True, "trigger_id": trigger_id, **self._triggers[trigger_id]}

    def add_interval_trigger(
        self, interval_seconds: float, tool_name: str, arguments: Dict = None, label: str = ""
    ) -> Dict:
        """Fire tool_name(arguments) every interval_seconds, indefinitely."""
        trigger_id = str(uuid.uuid4())[:8]
        self._triggers[trigger_id] = {
            "type": "interval",
            "interval_seconds": interval_seconds,
            "tool": tool_name,
            "arguments": arguments or {},
            "label": label,
            "enabled": True,
        }
        self._save()
        return {"success": True, "trigger_id": trigger_id, **self._triggers[trigger_id]}

    def remove_trigger(self, trigger_id: str) -> Dict:
        if trigger_id not in self._triggers:
            return {"error": f"No trigger with id '{trigger_id}'"}
        del self._triggers[trigger_id]
        self._last_fired.pop(trigger_id, None)
        self._save()
        return {"success": True, "removed": trigger_id}

    def enable_trigger(self, trigger_id: str, enabled: bool = True) -> Dict:
        if trigger_id not in self._triggers:
            return {"error": f"No trigger with id '{trigger_id}'"}
        self._triggers[trigger_id]["enabled"] = enabled
        self._save()
        return {"success": True, "trigger_id": trigger_id, "enabled": enabled}

    def list_triggers(self) -> Dict:
        return {"count": len(self._triggers), "triggers": self._triggers}

    def _loop(self):
        while not self._stop_flag.is_set():
            now = datetime.now()
            today_key = now.strftime("%Y-%m-%d")
            for trigger_id, trig in list(self._triggers.items()):
                if not trig.get("enabled", True):
                    continue
                try:
                    if trig["type"] == "daily":
                        if now.hour == trig["hour"] and now.minute == trig["minute"]:
                            weekday = _WEEKDAY_NAMES[now.weekday()]
                            if trig.get("days") and weekday not in trig["days"]:
                                continue
                            fired_key = f"{today_key}-{trigger_id}"
                            if self._last_fired.get(trigger_id) != fired_key:
                                self._fire(trigger_id, trig)
                                self._last_fired[trigger_id] = fired_key
                    elif trig["type"] == "interval":
                        due_at = trig.get("_next_due", 0)
                        if time.time() >= due_at:
                            self._fire(trigger_id, trig)
                            trig["_next_due"] = time.time() + trig["interval_seconds"]
                except Exception as e:
                    print(f"[TimeTrigger] Trigger '{trigger_id}' raised: {e}")
            time.sleep(1)

    def _fire(self, trigger_id: str, trig: Dict) -> None:
        from ai.tool_runtime import execute_tool_call as execute_tool

        result = execute_tool(trig["tool"], trig.get("arguments", {}))
        print(f"[TimeTrigger] '{trigger_id}' ({trig.get('label', '')}) ran '{trig['tool']}' -> {result}")

    def stop(self) -> None:
        self._stop_flag.set()


_time_trigger: Optional[TimeTrigger] = None


def get_time_trigger() -> TimeTrigger:
    global _time_trigger
    if _time_trigger is None:
        _time_trigger = TimeTrigger()
    return _time_trigger
