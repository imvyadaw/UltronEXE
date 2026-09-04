"""Keyboard Control
==================
Physical-keyboard device and input-behavior management - distinct
from every other keyboard-adjacent module already in the codebase:

- automation/keyboard/keyboard.py - types text and presses key combos
  *into* the focused window (simulated input for automation). This
  module never simulates a keystroke; it manages the device and the
  OS-level input settings that apply to real keypresses.
- windows/accessibility.py - already owns Sticky Keys and Toggle Keys
  (plus Narrator/high contrast/Magnifier). This module does not
  duplicate either; it covers what's left uncovered on the keyboard
  side: Filter Keys (a distinct accessibility feature - ignores brief/
  repeated keystrokes - that accessibility.py doesn't touch), repeat
  delay/speed, lock-key (Caps/Num/Scroll) state, and the physical
  device itself.

Repeat delay/speed and lock-key state are per-user HKCU settings/Win32
calls, same convenience class as cursor_manager.py's pointer settings
- not confirm-gated. Filter Keys is an accessibility toggle, same
class as accessibility.py's own toggles there (also not gated).
Enabling/disabling the physical keyboard device is confirm-gated and
needs admin - obviously worth a second look before doing to the very
device used to confirm things.
"""

import ctypes
import subprocess
import winreg
from typing import Dict

_SPI_GETKEYBOARDSPEED = 0x000A
_SPI_SETKEYBOARDSPEED = 0x000B
_SPI_SETKEYBOARDDELAY = 0x0017
_SPI_GETFILTERKEYS = 0x0032
_SPI_SETFILTERKEYS = 0x0033
_SPIF_SENDCHANGE = 0x02

_VK_CAPITAL = 0x14
_VK_NUMLOCK = 0x90
_VK_SCROLL = 0x91

_KEYBOARD_REG_PATH = r"Control Panel\Keyboard"


class _FILTERKEYS(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwFlags", ctypes.c_uint),
        ("iWaitMSec", ctypes.c_uint),
        ("iDelayMSec", ctypes.c_uint),
        ("iRepeatMSec", ctypes.c_uint),
        ("iBounceMSec", ctypes.c_uint),
    ]


_FKF_FILTERKEYSON = 0x00000001


class KeyboardHardwareControl:
    """Physical keyboard device enable/disable, repeat rate, lock-key
    state, and Filter Keys - distinct from simulated typing and from
    Sticky/Toggle Keys, both owned elsewhere."""

    def _run_ps(self, cmd: str, timeout: float = 20.0) -> Dict:
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

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "elevat" in err.lower()):
            return err + " - run ULTRON as Administrator."
        return err

    def list_keyboards(self) -> Dict:
        """All currently-known keyboard devices: friendly name,
        InstanceId, and status. Use InstanceId with
        set_keyboard_enabled() below. No admin needed."""
        result = self._run_ps(
            "Get-PnpDevice -Class Keyboard -ErrorAction SilentlyContinue | "
            "Select-Object FriendlyName, InstanceId, Status | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-PnpDevice failed"}
        if not result["stdout"]:
            return {"success": True, "keyboards": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse keyboard list"}
        keyboards = data if isinstance(data, list) else [data]
        return {"success": True, "keyboards": keyboards, "count": len(keyboards)}

    def set_keyboard_enabled(self, instance_id: str, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable a keyboard device by InstanceId (from
        list_keyboards). Confirm-gated - if this is the only keyboard
        and it's a USB/PS2 external unit, disabling it can leave the
        machine unusable until re-enabled from another input device
        or Safe Mode. Needs admin."""
        if not instance_id:
            return {"error": "instance_id must be non-empty"}
        action = "enable" if enabled else "disable"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {action} keyboard device {instance_id}. "
                f"If this is the only keyboard attached, disabling it can leave the machine hard to control.",
            }
        safe_id = instance_id.replace("'", "''")
        verb = "Enable-PnpDevice" if enabled else "Disable-PnpDevice"
        result = self._run_ps(f"{verb} -InstanceId '{safe_id}' -Confirm:$false")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not {action} keyboard")}
        return {"success": True, "instance_id": instance_id, "enabled": enabled}

    def get_repeat_settings(self) -> Dict:
        """Current key repeat delay (0-3, short to long) and repeat
        speed (0-31, slow to fast) - Settings > Devices > Typing >
        Advanced keyboard settings. No admin needed."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEYBOARD_REG_PATH) as key:
                delay, _ = winreg.QueryValueEx(key, "KeyboardDelay")
                speed, _ = winreg.QueryValueEx(key, "KeyboardSpeed")
                return {"success": True, "delay": int(delay), "speed": int(speed)}
        except FileNotFoundError:
            return {"error": "Keyboard registry settings not found"}
        except OSError as e:
            return {"error": str(e)}

    def set_repeat_settings(self, delay: int = None, speed: int = None) -> Dict:
        """Set key repeat delay (0-3) and/or speed (0-31). Not
        confirm-gated - a per-user input preference, reversible any
        time. Applies immediately via SystemParametersInfo, and is
        also written to the registry so it persists."""
        if delay is None and speed is None:
            return {"error": "Provide at least one of delay or speed"}
        result: Dict = {"success": True}
        try:
            if delay is not None:
                delay = max(0, min(3, int(delay)))
                ctypes.windll.user32.SystemParametersInfoW(_SPI_SETKEYBOARDDELAY, delay, None, _SPIF_SENDCHANGE)
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _KEYBOARD_REG_PATH) as key:
                    winreg.SetValueEx(key, "KeyboardDelay", 0, winreg.REG_SZ, str(delay))
                result["delay"] = delay
            if speed is not None:
                speed = max(0, min(31, int(speed)))
                ctypes.windll.user32.SystemParametersInfoW(_SPI_SETKEYBOARDSPEED, speed, None, _SPIF_SENDCHANGE)
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _KEYBOARD_REG_PATH) as key:
                    winreg.SetValueEx(key, "KeyboardSpeed", 0, winreg.REG_SZ, str(speed))
                result["speed"] = speed
            return result
        except OSError as e:
            return {"error": str(e)}

    def get_lock_key_states(self) -> Dict:
        """Current on/off state of Caps Lock, Num Lock, and Scroll
        Lock. No admin needed."""
        try:
            user32 = ctypes.windll.user32
            return {
                "success": True,
                "caps_lock": bool(user32.GetKeyState(_VK_CAPITAL) & 0x0001),
                "num_lock": bool(user32.GetKeyState(_VK_NUMLOCK) & 0x0001),
                "scroll_lock": bool(user32.GetKeyState(_VK_SCROLL) & 0x0001),
            }
        except Exception as e:
            return {"error": str(e)}

    def set_lock_key_state(self, key: str, on: bool) -> Dict:
        """Turn Caps Lock, Num Lock, or Scroll Lock on/off by
        simulating the key press (toggling only actually happens if
        the current state differs from the requested one). Not
        confirm-gated - a cheap, instantly-reversible toggle."""
        vk_map = {"caps_lock": _VK_CAPITAL, "num_lock": _VK_NUMLOCK, "scroll_lock": _VK_SCROLL}
        vk = vk_map.get(key.lower())
        if vk is None:
            return {"error": f"Unknown key '{key}'. Use 'caps_lock', 'num_lock', or 'scroll_lock'."}
        try:
            user32 = ctypes.windll.user32
            current = bool(user32.GetKeyState(vk) & 0x0001)
            if current != on:
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
            return {"success": True, "key": key, "on": on}
        except Exception as e:
            return {"error": str(e)}

    def get_filter_keys(self) -> Dict:
        """Whether Filter Keys (ignore brief or repeated keystrokes) is
        currently on - Settings > Accessibility > Keyboard. No admin
        needed."""
        try:
            fk = _FILTERKEYS()
            fk.cbSize = ctypes.sizeof(_FILTERKEYS)
            ctypes.windll.user32.SystemParametersInfoW(
                _SPI_GETFILTERKEYS, ctypes.sizeof(_FILTERKEYS), ctypes.byref(fk), 0
            )
            return {"success": True, "enabled": bool(fk.dwFlags & _FKF_FILTERKEYSON)}
        except Exception as e:
            return {"error": str(e)}

    def set_filter_keys(self, enabled: bool) -> Dict:
        """Turn Filter Keys on/off. Not confirm-gated - same class as
        accessibility.py's own toggles."""
        try:
            fk = _FILTERKEYS()
            fk.cbSize = ctypes.sizeof(_FILTERKEYS)
            fk.dwFlags = _FKF_FILTERKEYSON if enabled else 0
            fk.iWaitMSec = fk.iDelayMSec = fk.iRepeatMSec = fk.iBounceMSec = 0
            ctypes.windll.user32.SystemParametersInfoW(
                _SPI_SETFILTERKEYS, ctypes.sizeof(_FILTERKEYS), ctypes.byref(fk), _SPIF_SENDCHANGE
            )
            return {"success": True, "enabled": enabled}
        except Exception as e:
            return {"error": str(e)}

    def list_keyboard_layouts(self) -> Dict:
        """Installed keyboard input languages/layouts and which one is
        currently active - Settings > Time & Language > Language & region.
        Read-only; switching layout is a fast, frequent, low-stakes
        action best left to the existing Win+Space/language-bar UI
        rather than a scripted setter here. No admin needed."""
        result = self._run_ps(
            "Get-WinUserLanguageList | Select-Object LanguageTag, "
            "@{N='InputMethodTips';E={$_.InputMethodTips}} | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-WinUserLanguageList failed"}
        if not result["stdout"]:
            return {"success": True, "layouts": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse layout list"}
        layouts = data if isinstance(data, list) else [data]
        return {"success": True, "layouts": layouts, "count": len(layouts)}
