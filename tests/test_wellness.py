from datetime import datetime, timedelta, timezone
from pathlib import Path

import wellness.activity_tracker as activity_mod
import wellness.goal_manager as goal_mod
import wellness.streak_tracker as streak_mod


def _fresh_activity(tmp_path):
    activity_mod.DATA_PATH = Path(tmp_path) / "activity.json"
    return activity_mod.ActivityTracker()


def _fresh_goals(tmp_path):
    goal_mod.DATA_PATH = Path(tmp_path) / "goals.json"
    return goal_mod.GoalManager()


def test_log_steps_and_daily_summary(tmp_path):
    tracker = _fresh_activity(tmp_path)
    result = tracker.log_steps(5000)
    assert result["success"]

    summary = tracker.daily_summary()
    assert summary["steps"] == 5000


def test_log_steps_rejects_negative(tmp_path):
    tracker = _fresh_activity(tmp_path)
    assert tracker.log_steps(-10)["success"] is False


def test_log_sleep_rejects_out_of_range(tmp_path):
    tracker = _fresh_activity(tmp_path)
    assert tracker.log_sleep(30)["success"] is False
    assert tracker.log_sleep(7.5)["success"] is True


def test_log_mood_range(tmp_path):
    tracker = _fresh_activity(tmp_path)
    assert tracker.log_mood(6)["success"] is False
    assert tracker.log_mood(4, "feeling good")["success"] is True


def test_weekly_summary_aggregates_multiple_days(tmp_path):
    tracker = _fresh_activity(tmp_path)
    today = datetime.now(timezone.utc).astimezone().date()
    yesterday = (today - timedelta(days=1)).isoformat()
    tracker.log_steps(3000, date=yesterday)
    tracker.log_steps(4000)  # today

    week = tracker.weekly_summary()
    assert week["total_steps"] == 7000


def test_goal_status_reports_met_and_unmet(tmp_path):
    activity = _fresh_activity(tmp_path)
    activity.log_steps(9000)
    goal_mod.get_activity_tracker = lambda: activity

    goals = _fresh_goals(tmp_path)
    goals.set_goal("steps", 8000)
    goals.set_goal("sleep_hours", 8)

    status = goals.get_status()
    steps_row = next(r for r in status["goals"] if r["metric"] == "steps")
    sleep_row = next(r for r in status["goals"] if r["metric"] == "sleep_hours")
    assert steps_row["met"] is True
    assert sleep_row["met"] is False


def test_goal_rejects_unknown_metric(tmp_path):
    goals = _fresh_goals(tmp_path)
    assert goals.set_goal("calories", 2000)["success"] is False


def test_streak_current_and_best(tmp_path, monkeypatch):
    activity = _fresh_activity(tmp_path)
    today = datetime.now(timezone.utc).astimezone().date()

    # Met the goal for the last 3 days including today.
    for i in range(3):
        d = (today - timedelta(days=i)).isoformat()
        activity.log_steps(10000, date=d)
    # Missed it 5 days ago, but had a longer run before that (4 days).
    for i in range(6, 10):
        d = (today - timedelta(days=i)).isoformat()
        activity.log_steps(10000, date=d)

    monkeypatch.setattr(streak_mod, "get_activity_tracker", lambda: activity)

    goals = _fresh_goals(tmp_path)
    goals.set_goal("steps", 8000)
    monkeypatch.setattr(streak_mod, "get_goal_manager", lambda: goals)

    tracker = streak_mod.StreakTracker()
    result = tracker.get_streaks()
    steps_streak = next(s for s in result["streaks"] if s["metric"] == "steps")
    assert steps_streak["current_streak"] == 3
    assert steps_streak["best_streak"] == 4
