"""Wellness & fitness tracking module
======================================
New capability (grep for fitness/sleep/workout across the whole tree
came back with zero matches before this - proactive/health_remind.py is
a generic interval-reminder scheduler with no data storage, not a
tracker). Same JSON-backed, singleton-getter pattern as finance/.

Sub-modules:
    activity_tracker.py - log steps, water intake, sleep hours,
                           workouts, and a simple 1-5 mood check-in;
                           daily/weekly summaries.
    goal_manager.py      - user-set daily/weekly targets per metric,
                            checked against activity_tracker's actuals.
    streak_tracker.py    - consecutive-day streaks per metric, derived
                            from activity_tracker + goal_manager (no
                            separate storage, computed on read).
    insights_engine.py   - combines the three into one report,
                            optionally narrated via the AI router.

Scope, deliberately: movement/hydration/sleep/mood logging and streaks
only. No calorie counting, no weight tracking, no diet targets, and no
AI-generated numeric health/nutrition advice anywhere in this module -
every number here is a plain user-supplied log entry or a user-set
target, and the only interpretation Ultron adds is "did you hit the
target you set", never a judgment about the number itself.
"""
