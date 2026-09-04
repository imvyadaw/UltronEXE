"""
Face Memory
===========
Two independent layers on purpose: vision/face/recognition.py owns
pixels-to-name (a `face_recognition` embedding compared against
enrolled reference photos), this module owns name-to-context (when
was this person last seen, how often, and any free-text note about
them) in its own sqlite table under storage/sqlite/. Neither needs
the other to be enrolled through it - learn_face() can attach a note
to a name nobody's ever shown a camera, and recognize_live() works
against anyone enrolled purely through vision/face/recognition.py's
own enroll(), with no note or history until this module has seen
them at least once via recognize_live().

Every call into vision/ from here is best-effort and wrapped - no
`face_recognition` installed, no camera, no enrolled faces, or any
other failure all degrade to "recognition unavailable"
(recognize_live() returns None), never a crash.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "face_memory.db"


class FaceMemory:
    """Name <-> face-embedding_id associations. Use get_face_memory()."""

    def __init__(self):
        self._db_ok = True
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS people (
                    name TEXT PRIMARY KEY, embedding_id TEXT,
                    note TEXT, first_seen REAL, last_seen REAL, times_seen INTEGER
                )""")
            self._conn.commit()
        except Exception:
            self._db_ok = False
            self._fallback: Dict[str, Dict] = {}

    def learn_face(self, name: str, embedding_id: str, note: str = "") -> Dict:
        now = time.time()
        if not self._db_ok:
            entry = self._fallback.get(name, {"first_seen": now, "times_seen": 0})
            entry.update(
                {
                    "name": name,
                    "embedding_id": embedding_id,
                    "note": note,
                    "last_seen": now,
                    "times_seen": entry["times_seen"] + 1,
                }
            )
            self._fallback[name] = entry
            return entry

        self._conn.execute(
            "INSERT INTO people (name, embedding_id, note, first_seen, last_seen, times_seen) "
            "VALUES (?, ?, ?, ?, ?, 1) ON CONFLICT(name) DO UPDATE SET "
            "embedding_id=excluded.embedding_id, note=excluded.note, "
            "last_seen=excluded.last_seen, times_seen=people.times_seen + 1",
            (name, embedding_id, note, now, now),
        )
        self._conn.commit()
        return {"name": name, "embedding_id": embedding_id, "note": note, "last_seen": now}

    def recognize(self, embedding_id: str) -> Optional[str]:
        """Look up a name by embedding_id and bump last_seen. Returns
        None on no match - callers should treat that as "unknown
        person", not an error."""
        now = time.time()
        if not self._db_ok:
            for name, entry in self._fallback.items():
                if entry["embedding_id"] == embedding_id:
                    entry["last_seen"] = now
                    entry["times_seen"] += 1
                    return name
            return None

        cur = self._conn.cursor()
        cur.execute("SELECT name FROM people WHERE embedding_id=?", (embedding_id,))
        row = cur.fetchone()
        if not row:
            return None
        self._conn.execute(
            "UPDATE people SET last_seen=?, times_seen=times_seen+1 WHERE embedding_id=?",
            (now, embedding_id),
        )
        self._conn.commit()
        return row[0]

    def recognize_live(self, frame=None) -> Optional[str]:
        """Convenience path: runs vision/face/recognition.py's
        FaceRecognition.recognize() against `frame` (a PIL Image, or
        the current screen if `frame` is None) and, on a hit, bumps
        that name's last_seen/times_seen here if this module already
        has a row for them (see _bump_seen()). Any failure - no
        `face_recognition` installed, no camera, no enrolled faces,
        no face found - degrades to None ("can't recognize right
        now"), never a crash."""
        try:
            from vision.face.recognition import get_face_recognition

            result = get_face_recognition().recognize(image=frame)
            if "error" in result or not result.get("faces"):
                return None
            name = result["faces"][0]["name"]
            if name == "unknown":
                return None
            self._bump_seen(name)
            return name
        except Exception:
            return None

    def _bump_seen(self, name: str) -> None:
        """Updates last_seen/times_seen for `name` IF this module
        already has a row for them (created via learn_face()).
        recognize_live() can identify people who were only ever
        enrolled through vision/face/recognition.py's own enroll(),
        never through learn_face() here - for those this is
        deliberately a no-op rather than an auto-insert, since this
        module has no embedding_id or note to give them yet."""
        now = time.time()
        if not self._db_ok:
            if name in self._fallback:
                self._fallback[name]["last_seen"] = now
                self._fallback[name]["times_seen"] += 1
            return
        self._conn.execute(
            "UPDATE people SET last_seen=?, times_seen=times_seen+1 WHERE name=?",
            (now, name),
        )
        self._conn.commit()

    def known_people(self) -> List[Dict]:
        if not self._db_ok:
            return list(self._fallback.values())
        cur = self._conn.cursor()
        cur.execute("SELECT name, embedding_id, note, last_seen, times_seen FROM people ORDER BY last_seen DESC")
        cols = ["name", "embedding_id", "note", "last_seen", "times_seen"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # -- deletion primitive - forget.py is the only intended caller -----
    def _delete_person(self, name: str) -> bool:
        if not self._db_ok:
            return self._fallback.pop(name, None) is not None
        cur = self._conn.cursor()
        cur.execute("DELETE FROM people WHERE name=?", (name,))
        self._conn.commit()
        return cur.rowcount > 0


_face_memory: Optional[FaceMemory] = None


def get_face_memory() -> FaceMemory:
    global _face_memory
    if _face_memory is None:
        _face_memory = FaceMemory()
    return _face_memory
