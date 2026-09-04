"""
HTTP client
===========
Thin wrapper around `requests` used by anything in networking/ or
skills/ that needs plain HTTP(S) beyond what skills/internet/web_tools.py
already covers (that module is search + readable-text extraction
specifically; this is general-purpose GET/POST/PUT/DELETE with retry
and a shared timeout policy, for calling arbitrary APIs).

Not for browser automation (see browser/) - this never renders JS, it's
a plain request/response client.
"""

import time
from typing import Any, Dict, Optional

import requests

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 1.0

# Retry on transient failures only - a 404 or 400 retrying won't fix itself.
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class HTTPClient:
    """Small requests wrapper: JSON-friendly, retries transient failures,
    and always returns a plain dict instead of raising on HTTP errors."""

    def __init__(
        self, base_url: str = "", default_headers: Optional[Dict] = None, timeout: int = DEFAULT_TIMEOUT_SECONDS
    ):
        self.base_url = base_url.rstrip("/")
        self.default_headers = default_headers or {}
        self.timeout = timeout
        self._session = requests.Session()

    def _full_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}" if self.base_url else path

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        json_body: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> Dict:
        url = self._full_url(path)
        merged_headers = {**self.default_headers, **(headers or {})}

        last_error = ""
        for attempt in range(max_retries + 1):
            try:
                response = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=merged_headers,
                    timeout=self.timeout,
                )

                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < max_retries:
                    time.sleep(DEFAULT_RETRY_BACKOFF_SECONDS * (attempt + 1))
                    continue

                try:
                    body: Any = response.json()
                except ValueError:
                    body = response.text

                return {
                    "success": response.ok,
                    "status_code": response.status_code,
                    "body": body,
                    "url": url,
                }
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                if attempt < max_retries:
                    time.sleep(DEFAULT_RETRY_BACKOFF_SECONDS * (attempt + 1))
                    continue

        return {"error": last_error or "Request failed", "url": url}

    def get(self, path: str, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict:
        return self._request("GET", path, params=params, headers=headers)

    def post(self, path: str, json_body: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict:
        return self._request("POST", path, json_body=json_body, headers=headers)

    def put(self, path: str, json_body: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict:
        return self._request("PUT", path, json_body=json_body, headers=headers)

    def delete(self, path: str, headers: Optional[Dict] = None) -> Dict:
        return self._request("DELETE", path, headers=headers)
