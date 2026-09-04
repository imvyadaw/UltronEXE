"""
Logic conditions skill (Phase 5 facade)
==========================================
Combines automation/conditions/if_conditions.py's ConditionEvaluator
(evaluate a condition dict, run an if/then/else) with
automation/conditions/loops.py's LoopRunner (repeat/while/for-each over
tool calls) behind one BaseSkill interface - the branching + looping
building blocks other automation (workflow engine, event triggers) is
composed from.
"""

from skills.base_skill import BaseSkill
from automation.conditions.if_conditions import ConditionEvaluator
from automation.conditions.loops import LoopRunner


class LogicConditionsSkill(BaseSkill):
    """Evaluate conditions and run if/then/else, repeat, while, and for-each logic."""

    name = "logic_conditions"
    description = "Evaluate conditions (app/process/file/battery/CPU/RAM/time) and run if/repeat/while/for-each logic."
    category = "automation"

    def __init__(self):
        self._conditions = ConditionEvaluator()
        self._loops = LoopRunner()
        super().__init__()

    def register_actions(self) -> None:
        c, l = self._conditions, self._loops
        self._actions = {
            "evaluate": c.evaluate,
            "run_if": c.run_if,
            "repeat": l.repeat,
            "while_condition": l.while_condition,
            "for_each": l.for_each,
        }
