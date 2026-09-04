"""Bounded recovery policy for failed ULTRON missions."""


class RecoveryManager:
    def recover(self, result, attempt):
        if not isinstance(result, dict):
            reason = "verification_failed"
        else:
            reason = result.get("error") or result.get("stopped_reason") or "verification_failed"
        return {
            "action": "replan_and_retry",
            "attempt": attempt,
            "reason": str(reason),
        }
