"""
ACTIONS (Phase 18.7)
======================
Generic, app-agnostic device automation primitives - the low-level
building blocks, not the 61 dedicated per-app classes in apps/*.py
(Phase 6) or the API-based integrations in this phase's own CONNECT/:

    open_app.py     - launch any app by name/path. Stdlib only.
    type_text.py     - type at whatever currently has focus.
    click_mouse.py    - move/click a screen coordinate.
    fill_form.py      - sequences click_mouse.py + type_text.py
                        across several fields.
    send_message.py   - the generic, coordinate-based fallback for
                        sending a message when no dedicated
                        apps/communication/*.py class and no
                        CONNECT/*.py API integration applies.
    call_phone.py      - hands a number to the OS's tel: handler.

type_text.py and click_mouse.py both depend on `pyautogui`; the other
four either build on those two or need no optional package at all.
Every public method returns {"success": bool, ..., "error": Optional[str]}
and never raises, same contract this project keeps everywhere else.

Purely additive - nothing in Phase 1-18.6 imports from here.
"""

from actions.open_app import get_open_app
from actions.type_text import get_type_text
from actions.click_mouse import get_click_mouse
from actions.fill_form import get_fill_form
from actions.send_message import get_send_message
from actions.call_phone import get_call_phone

__all__ = [
    "get_open_app",
    "get_type_text",
    "get_click_mouse",
    "get_fill_form",
    "get_send_message",
    "get_call_phone",
]
