"""
Fill Form
=========
Sequences click_mouse.py and type_text.py across several fields in
one call - click a field, type its value, move to the next - the same
"higher module builds on lower ones" habit SEARCH/people_search.py
established for this project (there, google_search.py; here,
click_mouse.py + type_text.py). Imports both lazily inside the
method, not at module level, matching that same file's reasoning:
this module should still import cleanly even if one half of the pair
is missing, and only fail at call time.

A field that fails to click or type stops the run rather than
skipping ahead silently - a form filled out of order or missing a
field partway through is worse than one that visibly stopped, so
fill() reports exactly how far it got instead of pretending success.
"""

import time
from typing import Dict, List, Optional

DEFAULT_FIELD_DELAY_SECONDS = 0.3


class FillForm:
    """Sequenced multi-field form filling. Use get_fill_form()."""

    def is_available(self) -> bool:
        try:
            from actions.click_mouse import get_click_mouse
            from actions.type_text import get_type_text

            return get_click_mouse().is_available() and get_type_text().is_available()
        except Exception:
            return False

    def fill(self, fields: List[Dict], field_delay: float = DEFAULT_FIELD_DELAY_SECONDS) -> Dict:
        """`fields` is a list of {"x": int, "y": int, "text": str}
        dicts, filled in order. Returns
        {"success": bool, "filled_count": int, "error": Optional[str]}.
        `filled_count` is how many fields were completed before either
        finishing or hitting a failure - on partial failure `success`
        is False but `filled_count` still tells the caller how much
        of the form actually got done."""
        if not fields:
            return {"success": False, "filled_count": 0, "error": "no fields given"}
        try:
            from actions.click_mouse import get_click_mouse
            from actions.type_text import get_type_text
        except Exception:
            return {"success": False, "filled_count": 0, "error": "ACTIONS primitives unavailable"}

        clicker = get_click_mouse()
        typer = get_type_text()
        if not (clicker.is_available() and typer.is_available()):
            return {"success": False, "filled_count": 0, "error": "pyautogui not available"}

        filled_count = 0
        for field in fields:
            x, y, text = field.get("x"), field.get("y"), field.get("text", "")
            if x is None or y is None:
                return {
                    "success": False,
                    "filled_count": filled_count,
                    "error": f"field {filled_count} missing x/y",
                }
            click_result = clicker.click(x, y)
            if not click_result["success"]:
                return {"success": False, "filled_count": filled_count, "error": click_result["error"]}
            type_result = typer.type_text(text)
            if not type_result["success"]:
                return {"success": False, "filled_count": filled_count, "error": type_result["error"]}
            filled_count += 1
            time.sleep(field_delay)

        return {"success": True, "filled_count": filled_count, "error": None}


_fill_form: Optional[FillForm] = None


def get_fill_form() -> FillForm:
    global _fill_form
    if _fill_form is None:
        _fill_form = FillForm()
    return _fill_form
