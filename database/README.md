# database/ (structural placeholder)

Exists for parity with the requested project tree. Ultron's actual
data lives under **`storage/`**:

- `database/sqlite/`  -> `storage/sqlite/` (todos.db, auth.db, history.db,
  long_term_memory.db, file_index.db, vector_store.db)
- `database/vector/`  -> `storage/chroma/` (memory/vector_db/chroma_client.py)
- `database/memory/`  -> also `storage/sqlite/` - `memory/` (top-level) is
  the *code* package (short-term buffer, long-term/episodic/semantic/
  procedural memory); its data is the sqlite files above, not a
  separate folder.
- `database/backups/` -> `storage/backups/` (scripts/backup.py)

Nothing writes here. See PHASE14.md / PHASE15.md for why these
directories mirror `storage/` instead of duplicating it.

---
# ULTRON Phase 20.6 — Intelligence Database Layer

This phase adds seven dedicated SQLite stores, kept under
**`database/intelligence/`** rather than `database/` directly:

- `world_state.db` — world/context snapshots.
- `goals.db` — goals and decomposed goal steps.
- `learned_skills.db` — learned workflows/skills and run outcomes.
- `knowledge_graph.db` — entities and relationships, including temporal validity.
- `confidence_history.db` — confidence/risk/decision history.
- `performance_metrics.db` — provider/tool latency and success metrics.
- `conversation_history.db` — conversation turns and context.

Why a separate subfolder: several Phase 19.x subsystems already write
their own same-named files directly under `database/` (e.g.
`intelligence/goal_manager/goal_store.py` → `database/goals.db`,
`intelligence/world_state/pc_state.py` → `database/world_state.db`,
and similarly for knowledge_graph/skill_builder/confidence_engine/
conversation_layer). Those files use their own schema, independent of
`database_manager.py`'s. Putting both under the same path with the
same filename was tried and silently corrupted whichever wrote
second ("no such column" errors) - `database/intelligence/` keeps
Phase 20.6's consolidated copy fully separate from every phase's own
store, so neither has to know the other exists.

`database_manager.py` provides a small thread-safe API and keeps the
seven stores independent, creating their schema itself
(CREATE TABLE IF NOT EXISTS) rather than depending on the shipped
`.db` files already containing it - so it also self-heals if a store
is ever deleted or this runs against a fresh checkout. SQLite foreign
keys and busy-timeout are enabled for runtime connections.

Phase 20.6 is additive. The existing `intelligence_core.db` event logger is
not removed; the new databases are an additional persistence layer.

---
# ULTRON Phase 28 — User Profiles + Emotional History

Extends `database_manager.py`'s nine (was seven) stores under
`database/intelligence/` with two new ones:

- `user_profiles.db` — one row per user_id: display name, preferences
  (a free-form JSON blob - theme, language, etc.), traits, metadata.
  `upsert_user_profile()`/`get_user_profile()`/`list_user_profiles()`.
- `emotional_history.db` — a time-ordered log of detected/reported
  emotional data points (emotion label, optional intensity, a
  `source` tag for where the reading came from - e.g. `mood_analyzer`
  for [[modules/movie_assistant/mood_analyzer.py]]'s output, or
  `explicit` for something the user stated outright - plus optional
  user_id/turn_id/context). `record_emotion()`/`get_emotional_history()`/
  `get_latest_emotion()`.

Unlike the original seven, neither of these two consolidates an
existing Phase 19.x subsystem's own store - there wasn't one. They're
exposed to callers directly as methods on
`intelligence.intelligence_core.IntelligenceCore`
(`get_user_profile()`/`update_user_profile()`/`record_emotion()`/
`get_emotional_history()`/`get_latest_emotion()`), the same
direct-`self.db` pattern `IntelligenceCore.process_turn()` already
uses for `conversation_history.db` and `confidence_history.db`,
rather than through one of `intelligence_bridge/`'s 13 subsystem
bridges (there's no `user_profile_bridge.py`/`emotional_history_bridge.py`
- neither store maps to an existing `intelligence/` subsystem to
bridge onto).
