"""
PREDICTIVE_ENGINE
===================
Predicts what the user is likely to do next, so ULTRON can prepare
ahead of time instead of reacting cold.

    behavior_modeler       - transition/frequency model of action history
    next_action_predictor   - blends transition + time-of-day signals into ranked predictions
    resource_preallocator   - pre-warms caller-registered resources for high-confidence predictions
    anomaly_detector        - flags actions/timing/bursts that deviate from the learned pattern
    schedule_anticipator    - mines recurring weekday+hour routines
    context_preloader       - prefetches lightweight context (not heavy resources) ahead of need
"""

from .behavior_modeler import BehaviorModeler, ActionEvent
from .next_action_predictor import NextActionPredictor, Prediction
from .resource_preallocator import ResourcePreallocator, PreallocResult
from .anomaly_detector import AnomalyDetector, AnomalyFlag
from .schedule_anticipator import ScheduleAnticipator, RoutineCandidate
from .context_preloader import ContextPreloader

__all__ = [
    "BehaviorModeler",
    "ActionEvent",
    "NextActionPredictor",
    "Prediction",
    "ResourcePreallocator",
    "PreallocResult",
    "AnomalyDetector",
    "AnomalyFlag",
    "ScheduleAnticipator",
    "RoutineCandidate",
    "ContextPreloader",
]
