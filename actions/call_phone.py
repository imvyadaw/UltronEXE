"""
Call Phone
==========
Hands a phone number off to whatever the OS has registered as the
`tel:` protocol handler - on Windows 11 that's typically Phone Link
for a paired Android device, elsewhere it might be Skype or nothing
at all. Deliberately the simplest possible approach rather than a
dedicated telephony integration: this project's roadmap lists Android
integration as its own future phase, and building a real dialer here
would duplicate whatever that phase eventually does properly. Stdlib
`webbrowser` only, so there's no package to be missing - the only
real failure mode is "no handler registered for tel:", which the OS
doesn't reliably report back, so is_available() can only promise the
stdlib call itself will work, not that a call will actually happen.
"""

import re
import webbrowser
from typing import Dict, Optional

NUMBER_PATTERN = re.compile(r"^\+?[\d\s().-]{5,20}$")


class CallPhone:
    """tel: protocol handoff for phone calls. Use get_call_phone()."""

    def is_available(self) -> bool:
        return True

    def call(self, number: str) -> Dict:
        """Opens `tel:{number}` via the OS's registered handler.
        Returns {"success": bool, "error": Optional[str]}.
        `success` reflects whether the handoff itself succeeded, not
        whether a call actually connected - webbrowser.open() can't
        see past its own OS call, so a bad or unregistered handler
        may still report success here."""
        if not number or not NUMBER_PATTERN.match(number.strip()):
            return {"success": False, "error": "number doesn't look like a phone number"}
        try:
            opened = webbrowser.open(f"tel:{number.strip()}")
            if not opened:
                return {"success": False, "error": "no tel: handler available"}
            return {"success": True, "error": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


_call_phone: Optional[CallPhone] = None


def get_call_phone() -> CallPhone:
    global _call_phone
    if _call_phone is None:
        _call_phone = CallPhone()
    return _call_phone
