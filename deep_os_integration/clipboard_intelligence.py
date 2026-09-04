"""
clipboard_intelligence.py
==========================
Watches for clipboard changes and classifies what was copied (URL,
email, phone number, code snippet, plain text) so ULTRON can offer a
useful next action - "you copied an address, want directions?",
"that looks like code, want it explained?".

Scope note: history is kept in memory only, capped at
`max_history`, and is never written to disk or sent anywhere by this
module. If you want persistence later, that should be an explicit,
separate opt-in (e.g. an encrypted local store), not a default here -
a background process that silently logs everything a user copies
(which routinely includes passwords, OTPs, personal messages) is
exactly the shape of a credential-stealing tool, so this module is
deliberately scoped to not do that.

Dependencies: pip install pyperclip
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Optional

import pyperclip

logger = logging.getLogger("ultron.clipboard_intelligence")

_PATTERNS = {
    "url": re.compile(r"^https?://\S+$", re.I),
    "email": re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$"),
    "phone": re.compile(r"^\+?[\d\s\-()]{7,15}$"),
    "code": re.compile(r"[{};]|^\s*(def |class |import |function |const |let )"),
}


@dataclass
class ClipboardEntry:
    text: str
    content_type: str
    timestamp: float


class ClipboardIntelligence:
    def __init__(self, max_history: int = 25, poll_interval: float = 0.5):
        self.max_history = max_history
        self.poll_interval = poll_interval
        self._history: Deque[ClipboardEntry] = deque(maxlen=max_history)
        self._last_value: Optional[str] = None
        self._on_change: Optional[Callable[[ClipboardEntry], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def classify(self, text: str) -> str:
        stripped = text.strip()
        for label, pattern in _PATTERNS.items():
            if pattern.search(stripped):
                return label
        return "text"

    def on_change(self, callback: Callable[[ClipboardEntry], None]):
        """Register a callback fired with the new ClipboardEntry each time
        the clipboard changes."""
        self._on_change = callback

    def _poll_loop(self):
        while self._running:
            try:
                current = pyperclip.paste()
            except Exception:
                current = None
            if current and current != self._last_value:
                self._last_value = current
                entry = ClipboardEntry(
                    text=current,
                    content_type=self.classify(current),
                    timestamp=time.time(),
                )
                self._history.append(entry)
                logger.debug("Clipboard changed: type=%s len=%d", entry.content_type, len(entry.text))
                if self._on_change:
                    self._on_change(entry)
            time.sleep(self.poll_interval)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("ClipboardIntelligence started (in-memory history, cap=%d)", self.max_history)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("ClipboardIntelligence stopped")

    def recent(self, n: int = 5):
        return list(self._history)[-n:]

    def clear_history(self):
        self._history.clear()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ci = ClipboardIntelligence()
    ci.on_change(lambda e: print(f"[{e.content_type}] {e.text[:60]}"))
    ci.start()
    print("Copy something... Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ci.stop()
