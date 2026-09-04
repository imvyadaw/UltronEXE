"""
Price Tag
=========
EYES/object_finder.py finds *where* a blob is, never *what* it is - it
has no label better than "object". This module doesn't try to close
that gap with guessing; instead it's a small, user-taught (name ->
price) table, the same "storage layer built independent of the hard
part" split face_memory.py already drew between naming and pixels.
tag_box() pairs a *user-supplied* name for a specific box with
whatever price that name is already taught, so drawing a price tag is
always the user (or a caller acting on the user's behalf) saying "this
box is the coffee grinder", never this module inferring it.

Storage is a flat sqlite table, deliberately simpler than
long_term.py's confidence/reinforcement machinery - a price either is
or isn't known, and the most recent teach_price() call always wins;
there's no reinforcement story that makes sense for a price the way it
does for a repeated conversational fact.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import cv2

    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "price_tags.db"
TAG_COLOR = (40, 180, 220)  # BGR


class PriceTag:
    """User-taught (name -> price) lookup + box overlay. Use get_price_tag()."""

    def __init__(self):
        self._db_ok = True
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS prices (
                    name TEXT PRIMARY KEY, price REAL, currency TEXT, taught_at REAL
                )""")
            self._conn.commit()
        except Exception:
            self._db_ok = False
            self._fallback: Dict[str, Dict] = {}

    def teach_price(self, name: str, price: float, currency: str = "USD") -> Dict:
        now = time.time()
        if not self._db_ok:
            entry = {"name": name, "price": price, "currency": currency, "taught_at": now}
            self._fallback[name] = entry
            return entry
        self._conn.execute(
            "INSERT INTO prices (name, price, currency, taught_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET price=excluded.price, currency=excluded.currency, "
            "taught_at=excluded.taught_at",
            (name, price, currency, now),
        )
        self._conn.commit()
        return {"name": name, "price": price, "currency": currency, "taught_at": now}

    def price_for(self, name: str) -> Optional[Dict]:
        if not self._db_ok:
            return self._fallback.get(name)
        cur = self._conn.cursor()
        cur.execute("SELECT name, price, currency, taught_at FROM prices WHERE name=?", (name,))
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip(["name", "price", "currency", "taught_at"], row))

    def known_prices(self) -> List[Dict]:
        if not self._db_ok:
            return list(self._fallback.values())
        cur = self._conn.cursor()
        cur.execute("SELECT name, price, currency, taught_at FROM prices ORDER BY name")
        cols = ["name", "price", "currency", "taught_at"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def tag_box(self, frame, box: Tuple[int, int, int, int], name: str):
        """Draws `name` + its known price (or "price unknown") over
        `box` on a copy of frame. Returns the original frame unchanged
        if drawing isn't possible."""
        if not _CV2_AVAILABLE or frame is None:
            return frame
        try:
            x, y, w, h = box
            entry = self.price_for(name)
            label = f"{name}: {entry['price']:.2f} {entry['currency']}" if entry else f"{name}: price unknown"
            annotated = frame.copy()
            cv2.rectangle(annotated, (x, y), (x + w, y + h), TAG_COLOR, 2)
            cv2.putText(annotated, label, (x, max(y - 10, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, TAG_COLOR, 2)
            return annotated
        except Exception:
            return frame


_price_tag: Optional[PriceTag] = None


def get_price_tag() -> PriceTag:
    global _price_tag
    if _price_tag is None:
        _price_tag = PriceTag()
    return _price_tag
