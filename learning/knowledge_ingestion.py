import hashlib


class KnowledgeIngestion:
    def __init__(self):
        self.seen = set()

    def ingest(self, source, content):
        h = hashlib.sha256(str(content).encode()).hexdigest()
        if h in self.seen:
            return {"accepted": False, "duplicate": True}
        self.seen.add(h)
        return {"accepted": True, "source": source, "content": str(content)}
