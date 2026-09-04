"""
Predictive mind
================
User-facing analytics layer on top of proactive/predictor.py's
ActionPredictor - that module already owns observation storage
(database/proactive_predictor.db) and the two prediction strategies
(time-of-day pattern, sequence chain); this package doesn't
reimplement either, it just turns predict_next()/predict_routine()
plus the raw observations table into a friendlier "behavior profile"
(busiest hours, most common actions/categories, a plain-language
routine summary) - the kind of thing a dashboard panel or a "how do I
usually use you" answer would want, rather than raw prediction tuples.
"""

from predictive_mind.user_behavior_predictor import get_behavior_profile, predict_next_action

__all__ = ["get_behavior_profile", "predict_next_action"]
