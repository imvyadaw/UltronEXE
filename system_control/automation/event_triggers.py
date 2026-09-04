"""Native Windows event triggers
================================
Not to be confused with automation/triggers/event_triggers.py's
EventTriggersSkill (time-of-day, filesystem-watch, and CPU/RAM/battery
*threshold-polling* triggers that fire an arbitrary AI tool call) -
that module is cross-platform-flavoured and app-level. This one is
specifically native-Windows and reads real OS event sources via
PowerShell/WMI that the other module has no access to: USB device
plug/unplug, display/monitor connect/disconnect, AC-power<->battery
source changes, and arbitrary Windows Event Log entries (by log name +
provider + event ID). Each is still implemented as a lightweight
background-thread poll (diffing `Get-PnpDevice`/`Get-CimInstance`/
`Get-WinEvent` output every few seconds) rather than a true WMI
event subscription, to avoid a pywin32/WMI-COM dependency - same
graceful-degradation philosophy as the rest of this codebase.

Callbacks fire in-process (same shape as system_trigger.py's
on_cpu_threshold etc.) - wire them to whatever the caller wants
(a saved workflow, a macro, a plain tool call) at the call site.
Registering/removing/listing triggers doesn't change anything on the
machine itself, so none of this is confirm-gated.
"""

import json
import subprocess
import threading
import time
import uuid
from typing import Callable, Dict, Optional


def _run_ps(cmd: str, timeout: float = 15.0) -> Dict:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except FileNotFoundError:
        return {"error": "PowerShell not found - this is only available on Windows"}
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out"}
    except Exception as e:
        return {"error": str(e)}


class WindowsEventTrigger:
    """Poll native Windows event sources (USB, display, power source,
    Event Log) and fire a callback when they change."""

    def __init__(self, poll_interval: float = 5.0):
        self.poll_interval = poll_interval
        self._triggers: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _ensure_running(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def _loop(self):
        while self._running:
            with self._lock:
                items = list(self._triggers.items())
            for tid, t in items:
                try:
                    if t["kind"] == "usb":
                        self._check_usb(tid, t)
                    elif t["kind"] == "display":
                        self._check_display(tid, t)
                    elif t["kind"] == "power_source":
                        self._check_power_source(tid, t)
                    elif t["kind"] == "event_log":
                        self._check_event_log(tid, t)
                except Exception as e:
                    print(f"[WindowsEventTrigger] '{tid}' check raised: {e}")
            time.sleep(self.poll_interval)

    def _check_usb(self, tid: str, t: Dict):
        result = _run_ps(
            "Get-PnpDevice -PresentOnly | Where-Object {$_.InstanceId -like 'USB*'} "
            "| Select-Object -ExpandProperty InstanceId"
        )
        if not result.get("success"):
            return
        current = set(result["stdout"].splitlines())
        previous = t.get("_last")
        if previous is not None:
            added = current - previous
            removed = previous - current
            if added:
                t["callback"]({"event": "usb_connected", "devices": sorted(added)})
            if removed:
                t["callback"]({"event": "usb_disconnected", "devices": sorted(removed)})
        t["_last"] = current

    def _check_display(self, tid: str, t: Dict):
        result = _run_ps(
            "Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorBasicDisplayParams "
            "| Select-Object -ExpandProperty InstanceName"
        )
        if not result.get("success"):
            return
        current = set(result["stdout"].splitlines())
        previous = t.get("_last")
        if previous is not None and current != previous:
            t["callback"](
                {
                    "event": "display_config_changed",
                    "added": sorted(current - previous),
                    "removed": sorted(previous - current),
                }
            )
        t["_last"] = current

    def _check_power_source(self, tid: str, t: Dict):
        result = _run_ps("(Get-CimInstance -ClassName Win32_Battery).BatteryStatus")
        if not result.get("success"):
            return
        # BatteryStatus 2 = AC/charging, everything else treated as "on battery"
        raw = result["stdout"].strip()
        source = "ac" if raw == "2" else "battery"
        previous = t.get("_last")
        if previous is not None and source != previous:
            t["callback"]({"event": "power_source_changed", "from": previous, "to": source})
        t["_last"] = source

    def _check_event_log(self, tid: str, t: Dict):
        safe_log = t["log_name"].replace("'", "''")
        filter_parts = [f"LogName='{safe_log}'"]
        if t.get("provider"):
            filter_parts.append(f"ProviderName='{t['provider'].replace(chr(39), chr(39)*2)}'")
        if t.get("event_id"):
            filter_parts.append(f"Id={int(t['event_id'])}")
        since = t.get("_since")
        if since:
            filter_parts.append(f"StartTime='{since}'")
        cmd = (
            f"Get-WinEvent -FilterHashtable @{{{'; '.join(filter_parts)}}} -MaxEvents 20 "
            f"-ErrorAction SilentlyContinue | Select-Object TimeCreated,Id,Message | ConvertTo-Json"
        )
        result = _run_ps(cmd)
        if not result.get("success") or not result["stdout"]:
            return
        try:
            data = json.loads(result["stdout"])
            events = data if isinstance(data, list) else [data]
        except Exception:
            return
        if events:
            t["callback"]({"event": "event_log_match", "log_name": t["log_name"], "entries": events})
            t["_since"] = time.strftime("%m/%d/%Y %H:%M:%S")

    # -- public API -------------------------------------------------
    def on_usb_change(self, callback: Callable[[Dict], None], trigger_id: str = None) -> str:
        """Fire callback({"event": "usb_connected"|"usb_disconnected", "devices": [...]})
        whenever a USB device is plugged in or removed."""
        trigger_id = trigger_id or str(uuid.uuid4())[:8]
        with self._lock:
            self._triggers[trigger_id] = {"kind": "usb", "callback": callback, "_last": None}
        self._ensure_running()
        return trigger_id

    def on_display_change(self, callback: Callable[[Dict], None], trigger_id: str = None) -> str:
        """Fire callback({"event": "display_config_changed", "added": [...], "removed": [...]})
        whenever a monitor is connected or disconnected."""
        trigger_id = trigger_id or str(uuid.uuid4())[:8]
        with self._lock:
            self._triggers[trigger_id] = {"kind": "display", "callback": callback, "_last": None}
        self._ensure_running()
        return trigger_id

    def on_power_source_change(self, callback: Callable[[Dict], None], trigger_id: str = None) -> str:
        """Fire callback({"event": "power_source_changed", "from": "ac"|"battery", "to": ...})
        whenever the machine switches between AC power and battery."""
        trigger_id = trigger_id or str(uuid.uuid4())[:8]
        with self._lock:
            self._triggers[trigger_id] = {"kind": "power_source", "callback": callback, "_last": None}
        self._ensure_running()
        return trigger_id

    def on_event_log(
        self,
        log_name: str,
        callback: Callable[[Dict], None],
        provider: str = "",
        event_id: int = None,
        trigger_id: str = None,
    ) -> str:
        """Fire callback({"event": "event_log_match", "entries": [...]}) when
        new entries matching log_name (e.g. 'System', 'Application') and
        optionally provider/event_id appear in the Windows Event Log."""
        if not log_name:
            return ""
        trigger_id = trigger_id or str(uuid.uuid4())[:8]
        with self._lock:
            self._triggers[trigger_id] = {
                "kind": "event_log",
                "callback": callback,
                "log_name": log_name,
                "provider": provider,
                "event_id": event_id,
                "_since": time.strftime("%m/%d/%Y %H:%M:%S"),
            }
        self._ensure_running()
        return trigger_id

    def remove_trigger(self, trigger_id: str) -> Dict:
        """Stop and remove a registered trigger."""
        with self._lock:
            if trigger_id in self._triggers:
                del self._triggers[trigger_id]
                return {"success": True, "trigger_id": trigger_id, "removed": True}
        return {"error": f"No trigger with id '{trigger_id}'"}

    def list_triggers(self) -> Dict:
        """List all registered native-event triggers."""
        with self._lock:
            return {
                "success": True,
                "triggers": [{"trigger_id": tid, "kind": t["kind"]} for tid, t in self._triggers.items()],
            }

    def stop_all(self) -> Dict:
        """Stop the background polling loop and clear all triggers."""
        self._running = False
        with self._lock:
            self._triggers.clear()
        return {"success": True, "message": "Stopped native event polling"}
