class VerificationLoop:
    def verify(self, result, criteria=""):
        ok = bool(result.get("satisfied", result.get("success", False))) if isinstance(result, dict) else bool(result)
        return {"verified": ok, "criteria": criteria}
