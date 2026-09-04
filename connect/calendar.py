"""
Calendar (CONNECT)
====================
Reads and creates events via the Google Calendar REST API v3 directly
over `requests` - deliberately not the `google-api-python-client` SDK,
matching this project's consistent preference (see
PHASE_18_5_SEARCH_ENGINE's own docstring) for a plain HTTP call over a
heavy client library once the REST surface is this simple.

Takes a pre-obtained OAuth access token via GOOGLE_CALENDAR_ACCESS_TOKEN
rather than performing its own OAuth flow - this project doesn't build
OAuth flows from scratch anywhere else either, so refreshing that
token is the caller's responsibility, the same way every other
CONNECT/*.py module here expects its credential env var to already be
valid. GOOGLE_CALENDAR_ID defaults to "primary" (the signed-in user's
main calendar) and can be overridden to target a different calendar.

Same empty/failure-safe contract as the rest of this project: no
`requests`, no token, or any request failure collapse to an empty
list or {"success": False, ...} rather than an exception.
"""

import os
from typing import Dict, List, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except Exception:
    _REQUESTS_AVAILABLE = False

ACCESS_TOKEN_ENV = "GOOGLE_CALENDAR_ACCESS_TOKEN"
CALENDAR_ID_ENV = "GOOGLE_CALENDAR_ID"
DEFAULT_CALENDAR_ID = "primary"
API_BASE = "https://www.googleapis.com/calendar/v3"
DEFAULT_TIMEOUT_SECONDS = 8
DEFAULT_NUM_EVENTS = 5


class CalendarConnect:
    """Google Calendar REST API reader/writer. Use get_calendar()."""

    def is_available(self) -> bool:
        return _REQUESTS_AVAILABLE and bool(os.environ.get(ACCESS_TOKEN_ENV))

    def list_upcoming(self, num: int = DEFAULT_NUM_EVENTS) -> List[Dict]:
        """Returns up to `num` upcoming events, soonest first, as
        {"id": str, "summary": str, "start": str, "end": str}.
        `start`/`end` are whatever ISO string Google returns
        (dateTime for timed events, date for all-day ones). Empty
        list on no backend or any request failure."""
        if not self.is_available():
            return []
        calendar_id = os.environ.get(CALENDAR_ID_ENV, DEFAULT_CALENDAR_ID)
        try:
            response = requests.get(
                f"{API_BASE}/calendars/{calendar_id}/events",
                headers={"Authorization": f"Bearer {os.environ[ACCESS_TOKEN_ENV]}"},
                params={
                    "maxResults": max(1, num),
                    "orderBy": "startTime",
                    "singleEvents": "true",
                    "timeMin": self._now_iso(),
                },
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items = response.json().get("items", [])
            return [
                {
                    "id": i.get("id", ""),
                    "summary": i.get("summary", "(no title)"),
                    "start": (i.get("start") or {}).get("dateTime") or (i.get("start") or {}).get("date", ""),
                    "end": (i.get("end") or {}).get("dateTime") or (i.get("end") or {}).get("date", ""),
                }
                for i in items
            ]
        except Exception:
            return []

    def create_event(self, summary: str, start_iso: str, end_iso: str, description: str = "") -> Dict:
        """Creates a timed event. `start_iso`/`end_iso` must be full
        ISO 8601 datetimes with timezone (e.g.
        "2026-08-10T15:00:00+05:30"). Returns
        {"success": bool, "event_id": Optional[str], "error": Optional[str]}."""
        if not self.is_available():
            return {"success": False, "event_id": None, "error": "backend unavailable"}
        if not summary or not start_iso or not end_iso:
            return {"success": False, "event_id": None, "error": "summary, start_iso, and end_iso all required"}
        calendar_id = os.environ.get(CALENDAR_ID_ENV, DEFAULT_CALENDAR_ID)
        try:
            response = requests.post(
                f"{API_BASE}/calendars/{calendar_id}/events",
                headers={"Authorization": f"Bearer {os.environ[ACCESS_TOKEN_ENV]}"},
                json={
                    "summary": summary,
                    "description": description,
                    "start": {"dateTime": start_iso},
                    "end": {"dateTime": end_iso},
                },
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return {"success": True, "event_id": response.json().get("id"), "error": None}
        except Exception as exc:
            return {"success": False, "event_id": None, "error": str(exc)}

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()


_calendar: Optional[CalendarConnect] = None


def get_calendar() -> CalendarConnect:
    global _calendar
    if _calendar is None:
        _calendar = CalendarConnect()
    return _calendar
