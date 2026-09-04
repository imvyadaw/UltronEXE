"""System trigger
==============
Fires a Ultron tool call when a system-state condition becomes true:
CPU/RAM usage crossing a threshold, battery level crossing a threshold
(and charging/discharging), or a named process starting or stopping.
Polls on a background thread - there's no OS-level push notification
for most of these, so polling (a few seconds apart) is the practical
approach.
"""

import threading
import time
import uuid
from typing import Dict, Optional

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def _fire(tool_name: str, arguments: Dict, extra: Dict) -> None:
    try:
        from ai.tool_runtime import execute_tool_call as execute_tool

        args = dict(arguments or {})
        args.update(extra)
        result = execute_tool(tool_name, args)
        print(f"[SystemTrigger] Ran '{tool_name}' -> {result}")
    except Exception as e:
        print(f"[SystemTrigger] Action '{tool_name}' raised: {e}")


class SystemTrigger:
    """Poll system state and fire a tool call when a condition is met."""

    def __init__(self, poll_interval: float = 3.0):
        if not HAS_PSUTIL:
            raise RuntimeError("psutil not installed - run: pip install psutil")
        self.poll_interval = poll_interval
        self._triggers: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self._stop_flag = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def on_cpu_threshold(self, above_percent: float, tool_name: str, arguments: Dict = None, label: str = "") -> Dict:
        """Fire once each time CPU usage rises above above_percent (re-arms
        once usage drops back below, to avoid re-firing every poll)."""
        return self._add({"kind": "cpu", "threshold": above_percent, "armed": True}, tool_name, arguments, label)

    def on_ram_threshold(self, above_percent: float, tool_name: str, arguments: Dict = None, label: str = "") -> Dict:
        """Fire once each time RAM usage rises above above_percent."""
        return self._add({"kind": "ram", "threshold": above_percent, "armed": True}, tool_name, arguments, label)

    def on_battery_threshold(
        self,
        below_percent: float,
        tool_name: str,
        arguments: Dict = None,
        only_when_discharging: bool = True,
        label: str = "",
    ) -> Dict:
        """Fire once each time battery drops below below_percent."""
        return self._add(
            {"kind": "battery", "threshold": below_percent, "only_discharging": only_when_discharging, "armed": True},
            tool_name,
            arguments,
            label,
        )

    def on_process_start(self, process_name: str, tool_name: str, arguments: Dict = None, label: str = "") -> Dict:
        """Fire when a process matching process_name starts running (having not been running before)."""
        return self._add(
            {
                "kind": "process_start",
                "process_name": process_name.lower(),
                "was_running": self._process_running(process_name),
            },
            tool_name,
            arguments,
            label,
        )

    def on_process_stop(self, process_name: str, tool_name: str, arguments: Dict = None, label: str = "") -> Dict:
        """Fire when a process matching process_name stops running (having been running before)."""
        return self._add(
            {
                "kind": "process_stop",
                "process_name": process_name.lower(),
                "was_running": self._process_running(process_name),
            },
            tool_name,
            arguments,
            label,
        )

    def _add(self, condition: Dict, tool_name: str, arguments: Dict, label: str) -> Dict:
        trigger_id = str(uuid.uuid4())[:8]
        with self._lock:
            self._triggers[trigger_id] = {
                "condition": condition,
                "tool": tool_name,
                "arguments": arguments or {},
                "label": label,
                "enabled": True,
            }
        return {"success": True, "trigger_id": trigger_id, "label": label}

    def _process_running(self, name: str) -> bool:
        name_lower = name.lower()
        return any(name_lower in (p.info.get("name") or "").lower() for p in psutil.process_iter(["name"]))

    def remove_trigger(self, trigger_id: str) -> Dict:
        with self._lock:
            if trigger_id not in self._triggers:
                return {"error": f"No trigger with id '{trigger_id}'"}
            del self._triggers[trigger_id]
        return {"success": True, "removed": trigger_id}

    def list_triggers(self) -> Dict:
        with self._lock:
            return {
                "count": len(self._triggers),
                "triggers": {
                    tid: {"condition": t["condition"], "tool": t["tool"], "label": t["label"], "enabled": t["enabled"]}
                    for tid, t in self._triggers.items()
                },
            }

    def _loop(self):
        while not self._stop_flag.is_set():
            time.sleep(self.poll_interval)
            try:
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                battery = psutil.sensors_battery()
            except Exception:
                continue

            with self._lock:
                items = list(self._triggers.items())

            for trigger_id, trig in items:
                if not trig.get("enabled", True):
                    continue
                cond = trig["condition"]
                try:
                    if cond["kind"] == "cpu":
                        self._check_threshold_upward(trigger_id, trig, cond, cpu)
                    elif cond["kind"] == "ram":
                        self._check_threshold_upward(trigger_id, trig, cond, ram)
                    elif cond["kind"] == "battery" and battery is not None:
                        below = battery.percent < cond["threshold"]
                        discharging_ok = (not cond.get("only_discharging")) or (not battery.power_plugged)
                        if below and discharging_ok and cond["armed"]:
                            _fire(trig["tool"], trig["arguments"], {"battery_percent": battery.percent})
                            cond["armed"] = False
                        elif not below:
                            cond["armed"] = True
                    elif cond["kind"] == "process_start":
                        running = self._process_running(cond["process_name"])
                        if running and not cond["was_running"]:
                            _fire(trig["tool"], trig["arguments"], {"process_name": cond["process_name"]})
                        cond["was_running"] = running
                    elif cond["kind"] == "process_stop":
                        running = self._process_running(cond["process_name"])
                        if not running and cond["was_running"]:
                            _fire(trig["tool"], trig["arguments"], {"process_name": cond["process_name"]})
                        cond["was_running"] = running
                except Exception as e:
                    print(f"[SystemTrigger] Trigger '{trigger_id}' raised: {e}")

    def _check_threshold_upward(self, trigger_id: str, trig: Dict, cond: Dict, value: float) -> None:
        above = value >= cond["threshold"]
        if above and cond["armed"]:
            _fire(trig["tool"], trig["arguments"], {"value": value})
            cond["armed"] = False
        elif not above:
            cond["armed"] = True

    def stop(self) -> None:
        self._stop_flag.set()


_system_trigger: Optional[SystemTrigger] = None


def get_system_trigger() -> "SystemTrigger":
    global _system_trigger
    if _system_trigger is None and HAS_PSUTIL:
        _system_trigger = SystemTrigger()
    return _system_trigger
