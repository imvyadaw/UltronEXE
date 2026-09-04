"""Browser cookie access
======================
Read cookies from the local Chrome/Edge/Firefox cookie stores via
browser_cookie3, which handles each browser's storage format
(including Windows DPAPI decryption for Chromium browsers). Read-only
- there's no cookie *writing* here since that's rarely something you
want an assistant doing unsupervised.
"""

from typing import Dict

try:
    import browser_cookie3

    HAS_BROWSER_COOKIE3 = True
except ImportError:
    HAS_BROWSER_COOKIE3 = False


class CookieTools:
    """Read-only access to locally stored browser cookies."""

    def get_cookies(self, domain: str, browser: str = "chrome") -> Dict:
        """Get cookies for a domain from the given browser ('chrome', 'edge', or 'firefox')."""
        if not HAS_BROWSER_COOKIE3:
            return {"error": "browser_cookie3 not installed - run: pip install browser_cookie3"}
        try:
            browser = browser.lower()
            loaders = {
                "chrome": browser_cookie3.chrome,
                "edge": browser_cookie3.edge,
                "firefox": browser_cookie3.firefox,
            }
            if browser not in loaders:
                return {"error": f"Unknown browser '{browser}' - use chrome, edge, or firefox"}

            cj = loaders[browser](domain_name=domain)
            cookies = [
                {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path, "expires": c.expires} for c in cj
            ]
            return {"domain": domain, "browser": browser, "count": len(cookies), "cookies": cookies}
        except Exception as e:
            return {"error": str(e)}

    def get_cookie_value(self, domain: str, cookie_name: str, browser: str = "chrome") -> Dict:
        """Get a single named cookie's value for a domain."""
        result = self.get_cookies(domain, browser)
        if "error" in result:
            return result
        for c in result["cookies"]:
            if c["name"] == cookie_name:
                return {"domain": domain, "name": cookie_name, "value": c["value"]}
        return {"error": f"Cookie '{cookie_name}' not found for {domain} in {browser}"}
