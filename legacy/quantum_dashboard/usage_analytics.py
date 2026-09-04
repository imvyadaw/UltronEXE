"""
usage_analytics.py
====================
Tracks how ULTRON itself is being used - which commands/skills fire,
how often, how long they take to respond, and session length. Local
SQLite store, so "what did I ask ULTRON to do most this month" has an
actual answer.

Dependencies: none beyond stdlib
"""

from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("ultron.usage_analytics")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS command_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill TEXT NOT NULL,
    command TEXT,
    duration_ms REAL,
    success INTEGER,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skill ON command_events(skill);
CREATE INDEX IF NOT EXISTS idx_timestamp ON command_events(timestamp);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    ended_at REAL
);
"""


@dataclass
class SkillUsage:
    skill: str
    call_count: int
    avg_duration_ms: float
    success_rate: float


class UsageAnalytics:
    def __init__(self, db_path: str = "./ultron_usage.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()
        self._session_id: Optional[int] = None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ------------------------------------------------------------ sessions
    def start_session(self) -> int:
        with closing(self._connect()) as conn:
            cur = conn.execute("INSERT INTO sessions (started_at) VALUES (?)", (time.time(),))
            conn.commit()
            self._session_id = cur.lastrowid
        return self._session_id

    def end_session(self):
        if self._session_id is None:
            return
        with closing(self._connect()) as conn:
            conn.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (time.time(), self._session_id))
            conn.commit()
        self._session_id = None

    # -------------------------------------------------------------- events
    def log_command(
        self, skill: str, command: Optional[str] = None, duration_ms: Optional[float] = None, success: bool = True
    ):
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO command_events (skill, command, duration_ms, success, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (skill, command, duration_ms, int(success), time.time()),
            )
            conn.commit()
        logger.debug("Logged usage: skill=%s success=%s duration=%sms", skill, success, duration_ms)

    # ------------------------------------------------------------ queries
    def top_skills(self, since_days: Optional[int] = None, limit: int = 10) -> List[SkillUsage]:
        since_ts = time.time() - since_days * 86400 if since_days else 0
        query = """
            SELECT skill,
                   COUNT(*) as calls,
                   AVG(duration_ms) as avg_dur,
                   AVG(success) as success_rate
            FROM command_events
            WHERE timestamp >= ?
            GROUP BY skill
            ORDER BY calls DESC
            LIMIT ?
        """
        with closing(self._connect()) as conn:
            rows = conn.execute(query, (since_ts, limit)).fetchall()
        return [
            SkillUsage(
                skill=r[0],
                call_count=r[1],
                avg_duration_ms=round(r[2] or 0, 1),
                success_rate=round((r[3] or 0) * 100, 1),
            )
            for r in rows
        ]

    def total_commands(self, since_days: Optional[int] = None) -> int:
        since_ts = time.time() - since_days * 86400 if since_days else 0
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT COUNT(*) FROM command_events WHERE timestamp >= ?", (since_ts,)).fetchone()
        return row[0] if row else 0

    def average_session_minutes(self) -> float:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT started_at, ended_at FROM sessions WHERE ended_at IS NOT NULL").fetchall()
        if not rows:
            return 0.0
        durations = [(end - start) / 60 for start, end in rows]
        return round(sum(durations) / len(durations), 1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ua = UsageAnalytics()
    ua.start_session()
    ua.log_command("voice.wake", duration_ms=120, success=True)
    ua.log_command("browser.open_tab", command="open youtube", duration_ms=340, success=True)
    ua.end_session()
    print(ua.top_skills())
    print("Total commands:", ua.total_commands())
