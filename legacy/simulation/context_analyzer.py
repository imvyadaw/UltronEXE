class ContextAnalyzer:
    def analyze(self, goal, signals=None):
        return {"goal": goal, "signals": signals or []}
