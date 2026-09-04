from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory
from memory.episodic_memory import EpisodicStore
from memory.knowledge_graph import KnowledgeGraph
from memory.experience_store import ExperienceStore


class MemoryManager:
    def __init__(self):
        self.short = ShortTermMemory()
        self.long = LongTermMemory()
        self.episodic = EpisodicStore()
        self.graph = KnowledgeGraph()
        self.experiences = ExperienceStore()

    def record_event(self, e, c=None):
        self.short.add({"event": e, "context": c})
        return self.episodic.record(e, c)

    def record_experience(self, x):
        self.short.add(x)
        return self.experiences.add(x)

    def recall(self, n=10):
        return {"recent": self.short.recent(n), "experiences": self.experiences.recent(n)}
