"""
ui/overlay/popup.py - alias for ui/overlay/overlay.py.

The real implementation lives in overlay.py; this file exists only so
the path `ui/overlay/popup.py` from the originally requested project
tree also works, without maintaining two copies of the same code.

    from ui.overlay.popup import Overlay, enable_overlay
"""

from ui.overlay.overlay import Overlay, enable_overlay

__all__ = ["Overlay", "enable_overlay"]
