# LEARNING (Phase 4.2 + 4.3 + 4.4 + 4.5)

Reads raw text and Ultron's own structured outcome data, and turns
both into durable, confidence-scored memory. Distinct from `learn/`
and `learning_engine/`, which adapt Ultron's behaviour from explicit
feedback/corrections one at a time - this package works in bulk, off
data that's already being collected, and writes into `knowledge_base/`
(Phase 4.2, outside-world knowledge) and `memory/episodic|semantic|
procedural|user/` (Phase 4.3, self-generated knowledge about how
Ultron's own tasks tend to go).

## Phase 4.2 - external knowledge

| File | Responsibility |
|---|---|
| `knowledge_extractor.py` | Orchestrator. LLM pass (`ai/llm/model_factory.ModelFactory`) pulls facts/concepts/relationships out of text as JSON, with a no-LLM sentence-split fallback. De-dupes against existing facts via `ai/embeddings` cosine similarity, routing repeats to corroboration instead of new rows. |
| `source_validator.py` | Domain-heuristic + persisted trust score/tier (`trusted` / `neutral` / `low_quality` / `unverified`) for a source, with a manual-override escape hatch. |
| `confidence.py` | Pure scoring functions: `score()` (new fact), `corroborate()` (existing fact + new source), `apply_time_decay()` (stale, unconfirmed facts), `classify()` (numeric -> high/medium/low). No I/O. |

## Phase 4.3 - self-generated knowledge (memory consolidation)

| File | Responsibility |
|---|---|
| `pattern_detector.py` | Scans `memory/episodic/` for recurring step-sequences (promotes them to `memory/procedural/`), recurring time-of-day windows and reliability trends (writes both to `memory/semantic/`, and to `memory/user/` once confident enough to call it a user trait). |
| `failure_learner.py` | Aggregates success/failure data already being tracked - `memory/procedural/` (per procedure), `memory/episodic/` (per episode kind), `memory/history/tracker.py` (per tool) - into durable, subject-keyed `lessons` (`storage/learning/failure_lessons.json`). `should_caution(subject)` is the read side; never blocks anything on its own. |

## Phase 4.4 - consolidation, forgetting, skill mastery, scheduling

Phase 4.3's two modules are deliberately conservative: `pattern_detector.py`
"only ever reinforces or creates" and `failure_learner.py` "never blocks
anything... only raises a flag". Nothing from Phase 4.2/4.3 ever deletes
anything, ever runs on its own schedule, or ever grades a skill's
mastery - Phase 4.4 is those four missing pieces.

| File | Responsibility |
|---|---|
| `memory_consolidator.py` | Runs `pattern_detector.run_detection()`, then `digest_stale_episodes()` (rolls episodes past `older_than_days` that never got promoted into a compact `episode_digest` semantic pattern per `kind`, so a one-off task isn't a permanent straggler) and `merge_duplicate_patterns()` (fuzzy-matches same-`pattern_type` descriptions via `difflib` and folds them together). |
| `forgetting.py` | The automatic counterpart to `memory/forget.py` (which stays manual/user-directed). `decay_and_prune_patterns()` applies `confidence.apply_time_decay()` at read time and deletes patterns that have decayed near the floor without ever being well-observed. `prune_digested_episodes()` deletes raw episodes only once `memory_consolidator.py` has folded them into a pattern's `source_episode_ids`. Every prune is logged to `storage/learning/forgetting_log.json`. |
| `skill_learner.py` | `learn_from_episode()` saves one already-successful episode straight into `memory/procedural/` + `intelligence/skill_builder/`'s `SkillStore`, skipping `pattern_detector`'s recurrence threshold - for explicit "remember this" intent. `assess_mastery()` grades a procedure novice/competent/mastered from its success-rate + use-count; `promote_masters()` syncs mastered procedures to `SkillStore`'s `STATUS_ACTIVE`. |
| `learning_scheduler.py` | Background job (`automation/scheduler/task_scheduler.py`, same backend as `core/scheduler.py`) that runs the above in dependency order - consolidate, then failure-scan, then promote masters, then forget - on a recurring interval (`start()`/`stop()`), or once on demand (`run_once()`). |

`memory/semantic/semantic_memory.py` gained two small additions for
this phase: `all_source_episode_ids()` (a plain query) and
`_delete_pattern()` (private, same underscore convention as
`memory/forget.py`'s primitives - `forgetting.py` is the only intended
caller). `memory/episodic/episodic_memory.py` gained the matching
`_delete_episode()`.

```python
from learning.learning_scheduler import get_learning_scheduler

scheduler = get_learning_scheduler()
scheduler.run_once()                 # one full cycle, right now
scheduler.start(interval_seconds=6 * 60 * 60)   # or: every 6 hours in the background
scheduler.status()
```

```python
from learning.skill_learner import get_skill_learner

sl = get_skill_learner()
sl.learn_from_episode(episode_id=42, name="organize_downloads")  # explicit teach, no repetition needed
sl.assess_mastery("organize_downloads")   # -> novice / competent / mastered
sl.promote_masters()                      # syncs any mastered procedure into skill_builder as active
```

Design notes:
- `forgetting.py`'s decay is read-time only (matching `confidence.py`'s
  own docstring) - nothing stored gets its `confidence` column rewritten,
  it's only ever recomputed at the moment of deciding whether to prune.
- `confidence.apply_time_decay()` asymptotically approaches
  `DECAY_FLOOR` (0.2) and never crosses it, so `forgetting.py`'s prune
  threshold sits just *above* that floor (`DECAY_FLOOR + 0.05`) rather
  than below it - a threshold below the floor would mean nothing ever
  decays far enough to qualify.
- A pattern with a high `observation_count` is protected from pruning
  regardless of age - repetition itself is evidence the regularity
  still matters, same reasoning `pattern_detector.py` uses to promote
  in the first place.
- `learning_scheduler.py`'s ordering is load-bearing: consolidation
  must run before forgetting, since forgetting only ever prunes an
  episode that consolidation already digested into a pattern.

See `memory/episodic/`, `memory/semantic/`, `memory/procedural/`,
`memory/user/` (each module's own docstring) for how they relate to
the pre-existing flat `memory/episodic_memory.py` / `semantic_memory.py`
/ `procedural_memory.py` modules.

`knowledge_base/` (facts/, concepts/, sources/, relationships/) is the
storage this writes to - see `knowledge_base/__init__.py` for the
`KnowledgeBase` facade and how the four record types link together.

## Usage

```python
from learning.knowledge_extractor import KnowledgeExtractor

extractor = KnowledgeExtractor()
result = extractor.extract(
    text="The Reserve Bank of India was established in 1935 and is headquartered in Mumbai.",
    source_name="RBI - About Us",
    source_url="https://www.rbi.org.in/about",
)
result["facts_added"]          # int
result["new_facts"]            # list of stored fact records, each with a confidence score
```

```python
from knowledge_base import KnowledgeBase

kb = KnowledgeBase()
kb.facts_about("Reserve Bank of India")   # everything linked to that concept
kb.search("Mumbai")                        # substring search over facts + concepts
kb.stats()                                 # counts per category
```

```python
from memory.episodic import get_episodic_memory
from learning.pattern_detector import get_pattern_detector
from learning.failure_learner import get_failure_learner

episodic = get_episodic_memory()
ep = episodic.start_episode("organize_downloads", goal="clean up the downloads folder")
episodic.add_step(ep["episode_id"], "list_files", success=True)
episodic.end_episode(ep["episode_id"], success=True, outcome="organized")

get_pattern_detector().run_detection()      # consolidates recent episodes into semantic/procedural/user memory
get_failure_learner().run_scan()            # flags unreliable procedures/episode kinds/tools
get_failure_learner().should_caution("organize_downloads", "episode_kind")
```

## Design notes

- Storage is one JSON file per record (see `knowledge_base/store.py`),
  not SQLite like `memory/long_term` - the knowledge base is meant to
  stay human-browsable on disk, and its scale (reference facts, not a
  chat log) doesn't need a real DB.
- `source_validator.py` is a trust *tier*, not a fact-checker - it
  never calls a fact-checking API. Corroboration across independent
  sources is what actually raises a fact's confidence over time.
- A fact's confidence never drops just because a new source agrees
  with it (`confidence.corroborate()` only ever raises or holds); it
  only drifts down via `apply_time_decay()`, and only toward a floor of
  0.2, never toward "false".
- Phase 4.3's `memory/` subpackages are SQLite (matching `memory/history/`,
  `memory/vector_db/`), unlike `knowledge_base/`'s JSON files - episodes/
  patterns/procedures/traits are Ultron's own operational memory, not a
  human-browsable reference like the knowledge base.
- `pattern_detector.py` only ever reinforces or creates - it never
  deletes a pattern or procedure. `failure_learner.py` only ever flags
  a caution - it never blocks an action or deletes a procedure. Acting
  on either (skip a flaky procedure, ask before repeating a low-success
  task) is a decision for a higher-level caller, not this package.

## Phase 4.5 - safety

`skill_learner.py`'s `promote_masters()` was the one place in Phase
4.2-4.4 that *acted autonomously on newly invented behavior* - flip a
mastered procedure straight to `skill_builder`'s `STATUS_ACTIVE`, no
matter what the procedure actually does. `../safety/` (its own
top-level package, not under `learning/`, since it also watches
`learning_scheduler.py`'s cycle as a whole) is the higher-level caller
this MANIFEST kept saying was needed:

- `safety/policy.py` classifies a procedure `auto` / `needs_review` by
  keyword heuristic (destructive / financial / outbound-communication /
  system-security), with a persisted manual-override escape hatch.
- `safety/review_queue.py` is where anything `needs_review` waits for a
  human `approve()`/`reject()` instead of being promoted or silently
  dropped.
- `safety/guardian.py` watches `learning_scheduler.py`'s own cycle
  results for a prune-fraction spike or repeated cycle failures, and
  can tell the scheduler to `stop()` its recurring run.

`promote_masters()` now queues instead of promoting when
`safety/policy.py` says `needs_review`, and separately applies any
promotions a human has since approved
(`apply_approved_promotions()`). `learning_scheduler.py`'s `run_once()`
snapshots pattern/episode counts before each cycle and hands them plus
the cycle result to `safety/guardian.py.check_cycle()` after; a `halt`
verdict pauses the recurring schedule. See `safety/MANIFEST.md` and
`safety/__init__.py`'s docstring for the full design.
