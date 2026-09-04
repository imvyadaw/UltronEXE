class RiskEngine:
    def assess(self, action):
        a = action.lower()
        return (
            "HIGH"
            if any(x in a for x in ("delete", "format", "credential", "shutdown"))
            else ("MEDIUM" if any(x in a for x in ("write", "send", "execute")) else "LOW")
        )
