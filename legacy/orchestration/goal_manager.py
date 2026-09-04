from ULTRON_CORE.common import Goal


class GoalManager:
    def create(self, text):
        return Goal(text)

    def finish(self, g, ok):
        g.status = "completed" if ok else "failed"
        return g
