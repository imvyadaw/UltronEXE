class SystemIntegrator:
    def __init__(self):
        self.components = {}

    def add(self, name, obj):
        self.components[name] = obj

    def status(self):
        return {k: v is not None for k, v in self.components.items()}
