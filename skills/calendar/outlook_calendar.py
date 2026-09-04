"""
Outlook Calendar skill
======================
Create, list, update, delete events on Outlook / Microsoft 365 calendars
via Microsoft Graph, reusing the same MSAL device-code auth pattern as
skills/email/outlook.py (with the Calendars.ReadWrite scope added).
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

import requests

try:
    import msal

    HAS_MSAL = True
except ImportError:
    HAS_MSAL = False

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GRAPH_URL = "https://graph.microsoft.com/v1.0"
SCOPES = ["Calendars.ReadWrite"]


class OutlookCalendarClient:
    """Wrapper around Microsoft Graph calendar endpoints."""

    def __init__(
        self, client_id: Optional[str] = None, tenant_id: Optional[str] = None, cache_path: Optional[str] = None
    ):
        self.client_id = client_id or os.getenv("OUTLOOK_CLIENT_ID")
        self.tenant_id = tenant_id or os.getenv("OUTLOOK_TENANT_ID", "common")
        self.cache_path = Path(
            cache_path
            or os.getenv("OUTLOOK_CAL_TOKEN_CACHE", BASE_DIR / "storage" / "cache" / "outlook_cal_token_cache.bin")
        )

    def is_configured(self) -> bool:
        return HAS_MSAL and bool(self.client_id)

    def _get_token(self) -> str:
        if not HAS_MSAL:
            raise RuntimeError("Outlook Calendar support needs: pip install msal")
        if not self.client_id:
            raise RuntimeError("Set OUTLOOK_CLIENT_ID in .env")

        cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            cache.deserialize(self.cache_path.read_text())

        app = msal.PublicClientApplication(
            self.client_id, authority=f"https://login.microsoftonline.com/{self.tenant_id}", token_cache=cache
        )
        accounts = app.get_accounts()
        result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
        if not result:
            flow = app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise RuntimeError(f"Device flow failed: {flow}")
            print(flow["message"])
            result = app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Auth failed: {result.get('error_description', result)}")

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(cache.serialize())
        return result["access_token"]

    def _headers(self) -> Dict:
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    # -- CRUD -----------------------------------------------------------
    def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
        attendees: Optional[List[str]] = None,
        timezone: str = "India Standard Time",
    ) -> Dict:
        try:
            payload = {
                "subject": title,
                "body": {"contentType": "Text", "content": description},
                "start": {"dateTime": start_time, "timeZone": timezone},
                "end": {"dateTime": end_time, "timeZone": timezone},
                "location": {"displayName": location},
            }
            if attendees:
                payload["attendees"] = [{"emailAddress": {"address": a}, "type": "required"} for a in attendees]
            resp = requests.post(f"{GRAPH_URL}/me/events", headers=self._headers(), json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return {"success": True, "event_id": data["id"], "link": data.get("webLink")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_events(self, max_results: int = 10) -> Dict:
        try:
            params = {"$top": max_results, "$orderby": "start/dateTime"}
            resp = requests.get(f"{GRAPH_URL}/me/events", headers=self._headers(), params=params, timeout=15)
            resp.raise_for_status()
            events = [
                {
                    "id": e["id"],
                    "title": e.get("subject", "(no title)"),
                    "start": e["start"]["dateTime"],
                    "end": e["end"]["dateTime"],
                    "location": e.get("location", {}).get("displayName", ""),
                }
                for e in resp.json().get("value", [])
            ]
            return {"success": True, "count": len(events), "events": events}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_event(self, event_id: str, **fields) -> Dict:
        try:
            payload = {}
            if "title" in fields:
                payload["subject"] = fields["title"]
            if "description" in fields:
                payload["body"] = {"contentType": "Text", "content": fields["description"]}
            if "start_time" in fields:
                payload["start"] = {
                    "dateTime": fields["start_time"],
                    "timeZone": fields.get("timezone", "India Standard Time"),
                }
            if "end_time" in fields:
                payload["end"] = {
                    "dateTime": fields["end_time"],
                    "timeZone": fields.get("timezone", "India Standard Time"),
                }
            if "location" in fields:
                payload["location"] = {"displayName": fields["location"]}

            resp = requests.patch(
                f"{GRAPH_URL}/me/events/{event_id}", headers=self._headers(), json=payload, timeout=15
            )
            resp.raise_for_status()
            return {"success": True, "event_id": event_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_event(self, event_id: str) -> Dict:
        try:
            resp = requests.delete(f"{GRAPH_URL}/me/events/{event_id}", headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return {"success": True, "event_id": event_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
