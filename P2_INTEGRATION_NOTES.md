# P2 Integration Notes

Implements and wires the 2 items you marked P2. Verified with
`python3 -m py_compile` on every touched/new file plus a standalone
functional smoke test (claim logging + outcome + source reliability
math; failure-signature clustering across 3 differently-worded errors
correctly collapsing into 1 pattern; precursor correlation correctly
detecting that `open_browser` reliably preceded `click_ui_element`
failures) - all passed. Not run inside the full app - test end-to-end
in your own environment before relying on it.

## 1. Evidence Ledger & Confidence Tracking
New: `intelligence/evidence_ledger/` (`ledger_store.py`, `evidence_ledger.py`)
- Sits directly downstream of the existing `reasoning/fact_checker.py`
  + `reasoning/evidence.py` (Phase 30) - those already produce a
  confidence-labeled verdict per claim but never persisted it. This
  adds that persistence layer to `database/evidence_ledger.db`.
- `ai/phase30_extended_tools.py`'s `_check_fact` now auto-logs every
  `check_fact` tool call into the ledger (best-effort, wrapped in
  try/except so a ledger failure never breaks the fact-check response)
- `record_outcome()` feeds real-world correctness back into a running
  **per-source reliability score** (same Bayesian-prior scoring style
  as P1's `tool_chain_optimizer`, so scores mean the same thing
  everywhere in the codebase)
- `why_did_you_believe(claim)` answers "why did you say X" from the
  ledger; `get_untrustworthy_sources()` surfaces sources that have
  quietly gone bad
- New tools: `log_claim_check`, `record_evidence_outcome`,
  `why_did_you_believe`, `get_source_reliability`,
  `get_recent_evidence_entries`, `get_untrustworthy_sources`

## 2. Failure Pattern Learning Engine
New: `learning_engine/failure_pattern_engine.py`
- Unifies what `learning_engine/mistake_learner.py` (per-action mistake
  counting) and `self_healing/crash_analyzer.py` (after-the-fact log
  scanning) each do separately, but **live**: hooked into
  `core/action_pipeline.py` stage 5 (record) right alongside P1's
  tool-chain optimizer hook, so every real action feeds it immediately
- Error messages are normalized (paths/numbers/quoted values stripped)
  so differently-worded instances of the same underlying failure
  cluster into one pattern instead of looking like N separate ones
- New: **precursor correlation** - tracks a rolling window of recent
  tool calls and persists which tool tends to run right before another
  tool's failures, so a chain-shaped root cause (e.g. "X fails whenever
  Y ran right before it") can be flagged, not just single-tool flakiness
- `check_risk(tool_name)` gives an empirical low/medium/high risk label
  before calling a tool - complements
  `intelligence/confidence_engine/decision_gate.py` (which reasons
  about a pending action's *stated* signals) with "has this tool
  actually been failing in a recognizable way lately"
- Deliberately only flags, never blocks on its own - matches this
  codebase's existing separation (mistake_learner.py's docstring:
  "never silently blocks... only raises a flag")
- New tools: `check_tool_failure_risk`, `get_failure_patterns`,
  `get_failure_pattern_report`

## Design principle followed (same as P1)
Every init wrapped in the same `try/except Exception: logger.exception(...)`
pattern used throughout `core/assistant.py`; every hook added to
`core/action_pipeline.py` is independently wrapped so P1's hook, P2's
two hooks, and the base action logic can never take each other down.

## Files touched (existing files, small additive edits)
- `core/action_pipeline.py` - added failure-pattern recording (2nd hook in stage 5)
- `core/executor.py` - added 2 singletons + 9 tool_map entries
- `ai/tools_schema.py` - appended `P2_ENGINE_TOOLS`
- `ai/phase30_extended_tools.py` - `_check_fact` now auto-logs to the ledger
- `core/assistant.py` - added 2 init blocks (evidence_ledger / failure_pattern_engine)

## Files added
- `intelligence/evidence_ledger/__init__.py`
- `intelligence/evidence_ledger/ledger_store.py`
- `intelligence/evidence_ledger/evidence_ledger.py`
- `learning_engine/failure_pattern_engine.py`
- `ai/p2_engine_tools.py`

## Not yet done (left for later passes)
- Nothing currently calls `check_tool_failure_risk` *before* running a
  risky action automatically - the tool exists and is wired, but
  wiring it into `core/action_pipeline.py`'s stage 2 (permit) as an
  actual soft-gate (e.g. require confirmation when risk is "high",
  the same way capability_isolation's "ask" mode works) is a natural
  next step once you've seen it accumulate some real data.
- `why_did_you_believe` matches by simple substring on stored claim
  text - fine for now, but a semantic match (via
  `memory/semantic_memory.py`, already in the codebase) would catch
  paraphrased questions too.

See `P1_INTEGRATION_NOTES.md` for the P1 writeup and the full P3-P5
roadmap.
