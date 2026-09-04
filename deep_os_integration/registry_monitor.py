"""
registry_monitor.py
====================
Polls specific, named registry key trees for changes - the same idea
as Sysinternals Autoruns: notice when something adds itself to
startup, changes a file association, or installs a new program.
It watches an explicit list of key paths you give it, not the whole
registry.

Dependencies: none beyond stdlib (winreg is built into Windows Python)
"""

from __future__ import annotations

import logging
import threading
import time
import winreg
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("ultron.registry_monitor")

_HIVES = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKCR": winreg.HKEY_CLASSES_ROOT,
    "HKU": winreg.HKEY_USERS,
}

# Common, useful defaults - a starting point, not exhaustive.
COMMON_STARTUP_KEYS = [
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
]


@dataclass
class RegistryChange:
    hive: str
    key_path: str
    change_type: str  # "value_added" | "value_removed" | "value_changed"
    value_name: str
    old_value: Optional[str]
    new_value: Optional[str]
    timestamp: float


def _read_values(hive: str, key_path: str) -> Dict[str, str]:
    values = {}
    try:
        with winreg.OpenKey(_HIVES[hive], key_path, 0, winreg.KEY_READ) as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    values[name] = str(value)
                    i += 1
                except OSError:
                    break
    except FileNotFoundError:
        from core.error_trace import log_swallowed as _lsw

        _lsw("deep_os_integration.registry_monitor._read_values")
    return values


class RegistryMonitor:
    """Snapshots named registry keys on an interval and reports diffs."""

    def __init__(self, keys: Optional[List[Tuple[str, str]]] = None, poll_interval: float = 5.0):
        self.keys = keys or COMMON_STARTUP_KEYS
        self.poll_interval = poll_interval
        self._snapshots: Dict[Tuple[str, str], Dict[str, str]] = {}
        self._on_change: Optional[Callable[[RegistryChange], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def add_key(self, hive: str, key_path: str):
        self.keys.append((hive, key_path))

    def on_change(self, callback: Callable[[RegistryChange], None]):
        self._on_change = callback

    def _take_snapshot(self):
        for hive, key_path in self.keys:
            self._snapshots[(hive, key_path)] = _read_values(hive, key_path)

    def _diff_and_update(self):
        for hive, key_path in self.keys:
            old = self._snapshots.get((hive, key_path), {})
            new = _read_values(hive, key_path)

            for name, val in new.items():
                if name not in old:
                    self._emit(hive, key_path, "value_added", name, None, val)
                elif old[name] != val:
                    self._emit(hive, key_path, "value_changed", name, old[name], val)
            for name in old:
                if name not in new:
                    self._emit(hive, key_path, "value_removed", name, old[name], None)

            self._snapshots[(hive, key_path)] = new

    def _emit(self, hive, key_path, change_type, name, old_val, new_val):
        change = RegistryChange(
            hive=hive,
            key_path=key_path,
            change_type=change_type,
            value_name=name,
            old_value=old_val,
            new_value=new_val,
            timestamp=time.time(),
        )
        logger.info("Registry %s: %s\\%s -> %s (%s -> %s)", change_type, hive, key_path, name, old_val, new_val)
        if self._on_change:
            self._on_change(change)

    def _poll_loop(self):
        self._take_snapshot()
        while self._running:
            time.sleep(self.poll_interval)
            self._diff_and_update()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("RegistryMonitor watching %d key(s) every %.1fs", len(self.keys), self.poll_interval)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mon = RegistryMonitor(poll_interval=3.0)
    mon.on_change(lambda c: print(f"{c.change_type}: {c.value_name} = {c.new_value}"))
    mon.start()
    print("Watching startup keys for changes... Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mon.stop()
