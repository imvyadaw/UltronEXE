"""
Deliberative Reasoning Engine
==============================
Upgrade over ai/chain_of_thought.py's decompose -> answer -> synthesize
pipeline. Three concrete additions, each a known technique from
reasoning-LLM research adapted to Ultron's existing ai_router - not a
rename, an actual behavioral upgrade:

1. Cross-referenced sub-answering - chain_of_thought.py answers each
   sub-question in isolation (no visibility into siblings), which lets
   contradictory sub-answers slip straight through to synthesis. Here,
   each sub-question is answered with the prior sub-Q&A pairs in its
   prompt, so answer N can see (and is asked to flag contradictions
   against) answers 1..N-1.

2. Self-consistency synthesis (Wang et al., 2022) - instead of one
   synthesis call, run `consistency_paths` independent synthesis calls
   in parallel (ai_router.complete() is a stateless single-shot call -
   see its own docstring: "no shared conversation history" - so it's
   safe to fan out over threads). Candidate answers are clustered by
   token overlap; if they substantially agree, that's the answer at
   high confidence. If they diverge, an adjudicator pass is shown all
   candidates and picks/merges the best-supported one at lower
   confidence - divergence is signal, not noise to discard.

3. Critique-and-revise - mirrors cognitive_core/self_critique_agent.py's
   pattern (fails closed, one extra round-trip, never raises) but checks
   the *reasoning* itself rather than an execution report: unsupported
   claims, contradictions between findings, and logical gaps between
   findings and the final answer. One bounded revision pass if the
   critique finds a real problem.

Confidence is not decoration: it starts from step 2's agreement_ratio
and is nudged down if step 3 found a real problem the revision didn't
fully resolve. Downstream callers (decision_engine.py, autonomous
loops) can use it exactly the way confidence_engine's decision_gate.py
already uses action-confidence - as a real signal for auto-proceed vs
ask-the-user, extended here to conclusions instead of actions.

Return shape is backward-compatible with ai/chain_of_thought.py's
("final_answer", "trace", no "error" key on success) with new fields
added on top (confidence, agreement_ratio, critique, revised,
candidate_answers) - reasoning_engine.py tries this first and falls
back to the old single-path engine on any failure, so this is purely
additive; nothing existing is removed or changed.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple

try:
    from core.logger import get_logger

    logger = get_logger("ultron.deliberative_reasoning")
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("ultron.deliberative_reasoning")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

try:
    from ai.ai_router import get_router as _default_router_factory
except Exception as exc:  # pragma: no cover
    _default_router_factory = None
    logger.warning(f"[deliberative_reasoning] ai.ai_router unavailable: {exc}")

DECOMPOSE_PROMPT = """Break the following question or problem into 2-5 smaller
sub-questions that, once answered, make the original easy to answer.
Respond with ONLY a JSON array of strings, nothing else.

Question: {question}"""

ANSWER_SUBQUESTION_PROMPT = """Answer this sub-question concisely (2-4 sentences), as
one step of reasoning toward a larger question. Use the prior findings below if
they're relevant, and explicitly say so if this answer contradicts one of them.

Larger question: {question}

Prior findings:
{prior}

Sub-question: {subquestion}"""

SYNTHESIZE_PROMPT = """You reasoned through this question step by step. Combine the
findings below into one clear, direct final answer. Base the answer only on the
findings given - don't introduce new claims they don't support.

Question: {question}

Findings:
{findings}

Final answer:"""

ADJUDICATE_PROMPT = """You produced {n} independent candidate answers to the same
question. They disagree in some way. Pick the one best supported by the findings
below, or merge them into a single answer that resolves the disagreement.
Respond with ONLY the final answer text, nothing else.

Question: {question}

Findings:
{findings}

Candidates:
{candidates}"""

CRITIQUE_PROMPT = """Judge this reasoning chain honestly. Look specifically for:
unsupported claims (stated as fact but not backed by a finding below),
contradictions between findings, and logical gaps between the findings and the
final answer.

Respond with ONLY a JSON object, nothing else - no prose, no markdown fences:
{{"has_problem": true or false, "issue": "one sentence or empty string"}}

Question: {question}

Findings:
{findings}

Final answer: {answer}"""

REVISE_PROMPT = """Your previous final answer to this question had a flagged
problem. Produce a corrected final answer that fixes it, using only the findings
below.

Question: {question}

Findings:
{findings}

Previous answer: {answer}
Problem: {issue}

Corrected final answer:"""


class DeliberativeReasoner:
    """Decompose -> cross-referenced answer -> self-consistent synthesis ->
    critique -> bounded revision, with a confidence score and full trace.

    `router_factory` is injectable (defaults to ai.ai_router.get_router) so
    this can be unit-tested / benchmarked with a stub router that doesn't
    need network access - see tests/benchmark_deliberative_reasoning.py.
    """

    def __init__(self, router_factory: Optional[Callable[[], object]] = None):
        self._router_factory = router_factory or _default_router_factory
        if self._router_factory is None:
            raise RuntimeError("no router_factory available (ai.ai_router import failed and none was injected)")

    def _complete(self, prompt: str, **kw) -> str:
        return self._router_factory().complete(prompt, **kw)

    def run(self, question: str, max_subquestions: int = 5, consistency_paths: int = 3) -> Dict:
        trace: List[Dict] = []
        try:
            subquestions = self._decompose(question, max_subquestions)
            trace.append({"step": "decompose", "subquestions": subquestions})

            findings: List[Tuple[str, str]] = []
            for sq in subquestions:
                prior_text = "\n".join(f"- {q}: {a}" for q, a in findings) or "(none yet)"
                answer = self._complete(
                    ANSWER_SUBQUESTION_PROMPT.format(question=question, subquestion=sq, prior=prior_text),
                    temperature=0.3,
                    max_tokens=250,
                )
                answer = (answer or "").strip()
                findings.append((sq, answer))
                trace.append({"step": "answer_subquestion", "subquestion": sq, "answer": answer})

            findings_text = "\n".join(f"{i + 1}. {q}: {a}" for i, (q, a) in enumerate(findings)) or "(no findings)"

            candidates = self._synthesize_consistency(question, findings_text, max(1, consistency_paths))
            trace.append({"step": "self_consistency", "candidates": candidates})

            final_answer, agreement_ratio = self._resolve_candidates(question, findings_text, candidates)
            trace.append({"step": "resolve", "agreement_ratio": agreement_ratio, "answer": final_answer})

            critique = self._critique(question, findings_text, final_answer)
            trace.append({"step": "critique", **critique})

            revised = False
            if critique.get("has_problem"):
                revised_answer = self._revise(question, findings_text, final_answer, critique.get("issue", ""))
                if revised_answer:
                    final_answer = revised_answer
                    revised = True
                    trace.append({"step": "revise", "answer": final_answer})

            confidence = self._score_confidence(agreement_ratio, critique, revised)

            return {
                "question": question,
                "final_answer": final_answer,
                "confidence": confidence,
                "agreement_ratio": round(agreement_ratio, 2),
                "critique": critique,
                "revised": revised,
                "candidate_answers": candidates,
                "trace": trace,
                "source": "deliberative",
            }
        except Exception as e:
            logger.info(f"[deliberative_reasoning] run() failed: {e}")
            return {"error": str(e), "trace": trace}

    # -- pipeline stages -------------------------------------------------

    def _decompose(self, question: str, max_subquestions: int) -> List[str]:
        text = self._complete(DECOMPOSE_PROMPT.format(question=question), temperature=0.3, max_tokens=300)
        subs: List[str] = []
        try:
            parsed = json.loads(text)
            subs = [str(s).strip() for s in parsed if str(s).strip()]
        except Exception:
            subs = [line.strip("-*\t ") for line in (text or "").splitlines() if line.strip()]
        subs = subs[:max_subquestions] or [question]
        return subs

    def _synthesize_consistency(self, question: str, findings_text: str, n: int) -> List[str]:
        prompt = SYNTHESIZE_PROMPT.format(question=question, findings=findings_text)
        results: List[Optional[str]] = [None] * n
        with ThreadPoolExecutor(max_workers=min(n, 5)) as pool:
            futs = {pool.submit(self._complete, prompt, temperature=0.6, max_tokens=250): i for i in range(n)}
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    results[i] = (fut.result() or "").strip()
                except Exception as e:
                    logger.info(f"[deliberative_reasoning] consistency path {i} failed: {e}")
                    results[i] = None
        return [r for r in results if r]

    def _resolve_candidates(self, question: str, findings_text: str, candidates: List[str]) -> Tuple[str, float]:
        if not candidates:
            return "", 0.0

        def norm(s: str) -> set:
            return set(re.findall(r"[a-z0-9]+", s.lower()))

        groups: List[List[str]] = []
        for c in candidates:
            ctoks = norm(c)
            placed = False
            for g in groups:
                gtoks = norm(g[0])
                union = len(ctoks | gtoks) or 1
                overlap = len(ctoks & gtoks) / union
                if overlap >= 0.5:
                    g.append(c)
                    placed = True
                    break
            if not placed:
                groups.append([c])
        groups.sort(key=len, reverse=True)
        agreement_ratio = len(groups[0]) / len(candidates)

        if len(groups) == 1:
            return groups[0][0], agreement_ratio

        candidates_text = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(candidates))
        try:
            adjudicated = self._complete(
                ADJUDICATE_PROMPT.format(
                    n=len(candidates), question=question, findings=findings_text, candidates=candidates_text
                ),
                temperature=0.2,
                max_tokens=250,
            )
            return (adjudicated or groups[0][0]).strip(), agreement_ratio
        except Exception as e:
            logger.info(f"[deliberative_reasoning] adjudication failed, using majority cluster: {e}")
            return groups[0][0], agreement_ratio

    def _critique(self, question: str, findings_text: str, answer: str) -> Dict:
        try:
            text = self._complete(
                CRITIQUE_PROMPT.format(question=question, findings=findings_text, answer=answer),
                temperature=0.1,
                max_tokens=200,
            )
            text = (text or "").strip().strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
            parsed = json.loads(text)
            return {
                "has_problem": bool(parsed.get("has_problem", False)),
                "issue": str(parsed.get("issue", "")).strip(),
            }
        except Exception as e:
            logger.info(f"[deliberative_reasoning] critique failed, assuming no problem: {e}")
            return {"has_problem": False, "issue": ""}

    def _revise(self, question: str, findings_text: str, answer: str, issue: str) -> str:
        try:
            text = self._complete(
                REVISE_PROMPT.format(question=question, findings=findings_text, answer=answer, issue=issue),
                temperature=0.2,
                max_tokens=300,
            )
            return (text or "").strip()
        except Exception as e:
            logger.info(f"[deliberative_reasoning] revision failed, keeping prior answer: {e}")
            return ""

    def _score_confidence(self, agreement_ratio: float, critique: Dict, revised: bool) -> float:
        score = 0.5 + 0.5 * agreement_ratio  # pure self-consistency band: 0.5 .. 1.0
        if critique.get("has_problem"):
            score -= 0.15 if revised else 0.3
        return round(max(0.05, min(1.0, score)), 2)


_instance: Optional[DeliberativeReasoner] = None


def get_deliberative_reasoner() -> DeliberativeReasoner:
    """Process-wide DeliberativeReasoner singleton (uses the real ai_router)."""
    global _instance
    if _instance is None:
        _instance = DeliberativeReasoner()
    return _instance
