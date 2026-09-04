class ProblemPreventer:
    def analyze(self, signals):
        return [s for s in signals if s.get("risk", 0) >= 0.7]
