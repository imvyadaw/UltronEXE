"""
Emotional Analyzer (Phase 23.8 - Cognitive Reasoning Layer)
=========================================================
Eighth stage of the Phase 23 cognitive loop (see intent_analyzer.py's
header for the full pipeline diagram). decision_engine.py consults
this module's is_user_frustrated_recently() before letting a step
auto-execute, and self_critique.py/goal_planner.py can use analyze()
directly when they want a same-turn emotional read.

Layered on top of two existing, narrower modules rather than
duplicating them:
    intelligence.conversation_layer.emotional_tone - stateless,
        keyword/punctuation heuristic, one turn at a time, picks a
        *response* tone for Ultron. This module reuses it as the fast
        always-available first pass.
    memory.emotional_memory - long-term store of emotionally
        significant memories tied to specific events/people. This
        module is about short-term *trend* (the last few minutes of
        this session), not long-term memory, and doesn't touch that
        store directly.

When the LLM path is available, analyze() also asks for an emotion
label + intensity beyond emotional_tone.py's five buckets, but the
heuristic pass always runs first and its result is always the
fallback if the LLM call fails - this module never returns nothing.

Storage: database/emotional_analysis.db, table emotional_readings -
a short rolling log (not a long-term archive) that get_trend()/
is_user_frustrated_recently() read back over a recent time window.
"""

import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    from core.logger import get_logger

    logger = get_logger("ultron.emotional_analyzer")
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("ultron.emotional_analyzer")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

try:
    from ai.ai_router import get_router
except Exception as exc:  # pragma: no cover
    get_router = None
    logger.warning(f"[emotional_analyzer] ai.ai_router unavailable, heuristic-only mode: {exc}")

try:
    from intelligence.conversation_layer.emotional_tone import get_emotional_tone
except Exception as exc:  # pragma: no cover
    get_emotional_tone = None
    logger.warning(f"[emotional_analyzer] conversation_layer.emotional_tone unavailable: {exc}")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "emotional_analysis.db"

_instance: Optional["EmotionalAnalyzer"] = None
_instance_lock = threading.Lock()

_FRUSTRATION_WINDOW_SECONDS = 10 * 60  # look back 10 minutes for "recently frustrated"
_FRUSTRATION_TONES = {"frustrated", "urgent"}

EMOTION_PROMPT = """Read the emotional state behind this message. Respond with ONLY
a JSON object, nothing else - no prose, no markdown fences:
{{"emotion": "one word, e.g. frustrated/happy/anxious/neutral/excited/confused",
  "intensity": 0.0-1.0}}

Message: {text}"""


class EmotionalAnalyzer:
    """analyze(text) -> emotional read; is_user_frustrated_recently() -> bool trend check."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS emotional_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                tone TEXT,
                emotion TEXT,
                intensity REAL,
                source TEXT,
                timestamp REAL
            )""")
        self._conn.commit()
        self._tone = get_emotional_tone() if get_emotional_tone else None

    def analyze(self, text: str) -> Dict:
        """Analyze the emotional state behind `text`. Always includes
        the heuristic tone read; adds an LLM emotion/intensity read on
        top of it when available."""
        text = (text or "").strip()
        if not text:
            return {"error": "empty text"}

        tone_result = self._tone.detect(text) if self._tone else {"tone": "neutral", "confidence": 0.0, "signals": []}
        emotion, intensity, source = self._analyze_emotion_llm(text)

        result = {
            "tone": tone_result["tone"],
            "tone_confidence": tone_result["confidence"],
            "emotion": emotion,
            "intensity": intensity,
            "signals": tone_result.get("signals", []),
        }
        self._log(text, result, source)
        return result

    def _analyze_emotion_llm(self, text: str) -> (str, float, str):
        if get_router is None:
            return self._fallback_emotion(text), 0.5, "heuristic"
        try:
            raw = get_router().complete(EMOTION_PROMPT.format(text=text), temperature=0.1, max_tokens=80)
            body = raw.strip().strip("`")
            if body.lower().startswith("json"):
                body = body[4:].strip()
            match = re.search(r"\{.*\}", body, re.DOTALL)
            if match:
                body = match.group(0)
            parsed = json.loads(body)
            emotion = str(parsed.get("emotion", "neutral")).strip().lower() or "neutral"
            try:
                intensity = max(0.0, min(1.0, float(parsed.get("intensity", 0.5))))
            except (TypeError, ValueError):
                intensity = 0.5
            return emotion, intensity, "llm"
        except Exception as e:
            logger.info(f"[emotional_analyzer] LLM emotion read failed, falling back: {e}")
            return self._fallback_emotion(text), 0.5, "heuristic"

    @staticmethod
    def _fallback_emotion(text: str) -> str:
        lowered = text.lower()
        if any(w in lowered for w in ("ugh", "annoying", "frustrat", "ridiculous", "sick of")):
            return "frustrated"
        if any(w in lowered for w in ("thanks", "great", "awesome", "love", "perfect")):
            return "happy"
        if any(w in lowered for w in ("confused", "don't understand", "unclear")):
            return "confused"
        return "neutral"

    def _log(self, text: str, result: Dict, source: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO emotional_readings (text, tone, emotion, intensity, source, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (text, result["tone"], result["emotion"], result["intensity"], source, now),
            )
            self._conn.commit()

    # -- trend --------------------------------------------------------------------
    def get_trend(self, window_seconds: int = _FRUSTRATION_WINDOW_SECONDS) -> List[Dict]:
        """Emotional readings within the last `window_seconds`, oldest
        first - a lightweight session-level trend, not a long-term
        history (see memory.emotional_memory for that)."""
        cutoff = time.time() - window_seconds
        with self._lock:
            rows = self._conn.execute(
                """SELECT text, tone, emotion, intensity, timestamp FROM emotional_readings
                   WHERE timestamp >= ? ORDER BY id ASC""",
                (cutoff,),
            ).fetchall()
        return [{"text": r[0], "tone": r[1], "emotion": r[2], "intensity": r[3], "timestamp": r[4]} for r in rows]

    def is_user_frustrated_recently(self, window_seconds: int = _FRUSTRATION_WINDOW_SECONDS) -> bool:
        """True if a majority of readings in the recent window look
        frustrated/urgent - the guard decision_engine.py consults
        before letting anything auto-execute."""
        trend = self.get_trend(window_seconds)
        if not trend:
            return False
        frustrated = sum(1 for r in trend if r["tone"] in _FRUSTRATION_TONES or r["emotion"] == "frustrated")
        return frustrated / len(trend) > 0.5


def get_emotional_analyzer() -> EmotionalAnalyzer:
    """Process-wide EmotionalAnalyzer singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = EmotionalAnalyzer()
    return _instance
