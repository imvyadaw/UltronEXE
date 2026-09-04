"""
Predictive Preparation (Phase 20.2)
=============================
ULTRON getting things ready before it's asked - as opposed to Phase
20.1's proactive_intelligence/, which decides whether to *say*
something on its own. This package never speaks or interrupts; it
only warms things in the background so that whatever ULTRON (or the
user) does next feels instant instead of paying a cold-start. A
completed task is recorded, the next task is predicted from learned
sequence and time-of-day patterns, and - only where confidence and
system resources allow - the app, local model, and contextual data
that prediction is known to need get preloaded ahead of time:

    next_task_predictor.py  - learns from record_task() calls
                               (transition + time-of-day patterns) and
                               answers predict_next(). Owns tables
                               `task_events` and `transition_counts`.
    resource_optimizer.py   - the gatekeeper every preloader below
                               checks before spending anything (CPU/
                               memory/battery headroom, per-kind
                               cooldown). Stateless besides an
                               in-memory cooldown cache, no DB.
    app_preloader.py        - silently launches a whitelisted,
                               registered app minimized ahead of
                               predicted need. Owns table
                               `preload_log`.
    model_preloader.py      - warms a registered local model (Ollama
                               keep_alive) ahead of predicted need.
                               Owns table `model_warm_log`.
    context_preloader.py    - runs registered no-argument provider
                               callables to prefetch data (calendar,
                               files, etc) into an in-memory cache
                               ahead of predicted need. Owns table
                               `context_preload_log` (metadata only -
                               fetched values never touch disk).
    predictive_engine.py    - single entry point tying all of the
                               above together; owns table
                               `predictive_preparation_events`

Usage:
    from intelligence.predictive_preparation import (
        get_predictive_engine, get_app_preloader, get_model_preloader, get_context_preloader,
    )
    engine = get_predictive_engine()

    # one-time setup elsewhere in ULTRON - nothing is registered by default:
    get_app_preloader().register_app("vscode", r"C:\\Users\\you\\AppData\\Local\\Programs\\...\\Code.exe")
    get_app_preloader().register_task_app_mapping("open_project", ["vscode"])
    get_model_preloader().register_model_mapping("coding_help", "qwen2.5-coder:7b")
    get_context_preloader().register_provider("todays_calendar", fetch_todays_calendar, ttl_seconds=600)
    get_context_preloader().register_task_context_mapping("open_project", ["todays_calendar"])

    # normal use - one call per completed task, learns and prepares in one step:
    result = engine.record_task("open_project", category="dev", session_id=session_id)
    # result["prepared"]["acted"] -> what got preloaded for whatever's predicted next

    # or ask without recording anything:
    outlook = engine.predict_and_prepare(current_task="open_project", session_id=session_id)

Each sub-module also exposes its own get_x() singleton and can be
used directly - e.g. call next_task_predictor.py alone just to get a
prediction, with no preloading involved.

Purely additive - nothing in Phase 1-20 imports from here, and this
package does not import from proactive_intelligence/ (Phase 20.1).
Registration (register_app/register_model_mapping/register_provider/
the *_mapping calls) is left to whichever caller elsewhere in ULTRON
owns that app/model/data source - this package ships with empty
registries and predicts/learns regardless, it just has nothing to
preload until something is registered.
"""

from intelligence.predictive_preparation.next_task_predictor import NextTaskPredictor, get_next_task_predictor
from intelligence.predictive_preparation.resource_optimizer import (
    ResourceOptimizer,
    get_resource_optimizer,
    KIND_APP,
    KIND_MODEL,
    KIND_CONTEXT,
    COST_LOW,
    COST_MEDIUM,
    COST_HIGH,
)
from intelligence.predictive_preparation.app_preloader import AppPreloader, get_app_preloader
from intelligence.predictive_preparation.model_preloader import ModelPreloader, get_model_preloader
from intelligence.predictive_preparation.context_preloader import ContextPreloader, get_context_preloader
from intelligence.predictive_preparation.predictive_engine import (
    PredictiveEngine,
    get_predictive_engine,
    MIN_CONFIDENCE_TO_PREPARE,
    MAX_PREDICTIONS_TO_ACT_ON,
)

__all__ = [
    "PredictiveEngine",
    "get_predictive_engine",
    "MIN_CONFIDENCE_TO_PREPARE",
    "MAX_PREDICTIONS_TO_ACT_ON",
    "NextTaskPredictor",
    "get_next_task_predictor",
    "ResourceOptimizer",
    "get_resource_optimizer",
    "KIND_APP",
    "KIND_MODEL",
    "KIND_CONTEXT",
    "COST_LOW",
    "COST_MEDIUM",
    "COST_HIGH",
    "AppPreloader",
    "get_app_preloader",
    "ModelPreloader",
    "get_model_preloader",
    "ContextPreloader",
    "get_context_preloader",
]
