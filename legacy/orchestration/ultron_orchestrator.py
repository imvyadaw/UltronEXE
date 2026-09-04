"""Top-level ULTRON goal orchestration.

The cognitive executor already owns the detailed plan/decompose/execute/
critique loop. This layer adds mission lifecycle, bounded outer recovery,
kill-switch checks, audit/memory recording, and defensive error handling.
"""

from typing import Any, Dict

from orchestration.goal_manager import GoalManager
from orchestration.execution_loop import ExecutionLoop
from orchestration.verification_loop import VerificationLoop
from orchestration.recovery_manager import RecoveryManager
from memory.memory_manager import MemoryManager
from security.kill_switch import KillSwitch
from security.audit_logger import AuditLogger


class UltronOrchestrator:
    MAX_ATTEMPTS = 2

    def __init__(self):
        from cognitive_core.autonomous_executor import AutonomousExecutor

        self.goals = GoalManager()
        self.executor = ExecutionLoop(AutonomousExecutor())
        self.verifier = VerificationLoop()
        self.recovery = RecoveryManager()
        self.memory = MemoryManager()
        self.kill = KillSwitch()
        self.audit = AuditLogger()

    @staticmethod
    def _safe_call(fn, *args, default=None, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            return default

    def run(self, text: str, quick: bool = False) -> Dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            return {"success": False, "error": "goal must be a non-empty string"}
        if self.kill.active():
            return {"success": False, "error": "kill switch active"}

        goal_text = text.strip()
        goal = self.goals.create(goal_text)
        self._safe_call(self.audit.record, "goal_started", {"goal": goal_text})
        self._safe_call(self.memory.record_event, "goal.started", {"goal": goal_text})

        attempts = 0
        result: Dict[str, Any] = {}
        current_goal = goal_text

        while attempts < self.MAX_ATTEMPTS:
            if self.kill.active():
                result = {
                    "goal": current_goal,
                    "satisfied": False,
                    "error": "kill switch activated during execution",
                }
                break

            attempts += 1
            try:
                result = self.executor.run(current_goal, quick=quick)
            except Exception as exc:
                result = {"goal": current_goal, "satisfied": False, "error": str(exc)}

            verification = self._safe_call(
                self.verifier.verify, result, default={"verified": False, "criteria": "verification error"}
            )
            if verification.get("verified", False):
                break

            if attempts < self.MAX_ATTEMPTS:
                recovery = self.recovery.recover(result, attempts)
                feedback = recovery.get("reason") or recovery.get("action")
                # Give the bounded second attempt explicit failure context
                # instead of silently repeating the exact same mission.
                if feedback:
                    current_goal = f"{goal_text}\n\nRecovery context from previous attempt: {feedback}"
                self._safe_call(
                    self.audit.record,
                    "goal_recovery",
                    {"goal": goal_text, "attempt": attempts, "feedback": feedback},
                    success=True,
                )

        ok = bool(result.get("satisfied", result.get("success", False)))
        self.goals.finish(goal, ok)
        self._safe_call(
            self.audit.record,
            "goal_finished",
            {"goal": goal_text, "attempts": attempts},
            success=ok,
        )
        self._safe_call(
            self.memory.record_experience,
            {"goal": goal_text, "result": result, "success": ok, "attempts": attempts},
        )

        return {
            "goal_id": goal.id,
            "goal": goal_text,
            "success": ok,
            "attempts": attempts,
            "result": result,
        }
