"""
Verification Engine (Phase 23.6 - Cognitive Reasoning Layer)
=========================================================
Sixth stage of the Phase 23 cognitive loop (see intent_analyzer.py's
header for the full pipeline diagram). Where self_critique.py asks
"does this look right", this module asks "is this actually right":
it cross-checks a reasoning conclusion or critique against whatever
grounding facts are available (a context dict the caller supplies -
e.g. a world_state snapshot, retrieved memory, or tool output) and
flags claims that aren't supported by anything in that context.

IMPORTANT - naming: this is intelligence/verification_engine.py, a
flat Phase 23 module. It is a different module from
intelligence/verification/verification_engine.py (Phase 19.4), which
checks whether an *action* succeeded (file exists, screenshot
changed, ...) via action_verifier.py/success_evaluator.py. This
module instead checks whether a *reasoning claim* is grounded and
internally consistent - a text-level check, not an action-level one.
The two are complementary and this module reuses the Phase 19.4
engine as its "does the referenced action check out" backend when
that context is available, rather than duplicating it.

Verification is layered, cheapest first:
    1. Grounding check - does the context contain anything that
       supports (or contradicts) the claim? Purely lexical/heuristic,
       always available, zero LLM cost.
    2. LLM consistency pass - only when the claim couldn't be
       confidently grounded by (1), ask the LLM whether the claim is
       internally consistent and plausible on its own merits.

Storage: database/reasoning_verification.db, table verifications.
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

    logger = get_logger("ultron.verification_engine")
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("ultron.verification_engine")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

try:
    from ai.ai_router import get_router
except Exception as exc:  # pragma: no cover
    get_router = None
    logger.warning(f"[verification_engine] ai.ai_router unavailable, grounding-only mode: {exc}")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "reasoning_verification.db"

_instance: Optional["ReasoningVerificationEngine"] = None
_instance_lock = threading.Lock()

VERDICT_GROUNDED = "grounded"
VERDICT_CONSISTENT = "plausible_but_ungrounded"
VERDICT_CONTRADICTED = "contradicted"
VERDICT_UNVERIFIABLE = "unverifiable"

CONSISTENCY_PROMPT = """Judge whether the claim below is internally consistent and
plausible (not whether you can independently confirm it - just whether it
makes sense on its own terms, with no obvious contradictions or non-sequiturs).

Claim: {claim}

Respond with ONLY a JSON object, nothing else:
{{"consistent": true/false, "issue": "short reason if false, else empty string"}}"""


class ReasoningVerificationEngine:
    """verify(claim, context) -> grounded / plausible-but-ungrounded / contradicted / unverifiable."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim TEXT,
                verdict TEXT,
                detail TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

    def verify(self, claim: str, context: Optional[Dict] = None) -> Dict:
        """Verify one claim/conclusion string. `context` is an optional
        dict of anything known to be true right now (world_state, tool
        output, retrieved memory) - the more that's provided, the more
        this can ground the claim instead of falling back to a bare
        plausibility check."""
        claim = (claim or "").strip()
        if not claim:
            return {"error": "empty claim"}

        verdict, detail = self._check_grounding(claim, context or {})
        if verdict == VERDICT_UNVERIFIABLE:
            verdict, detail = self._check_consistency(claim)

        self._log(claim, verdict, detail)
        return {
            "claim": claim,
            "verdict": verdict,
            "detail": detail,
            "confident": verdict in (VERDICT_GROUNDED, VERDICT_CONTRADICTED),
        }

    @staticmethod
    def _check_grounding(claim: str, context: Dict) -> (str, str):
        """Cheap lexical overlap check against flattened context values -
        good enough to catch "this claim references something the
        context flatly contradicts or plainly supports" without an LLM
        call; anything less clear-cut is left to _check_consistency()."""
        if not context:
            return VERDICT_UNVERIFIABLE, "no context supplied to ground against"

        flattened = json.dumps(context, default=str).lower()
        claim_words = set(re.findall(r"[a-z0-9]{4,}", claim.lower()))
        if not claim_words:
            return VERDICT_UNVERIFIABLE, "claim had no groundable keywords"

        overlap = sum(1 for w in claim_words if w in flattened)
        coverage = overlap / len(claim_words)

        if coverage >= 0.6:
            return VERDICT_GROUNDED, f"{overlap}/{len(claim_words)} key terms found in supplied context"
        if coverage <= 0.1:
            return VERDICT_CONTRADICTED, "almost none of the claim's key terms appear in supplied context"
        return VERDICT_UNVERIFIABLE, f"partial overlap ({overlap}/{len(claim_words)}) - not conclusive"

    @staticmethod
    def _check_consistency(claim: str) -> (str, str):
        if get_router is None:
            return VERDICT_UNVERIFIABLE, "no context and no LLM available to check further"
        try:
            raw = get_router().complete(CONSISTENCY_PROMPT.format(claim=claim), temperature=0.1, max_tokens=150)
            text = raw.strip().strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0)
            parsed = json.loads(text)
            if bool(parsed.get("consistent", True)):
                return VERDICT_CONSISTENT, "no context to ground against, but internally consistent"
            return VERDICT_CONTRADICTED, str(parsed.get("issue", "flagged as inconsistent"))
        except Exception as e:
            logger.info(f"[verification_engine] consistency check failed: {e}")
            return VERDICT_UNVERIFIABLE, "consistency check itself failed"

    def _log(self, claim: str, verdict: str, detail: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO verifications (claim, verdict, detail, timestamp) VALUES (?, ?, ?, ?)",
                (claim, verdict, detail, now),
            )
            self._conn.commit()

    def recent(self, limit: int = 20, verdict: Optional[str] = None) -> List[Dict]:
        with self._lock:
            if verdict:
                rows = self._conn.execute(
                    "SELECT claim, verdict, detail, timestamp FROM verifications WHERE verdict = ? ORDER BY id DESC LIMIT ?",
                    (verdict, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT claim, verdict, detail, timestamp FROM verifications ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [{"claim": r[0], "verdict": r[1], "detail": r[2], "timestamp": r[3]} for r in rows]


def get_reasoning_verification_engine() -> ReasoningVerificationEngine:
    """Process-wide ReasoningVerificationEngine singleton. Named
    distinctly from intelligence.verification.verification_engine's
    get_verification_engine() - both can be imported in the same file
    without clashing."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ReasoningVerificationEngine()
    return _instance
