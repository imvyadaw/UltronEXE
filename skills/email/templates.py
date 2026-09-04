"""
Email templates
================
Save, load, list, render and delete reusable email templates (subject + body
with {placeholder} fields), stored as JSON at storage/cache/email_templates.json.
Works with both gmail.py and outlook.py - render() returns plain strings that
can be passed straight into send_email().
"""

import json
import string
from pathlib import Path
from typing import Dict, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORE_PATH = BASE_DIR / "storage" / "cache" / "email_templates.json"

DEFAULT_TEMPLATES = {
    "meeting_request": {
        "subject": "Meeting Request: {topic}",
        "body": "Hi {name},\n\nCould we schedule a meeting to discuss {topic}? "
        "I'm available {availability}.\n\nBest,\n{sender}",
    },
    "follow_up": {
        "subject": "Following up: {topic}",
        "body": "Hi {name},\n\nJust following up on {topic}. Let me know if you need "
        "anything else from my side.\n\nBest,\n{sender}",
    },
    "thank_you": {
        "subject": "Thank you!",
        "body": "Hi {name},\n\nThank you for {reason}. It's much appreciated.\n\nBest,\n{sender}",
    },
}


class EmailTemplates:
    """CRUD + render for reusable email templates."""

    def __init__(self, store_path: Optional[str] = None):
        self.store_path = Path(store_path) if store_path else STORE_PATH
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self._save(dict(DEFAULT_TEMPLATES))

    def _load(self) -> Dict:
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, data: Dict) -> None:
        self.store_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_templates(self) -> Dict:
        templates = self._load()
        return {"success": True, "templates": list(templates.keys())}

    def get_template(self, name: str) -> Dict:
        templates = self._load()
        if name not in templates:
            return {"success": False, "error": f"Template '{name}' not found"}
        return {"success": True, "name": name, **templates[name]}

    def save_template(self, name: str, subject: str, body: str) -> Dict:
        templates = self._load()
        templates[name] = {"subject": subject, "body": body}
        self._save(templates)
        return {"success": True, "name": name, "action": "saved"}

    def delete_template(self, name: str) -> Dict:
        templates = self._load()
        if name not in templates:
            return {"success": False, "error": f"Template '{name}' not found"}
        del templates[name]
        self._save(templates)
        return {"success": True, "name": name, "action": "deleted"}

    def render(self, name: str, **fields) -> Dict:
        """Fill a template's {placeholder} fields. Missing fields become blank
        instead of raising, so a partially-filled draft is still usable."""
        templates = self._load()
        if name not in templates:
            return {"success": False, "error": f"Template '{name}' not found"}

        tpl = templates[name]
        safe_fields = _SafeDict(fields)
        subject = string.Formatter().vformat(tpl["subject"], (), safe_fields)
        body = string.Formatter().vformat(tpl["body"], (), safe_fields)
        return {"success": True, "name": name, "subject": subject, "body": body}


class _SafeDict(dict):
    """dict that leaves {missing} placeholders visible instead of KeyError-ing."""

    def __missing__(self, key):
        return "{" + key + "}"
