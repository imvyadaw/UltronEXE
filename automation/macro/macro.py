"""Macro recorder/player
======================
Record a sequence of mouse/keyboard actions as a named macro, then
replay it later. Macros are stored as JSON so they survive a restart.
Recording itself listens to real input events via the `pynput` library
(separate from pyautogui, which is for *generating* input, not
capturing it).
"""

import json
import time
from pathlib import Path
from typing import Dict, List

try:
    from pynput import mouse as pynput_mouse, keyboard as pynput_keyboard

    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

MACROS_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "macros"


class MacroRecorder:
    """Record and replay sequences of mouse clicks / key presses."""

    def __init__(self):
        MACROS_DIR.mkdir(parents=True, exist_ok=True)
        self._events: List[Dict] = []
        self._recording = False
        self._start_time = 0.0
        self._mouse_listener = None
        self._keyboard_listener = None

    def start_recording(self) -> Dict:
        """Start capturing mouse clicks and key presses."""
        if not HAS_PYNPUT:
            return {"error": "pynput not installed - run: pip install pynput"}
        if self._recording:
            return {"error": "Already recording"}
        self._events = []
        self._recording = True
        self._start_time = time.time()

        def on_click(x, y, button, pressed):
            if pressed:
                self._events.append(
                    {"type": "click", "x": x, "y": y, "button": str(button), "t": time.time() - self._start_time}
                )

        def on_press(key):
            try:
                key_repr = key.char
            except AttributeError:
                key_repr = str(key).replace("Key.", "")
            self._events.append({"type": "key", "key": key_repr, "t": time.time() - self._start_time})

        self._mouse_listener = pynput_mouse.Listener(on_click=on_click)
        self._keyboard_listener = pynput_keyboard.Listener(on_press=on_press)
        self._mouse_listener.start()
        self._keyboard_listener.start()
        return {"success": True, "message": "Recording started"}

    def stop_recording(self, macro_name: str) -> Dict:
        """Stop capturing and save the recorded macro under a name."""
        if not self._recording:
            return {"error": "Not currently recording"}
        self._recording = False
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()

        path = MACROS_DIR / f"{macro_name}.json"
        with open(path, "w") as f:
            json.dump(self._events, f, indent=2)
        return {"success": True, "macro_name": macro_name, "event_count": len(self._events), "saved_to": str(path)}

    def list_macros(self) -> Dict:
        """List all saved macros."""
        try:
            macros = [p.stem for p in MACROS_DIR.glob("*.json")]
            return {"macros": macros, "count": len(macros)}
        except Exception as e:
            return {"error": str(e)}

    def play_macro(self, macro_name: str, speed: float = 1.0) -> Dict:
        """Replay a saved macro. speed > 1 plays faster, < 1 plays slower."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        path = MACROS_DIR / f"{macro_name}.json"
        if not path.exists():
            return {"error": f"No macro named '{macro_name}'"}
        try:
            with open(path) as f:
                events = json.load(f)

            last_t = 0.0
            for event in events:
                wait = (event["t"] - last_t) / speed
                if wait > 0:
                    time.sleep(min(wait, 3.0))  # cap gaps so a macro never "hangs"
                last_t = event["t"]

                if event["type"] == "click":
                    button = (
                        "left" if "left" in event["button"] else ("right" if "right" in event["button"] else "middle")
                    )
                    pyautogui.click(event["x"], event["y"], button=button)
                elif event["type"] == "key":
                    key = event["key"]
                    if len(key) == 1:
                        pyautogui.typewrite(key)
                    else:
                        try:
                            pyautogui.press(key.lower())
                        except Exception:
                            from core.error_trace import log_swallowed as _lsw

                            _lsw("automation.macro.macro.play_macro")

            return {"success": True, "macro_name": macro_name, "events_played": len(events)}
        except Exception as e:
            return {"error": str(e)}

    def delete_macro(self, macro_name: str) -> Dict:
        """Delete a saved macro."""
        path = MACROS_DIR / f"{macro_name}.json"
        if not path.exists():
            return {"error": f"No macro named '{macro_name}'"}
        path.unlink()
        return {"success": True, "deleted": macro_name}
