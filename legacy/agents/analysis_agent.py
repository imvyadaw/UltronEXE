class AnalysisAgent:
    def analyze(self, data):
        return {"summary": str(data)[:10000], "evidence_only": True}
