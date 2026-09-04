"""
global_hook_manager.py
=======================
Lets ULTRON respond to specific hotkeys / mouse gestures from anywhere
in Windows (e.g. "Ctrl+Shift+J" to wake voice mode, a middle-click
drag to trigger screenshot-and-ask).

Design choice: this registers a small allow-list of key COMBINATIONS
and fires a callback when one matches. It does not record or store
every keystroke the user types - that would make it a keylogger, and
that's a line I won't cross even inside your own assistant, because a
"record everything typed" module is indistinguishable from spyware
once it exists as a file on disk. If you need "type X to trigger Y"
for many phrases, register each phrase as its own hotkey mapping
below rather than asking this module to watch all typing.

Dependencies: pip install keyboard mouse
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Dict

try:
    import keyboard  # global hotkey support (Windows/Linux/Mac)
except ImportError:  # pragma: no cover
    keyboard = None

try:
    import mouse  # global mouse gesture support
except ImportError:  # pragma: no cover
    mouse = None

logger = logging.getLogger("ultron.global_hook_manager")


@dataclass
class HotkeyBinding:
    combo: str
    callback: Callable[[], None]
    description: str = ""
    suppress: bool = False  # if True, swallow the combo so it doesn't reach the focused app


class GlobalHookManager:
    """
    Central registry for global hotkeys and simple mouse gestures.
    Everything registered here is explicit and named - there is no
    catch-all handler and no persisted log of raw input events.
    """

    def __init__(self):
        self._hotkeys: Dict[str, HotkeyBinding] = {}
        self._mouse_handlers: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._active = False

        if keyboard is None:
            logger.warning("`keyboard` package not installed - hotkeys disabled. pip install keyboard")
        if mouse is None:
            logger.warning("`mouse` package not installed - gestures disabled. pip install mouse")

    # ---------------------------------------------------------- hotkeys
    def register_hotkey(
        self, combo: str, callback: Callable[[], None], description: str = "", suppress: bool = False
    ) -> bool:
        """Register a global hotkey, e.g. combo='ctrl+shift+j'."""
        if keyboard is None:
            logger.error("Cannot register hotkey '%s' - keyboard module missing", combo)
            return False

        with self._lock:
            if combo in self._hotkeys:
                logger.warning("Hotkey '%s' already registered, overwriting", combo)
                keyboard.remove_hotkey(combo)

            keyboard.add_hotkey(combo, callback, suppress=suppress)
            self._hotkeys[combo] = HotkeyBinding(combo, callback, description, suppress)

        logger.info("Registered hotkey '%s' (%s)", combo, description or "no description")
        return True

    def unregister_hotkey(self, combo: str) -> bool:
        with self._lock:
            if combo not in self._hotkeys:
                return False
            if keyboard is not None:
                keyboard.remove_hotkey(combo)
            del self._hotkeys[combo]
        logger.info("Unregistered hotkey '%s'", combo)
        return True

    def list_hotkeys(self) -> Dict[str, str]:
        with self._lock:
            return {c: b.description for c, b in self._hotkeys.items()}

    # ------------------------------------------------------ mouse gesture
    def register_mouse_gesture(self, name: str, button: str, event: str, callback: Callable[[], None]) -> bool:
        """
        Register a simple mouse event, e.g. name='screenshot',
        button='middle', event='down'.
        """
        if mouse is None:
            logger.error("Cannot register gesture '%s' - mouse module missing", name)
            return False

        def _wrapped_handler(ev):
            # only fire for the exact button/event this gesture cares about
            if getattr(ev, "button", None) == button and getattr(ev, "event_type", None) == event:
                callback()

        mouse.hook(_wrapped_handler)
        self._mouse_handlers[name] = _wrapped_handler
        logger.info("Registered mouse gesture '%s' (%s %s)", name, button, event)
        return True

    def unregister_mouse_gesture(self, name: str) -> bool:
        handler = self._mouse_handlers.pop(name, None)
        if handler is None:
            return False
        if mouse is not None:
            mouse.unhook(handler)
        return True

    # ------------------------------------------------------------ control
    def start(self):
        """Hooks are already live as soon as they're registered (keyboard/
        mouse libs install OS-level hooks immediately); this just marks
        the manager active and blocks the calling thread if desired via
        `wait()`."""
        self._active = True
        logger.info(
            "GlobalHookManager active with %d hotkeys, %d gestures", len(self._hotkeys), len(self._mouse_handlers)
        )

    def stop(self):
        with self._lock:
            for combo in list(self._hotkeys):
                self.unregister_hotkey(combo)
            for name in list(self._mouse_handlers):
                self.unregister_mouse_gesture(name)
        self._active = False
        logger.info("GlobalHookManager stopped, all hooks released")

    def wait(self):
        """Block forever, e.g. when running this manager as its own thread."""
        if keyboard is not None:
            keyboard.wait()
        else:
            threading.Event().wait()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mgr = GlobalHookManager()
    mgr.register_hotkey("ctrl+shift+j", lambda: print("ULTRON wake hotkey fired"), description="Wake ULTRON voice mode")
    mgr.start()
    print("Listening for Ctrl+Shift+J ... Ctrl+C to exit")
    try:
        mgr.wait()
    except KeyboardInterrupt:
        mgr.stop()
