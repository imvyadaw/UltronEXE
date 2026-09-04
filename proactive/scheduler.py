class ProactiveScheduler:
    def due(self, items):
        return [x for x in items if x.get("due")]
