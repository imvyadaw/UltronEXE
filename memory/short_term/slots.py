"""memory/short_term/slots.py - addressable, TTL'd memory slots + naive
pronoun/reference resolution.

FIX NOTE (this file did not exist before): this logic used to live in a
top-level memory/short_term.py, which was silently unreachable because
Python always resolves `memory.short_term` to the memory/short_term/
*package* (this directory), never to a same-named .py file next to it.
Nothing in the codebase could ever import it, so `resolve_reference()`
("close it" after "open notepad.exe") was dead code despite being fully
written. Moved here, inside the real package, so it's actually importable.

Distinct from memory/short_term/buffer.py's ConversationBuffer (raw turn
history for the LLM) - this is about *addressable slots* ("the file I
just opened", "the place we're talking about") with a TTL, plus resolving
a pronoun back to the most recent matching slot. Exported below as
get_reference_memory() (not get_short_term_memory(), which is already
taken by buffer.py's ConversationBuffer alias - see short_term/__init__.py).
"""

import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

DEFAULT_TTL_SECONDS = 600  # 10 minutes - long enough for a task, short enough to not go stale
MAX_TURN_BUFFER = 40
REFERENCE_WORDS = {"it", "that", "this", "there", "him", "her", "them", "yeh", "woh", "yahan", "wahan"}


class ReferenceMemory:
    """Session-scoped slot memory + naive pronoun resolution.
    Use get_reference_memory(). Was previously named ShortTermMemory in
    the dead top-level memory/short_term.py."""

    def __init__(self):
        self._slots: Dict[str, Dict[str, Any]] = {}  # key -> {"value", "kind", "expires_at"}
        self._turns: Deque[Dict] = deque(maxlen=MAX_TURN_BUFFER)

    # -- slots ---------------------------------------------------------
    def remember(self, key: str, value: Any, kind: str = "generic", ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        """Store a short-lived fact/slot. `kind` lets resolve_reference()
        find "the last place-like thing" vs "the last file-like thing"
        without the caller needing to know every key name in advance."""
        self._slots[key] = {"value": value, "kind": kind, "expires_at": time.time() + ttl_seconds}

    def recall(self, key: str) -> Optional[Any]:
        self._purge_expired()
        entry = self._slots.get(key)
        return entry["value"] if entry else None

    def forget_key(self, key: str) -> bool:
        return self._slots.pop(key, None) is not None

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._slots.items() if v["expires_at"] <= now]
        for k in expired:
            del self._slots[k]

    # -- turn buffer -----------------------------------------------------
    def remember_turn(self, role: str, text: str) -> None:
        """role: "user" or "ultron". Cheap append, no analysis -
        decision_maker/intent_resolver already do the heavy lifting on
        the text itself; this just keeps the trail."""
        self._turns.append({"role": role, "text": text, "timestamp": time.time()})

    def recent_turns(self, limit: int = 10) -> List[Dict]:
        return list(self._turns)[-limit:]

    # -- reference resolution ---------------------------------------------
    def resolve_reference(self, word: str, kind: Optional[str] = None) -> Optional[Any]:
        """Naive pronoun resolution: given "it"/"that"/etc., return the
        most recently remembered slot's value, optionally filtered to a
        `kind` (e.g. resolve_reference("it", kind="file")). Not real
        coreference resolution - just recency, on purpose. Callers may
        pass any word, not just one from REFERENCE_WORDS - that set
        exists for the caller's own dispatch logic, not as a gate
        enforced here."""
        self._purge_expired()
        candidates = [(v["expires_at"], v["value"]) for v in self._slots.values() if kind is None or v["kind"] == kind]
        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[0][1]

    # -- rollup ------------------------------------------------------------
    def snapshot(self) -> Dict:
        self._purge_expired()
        context_facts = None
        try:
            from core.context import get_context

            ctx = get_context()
            context_facts = ctx.snapshot() if hasattr(ctx, "snapshot") else None
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("memory.short_term.slots.snapshot")

        return {
            "active_slots": {k: v["value"] for k, v in self._slots.items()},
            "turn_buffer_size": len(self._turns),
            "last_turn": self._turns[-1] if self._turns else None,
            "context_facts": context_facts,
        }


_reference_memory: Optional[ReferenceMemory] = None


def get_reference_memory() -> ReferenceMemory:
    """Process-wide singleton, mirroring get_conversation_buffer() /
    get_long_term_memory()."""
    global _reference_memory
    if _reference_memory is None:
        _reference_memory = ReferenceMemory()
    return _reference_memory
