"""
Chrome cookies
================
Chrome-scoped cookie tools. Reading (with value decryption, since
Chromium stores cookie values DPAPI-encrypted on Windows) reuses
browser/cookies/cookies.py's browser_cookie3-backed CookieTools -
duplicating DPAPI handling here would be redundant and riskier to get
subtly wrong. Deleting is new: it talks to Chrome's own Cookies SQLite
file directly, which browser_cookie3 (read-only by design) doesn't
support - Chrome must be closed first since the file is locked while
it's running.
"""

import sqlite3
from pathlib import Path
from typing import Dict, Optional

from browser.cookies.cookies import CookieTools

# Modern Chrome keeps cookies under Network/; older versions kept them
# directly in the profile folder.
_CANDIDATE_PATHS = [
    Path.home() / "AppData/Local/Google/Chrome/User Data/Default/Network/Cookies",
    Path.home() / "AppData/Local/Google/Chrome/User Data/Default/Cookies",
]


class ChromeCookies:
    """Read (decrypted) and delete cookies from Chrome's own cookie store."""

    def __init__(self):
        self._tools = CookieTools()

    def get_cookies(self, domain: str) -> Dict:
        """All cookies (name/value/path/expiry) Chrome has stored for a domain."""
        return self._tools.get_cookies(domain, browser="chrome")

    def get_cookie_value(self, domain: str, cookie_name: str) -> Dict:
        return self._tools.get_cookie_value(domain, cookie_name, browser="chrome")

    def _cookies_db_path(self) -> Optional[Path]:
        for p in _CANDIDATE_PATHS:
            if p.exists():
                return p
        return None

    def delete_cookies_for_domain(self, domain: str, confirm: bool = False) -> Dict:
        """Delete every stored cookie for a domain. Close Chrome first -
        the Cookies file is locked while Chrome is running. Safety-gated:
        needs confirm=true."""
        if not confirm:
            return {
                "error": "This permanently deletes cookies for the domain. Call again with confirm=true to proceed."
            }
        path = self._cookies_db_path()
        if not path:
            return {"error": "Chrome's Cookies database was not found - is Chrome installed?"}
        try:
            conn = sqlite3.connect(str(path))
            cur = conn.cursor()
            cur.execute("DELETE FROM cookies WHERE host_key LIKE ?", (f"%{domain}%",))
            deleted = cur.rowcount
            conn.commit()
            conn.close()
            return {"success": True, "domain": domain, "deleted_count": deleted}
        except sqlite3.OperationalError as e:
            return {
                "error": f"{e} - Chrome likely needs to be closed first (the Cookies file is locked while it's running)"
            }
        except Exception as e:
            return {"error": str(e)}
