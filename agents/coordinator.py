class Coordinator:
    def assign(self, task):
        t = task.lower()
        if any(x in t for x in ("code", "bug", "implement")):
            return "coding"
        if any(x in t for x in ("research", "search", "investigate")):
            return "research"
        if "test" in t:
            return "testing"
        return "analysis"
