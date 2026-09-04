"""Gesture Control
===================
Binds gestures DETECTED by vision.gestures.recognizer.GestureRecognizer
(hand landmark classification - thumbs_up, open_palm, fist, etc, see
that module for the actual CV) to real system actions. That module
only classifies a single frame; it has no concept of "what should
happen" for a gesture. This module owns that mapping (stored as a
simple JSON file), executes the bound action directly via pyautogui
for mouse/keyboard-level actions, and delegates volume/mute to
system_control.hardware.speaker_control.SpeakerControl rather than
re-implementing audio control.

Binding or unbinding a gesture, and enabling continuous gesture
control, are confirm-gated since an active binding means webcam
frames start driving system actions.
"""

import json
from pathlib import Path
from typing import Dict, Optional

_BINDINGS_PATH = Path(__file__).resolve().parent / "_gesture_bindings.json"

_BUILTIN_ACTIONS = {
    "volume_up",
    "volume_down",
    "mute_toggle",
    "media_play_pause",
    "media_next",
    "media_prev",
    "scroll_up",
    "scroll_down",
    "alt_tab",
    "screenshot",
}


class GestureControl:
    def __init__(self):
        self._enabled = False

    def _load_bindings(self) -> Dict:
        if _BINDINGS_PATH.exists():
            try:
                return json.loads(_BINDINGS_PATH.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_bindings(self, bindings: Dict) -> None:
        _BINDINGS_PATH.write_text(json.dumps(bindings, indent=2), encoding="utf-8")

    def list_available_gestures(self) -> Dict:
        """Gestures vision.gestures.recognizer.GestureRecognizer._classify() can emit."""
        return {"gestures": ["thumbs_up", "thumbs_down", "open_palm", "fist", "peace", "pointing", "none"]}

    def list_available_actions(self) -> Dict:
        return {"actions": sorted(_BUILTIN_ACTIONS)}

    def list_bindings(self) -> Dict:
        return {"bindings": self._load_bindings()}

    def bind_gesture(self, gesture: str, action: str, confirm: bool = False) -> Dict:
        if action not in _BUILTIN_ACTIONS:
            return {"error": f"Unknown action '{action}'. See list_available_actions()."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will bind gesture '{gesture}' to action '{action}'.",
            }
        bindings = self._load_bindings()
        bindings[gesture] = action
        self._save_bindings(bindings)
        return {"success": True, "gesture": gesture, "action": action}

    def unbind_gesture(self, gesture: str, confirm: bool = False) -> Dict:
        if not confirm:
            return {"requires_confirmation": True, "preview": f"This will remove the binding for gesture '{gesture}'."}
        bindings = self._load_bindings()
        removed = bindings.pop(gesture, None)
        self._save_bindings(bindings)
        return {"success": True, "removed": removed}

    def _execute_action(self, action: str) -> Dict:
        try:
            if action in ("volume_up", "volume_down", "mute_toggle"):
                from system_control.hardware.speaker_control import SpeakerControl

                sc = SpeakerControl()
                if action == "mute_toggle":
                    cur = sc.get_device_mute()
                    return sc.set_device_mute(not cur.get("muted", False))
                cur = sc.get_device_volume()
                level = cur.get("volume", 50)
                delta = 10 if action == "volume_up" else -10
                return sc.set_device_volume(max(0, min(100, level + delta)))
            import pyautogui

            if action == "media_play_pause":
                pyautogui.press("playpause")
            elif action == "media_next":
                pyautogui.press("nexttrack")
            elif action == "media_prev":
                pyautogui.press("prevtrack")
            elif action == "scroll_up":
                pyautogui.scroll(300)
            elif action == "scroll_down":
                pyautogui.scroll(-300)
            elif action == "alt_tab":
                pyautogui.hotkey("alt", "tab")
            elif action == "screenshot":
                from vision.screen.capture import ScreenCapture
                import tempfile

                path = str(Path(tempfile.gettempdir()) / "ultron_gesture_screenshot.png")
                return ScreenCapture().capture_to_file(path)
            else:
                return {"error": f"No handler wired for action '{action}'."}
            return {"success": True, "action": action}
        except ImportError as e:
            return {"error": f"Missing dependency for '{action}': {e}"}
        except Exception as e:
            return {"error": str(e)}

    def process_frame(self, image=None) -> Dict:
        """Detect a gesture in a single frame and, if bound and gesture
        control is enabled, execute the bound action. Detection itself is
        entirely delegated to GestureRecognizer."""
        from vision.gestures.recognizer import GestureRecognizer

        detection = GestureRecognizer().detect(image=image)
        gesture = detection.get("gesture") if isinstance(detection, dict) else None
        if not gesture or gesture == "none":
            return {"gesture": gesture, "action_taken": None}
        bindings = self._load_bindings()
        action = bindings.get(gesture)
        if not action:
            return {"gesture": gesture, "action_taken": None, "note": "no binding for this gesture"}
        if not self._enabled:
            return {
                "gesture": gesture,
                "bound_action": action,
                "action_taken": None,
                "note": "gesture control is disabled - call set_enabled(True, confirm=True)",
            }
        result = self._execute_action(action)
        return {"gesture": gesture, "action_taken": action, "result": result}

    def set_enabled(self, enabled: bool, confirm: bool = False) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will {'ENABLE' if enabled else 'disable'} gesture-driven system actions - bound gestures will start controlling this PC."
                    if enabled
                    else "This will disable gesture-driven system actions."
                ),
            }
        self._enabled = enabled
        return {"success": True, "enabled": enabled}

    def get_status(self) -> Dict:
        return {"enabled": self._enabled, "bindings": self._load_bindings()}


_instance: Optional[GestureControl] = None


def get_gesture_control() -> GestureControl:
    global _instance
    if _instance is None:
        _instance = GestureControl()
    return _instance
