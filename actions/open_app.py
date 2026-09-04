"""
Open App
========
Launches an application generically by name or path - `os.startfile`
on Windows, `subprocess.Popen` elsewhere. This is deliberately not
apps/*.py from Phase 6: those 61 classes each know how to launch *and
drive* one specific named application (Spotify, WhatsApp, VLC, ...)
through its own automation surface. This module knows how to launch
*anything*, and nothing past that - it's the low-level primitive
apps/*.py's own launch step could be built on, and the fallback for
any app that doesn't have a dedicated apps/*.py class yet.

Stdlib only, so there's no "package missing" failure mode here the
way SEARCH's `requests`-based modules have - is_available() is always
True. What can still fail is the launch itself (bad name, app not
installed, OS refuses), which open() reports through its own
success flag rather than raising, matching this project's standing
contract of never letting an optional action raise into the caller.
"""

import os
import subprocess
import sys
from typing import Dict, Optional


class OpenApp:
    """Generic application launcher. Use get_open_app()."""

    def is_available(self) -> bool:
        return True

    def open(self, target: str) -> Dict:
        """Launches `target` - an app name Windows can resolve
        (e.g. "notepad", "calc") or a full path to an executable/file.
        Returns {"success": bool, "error": Optional[str]}. Never
        raises - a bad name or a refusing OS is reported here, not
        thrown."""
        if not target:
            return {"success": False, "error": "no target given"}
        try:
            if sys.platform.startswith("win"):
                os.startfile(target)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen([target])
            return {"success": True, "error": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


_open_app: Optional[OpenApp] = None


def get_open_app() -> OpenApp:
    global _open_app
    if _open_app is None:
        _open_app = OpenApp()
    return _open_app
