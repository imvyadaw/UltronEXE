class VerificationAgent:
    def verify(self, result, criteria=None):
        return {
            "verified": (
                bool(result.get("satisfied", result.get("success", False)))
                if isinstance(result, dict)
                else bool(result)
            ),
            "criteria": criteria,
        }
