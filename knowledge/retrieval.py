class Retrieval:
    def search(self, docs, query, limit=5):
        return [(k, v) for k, v in docs.items() if query.lower() in str(v).lower()][:limit]
