class OpportunityFinder:
    def find(self, items):
        return sorted(items, key=lambda x: x.get("value", 0), reverse=True)
