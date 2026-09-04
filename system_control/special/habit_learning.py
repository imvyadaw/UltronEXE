"""Habit Learning Control
==========================
Wraps memory.habit_memory.HabitMemory, which already records and
detects repeated actions (detected_habits(), habit_confidence()) but
has no way to DO anything with a detected habit. This module is that
bridge: it turns a detected habit into an actual scheduled automation
by delegating to system_control.automation.workflow_engine's
SystemAutomationPipeline (save/run a named pipeline) rather than
building a second automation engine.

Turning a habit into a live automation, or deleting the tracked
history, is confirm-gated.
"""

from typing import Dict, List, Optional


class HabitLearningControl:
    def record_action(self, action: str, context: Optional[str] = None) -> Dict:
        from memory.habit_memory import get_habit_memory

        get_habit_memory().record_action(action, context=context)
        return {"success": True, "recorded": action}

    def get_detected_habits(self, min_occurrences: int = 3) -> Dict:
        from memory.habit_memory import get_habit_memory

        return {"habits": get_habit_memory().detected_habits(min_occurrences=min_occurrences)}

    def get_habit_confidence(self, action: str) -> Dict:
        from memory.habit_memory import get_habit_memory

        return {"action": action, "confidence": get_habit_memory().habit_confidence(action)}

    def suggest_automation_for_habit(self, habit: Dict) -> Dict:
        """Turn one entry from get_detected_habits() into a pipeline-step
        proposal the caller can review before create_automation_from_habit()."""
        action = habit.get("action")
        context = habit.get("context")
        return {
            "proposed_pipeline_name": f"habit_{action}".replace(" ", "_") if action else None,
            "proposed_steps": [{"action": action, "context": context}] if action else [],
            "confidence": habit.get("confidence"),
        }

    def create_automation_from_habit(self, pipeline_name: str, steps: List[Dict], confirm: bool = False) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will create a scheduled automation pipeline '{pipeline_name}' with {len(steps)} step(s) from a detected habit.",
            }
        from system_control.automation.workflow_engine import SystemAutomationPipeline

        return SystemAutomationPipeline().save_pipeline(pipeline_name, steps)

    def run_habit_automation(self, pipeline_name: str, confirm: bool = False) -> Dict:
        from system_control.automation.workflow_engine import SystemAutomationPipeline

        return SystemAutomationPipeline().run_pipeline(pipeline_name, confirm=confirm)

    def list_habit_automations(self) -> Dict:
        from system_control.automation.workflow_engine import SystemAutomationPipeline

        return SystemAutomationPipeline().list_pipelines()

    def clear_habit_history(self, action: str, confirm: bool = False) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will delete all recorded history for action '{action}'.",
            }
        from memory.habit_memory import get_habit_memory

        removed = get_habit_memory()._delete_action(action)
        return {"success": True, "removed_rows": removed}


_instance: Optional[HabitLearningControl] = None


def get_habit_learning_control() -> HabitLearningControl:
    global _instance
    if _instance is None:
        _instance = HabitLearningControl()
    return _instance
