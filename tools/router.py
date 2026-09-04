class ToolRouter:
    def __init__(self, registry):
        self.registry = registry

    def select(self, task):
        t = task.lower()
        return next((x for x in self.registry.list() if x["name"].replace("_", " ") in t), None)
