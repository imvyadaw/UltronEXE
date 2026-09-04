class PatternAnalyzer:
    def summarize(self, records):
        n = len(records)
        return {"count": n, "success_rate": sum(bool(x.get("success")) for x in records) / max(1, n)}
