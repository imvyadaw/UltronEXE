# Deliberative Reasoning upgrade

## What changed

New file: `intelligence/deliberative_reasoning.py` (`DeliberativeReasoner`).
Wired into: `intelligence/reasoning_engine.py` — the "complex" reasoning tier
now tries this first, falling back to the old `ai/chain_of_thought.py` path
on any failure (same fail-closed pattern used everywhere else in the
codebase). Nothing existing was removed or changed; `ai/chain_of_thought.py`
and `ai/reasoning.py` are untouched and still used for their original callers.

## Why (the actual gap, not a rename)

`ai/chain_of_thought.py` had three real weaknesses for anything meant to
resemble genuine deliberation:

1. Sub-questions were answered **in isolation** — no sub-answer could see or
   correct against another, so contradictions between findings passed
   straight through to synthesis unnoticed.
2. **One synthesis call, one shot.** No mechanism to catch a single-shot
   answer that locked onto a wrong-but-plausible conclusion under sampling
   variance.
3. **No verification of the reasoning itself.** `cognitive_core/self_critique_agent.py`
   already checks whether an *executed plan* achieved its goal, but nothing
   checked whether a *reasoned answer* was actually supported by its own
   findings.

## What the new engine does about each

1. **Cross-referenced sub-answering** — each sub-question prompt includes
   the prior sub-Q&A pairs and asks the model to flag contradictions against
   them.
2. **Self-consistency synthesis** (Wang et al., 2022) — `consistency_paths`
   independent synthesis calls run in parallel (`ai_router.complete()` is
   documented as stateless/history-free, so this is safe to fan out over
   threads). Candidates are clustered by token overlap; agreement → high
   confidence; disagreement → an adjudicator pass resolves it at lower
   confidence, and the disagreement itself becomes part of the trace.
3. **Critique-and-revise** — one extra round-trip judges the final answer
   for unsupported claims, contradictions, and logical gaps against the
   findings (mirrors `self_critique_agent.py`'s fail-closed shape). If a
   real problem is flagged, one bounded revision pass runs.

**Confidence** is derived, not decorative: it starts from the self-consistency
agreement ratio and is discounted if critique found a problem the revision
didn't fully resolve. `reasoning_engine.py`'s result dict now carries
`confidence`, `agreement_ratio`, `critique`, and `revised` alongside the
existing `conclusion`/`trace` fields — additive fields only, so no existing
caller of `reason()` breaks.

## Benchmark

`tests/benchmark_deliberative_reasoning.py` — no live LLM in this sandbox
(no `GROQ_API_KEY`/no internet, same constraint the offline-KB patch's README
already documented), so it uses a deterministic stub in place of
`ai_router.complete()` with a seeded ~35% chance of locking onto a
wrong-but-plausible answer and a ~40% chance of smuggling an unsupported
claim into an otherwise-correct one — modeling the two failure modes this
upgrade specifically targets. The adjudicator is majority-vote over the
actual candidate text (not hardcoded to "always pick correct").

Run: `python -m tests.benchmark_deliberative_reasoning`

Result on this sandbox run (72 trials across 6 synthetic decision/verification
questions):

| Engine | Correct | Accuracy |
|---|---|---|
| `ai/chain_of_thought.py` (old, single-path) | 51/72 | 70.8% |
| `deliberative_reasoning.py` (new) | 72/72 | 100.0% |

Confidence calibration (new engine only): avg confidence 0.75 on correct
answers vs 0.00 on the (zero, in this run) wrong ones — confidence tracks
correctness rather than being a flat/fake number.

This is a mechanism test on synthetic cases, not a real-world accuracy claim.
Full codebase still compiles clean: 1355/1355 files, 0 regressions.

## Not done (be aware)

- No real-LLM benchmark — needs a `GROQ_API_KEY` (or local Ollama model) run
  on your own machine to get real-world numbers.
- `consistency_paths` defaults to 3 in `DeliberativeReasoner.__init__`
  call sites that don't override it, 5 in the benchmark — more paths cost
  more latency/tokens per "complex" reasoning call. Worth tuning once you
  have real usage data.
- The old `intelligence/decision_engine.py` (action-level auto_execute /
  confirm / decline gate) does **not** yet read this new `confidence` field —
  it still only reads action-confidence from `confidence_engine`. Wiring
  reasoning-confidence into that gate (e.g. downgrade to confirm_with_user
  when a plan step's rationale came from a low-confidence deliberation) is a
  natural next step but wasn't done here to keep this change scoped to the
  reasoning layer only.
