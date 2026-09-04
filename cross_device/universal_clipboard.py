"""
universal_clipboard.py
====================
A small shared clipboard history that any paired device (with the
"clipboard" capability) can push to and pull from. Entries are kept
locally, capped in size and count, and content is truncated in logs
so a copy/paste of something sensitive doesn't linger in plaintext
log lines. This module does not read your OS clipboard on its own -
something on each device (or a small platform-specific hook you wire
up separately) still has to call `push()` when the user copies
something; that keeps "what counts as clipboard activity" an explicit
decision rather than a background listener.

Pure standard library.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger("ultron.universal_clipboard")

DEFAULT_STORE_PATH = "ultron_data/cross_device/clipboard.json"
MAX_ENTRY_CHARS = 20_000  # refuse to store anything larger (e.g. accidental image blob as text)
MAX_HISTORY_ENTRIES = 25
LOG_PREVIEW_CHARS = 40


@dataclass
class ClipboardEntry:
    entry_id: str
    content: str
    source_device_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    content_type: str = "text"  # "text" | "url" | "code"

    def preview(self) -> str:
        c = self.content.replace("\n", " ")
        return c[:LOG_PREVIEW_CHARS] + ("..." if len(c) > LOG_PREVIEW_CHARS else "")

    def to_dict(self) -> dict:
        return asdict(self)


class UniversalClipboard:
    """Shared clipboard history, newest-first, capped in size."""

    def __init__(self, store_path: str = DEFAULT_STORE_PATH):
        self.store_path = store_path
        self._history: List[ClipboardEntry] = []
        self._load()

    def push(self, content: str, source_device_id: str, content_type: str = "text") -> Optional[ClipboardEntry]:
        if not content:
            return None
        if len(content) > MAX_ENTRY_CHARS:
            logger.warning("Refused clipboard entry from %s: exceeds %d chars", source_device_id, MAX_ENTRY_CHARS)
            return None

        entry = ClipboardEntry(
            entry_id=f"cb_{int(time.time() * 1000)}",
            content=content,
            source_device_id=source_device_id,
            content_type=content_type,
        )
        self._history.insert(0, entry)
        self._history = self._history[:MAX_HISTORY_ENTRIES]
        self._save()
        logger.info("Clipboard push from %s: '%s'", source_device_id, entry.preview())
        return entry

    def latest(self) -> Optional[ClipboardEntry]:
        return self._history[0] if self._history else None

    def history(self, limit: int = 10) -> List[ClipboardEntry]:
        return self._history[:limit]

    def clear(self) -> None:
        self._history = []
        self._save()
        logger.info("Clipboard history cleared")

    def delete_entry(self, entry_id: str) -> bool:
        before = len(self._history)
        self._history = [e for e in self._history if e.entry_id != entry_id]
        changed = len(self._history) != before
        if changed:
            self._save()
        return changed

    # ---------------------------------------------------------- wire-format helpers
    def handle_incoming(self, device_id: str, message: dict) -> Optional[ClipboardEntry]:
        """Feed this to `websocket_server.on_message` (filtered to type=='clipboard_push')."""
        if message.get("type") != "clipboard_push":
            return None
        return self.push(message.get("content", ""), device_id, message.get("content_type", "text"))

    def _load(self) -> None:
        if not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path, "r") as f:
                raw = json.load(f)
            self._history = [ClipboardEntry(**e) for e in raw.get("history", [])]
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.error("Failed to load clipboard store: %s", exc)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        with open(self.store_path, "w") as f:
            json.dump({"history": [e.to_dict() for e in self._history]}, f, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cb = UniversalClipboard(store_path="ultron_data/cross_device/_demo_clipboard.json")
    cb.push("https://example.com/receipt", source_device_id="demo_phone", content_type="url")
    cb.push("def hello():\n    return 42", source_device_id="demo_laptop", content_type="code")
    print("Latest:", cb.latest())
    print("History:", [e.preview() for e in cb.history()])
