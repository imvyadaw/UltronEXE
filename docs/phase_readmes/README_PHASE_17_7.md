# PHASE 17.7 — INTELLIGENCE — build notes

All 16 files from your tree got built, exactly as named. Nothing was
skipped this time - this phase is prediction, local learning, and
self-healing, none of which needed scoping down the way a couple of
Phase 17.6 modules did.

Two are worth a short explanation anyway, so the "why" lives in one
place instead of repeated in every docstring:

- **`model_finetuner.py`** — the name could suggest gradient-based
  finetuning of the underlying LLM itself. It doesn't do that. It
  tunes small, local, transparent numeric parameters (the predictor's
  transition/time blend weights, anomaly sensitivity) using
  `feedback_collector`'s scored history as signal - all bounded,
  logged, and reversible with `reset_to_defaults()`. If you want
  actual LLM finetuning later (e.g. a proper job on your own exported,
  consented data), that deserves its own explicit, user-initiated
  skill rather than something running silently in the background loop.

- **`auto_recovery.py`** — recovery strategies only run for components
  you explicitly register a callback for (`register_strategy(name, fn)`).
  It never reaches out to kill or restart arbitrary OS processes on
  its own initiative.

## Install

```bash
pip install psutil
```

Everything else in this phase (behavior modeling, prediction,
feedback, RL, mistake tracking, user adaptation, crash log parsing,
dependency checks) is pure standard library.

## How the three sub-packages fit together

```
PREDICTIVE_ENGINE.BehaviorModeler.record(action)
        │
        ▼
PREDICTIVE_ENGINE.NextActionPredictor.predict()  ──►  ResourcePreallocator / ContextPreloader
        │
        ▼
 (user does / doesn't do the predicted thing)
        │
        ▼
LEARNING_ENGINE.FeedbackCollector.record(...)  ──►  ModelFinetuner.step_from_feedback(action)
                                                 ──►  ReinforcementLearner.reward(...)
                                                 ──►  MistakeLearner.record_mistake(...) on failures
                                                 ──►  UserAdaptationEngine.observe(...)

SELF_HEALING.HealthMonitor.check_once() ──► alerts ──► AutoRecovery.handle_alert(alert)
SELF_HEALING.CrashAnalyzer.scan_file(log_path)       (independent - point it at core.logger's log file)
SELF_HEALING.DependencyChecker.check_all(...)         (run at startup, before the above two)
SELF_HEALING.PerformanceOptimizer.analyze()           (run on a timer alongside HealthMonitor)
```

## Wiring into the rest of ULTRON

Each module is standalone and runnable on its own for a quick demo
(`python -m PHASE_17_7_INTELLIGENCE.PREDICTIVE_ENGINE.behavior_modeler`
etc.). To hook into the main assistant loop:

1. Instantiate `BehaviorModeler` once at startup and call `.record(action)`
   from wherever your existing intent router (or `core.events` event
   bus, if you're wiring this the way earlier phases did) dispatches
   a recognized action.
2. Feed its predictions into `NextActionPredictor`, then optionally
   into `ResourcePreallocator` / `ContextPreloader` with your own
   registered warm/fetch callbacks.
3. Wherever you currently confirm success/failure back to the user,
   also call `FeedbackCollector.positive/negative/implicit_correction`
   so `ModelFinetuner`, `ReinforcementLearner`, and `MistakeLearner`
   have something to learn from.
4. Start `HealthMonitor` on a background timer at boot, register any
   custom probes for your own long-running components (STT engine,
   wake-word listener, etc.), and wire `AutoRecovery.handle_alert` as
   its `on_alert` callback.
5. Point `CrashAnalyzer.scan_file()` at whatever log path
   `core/logger.py` writes to, on a schedule or on startup.

All storage is local JSON under `ultron_data/` by default (mirrors
the additive, on-disk style of earlier phases) - no network calls,
no telemetry, nothing sent anywhere by this phase.
