class KnowledgeBase:
    def __init__(self):
        self.docs = {}

    def add(self, key, content):
        self.docs[key] = content

    def get(self, key):
        return self.docs.get(key)
