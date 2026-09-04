"""RPA recorder
============
Records mouse clicks and key presses as a sequence of structured,
named steps (not just a raw timestamped event dump like
automation/macro/macro.py) so the result can be reviewed and edited
with editor.py before being replayed with player.py. Scripts are saved
as JSON under storage/cache/rpa/.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Dict, List

try:
    from pynput import mouse as pynput_mouse, keyboard as pynput_keyboard

    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

RPA_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "rpa"


class RPARecorder:
    """Record a sequence of UI actions as a named, step-based RPA script."""

    def __init__(self):
        RPA_DIR.mkdir(parents=True, exist_ok=True)
        self._steps: List[Dict] = []
        self._recording = False
        self._paused = False
        self._start_time = 0.0
        self._mouse_listener = None
        self._keyboard_listener = None

    def start_recording(self) -> Dict:
        """Start capturing clicks and key presses as RPA steps."""
        if not HAS_PYNPUT:
            return {"error": "pynput not installed - run: pip install pynput"}
        if self._recording:
            return {"error": "Already recording"}
        self._steps = []
        self._recording = True
        self._paused = False
        self._start_time = time.time()

        def on_click(x, y, button, pressed):
            if pressed and not self._paused:
                self._steps.append(
                    {
                        "id": str(uuid.uuid4())[:8],
                        "type": "click",
                        "x": x,
                        "y": y,
                        "button": str(button).replace("Button.", ""),
                        "t": round(time.time() - self._start_time, 3),
                    }
                )

        def on_press(key):
            if self._paused:
                return
            try:
                key_repr = key.char
            except AttributeError:
                key_repr = str(key).replace("Key.", "")
            self._steps.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "type": "key",
                    "key": key_repr,
                    "t": round(time.time() - self._start_time, 3),
                }
            )

        self._mouse_listener = pynput_mouse.Listener(on_click=on_click)
        self._keyboard_listener = pynput_keyboard.Listener(on_press=on_press)
        self._mouse_listener.start()
        self._keyboard_listener.start()
        return {"success": True, "message": "RPA recording started"}

    def pause_recording(self) -> Dict:
        """Pause capture without stopping the listeners (resume with resume_recording)."""
        if not self._recording:
            return {"error": "Not currently recording"}
        self._paused = True
        return {"success": True, "message": "Recording paused"}

    def resume_recording(self) -> Dict:
        if not self._recording:
            return {"error": "Not currently recording"}
        self._paused = False
        return {"success": True, "message": "Recording resumed"}

    def add_step(self, step_type: str, **fields) -> Dict:
        """Manually append a step (e.g. 'wait', 'open_app', 'run_tool') that
        isn't capturable from raw input, useful while recording or when
        building a script without recording at all."""
        step = {
            "id": str(uuid.uuid4())[:8],
            "type": step_type,
            "t": round(time.time() - self._start_time, 3) if self._recording else 0,
            **fields,
        }
        self._steps.append(step)
        return {"success": True, "step": step}

    def stop_recording(self, script_name: str) -> Dict:
        """Stop capturing and save the recorded steps as a named RPA script."""
        if not self._recording:
            return {"error": "Not currently recording"}
        self._recording = False
        self._paused = False
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()

        path = RPA_DIR / f"{script_name}.json"
        with open(path, "w") as f:
            json.dump({"name": script_name, "steps": self._steps}, f, indent=2)
        return {"success": True, "script_name": script_name, "step_count": len(self._steps), "saved_to": str(path)}

    def discard_recording(self) -> Dict:
        """Stop capturing without saving."""
        if not self._recording:
            return {"error": "Not currently recording"}
        self._recording = False
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()
        step_count = len(self._steps)
        self._steps = []
        return {"success": True, "discarded_steps": step_count}
