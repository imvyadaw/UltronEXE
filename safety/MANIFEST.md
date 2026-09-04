# SAFETY (Phase 4.5)

Human-review gate + anomaly watchdog on top of `learning/`'s Phase
4.2-4.4 pipeline. Nothing here touches confidence scoring, pattern
detection, or decay math - it only ever adds a stop in front of
autonomy `learning/` already had, never new autonomy of its own. See
`__init__.py`'s docstring for the full "why".

| File | Responsibility |
|---|---|
| `policy.py` | `classify(name, steps)` - keyword-heuristic risk tier (`auto` / `needs_review`) over a procedure's name + step tool/argument text, against four risk categories (destructive, financial, outbound_communication, system_security). Persisted manual override per name (`set_override()`/`clear_override()`), same escape-hatch shape as `learning/source_validator.py`'s trust-tier overrides. |
| `review_queue.py` | Plain JSON queue (`storage/safety/review_queue.json`) for anything `policy.py` flags `needs_review`. `request_approval()` is idempotent while a matching item is still pending. `approve()`/`reject()` are a human decision - nothing in this module decides on its own. `approved_unapplied()`/`mark_applied()` split "a human said yes" from "the promotion actually happened," so a caller crashing between the two can't lose or double-apply an approval. |
| `guardian.py` | `check_cycle(cycle_result, total_patterns_before, total_episodes_before)` - flags a `learning_scheduler.py` cycle that pruned an unusually large fraction of current patterns/episodes in one pass, or that follows several consecutive failed cycles. Returns `{"halt": bool, "incidents": [...]}`; never touches the scheduler itself. |

## Usage

```python
from safety.policy import get_safety_policy, TIER_REVIEW

policy = get_safety_policy()
policy.classify("cleanup_old_backups", steps=[{"tool": "delete_file", "arguments": {"path": "/backups/old"}}])
# -> {"tier": "needs_review", "matched": ["destructive"], ...}

policy.set_override("cleanup_old_backups", "auto", reason="reviewed - only touches the scratch folder")
```

```python
from safety.review_queue import get_review_queue

queue = get_review_queue()
queue.pending()                 # what's waiting on a human right now
queue.approve(item_id=1)        # or queue.reject(item_id=1)
```

```python
from learning.learning_scheduler import get_learning_scheduler

scheduler = get_learning_scheduler()
scheduler.run_once()            # skill_promotion step now queues risky procedures instead of promoting them
scheduler.status()              # includes recent_guardian_incidents
```

If a cycle trips `guardian.py` (a prune spike, or repeated failures)
while the scheduler is running on an interval, it stops itself the
same way a manual `stop()` would - `start()` again once you've looked
at what happened (`get_learning_guardian().incidents()`).

## Design notes

- `policy.py`'s keyword list is a fast first pass, not a guarantee -
  same spirit as `learning/source_validator.py`'s domain heuristics for
  source trust. It will misclassify some procedures in both
  directions; `set_override()` is the fix, not a bigger keyword list.
- A classification error fails closed (`needs_review`, not `auto`) -
  see `policy.py`'s `classify()`. An anomaly-check error in
  `guardian.py` fails open (`halt: False`) - a guardian bug shouldn't
  itself be able to silently stop the whole learning pipeline; it's
  logged instead.
- `review_queue.py` never reaches into `intelligence.skill_builder`
  itself - `skill_id` travels through as an opaque `payload`, and only
  `learning/skill_learner.py`'s `apply_approved_promotions()` acts on
  it. Keeps the queue reusable for whatever future risky auto-action
  wants the same gate.
- `guardian.py`'s prune-fraction threshold is evaluated against a
  snapshot taken *before* the cycle runs (`learning_scheduler.py`
  fetches it), not the count left after - comparing against the
  post-prune count would understate the fraction that was actually
  removed.
