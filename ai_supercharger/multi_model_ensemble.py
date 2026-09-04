"""
Multi-model ensemble
=====================
ai/ai_router.py's chat_with_tools() picks ONE backend per turn (first
one in fallback order that answers). This module is for the opposite
case: turns where getting the same question answered by several
already-configured cloud backends and combining them is worth the
extra latency/cost - factual questions, "are you sure", or anything
explicitly asked for a "double-checked"/"best of" answer.

Two combination strategies, both operating on plain completions
(ai_router.complete() - no tools, no shared chat history mutation)
so this never interferes with the live conversation the way calling
chat_with_tools() from multiple backends at once would:

  - "vote": ask a judge model (the fastest backend that answered) to
    pick the single best reply out of the candidates, given the
    original question. Cheap and usually the right call for factual
    Q&A where one candidate is just more correct than the others.
  - "merge": ask a judge model to synthesize ONE answer that combines
    whatever each candidate got right, dropping contradictions.
    Better for open-ended/creative prompts where no single candidate
    is strictly best.

Every candidate call runs in its own thread (same ThreadPoolExecutor
pattern as ai/tool_runtime.py's run_tools_parallel) so N backends
costs roughly one backend's worth of wall-clock time, not N.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("multi_model_ensemble")

_DEFAULT_TIMEOUT_SECONDS = 25
_MAX_CANDIDATES = 4


def _collect_candidates(
    prompt: str, temperature: float, max_tokens: int, backend_names: Optional[List[str]]
) -> List[Dict]:
    """Fan the same prompt out to every configured cloud backend (or the
    caller-provided subset) in parallel. Returns a list of
    {"backend": name, "text": str} for every backend that answered -
    a backend that errors or times out is silently dropped, same
    "never let one bad backend break the turn" spirit as ai_router.py."""
    from ai.ai_router import get_router

    router = get_router()
    backends = router._get_cloud_backends()
    if backend_names:
        wanted = set(backend_names)
        backends = [(n, c) for n, c in backends if n in wanted]
    backends = backends[:_MAX_CANDIDATES]

    if not backends:
        return []

    def _call_one(name_client):
        name, client = name_client
        try:
            text = client.complete_once(prompt, temperature=temperature, max_tokens=max_tokens)
            return {"backend": name, "text": text}
        except Exception as e:
            logger.info("ensemble candidate %s failed: %s", name, e)
            return None

    results = []
    with ThreadPoolExecutor(max_workers=len(backends)) as executor:
        futures = {executor.submit(_call_one, b): b[0] for b in backends}
        for future in as_completed(futures, timeout=_DEFAULT_TIMEOUT_SECONDS):
            try:
                res = future.result()
            except Exception as e:
                logger.info("ensemble candidate %s raised: %s", futures[future], e)
                res = None
            if res is not None:
                results.append(res)
    return results


def _judge(prompt: str, candidates: List[Dict], strategy: str) -> str:
    """A single extra completion (whichever backend is configured first,
    via ai_router.complete()'s own fallback chain) that either picks
    the best candidate or merges them into one answer."""
    from ai.ai_router import get_router

    numbered = "\n\n".join(f"Candidate {i + 1} ({c['backend']}):\n{c['text']}" for i, c in enumerate(candidates))
    if strategy == "merge":
        judge_prompt = (
            "You are combining multiple AI answers to the same question into "
            "ONE best answer. Keep what is correct and consistent across "
            "candidates, drop anything contradictory or wrong, and do not "
            "mention that this was combined from multiple sources.\n\n"
            f"Original question:\n{prompt}\n\n{numbered}\n\n"
            "Write the single combined answer now:"
        )
    else:
        judge_prompt = (
            "You are picking the single best answer to a question out of "
            "several AI-generated candidates. Reply with ONLY the text of "
            "the best candidate, verbatim, with no commentary, no candidate "
            "number, and no preamble.\n\n"
            f"Original question:\n{prompt}\n\n{numbered}\n\nBest candidate:"
        )
    return get_router().complete(judge_prompt, temperature=0.2, max_tokens=800)


def get_ensemble_response(
    prompt: str,
    strategy: str = "vote",
    backend_names: Optional[List[str]] = None,
    temperature: float = 0.4,
    max_tokens: int = 600,
) -> Dict:
    """Main entry point. strategy is "vote" (pick best) or "merge"
    (synthesize). Returns:
        {
          "success": bool,
          "answer": str,
          "strategy": str,
          "candidates": [{"backend": ..., "text": ...}, ...],
        }
    Falls back to a single ai_router.complete() call (no ensembling)
    if fewer than 2 backends actually answered - there is nothing
    meaningful to vote on or merge with just one candidate."""
    if strategy not in ("vote", "merge"):
        strategy = "vote"

    candidates = _collect_candidates(prompt, temperature, max_tokens, backend_names)

    if len(candidates) == 0:
        from ai.ai_router import get_router

        try:
            answer = get_router().complete(prompt, temperature=temperature, max_tokens=max_tokens)
            return {"success": True, "answer": answer, "strategy": "single_fallback", "candidates": []}
        except Exception as e:
            return {"success": False, "answer": "", "strategy": strategy, "candidates": [], "error": str(e)}

    if len(candidates) == 1:
        return {
            "success": True,
            "answer": candidates[0]["text"],
            "strategy": "single_candidate",
            "candidates": candidates,
        }

    try:
        answer = _judge(prompt, candidates, strategy)
    except Exception as e:
        logger.info("ensemble judge failed, falling back to first candidate: %s", e)
        answer = candidates[0]["text"]

    return {"success": True, "answer": answer, "strategy": strategy, "candidates": candidates}
