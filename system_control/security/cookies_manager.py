"""Cookies Manager (privacy hygiene)
======================================
Domain-level cookie hygiene across Chrome, Edge, and Firefox - list
which domains have cookies stored and how many, and clear them (one
domain or everything), for privacy cleanup. Distinct from
browser/cookies/cookies.py and browser/chrome/cookies.py, which read
actual cookie *values* (including session tokens) for automation
purposes - this module deliberately never returns a cookie's value,
only its domain/name/expiry metadata, since a value-reading path here
would double as a session-hijacking primitive with no gate on it.
If value-level access is genuinely needed for an automation task, use
browser/cookies/cookies.py's CookieTools directly - not this module.

Listing domains/counts is a plain read. Every delete is confirm-gated.
Chromium browsers must be closed first since their Cookies file is
locked while running; this is checked and reported rather than
force-killing the browser out from under the user.
"""

import sqlite3
import subprocess
from pathlib import Path
from typing import Dict, Optional


class CookiesManager:
    """Inspect (metadata-only) and clear browser cookies for privacy hygiene."""

    _PATHS = {
        "chrome": [
            Path.home() / "AppData/Local/Google/Chrome/User Data/Default/Network/Cookies",
            Path.home() / "AppData/Local/Google/Chrome/User Data/Default/Cookies",
        ],
        "edge": [
            Path.home() / "AppData/Local/Microsoft/Edge/User Data/Default/Network/Cookies",
            Path.home() / "AppData/Local/Microsoft/Edge/User Data/Default/Cookies",
        ],
    }
    # Firefox keeps cookies in cookies.sqlite inside a randomly-named
    # profile folder; resolved lazily in _firefox_db_path().
    _FIREFOX_PROFILES = Path.home() / "AppData/Roaming/Mozilla/Firefox/Profiles"

    _PROCESS_NAMES = {"chrome": "chrome", "edge": "msedge", "firefox": "firefox"}

    def _db_path(self, browser: str) -> Optional[Path]:
        browser = browser.lower()
        if browser in self._PATHS:
            for p in self._PATHS[browser]:
                if p.exists():
                    return p
            return None
        if browser == "firefox":
            return self._firefox_db_path()
        return None

    def _firefox_db_path(self) -> Optional[Path]:
        if not self._FIREFOX_PROFILES.exists():
            return None
        for profile_dir in self._FIREFOX_PROFILES.iterdir():
            candidate = profile_dir / "cookies.sqlite"
            if candidate.exists():
                return candidate
        return None

    def _is_running(self, browser: str) -> bool:
        proc_name = self._PROCESS_NAMES.get(browser.lower())
        if not proc_name:
            return False
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {proc_name}.exe"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc_name.lower() in result.stdout.lower()
        except Exception:
            return False

    def list_domains(self, browser: str = "chrome") -> Dict:
        """List every domain with stored cookies and how many, for a
        browser ('chrome', 'edge', or 'firefox'). Metadata only - no
        cookie values are read or returned."""
        browser = browser.lower()
        path = self._db_path(browser)
        if not path:
            return {"error": f"Could not find a cookie store for '{browser}' - is it installed?"}
        host_col = "host" if browser == "firefox" else "host_key"
        table = "moz_cookies" if browser == "firefox" else "cookies"
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute(f"SELECT {host_col}, COUNT(*) FROM {table} GROUP BY {host_col} ORDER BY COUNT(*) DESC")
            rows = cur.fetchall()
            conn.close()
        except sqlite3.OperationalError as e:
            return {"error": f"Could not read the cookie store ({e}). Close {browser} first and retry."}
        except Exception as e:
            return {"error": str(e)}
        domains = [{"domain": r[0], "cookie_count": r[1]} for r in rows]
        return {
            "browser": browser,
            "domains": domains,
            "total_domains": len(domains),
            "total_cookies": sum(d["cookie_count"] for d in domains),
        }

    def get_domain_cookie_count(self, domain: str, browser: str = "chrome") -> Dict:
        """How many cookies are stored for one domain - a lighter check
        than list_domains() when you only care about a single site."""
        listed = self.list_domains(browser)
        if "error" in listed:
            return listed
        for d in listed["domains"]:
            if domain.lower() in d["domain"].lower():
                return {"domain": d["domain"], "browser": browser, "cookie_count": d["cookie_count"]}
        return {"domain": domain, "browser": browser, "cookie_count": 0}

    def clear_domain(self, domain: str, browser: str = "chrome", confirm: bool = False) -> Dict:
        """Delete every stored cookie matching a domain, for one browser.
        Confirm-gated. The browser must be closed first - its cookie file
        is locked while running."""
        browser = browser.lower()
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will delete all cookies for domains matching '{domain}' in {browser}. "
                f"You'll be signed out of any sites under that domain.",
            }
        if self._is_running(browser):
            return {"error": f"{browser} is currently running - close it first, its cookie store is locked while open."}
        path = self._db_path(browser)
        if not path:
            return {"error": f"Could not find a cookie store for '{browser}'."}
        host_col = "host" if browser == "firefox" else "host_key"
        table = "moz_cookies" if browser == "firefox" else "cookies"
        try:
            conn = sqlite3.connect(str(path))
            cur = conn.cursor()
            cur.execute(f"DELETE FROM {table} WHERE {host_col} LIKE ?", (f"%{domain}%",))
            deleted = cur.rowcount
            conn.commit()
            conn.close()
        except Exception as e:
            return {"error": str(e)}
        return {"success": True, "browser": browser, "domain": domain, "cookies_deleted": deleted}

    def clear_all(self, browser: str = "chrome", confirm: bool = False) -> Dict:
        """Delete ALL cookies for a browser. Confirm-gated. Browser must
        be closed first."""
        browser = browser.lower()
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will delete ALL stored cookies for {browser}. You'll be signed out "
                f"of every site you're currently logged into there.",
            }
        if self._is_running(browser):
            return {"error": f"{browser} is currently running - close it first, its cookie store is locked while open."}
        path = self._db_path(browser)
        if not path:
            return {"error": f"Could not find a cookie store for '{browser}'."}
        table = "moz_cookies" if browser == "firefox" else "cookies"
        try:
            conn = sqlite3.connect(str(path))
            cur = conn.cursor()
            cur.execute(f"DELETE FROM {table}")
            deleted = cur.rowcount
            conn.commit()
            conn.close()
        except Exception as e:
            return {"error": str(e)}
        return {"success": True, "browser": browser, "cookies_deleted": deleted}
