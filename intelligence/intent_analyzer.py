"""
Intent Analyzer (Phase 23.1 - Cognitive Reasoning Layer)
=========================================================
Deep, LLM-backed read of a single user turn: primary intent, any
secondary intents riding along with it, named entities/parameters
mentioned, how complex the request actually is, how urgent it sounds,
and whether Ultron should ask a clarifying question before doing
anything else. This is the first stage of the Phase 23 cognitive loop:

    intent_analyzer -> reasoning_engine -> goal_planner -> decision_engine
                              ^                                  |
                              |                                  v
                     self_critique <---- verification_engine <---'
                              |
                              v
                     learning_engine -> model_trainer

Deliberately distinct from intelligence/intent_prediction/ (Phase 19.2):
that package predicts intent statistically from context/action history
*without* looking at what the user actually typed this turn (good for
"what will they probably do next"). This module instead reads the
literal text of the current turn with an LLM (good for "what did they
just ask for, precisely, right now") - the two are complementary, not
competing, and intelligence_core.py's process_turn() can use either or
both depending on what a caller needs.

Goes through ai.ai_router (like ai/reasoning.py, ai/planning.py) so this
also gets automatic online/offline fallback instead of hard-failing
without GROQ_API_KEY. If the LLM call fails outright, analyze() falls
back to a cheap keyword/heuristic pass so callers always get a usable
(if less precise) result rather than an exception.

Storage: database/intent_analysis.db, table intent_analyses - every
call to analyze() is logged so goal_planner.py/learning_engine.py can
look back at what was actually asked for, not just the final decision.
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

    logger = get_logger("ultron.intent_analyzer")
except Exception:  # pragma: no cover - usable outside the full Ultron repo
    import logging

    logger = logging.getLogger("ultron.intent_analyzer")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

try:
    from ai.ai_router import get_router
except Exception as exc:  # pragma: no cover
    get_router = None
    logger.warning(f"[intent_analyzer] ai.ai_router unavailable, falling back to heuristics only: {exc}")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "intent_analysis.db"

_instance: Optional["IntentAnalyzer"] = None
_instance_lock = threading.Lock()

COMPLEXITY_SIMPLE = "simple"
COMPLEXITY_MODERATE = "moderate"
COMPLEXITY_COMPLEX = "complex"

URGENCY_LOW = "low"
URGENCY_MEDIUM = "medium"
URGENCY_HIGH = "high"

ANALYSIS_PROMPT = """Analyze the user's message below and respond with ONLY a JSON object,
nothing else - no prose, no markdown code fences.

{{
  "primary_intent": "short verb-phrase, e.g. 'open an application'",
  "secondary_intents": ["any other things being asked for in the same message"],
  "entities": {{"key": "value"}},
  "complexity": "simple|moderate|complex",
  "urgency": "low|medium|high",
  "requires_clarification": true/false,
  "clarification_question": "only if requires_clarification is true, else empty string"
}}

complexity guide: "simple" = one clear action, no ambiguity. "moderate" = a
few steps or some judgement needed. "complex" = multi-step, ambiguous, or
needs real planning.

Message: {text}"""

_URGENT_WORDS = {"asap", "urgent", "now", "immediately", "hurry", "emergency"}
_MULTI_STEP_WORDS = {" and ", " then ", " after that", " also "}


class IntentAnalyzer:
    """analyze(text) -> structured intent breakdown for one user turn."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS intent_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                primary_intent TEXT,
                complexity TEXT,
                urgency TEXT,
                requires_clarification INTEGER,
                result_json TEXT,
                source TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

    # -- main entry point -----------------------------------------------------
    def analyze(self, text: str, context: Optional[Dict] = None) -> Dict:
        """Analyze one user turn. `context` is optional extra info (e.g. a
        world_state snapshot) folded into the prompt when present. Always
        returns a usable dict - degrades to a heuristic analysis rather
        than raising if the LLM path is unavailable or fails."""
        text = (text or "").strip()
        if not text:
            return {"error": "empty text"}

        result = self._analyze_with_llm(text, context) if get_router is not None else None
        source = "llm"
        if result is None:
            result = self._analyze_heuristic(text)
            source = "heuristic"

        self._log_analysis(text, result, source)
        return result

    def _analyze_with_llm(self, text: str, context: Optional[Dict]) -> Optional[Dict]:
        try:
            prompt = ANALYSIS_PROMPT.format(text=text)
            if context:
                prompt += f"\n\nRelevant context: {json.dumps(context, default=str)[:500]}"
            raw = get_router().complete(prompt, temperature=0.2, max_tokens=350)
            parsed = _parse_json_object(raw)
            if not parsed:
                return None

            return {
                "primary_intent": str(parsed.get("primary_intent", "")).strip(),
                "secondary_intents": list(parsed.get("secondary_intents") or []),
                "entities": dict(parsed.get("entities") or {}),
                "complexity": (
                    parsed.get("complexity")
                    if parsed.get("complexity") in (COMPLEXITY_SIMPLE, COMPLEXITY_MODERATE, COMPLEXITY_COMPLEX)
                    else COMPLEXITY_MODERATE
                ),
                "urgency": (
                    parsed.get("urgency")
                    if parsed.get("urgency") in (URGENCY_LOW, URGENCY_MEDIUM, URGENCY_HIGH)
                    else URGENCY_LOW
                ),
                "requires_clarification": bool(parsed.get("requires_clarification", False)),
                "clarification_question": str(parsed.get("clarification_question", "")),
            }
        except Exception as e:
            logger.info(f"[intent_analyzer] LLM analysis failed, falling back to heuristic: {e}")
            return None

    @staticmethod
    def _analyze_heuristic(text: str) -> Dict:
        """No-LLM fallback: cheap enough to always work, precise enough to
        be a usable default when the LLM path is unavailable."""
        lowered = text.lower()
        urgency = URGENCY_HIGH if any(w in lowered for w in _URGENT_WORDS) else URGENCY_LOW
        complexity = (
            COMPLEXITY_COMPLEX
            if any(w in lowered for w in _MULTI_STEP_WORDS)
            else COMPLEXITY_SIMPLE if len(text.split()) <= 6 else COMPLEXITY_MODERATE
        )
        requires_clarification = text.strip().endswith("?") and len(text.split()) <= 3
        return {
            "primary_intent": text[:80],
            "secondary_intents": [],
            "entities": {},
            "complexity": complexity,
            "urgency": urgency,
            "requires_clarification": requires_clarification,
            "clarification_question": "Could you say a bit more about what you need?" if requires_clarification else "",
        }

    def _log_analysis(self, text: str, result: Dict, source: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO intent_analyses
                   (text, primary_intent, complexity, urgency, requires_clarification, result_json, source, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    text,
                    result.get("primary_intent", ""),
                    result.get("complexity", ""),
                    result.get("urgency", ""),
                    int(bool(result.get("requires_clarification"))),
                    json.dumps(result, default=str),
                    source,
                    now,
                ),
            )
            self._conn.commit()

    # -- history ---------------------------------------------------------------
    def recent(self, limit: int = 20) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT text, primary_intent, complexity, urgency, requires_clarification, result_json, source, timestamp
                   FROM intent_analyses ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            try:
                result = json.loads(r[5])
            except Exception:
                result = {}
            out.append(
                {
                    "text": r[0],
                    "primary_intent": r[1],
                    "complexity": r[2],
                    "urgency": r[3],
                    "requires_clarification": bool(r[4]),
                    "result": result,
                    "source": r[6],
                    "timestamp": r[7],
                }
            )
        return out


def _parse_json_object(raw: str) -> Optional[Dict]:
    """Strip markdown fences / leading 'json' label then parse a JSON
    object out of an LLM response, same tolerant approach ai/planning.py
    and ai/chain_of_thought.py use for their own JSON replies."""
    text = (raw or "").strip().strip("`")
    if text.lower().startswith("json"):
        text = text[4:].strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def get_intent_analyzer() -> IntentAnalyzer:
    """Process-wide IntentAnalyzer singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = IntentAnalyzer()
    return _instance
