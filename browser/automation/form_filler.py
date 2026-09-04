"""Form filler (automation)
============================
Fills web forms in whatever browser tab currently has focus, by typing
into fields and tabbing between them via pyautogui (there's no
cross-browser DOM access without a browser extension, so this drives
the UI the same way a person typing on the keyboard would). Also
stores reusable "profiles" (name/email/address/etc.) under
storage/cache so a form can be filled by profile name instead of
repeating every field each time.
"""

import json
import time
from pathlib import Path
from typing import Dict, List

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

PROFILES_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "form_profiles"


class FormFiller:
    """Fill web forms via keyboard automation, with saved autofill profiles."""

    def __init__(self):
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    def fill_field(self, value: str, press_tab_after: bool = True, delay: float = 0.03) -> Dict:
        """Type `value` into whichever field currently has focus, optionally
        pressing Tab afterward to move to the next field."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            pyautogui.typewrite(str(value), interval=delay)
            if press_tab_after:
                pyautogui.press("tab")
            return {"success": True, "typed": value}
        except Exception as e:
            return {"error": str(e)}

    def fill_sequence(self, values: List[str], delay_between_fields: float = 0.3) -> Dict:
        """Fill a sequence of fields in order, tabbing between each - assumes
        the first field already has focus and each Tab moves to the next in
        the expected order (true for most straightforward forms)."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            for i, value in enumerate(values):
                pyautogui.typewrite(str(value), interval=0.03)
                if i < len(values) - 1:
                    pyautogui.press("tab")
                    time.sleep(delay_between_fields)
            return {"success": True, "fields_filled": len(values)}
        except Exception as e:
            return {"error": str(e)}

    def submit_form(self) -> Dict:
        """Press Enter to submit the currently focused form."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            pyautogui.press("enter")
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def clear_field(self) -> Dict:
        """Clear the currently focused field (select-all then delete)."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("delete")
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    # --- autofill profiles ---
    def save_profile(self, profile_name: str, fields: Dict[str, str]) -> Dict:
        """Save a named autofill profile, e.g. {"first_name": "...", "email": "...", "address": "..."}."""
        path = PROFILES_DIR / f"{profile_name}.json"
        with open(path, "w") as f:
            json.dump(fields, f, indent=2)
        return {"success": True, "profile_name": profile_name, "field_count": len(fields)}

    def get_profile(self, profile_name: str) -> Dict:
        path = PROFILES_DIR / f"{profile_name}.json"
        if not path.exists():
            return {"error": f"No profile named '{profile_name}'"}
        with open(path) as f:
            return {"profile_name": profile_name, "fields": json.load(f)}

    def list_profiles(self) -> Dict:
        names = [p.stem for p in PROFILES_DIR.glob("*.json")]
        return {"profiles": names, "count": len(names)}

    def delete_profile(self, profile_name: str) -> Dict:
        path = PROFILES_DIR / f"{profile_name}.json"
        if not path.exists():
            return {"error": f"No profile named '{profile_name}'"}
        path.unlink()
        return {"success": True, "deleted": profile_name}

    def autofill_from_profile(self, profile_name: str, field_order: List[str]) -> Dict:
        """Fill the currently focused form using a saved profile, tabbing
        through fields in the order given by field_order (a list of the
        profile's keys, in the order they appear on the actual form)."""
        profile = self.get_profile(profile_name)
        if "error" in profile:
            return profile
        fields = profile["fields"]
        values = [fields.get(key, "") for key in field_order]
        result = self.fill_sequence(values)
        return {"profile_name": profile_name, **result}
