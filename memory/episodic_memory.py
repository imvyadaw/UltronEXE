from memory.episodic_memory_legacy import EpisodicMemory


class EpisodicStore:
    def __init__(self):
        self.backend = EpisodicMemory()

    def record(self, event, context=None, tags=""):
        return self.backend.record_event(event, str(context or ""), tags)

    def recent(self, n=20):
        return self.backend.recent_events(n)
