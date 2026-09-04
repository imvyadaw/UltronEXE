class FeedbackEngine:
    def score(self, expected, actual):
        return {"match": expected == actual, "expected": expected, "actual": actual}
