# Phase 29-B - Result hardening & verification layer

Sits on top of the existing runtime (AI Router -> Tool Selector -> Tool
Runtime -> Executor) and alongside `PHASE_29_A_STABILITY`:

```
EXISTING RUNTIME                    HARDENING LAYER
  AI Router                           B1 Result Normalizer
  Tool Selector          --->         B2 Evidence Collector
  Tool Runtime                        B3 Verification Engine
  Executor                              System / App / Browser / File /
                                         Keyboard-Mouse / Media / Voice-TTS /
                                         Memory / Automation / Integration
                                         Verifiers
                                       B6 False-Success Protection
                                       B4 Strict Truth Gate
                                       B5 Response Truth Guard

RESULT STATES: VERIFIED_SUCCESS | VERIFIED_FAILURE | PARTIAL_SUCCESS | UNKNOWN
CLAIM POLICY:  allowed | partial_only | blocked_success | blocked_definitive
```

| Module | What it does |
|---|---|
| `result_states.py` (**B1**) | The four `ResultState` values every call/turn is classified into, plus `combine()` to fold several per-call states into one turn-level state. |
| `result_normalizer.py` (**B1**) | Turns whatever a tool call returned (JSON string, dict, plain value) into one predictable `NormalizedResult(success, error, data)` shape. |
| `evidence_collector.py` (**B2**) | Groups one turn's (tool_name, arguments, normalized result, timestamp) into a `TurnEvidence`, in call order - raw tool result, execution metadata, and (via each call's arguments/data) the values the call itself claimed to change. |
| `verification_engine/` (**B3**) | Routes each call to one of **ten** domain verifiers (`verifiers.py`) by tool-name keyword match - System, Application, Browser, File, Keyboard/Mouse, Media, Voice/TTS, Memory, Automation, Integration - falls back to a generic `DefaultVerifier` for anything unrecognized. `verify_turn()` combines the per-call outcomes into a turn-level `ResultState`. |
| `false_success_protection.py` (**B6**) | Cross-cutting, tool-agnostic pass applied to every call after its domain verifier runs: never trust `success=True` alone, verify there's actual side-effect data (not just a flag), detect the resulting partial-execution shape, and fail closed - only ever downgrades a call *toward* `PARTIAL_SUCCESS`, never strengthens one. Skips read-only/query tools (`get_*`, `list_*`, ...) by design. |
| `truth_gate.py` (**B4** + advisory mismatch check) | Compares the final response text against the verified states - reuses `PHASE_29_A_STABILITY.truth_prompt_contract.check_turn()`'s regex signal *and* adds a second signal from the verified `ResultState`s themselves. Also classifies the turn-level state into a **strict claim policy**: `VERIFIED_SUCCESS` -> `allowed`, `PARTIAL_SUCCESS` -> `partial_only`, `VERIFIED_FAILURE` -> `blocked_success`, `UNKNOWN` -> `blocked_definitive` (see `CLAIM_POLICY`/`claim_policy()`). |
| `response_truth_guard.py` (**B5**) | `guard_turn()` - the single entry point wiring Normalizer -> Collector -> Engine -> False-Success Protection -> Gate together, locking in the verified `ResultState`/claim policy for the turn. Advisory only: logs a warning on mismatch, never rewrites, never invents, and never silently drops the verified values - it doesn't withhold the response either. |
| `run_phase29b.py` | VALIDATION CLI: compile / unit / integration checks, same GO/NO-GO convention as `PHASE_29_A_STABILITY/run_phase29a.py`. |

## Why this phase exists

`PHASE_29_A_STABILITY/truth_prompt_contract.py` added a first, cheap check:
does the final response *contain completion language* with no matching
successful tool call this turn. That's useful but shallow - it can only
ever say "the wording looks like a claim of success or it doesn't"; it has
no idea whether the *specific* action a tool call was for actually
happened the way the tool call implied. Two gaps that check structurally
can't close:

- **A tool call can report `success: True` and still not mean what it
  looks like it means.** This project has hit that for real more than
  once - `youtube_search`/`youtube_play` reporting success while only
  opening a search-results page instead of playing anything, and
  WhatsApp/Telegram/etc. `send_message` tools reporting success after only
  *typing* a message, not sending it (see `/areas/ultron-assistant.md`'s
  phase log). A regex over the response text can't catch that - it needs
  to look at what the tool's own result data actually says.
- **A destructive, confirm-gated action (`shutdown_pc`, `restart_pc`,
  `kill_process`, ...) that's correctly *not* taken because `confirm` was
  never set** still returns a "successful" tool call (the gate itself
  worked as designed) - but a response that says "done, shutting down now"
  off the back of that call would be wrong, and 29-A's regex has no way to
  know the difference between "the shutdown ran" and "the shutdown was
  correctly declined pending confirmation".

Phase 29-B is the deeper pipeline that classifies *what a tool call's
result actually means*, per tool category, before the truth gate ever
looks at the response text - rather than trying to teach one regex module
every domain-specific rule needed to catch cases like the two above.

It does not replace 29-A: `truth_gate.py` still calls `check_turn()` as
one of its two signals (single source of truth for that regex logic,
same "don't duplicate it" stance 29-A itself took for
`TRUTH_CONTRACT_ADDENDUM`). `TRUTH_CONTRACT_ADDENDUM`'s system-prompt
addendum is untouched and still wired into `ai/prompts/system_prompts.py`.

## Wiring

Both AI backends behind `ai/ai_router.py` now run the same hardening pass -
originally only the cloud path had it, see "gap found while wiring" below:

- `ai/cloud_models/groq_client.py`'s `chat_with_tools()` - the actual
  tool-calling loop, both the native and legacy-text-fallback paths - now
  tracks `turn_tool_args` alongside the `turn_tool_names`/`turn_tool_results`
  lists it already kept for 29-A, and calls
  `PHASE_29_B_HARDENING.guard_turn(final_response, turn_tool_names,
  turn_tool_args, turn_tool_results)` once per turn instead of calling
  `check_turn()` directly (that call now happens one layer down, inside
  `truth_gate.evaluate()`).
- `ai/local_models/manager.py`'s `chat_with_tools()` (the offline/Ollama
  path) gets the identical treatment: a new local `_parse_tool_result()`
  helper (same two-line JSON-parse as the cloud client's, duplicated
  rather than shared - not worth a cross-module import for that) plus the
  same `turn_tool_names`/`turn_tool_args`/`turn_tool_results` tracking and
  `guard_turn()` call before `final_response` is returned.

Failures inside `guard_turn()` are swallowed by its own internal
try/except *and* by each call site's, so this can never be the reason a
real response fails to return, on either backend.

### Gap found while wiring

The local/offline backend (`ai/local_models/manager.py`) had **zero**
Phase 29 coverage before this pass - not 29-A's `check_turn()`, not 29-B's
pipeline. Both READMEs (29-A's and this one, originally) described the
truth-checking as running "on every real turn" but that was only ever true
for `AI_MODE=cloud` (Groq); a conversation running on `AI_MODE=local`
(Ollama) got no verification at all, silently. Confirmed with a mocked
Ollama client: a confirm-gated `shutdown_pc` call (`confirm: False`,
correctly not executed) paired with a response of "Shutting down now,
Sir." now correctly produces `turn_state=PARTIAL_SUCCESS` and a logged
flag on the local path too - before this fix it would have gone through
uninspected.

## Usage

```bash
# from the Ultron/ directory
python -m PHASE_29_B_HARDENING.run_phase29b                # all three checks
python -m PHASE_29_B_HARDENING.run_phase29b --compile       # compile only
python -m PHASE_29_B_HARDENING.run_phase29b --unit          # unit tests only
python -m PHASE_29_B_HARDENING.run_phase29b --integration   # guard_turn() smoke test
```

Exit code `0` on PASS, `1` on FAIL - same convention as `core/startup.py`,
`PHASE_29_INTEGRATION/run_phase29.py`, and
`PHASE_29_A_STABILITY/run_phase29a.py`.

```python
from PHASE_29_B_HARDENING import guard_turn, ResultState

report = guard_turn(
    "I've opened Chrome for you, Sir.",
    tool_names=["open_application"],
    tool_args=[{"app_name": "Chrome"}],
    tool_results=[{"success": True, "app_name": "Chrome"}],
)
report.ok            # True
report.turn_state    # ResultState.VERIFIED_SUCCESS
```

## Tests

```bash
pytest PHASE_29_B_HARDENING/tests/ -v
```

Dependency-free (no groq/ultralytics/torch required) - fabricated
tool_name/args/result triples, same "fake stages, not the full dependency
stack" approach as `PHASE_29_A_STABILITY/tests/test_phase29a_stability.py`.
43 tests covering the normalizer, `combine()`'s aggregation rules, verifier
routing across all 10 categories, each verifier's generic and
domain-specific behavior (including the confirm-gate and youtube_play
regression checks above, plus the newer keyboard/mouse dispatch-vs-focus,
voice/TTS engine-switch-confirmation, and integration remote-status
checks), `false_success_protection.py`'s bare-flag downgrade and
never-strengthens-a-non-success guarantees (B6), the B4 claim-policy
mapping, and `guard_turn()` end-to-end (clean success, unmentioned
failure, no-tool-call turns, and mismatched-length input lists).

## Verified in this build

- `PHASE_29_B_HARDENING.run_phase29b` (all three checks) passes.
- `PHASE_29_A_STABILITY.run_phase29a --integration` and
  `PHASE_29_INTEGRATION.run_phase29 --pipeline` still pass with 29-B wired
  into `groq_client.py` - the existing runtime isn't affected.
- Full `PHASE_29_A_STABILITY/tests/`, `PHASE_29_INTEGRATION/tests/`, and
  `PHASE_29_B_HARDENING/tests/` suites together: 78 passed.
- Mocked end-to-end `chat_with_tools()` run (fake Groq SDK, fake tool
  executor): a `send_email` call reporting `{"success": false, "error":
  "SMTP auth failed"}` alongside a response of "Done, Sir - all set."
  produces `turn_state=VERIFIED_FAILURE` and a logged
  `truth gate: FLAGGED` warning without altering the response or raising;
  a clean `open_application` success run produces
  `turn_state=VERIFIED_SUCCESS` with no warning logged.
