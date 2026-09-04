"""
Temporal memory
================
"When" memory, in two parts:

    1. resolve_relative_time() - turns a phrase ("today", "yesterday",
       "this week", "last week", "this month") into a (start_ts, end_ts)
       window. Small and self-contained, but every other module that
       needs "what happened X" (episodic_memory.search/recall,
       memory_consolidator's lookback window) would otherwise
       reimplement this by hand - especially worth centralizing given
       the user mixes Hinglish phrasing, so the common aliases
       ("aaj"/"kal") are recognized too.

    2. detect_patterns() - scans recent episodic_memory.py events for a
       label that recurs at a similar hour-of-day and/or day-of-week
       often enough to call it a routine ("opens VS Code most weekday
       mornings around 9"). This is what agents/health_agent.py-style
       "notice a pattern" behavior needs but memory/episodic_memory.py
       has no concept of - it only stores a flat chronological log,
       never looks for repetition within it.

Routines are stored here, and a routine's supporting episodes are
linked via memory_graph.py ("routine:<id>" --instance_of--> "episodic:<id>",
edge direction from episode to routine) so "what routine is this event
part of" and "which events make up this routine" are both one
neighbors() call, not a bespoke query.
"""

import re
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

from memory.episodic_memory import EpisodicMemory

from advanced_memory.memory_graph import get_memory_graph

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "temporal_memory.db"

MIN_OCCURRENCES = 3
DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_temporal: Optional["TemporalMemory"] = None
_lock = Lock()


def resolve_relative_time(phrase: str, now: Optional[datetime] = None) -> Dict:
    """Best-effort phrase -> (start_ts, end_ts) window. Falls back to
    {"error": ...} for anything unrecognized rather than guessing -
    callers should treat that as "ask the user to be more specific",
    not silently default to some window."""
    now = now or datetime.now()
    p = phrase.strip().lower()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    aliases = {
        "today": 0,
        "aaj": 0,
        "yesterday": -1,
        "kal": -1,
        "kal was": -1,
        "tomorrow": 1,
    }
    if p in aliases:
        offset = aliases[p]
        start = today_start + timedelta(days=offset)
        end = start + timedelta(days=1)
        return {"phrase": phrase, "start_ts": start.timestamp(), "end_ts": end.timestamp()}

    if p in ("this week",):
        start = today_start - timedelta(days=today_start.weekday())
        end = start + timedelta(days=7)
        return {"phrase": phrase, "start_ts": start.timestamp(), "end_ts": end.timestamp()}

    if p in ("last week",):
        start = today_start - timedelta(days=today_start.weekday() + 7)
        end = start + timedelta(days=7)
        return {"phrase": phrase, "start_ts": start.timestamp(), "end_ts": end.timestamp()}

    if p in ("this month",):
        start = today_start.replace(day=1)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return {"phrase": phrase, "start_ts": start.timestamp(), "end_ts": next_month.timestamp()}

    if p in ("last month",):
        this_month_start = today_start.replace(day=1)
        end = this_month_start
        start = (this_month_start - timedelta(days=1)).replace(day=1)
        return {"phrase": phrase, "start_ts": start.timestamp(), "end_ts": end.timestamp()}

    m = re.match(r"last (\d+) days?", p)
    if m:
        days = int(m.group(1))
        start = today_start - timedelta(days=days)
        return {"phrase": phrase, "start_ts": start.timestamp(), "end_ts": now.timestamp()}

    return {"error": f"Could not resolve time phrase '{phrase}'"}


class TemporalMemory:
    """Recurring-routine detection + storage. Do not construct directly
    - use get_temporal_memory()."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS routines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT,
                cadence TEXT,
                day_of_week INTEGER,
                hour INTEGER,
                occurrence_count INTEGER,
                confidence REAL,
                created_at REAL,
                updated_at REAL,
                UNIQUE(label, cadence, day_of_week, hour)
            )""")
        self._conn.commit()
        self._write_lock = Lock()

        self._episodic = EpisodicMemory()
        self._graph = get_memory_graph()

    def detect_patterns(self, lookback_days: int = 14, min_occurrences: int = MIN_OCCURRENCES) -> Dict:
        """Scans episodic events from the last `lookback_days` and
        groups them by (normalized event text, hour-of-day bucket,
        day-of-week). Anything occurring at least `min_occurrences`
        times becomes/updates a routine. Bounded by lookback_days so a
        consolidation pass (memory_consolidator.py) never has to scan
        the whole history - only the recent window worth learning from."""
        end = time.time()
        start = end - lookback_days * 86400
        events_result = self._episodic.events_between(start, end)
        if "error" in events_result:
            return events_result

        buckets: Dict = defaultdict(list)
        for ev in events_result["events"]:
            occurred = datetime.fromtimestamp(ev["occurred_at"])
            label = _normalize_label(ev["event"])
            key = (label, occurred.hour, occurred.weekday())
            buckets[key].append(ev["id"])

        created, updated = [], []
        for (label, hour, weekday), event_ids in buckets.items():
            if len(event_ids) < min_occurrences:
                continue
            confidence = min(1.0, len(event_ids) / 10.0)
            result = self._upsert_routine(label, "weekly", weekday, hour, len(event_ids), confidence)
            if result.get("created"):
                created.append(result)
            else:
                updated.append(result)
            routine_node = f"routine:{result['id']}"
            self._graph.add_node(
                routine_node, "temporal", label, metadata={"cadence": "weekly", "day_of_week": weekday, "hour": hour}
            )
            for event_id in event_ids:
                self._graph.add_edge(f"episodic:{event_id}", routine_node, "instance_of")

        return {
            "lookback_days": lookback_days,
            "created": len(created),
            "updated": len(updated),
            "routines": created + updated,
        }

    def list_routines(self, min_confidence: float = 0.0) -> Dict:
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, label, cadence, day_of_week, hour, occurrence_count, confidence FROM routines "
                "WHERE confidence >= ? ORDER BY confidence DESC",
                (min_confidence,),
            )
            rows = cur.fetchall()
            routines = [
                {
                    "id": r[0],
                    "label": r[1],
                    "cadence": r[2],
                    "day_of_week": DAY_NAMES[r[3]] if r[3] is not None else None,
                    "hour": r[4],
                    "occurrence_count": r[5],
                    "confidence": r[6],
                }
                for r in rows
            ]
            return {"count": len(routines), "routines": routines}
        except Exception as e:
            return {"error": str(e)}

    def routine_events(self, routine_id: int) -> Dict:
        """Every episodic event this routine was built from."""
        nb = self._graph.neighbors(f"routine:{routine_id}", direction="in")
        if "error" in nb:
            return nb
        event_ids = [n["node_id"].split(":", 1)[1] for n in nb["neighbors"] if n["node_id"].startswith("episodic:")]
        return {"routine_id": routine_id, "count": len(event_ids), "event_ids": event_ids}

    def what_usually_happens(self, hour: int, weekday: Optional[int] = None, min_confidence: float = 0.3) -> Dict:
        """Routines whose time window matches `hour` (and `weekday` if
        given) - "what do I usually do around now"."""
        try:
            cur = self._conn.cursor()
            if weekday is not None:
                cur.execute(
                    "SELECT id, label, confidence FROM routines WHERE hour = ? AND day_of_week = ? AND confidence >= ? ORDER BY confidence DESC",
                    (hour, weekday, min_confidence),
                )
            else:
                cur.execute(
                    "SELECT id, label, confidence FROM routines WHERE hour = ? AND confidence >= ? ORDER BY confidence DESC",
                    (hour, min_confidence),
                )
            rows = cur.fetchall()
            return {
                "hour": hour,
                "weekday": weekday,
                "count": len(rows),
                "routines": [{"id": r[0], "label": r[1], "confidence": r[2]} for r in rows],
            }
        except Exception as e:
            return {"error": str(e)}

    # -- internal --------------------------------------------------------------
    def _upsert_routine(
        self, label: str, cadence: str, day_of_week: int, hour: int, occurrence_count: int, confidence: float
    ) -> Dict:
        now = time.time()
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id FROM routines WHERE label = ? AND cadence = ? AND day_of_week = ? AND hour = ?",
            (label, cadence, day_of_week, hour),
        )
        existing = cur.fetchone()
        with self._write_lock:
            self._conn.execute(
                "INSERT INTO routines (label, cadence, day_of_week, hour, occurrence_count, confidence, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(label, cadence, day_of_week, hour) DO UPDATE SET "
                "occurrence_count = excluded.occurrence_count, confidence = excluded.confidence, updated_at = excluded.updated_at",
                (label, cadence, day_of_week, hour, occurrence_count, confidence, now, now),
            )
            self._conn.commit()
        cur.execute(
            "SELECT id FROM routines WHERE label = ? AND cadence = ? AND day_of_week = ? AND hour = ?",
            (label, cadence, day_of_week, hour),
        )
        row = cur.fetchone()
        return {"id": row[0], "label": label, "created": existing is None}


def _normalize_label(event_text: str) -> str:
    """Lowercased, whitespace-collapsed event text - deliberately
    simple (no stemming/NLP) so two events only bucket together when
    they're genuinely near-identical, avoiding false-positive routines."""
    return re.sub(r"\s+", " ", event_text.strip().lower())


def get_temporal_memory() -> TemporalMemory:
    """Process-wide singleton, same pattern as memory_graph.get_memory_graph()."""
    global _temporal
    with _lock:
        if _temporal is None:
            _temporal = TemporalMemory()
        return _temporal
