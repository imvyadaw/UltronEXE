# ADVANCED_MEMORY

Four memory *types* (episodic/semantic/spatial/temporal), one shared
graph connecting them, a decay model deciding what's worth keeping,
and a bounded consolidator that's the only thing allowed to act on
that decision. Nothing here re-implements SQLite storage that
`memory/` already has - it wraps it.

| File | Wraps | Adds |
|---|---|---|
| `memory_graph.py` | nothing (new capability) | typed node/edge store (`add_node`/`add_edge`/`neighbors`/`find_path`) every other file mirrors into |
| `forgetting_curve.py` | nothing (new capability) | Ebbinghaus decay (`retention()`), spaced-repetition strengthening (`record_access()`), `get_forgettable()` as a read-only signal |
| `episodic_memory.py` | `memory/episodic_memory.py` (unchanged) | importance scoring, a graph node per event, embedding-backed `recall_similar()` via `memory/vector_db` |
| `semantic_memory.py` | `memory/semantic_memory.py` (unchanged) | confidence + provenance per concept, multi-hop `related_concepts()` over the shared graph (base module's `get_related()` is one hop only) |
| `spatial_memory.py` | nothing (new capability) | named places (geo/filesystem/app/network), `events_at_place()`, haversine `nearby_geo_places()` |
| `temporal_memory.py` | `memory/episodic_memory.py` (read-only) | `detect_patterns()` turning repeated events into routines, `resolve_relative_time()` for phrases like "yesterday"/"last week" (Hinglish aliases included) |
| `memory_consolidator.py` | `core.events` via `PHASE_17_1_FOUNDATION`'s bridge | the bounded promote/prune cycle tying all of the above together |

## Usage

```python
from PHASE_17_3_MEMORY_SYSTEM.ADVANCED_MEMORY import get_advanced_episodic_memory, get_spatial_memory

episodic = get_advanced_episodic_memory()
result = episodic.record_event("closed 40 Chrome tabs", importance=0.3)
episodic.recall_similar("cleaning up my browser")   # embedding search, not exact text

places = get_spatial_memory()
places.remember_place("project repo", "filesystem", locator="/home/user/projects/ultron")
```

```python
from PHASE_17_3_MEMORY_SYSTEM.ADVANCED_MEMORY import get_temporal_memory, resolve_relative_time

resolve_relative_time("yesterday")           # {"start_ts": ..., "end_ts": ...}
get_temporal_memory().detect_patterns()      # scans recent episodes for routines
```

```python
from PHASE_17_3_MEMORY_SYSTEM.ADVANCED_MEMORY import get_consolidator

summary = get_consolidator().run_cycle()
summary["promoted"]   # episodes turned into semantic concepts this cycle
summary["pruned"]     # weak episodic nodes dropped from the advanced layer
```

## Safety properties

- **Bounded, always.** `run_cycle()` caps promotion and pruning at
  `MAX_ITEMS_PER_CYCLE` (50) each - a large backlog is worked down over
  several cycles, never all at once. `detect_patterns()` only scans a
  `lookback_days` window, never the full episodic history.
- **Never destroys the layer beneath it.** Pruning here means removing
  a node from `memory_graph.py` and untracking it in
  `forgetting_curve.py` - the underlying row in
  `memory/episodic_memory.py`'s own SQLite table is never deleted or
  modified. Same non-destructive stance `PHASE_17_1_FOUNDATION` takes
  toward Phase 16.
- **User-stated facts always win.** `memory_consolidator.py` never
  overwrites a `semantic_memory.py` concept whose confidence is already
  1.0 (i.e., something `add_concept()` was called on directly, outside
  the consolidator) with an inferred, lower-confidence one.
- **Fails closed toward doing nothing.** Every public method returns
  `{"error": ...}` instead of raising; `run_cycle()` catches around
  `detect_patterns()` specifically so a bad pattern-detection pass
  still lets promotion/pruning run. `_emit()` never raises - a missing
  event subscriber can't interrupt consolidation.
- **Purely additive.** Nothing in `memory/`, `core/`, `ai/`, `agents/`,
  `main.py`, `PHASE_17_1_FOUNDATION/` or `PHASE_17_2_COGNITIVE_BRAIN/`
  imports anything from `PHASE_17_3_MEMORY_SYSTEM/`.

## Verifying

```bash
python3 -c "
from PHASE_17_3_MEMORY_SYSTEM.ADVANCED_MEMORY import get_advanced_episodic_memory, get_consolidator

ep = get_advanced_episodic_memory()
for i in range(3):
    ep.record_event('opened VS Code', importance=0.8)
print(get_consolidator().run_cycle())
"
```
