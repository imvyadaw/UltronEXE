"""
LEARNING_ENGINE
=================
Lets ULTRON improve from this user's own feedback over time, entirely
locally.

    feedback_collector   - records explicit + implicit feedback on ULTRON's actions
    model_finetuner      - tunes small local scoring parameters from aggregated feedback
                            (NOT LLM weight training - see the module docstring for scope)
    reinforcement_learner - epsilon-greedy bandit for picking between valid response options
    mistake_learner       - tracks repeated mistakes, flags actions with a poor track record
    user_adaptation       - slowly-adapting profile of verbosity/formality/confirmation style
"""

from .feedback_collector import FeedbackCollector, FeedbackEntry, FeedbackType
from .model_finetuner import ModelFinetuner, TunedParams
from .reinforcement_learner import ReinforcementLearner, ArmStats
from .mistake_learner import MistakeLearner, Mistake
from .user_adaptation import UserAdaptationEngine, UserProfile

__all__ = [
    "FeedbackCollector",
    "FeedbackEntry",
    "FeedbackType",
    "ModelFinetuner",
    "TunedParams",
    "ReinforcementLearner",
    "ArmStats",
    "MistakeLearner",
    "Mistake",
    "UserAdaptationEngine",
    "UserProfile",
]
