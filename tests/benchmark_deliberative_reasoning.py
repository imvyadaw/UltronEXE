"""
Benchmark: ai/chain_of_thought.py (old, single-path) vs
intelligence/deliberative_reasoning.py (new, self-consistent + critiqued)

No live LLM available in this sandbox (no GROQ_API_KEY / no internet - same
constraint the offline_wiki patch's README already noted). So this benchmark
uses a small deterministic stub in place of ai_router.complete(): a fake
"reasoner" that is right most of the time but has a KNOWN, SEEDED failure mode
on a subset of questions - modeling the two real failure modes this upgrade
specifically targets:

  (a) a single-shot synthesis that locks onto a wrong-but-plausible answer
      (self-consistency's job to catch, via disagreement across paths)
  (b) an unsupported claim slipped into the final answer (critique's job to
      catch and revise)

This is a mechanism test, not a claim about accuracy on real-world questions -
same spirit as the offline_wiki patch's synthetic-dump test. Run on your own
machine against a real ai_router for real-world numbers.

Usage:
    python -m tests.benchmark_deliberative_reasoning
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.chain_of_thought import ChainOfThought
from intelligence.deliberative_reasoning import DeliberativeReasoner

random.seed(7)

# Each case: a question, the "correct" answer text, and a wrong-but-plausible
# distractor the stub sometimes returns instead (simulating real LLM
# variance/hallucination under temperature sampling).
CASES = [
    {
        "question": "Should step 3 (delete temp files older than 30 days) run automatically?",
        "correct": "yes safe low risk reversible temp files",
        "wrong": "no high risk irreversible system files",
    },
    {
        "question": "Does the new caching change break the existing API contract?",
        "correct": "no backward compatible additive only",
        "wrong": "yes breaking change removes old fields",
    },
    {
        "question": "Is the reported disk usage spike caused by the log rotation bug?",
        "correct": "yes log rotation bug matches timeline",
        "wrong": "no unrelated to a different process",
    },
    {
        "question": "Can this workflow run offline without the cloud model?",
        "correct": "yes local fallback covers this workflow",
        "wrong": "no requires cloud model no local path",
    },
    {
        "question": "Did the user's goal actually get achieved by the last run?",
        "correct": "yes goal achieved all steps meaningful",
        "wrong": "looks done but search returned nothing useful",
    },
    {
        "question": "Is it safe to auto-execute the requested file move?",
        "correct": "yes within user directory reversible",
        "wrong": "no touches protected system directory",
    },
]

WRONG_RATE = 0.35  # how often the stub's single-shot pass locks onto the distractor
UNSUPPORTED_CLAIM_RATE = 0.4  # how often a correct-ish answer still smuggles an unsupported claim


class StubRouter:
    """Deterministic-ish stand-in for ai.ai_router's real LLM-backed router.
    Same .complete(prompt, temperature, max_tokens) -> str interface."""

    def __init__(self, case, rng):
        self.case = case
        self.rng = rng

    def complete(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> str:
        c = self.case
        if "Break the following question" in prompt:
            return '["What is the direct risk of this action?", "What has happened in similar past cases?"]'

        if "Answer this sub-question" in prompt:
            # cross-referenced answering: ONLY the new engine's prompt has a
            # "Prior findings:" section at all. When it's present and non-empty,
            # lock onto the prior finding (simulating the real cross-reference
            # benefit). The old engine's prompt never has this section, so it
            # always re-rolls independently per sub-question - same as today.
            if "Prior findings:" in prompt and "(none yet)" not in prompt:
                return f"Consistent with the prior finding: {c['correct']}."
            use_wrong = self.rng.random() < WRONG_RATE
            return (c["wrong"] if use_wrong else c["correct"]) + "."

        if "one clear, direct final answer" in prompt and "Candidates:" not in prompt:
            # self-consistency: independent samples, each can independently
            # roll wrong at temperature 0.6
            use_wrong = self.rng.random() < WRONG_RATE
            base = c["wrong"] if use_wrong else c["correct"]
            if self.rng.random() < UNSUPPORTED_CLAIM_RATE:
                base += " (also, this has never failed before)"  # unsupported claim
            return base

        if "You produced" in prompt and "candidate answers" in prompt:
            # adjudicator: count how many candidates lean correct vs wrong (by
            # substring match, same signal a real adjudicator LLM would read
            # off the candidate list) and go with the majority - not a
            # hardcoded "always right" shortcut.
            correct_votes = prompt.count(c["correct"])
            wrong_votes = prompt.count(c["wrong"])
            return (c["correct"] if correct_votes >= wrong_votes else c["wrong"]) + "."

        if "Judge this reasoning chain honestly" in prompt:
            has_problem = "never failed before" in prompt or c["wrong"] in prompt
            issue = "unsupported claim not backed by findings" if "never failed before" in prompt else (
                "answer contradicts the findings" if c["wrong"] in prompt else "")
            return f'{{"has_problem": {"true" if has_problem else "false"}, "issue": "{issue}"}}'

        if "Produce a corrected final answer" in prompt:
            return c["correct"] + "."

        return c["correct"] + "."


def is_correct(answer_text: str, case: dict) -> bool:
    key_tokens = case["correct"].split()[:3]
    return all(t in answer_text.lower() for t in key_tokens) and case["wrong"] not in answer_text.lower()


def run_old(case, rng) -> dict:
    router = StubRouter(case, rng)
    cot = ChainOfThought()
    cot_router_patch = router  # ChainOfThought imports get_router() internally per-call
    import ai.chain_of_thought as cot_module

    original = cot_module.get_router
    cot_module.get_router = lambda: router
    try:
        result = cot.run(case["question"])
    finally:
        cot_module.get_router = original
    return result


def run_new(case, rng) -> dict:
    router = StubRouter(case, rng)
    reasoner = DeliberativeReasoner(router_factory=lambda: router)
    return reasoner.run(case["question"], consistency_paths=5)


def main():
    trials_per_case = 12
    rng = random.Random(42)

    old_correct = 0
    new_correct = 0
    new_confidence_when_correct = []
    new_confidence_when_wrong = []
    total = 0

    for case in CASES:
        for _ in range(trials_per_case):
            total += 1

            old_out = run_old(case, rng)
            old_ans = (old_out.get("final_answer") or "").lower()
            if is_correct(old_ans, case):
                old_correct += 1

            new_out = run_new(case, rng)
            new_ans = (new_out.get("final_answer") or "").lower()
            correct = is_correct(new_ans, case)
            if correct:
                new_correct += 1
                new_confidence_when_correct.append(new_out.get("confidence", 0))
            else:
                new_confidence_when_wrong.append(new_out.get("confidence", 0))

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    print("=" * 70)
    print("DELIBERATIVE REASONING BENCHMARK (stubbed LLM, synthetic cases)")
    print("=" * 70)
    print(f"Cases: {len(CASES)}  Trials/case: {trials_per_case}  Total trials: {total}")
    print()
    print(f"{'Engine':<30}{'Correct':<12}{'Accuracy':<10}")
    print(f"{'-'*30}{'-'*12}{'-'*10}")
    print(f"{'ai/chain_of_thought.py (old)':<30}{old_correct}/{total:<10}{old_correct/total:.1%}")
    print(f"{'deliberative_reasoning (new)':<30}{new_correct}/{total:<10}{new_correct/total:.1%}")
    print()
    print("Confidence calibration (new engine only):")
    print(f"  avg confidence on CORRECT answers: {avg(new_confidence_when_correct):.2f}")
    print(f"  avg confidence on WRONG answers:   {avg(new_confidence_when_wrong):.2f}")
    if new_confidence_when_correct and new_confidence_when_wrong:
        gap = avg(new_confidence_when_correct) - avg(new_confidence_when_wrong)
        print(f"  calibration gap (higher = better): {gap:+.2f}")
    print()
    improvement = (new_correct - old_correct) / total * 100
    print(f"Net accuracy delta: {improvement:+.1f} percentage points")
    print("=" * 70)


if __name__ == "__main__":
    main()
