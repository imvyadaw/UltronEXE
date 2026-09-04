"""
ui/voice_ui/interface.py - alias for ui/voice_ui/avatar/{states,bridge}.py.

The real implementation is split across avatar/states.py (the
AvatarController state machine) and avatar/bridge.py (wiring it to
core.events); this file exists only so the path
`ui/voice_ui/interface.py` from the originally requested project tree
also works, without maintaining a second copy of the same logic.

    from ui.voice_ui.interface import get_avatar_controller, AvatarState, AvatarController
"""

from ui.voice_ui.avatar.states import AvatarState, AvatarEvent, AvatarController, InvalidTransition
from ui.voice_ui.avatar.bridge import get_avatar_controller

__all__ = [
    "AvatarState",
    "AvatarEvent",
    "AvatarController",
    "InvalidTransition",
    "get_avatar_controller",
]
