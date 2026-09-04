"""
Dynamic model switcher
========================
ai/ai_router.py's own routing is deliberately simple: a fixed
fallback ORDER (Groq -> NVIDIA -> DeepSeek -> OpenRouter -> xKiro ->
Gemini), tried top to bottom until one answers. That's the right
default (predictable, cheapest-first), but it never asks "which of
the currently-configured backends is actually the best fit for THIS
turn" - it only asks "is the next one in line up".

This module is a smart, opt-in extension the assistant can consult
BEFORE calling ai_router.chat_with_tools(), built on top of two things
that already exist rather than reimplementing them:

  - ai/complexity_router.classify() - reuses the existing
    normal/complex tiering instead of inventing a second classifier.
  - ai_router.get_status()'s rolling per-backend latency/error stats -
    a backend that's been erroring a lot this session is scored down,
    without ai_router.py's own fallback-order logic needing to change.

force_backend()/clear_override() give a short-lived manual pin (e.g.
"use gemini for this" from a debugging session or a user preference)
that choose_backend() honors before falling back to its own scoring -
it never bypasses AI_MODE=cloud/local forcing in ai_router.py itself,
only picks which cloud backend AMONG the configured ones is preferred.
"""

from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger("dynamic_model_switcher")

# name -> reason, cleared by clear_override() or after _OVERRIDE_TURNS turns
_override: Optional[Dict] = None
_OVERRIDE_TURNS_DEFAULT = 1


def force_backend(name: str, turns: int = _OVERRIDE_TURNS_DEFAULT, reason: str = "manual") -> None:
    """Pin the next `turns` calls to choose_backend() to a specific
    configured backend name (e.g. "groq", "gemini"). Does not verify
    the backend is actually configured here - choose_backend() checks
    that at call time so an override for a backend whose API key gets
    removed mid-session degrades to normal scoring instead of raising."""
    global _override
    _override = {"name": name, "remaining": max(1, turns), "reason": reason}
    logger.info("Model switcher override set: %s for %d turn(s) (%s)", name, turns, reason)


def clear_override() -> None:
    global _override
    _override = None


def _tier_prefers_fast(text: str) -> bool:
    try:
        from ai.complexity_router import classify

        return classify(text) == "normal"
    except Exception:
        return False


def _score_backend(name: str, status: Dict) -> float:
    """Lower is better - simple weighted mix of observed error rate and
    average latency from ai_router.get_status()'s rolling stats. A
    backend with zero calls so far this session (unproven) is treated
    neutrally rather than penalized, so it still gets a fair shot."""
    stats = status["stats"].get("cloud", {})
    calls = stats.get("calls", 0) or 0
    if calls == 0:
        return 0.5
    errors = stats.get("errors", 0) or 0
    avg_latency = stats.get("avg_latency", 0.0) or 0.0
    error_rate = errors / calls
    # Error rate dominates the score; latency is a smaller tiebreaker
    # normalized against a generous 10s ceiling.
    return (error_rate * 0.8) + (min(avg_latency, 10.0) / 10.0) * 0.2


def choose_backend(user_message: str = "") -> Dict:
    """Returns {"backend": name_or_None, "reason": str}. A None backend
    means "no preference - let ai_router's own fallback order decide",
    which is always a safe, valid outcome (this module only narrows
    the choice, it never removes ai_router's fallback safety net)."""
    global _override

    from ai.ai_router import get_router

    router = get_router()
    configured = [n for n, _ in router._get_cloud_backends()]

    if _override and _override["remaining"] > 0:
        name = _override["name"]
        _override["remaining"] -= 1
        if _override["remaining"] <= 0:
            _override = None
        if name in configured:
            return {"backend": name, "reason": f"override ({_override or 'last use'})"}
        logger.info("Override backend %s not currently configured - falling through to scoring.", name)

    if not configured:
        return {"backend": None, "reason": "no cloud backends configured"}

    if user_message and _tier_prefers_fast(user_message) and "groq" in configured:
        # Groq is the only backend with a fast-streamed tier
        # (chat_fast_stream) - casual/simple turns lean toward it so
        # the fast-tier path in ai_router.chat_fast_stream actually
        # gets used, matching complexity_router's own intent.
        return {"backend": "groq", "reason": "fast-tier eligible (complexity_router: normal)"}

    status = router.get_status()
    scored = sorted(configured, key=lambda n: _score_backend(n, status))
    best = scored[0]
    return {"backend": best, "reason": f"lowest error/latency score this session ({len(configured)} candidates)"}
