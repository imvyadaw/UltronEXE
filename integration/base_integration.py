"""
Base integration
=================
Small shared base for integration/ clients. Every client in this package
already follows the same conventions by hand (env-var config, an
`is_configured()` readiness check, `{"success": bool, ...}` returns) -
this just centralizes the repeated bits (env var lookup with a clear
"not set up" error, a requests wrapper that turns exceptions into the
same error shape, a token-cache-file helper) so integration/twitter/,
integration/linkedin/ and integration/gmail/ (Phase 11) don't hand-roll
them again, and so older clients can adopt it incrementally without a
breaking rewrite - subclassing this is optional, not required.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional

import requests

BASE_DIR = Path(__file__).resolve().parent.parent


class BaseIntegration:
    """Optional shared base for an integration/ client.

    Subclasses set `service_name` and implement `is_configured()`; the
    helper methods below are there to use or ignore as convenient.
    """

    service_name: str = "integration"

    def _env(self, name: str, default: Optional[str] = None) -> Optional[str]:
        return os.getenv(name, default)

    def is_configured(self) -> bool:
        raise NotImplementedError

    # -- response helpers -------------------------------------------------
    @staticmethod
    def _ok(**kwargs) -> Dict:
        return {"success": True, **kwargs}

    @staticmethod
    def _err(message: str) -> Dict:
        return {"success": False, "error": message}

    def _not_configured(self, hint: str) -> Dict:
        return self._err(f"{self.service_name} is not configured - {hint}")

    # -- HTTP helper --------------------------------------------------------
    def _request(self, method: str, url: str, **kwargs) -> Dict:
        """requests.request(), but exceptions and non-2xx responses come
        back as the standard {"success": False, "error": ...} shape
        instead of raising, so callers never need a bare try/except."""
        try:
            resp = requests.request(method, url, timeout=kwargs.pop("timeout", 15), **kwargs)
            resp.raise_for_status()
            if not resp.content:
                return self._ok()
            try:
                return self._ok(data=resp.json())
            except ValueError:
                return self._ok(data=resp.text)
        except requests.HTTPError as e:
            body = e.response.text if e.response is not None else ""
            return self._err(
                f"{self.service_name} API error ({e.response.status_code if e.response is not None else '?'}): {body[:300]}"
            )
        except Exception as e:
            return self._err(str(e))

    # -- token cache helper -------------------------------------------------
    @staticmethod
    def _load_json(path: Path) -> Optional[Dict]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _save_json(path: Path, data: Dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
