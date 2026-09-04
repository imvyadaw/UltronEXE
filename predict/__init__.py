"""
PREDICT (Phase 18.9.1)
===========================
Forward-looking pattern matching over whatever history a caller feeds
in - nothing here senses anything on its own, each module works
purely from what's been record()-ed/register()-ed into it before:

    next_action.py  - order-1 Markov chain over action names; ranks
                      what's historically followed the current/last
                      action.
    need_before.py  - day-of-week/hour bucketed recurring needs;
                      surfaces what's usually wanted around a given
                      time.
    danger_sense.py - aggregate, decaying risk score from arbitrary
                      registered signals, optionally enriched by
                      PHASE_18_8_SECURITY's intruder_alert.py and
                      PHASE_18_9_SMART_DEVICES's door_control.py
                      failure counts.
    mood_predict.py - lexicon-based surface tone scoring of text for
                      response-phrasing purposes only; explicitly not
                      a clinical or diagnostic signal - see its own
                      module docstring.

All local state (transition counts, need buckets) lives under
data/ai_evolution/ by default, each path overridable via its own
AI_EVOLUTION_*_ENV variable. danger_sense.py's two cross-phase
integrations are both import-guarded, so this package works
standalone if 18.8/18.9 aren't present.

Purely additive - nothing in Phase 1-18.9 imports from here.
"""

from predict.next_action import get_next_action
from predict.need_before import get_need_before
from predict.danger_sense import get_danger_sense
from predict.mood_predict import get_mood_predict

__all__ = [
    "get_next_action",
    "get_need_before",
    "get_danger_sense",
    "get_mood_predict",
]
