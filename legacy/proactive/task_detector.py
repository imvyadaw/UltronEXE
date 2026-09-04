class TaskDetector:
    def detect(self, events):
        return [e for e in events if e.get("status") in ("pending", "overdue")]
