class SourceManager:
    def __init__(self):
        self.sources = {}

    def register(self, name, kind):
        self.sources[name] = kind

    def list(self):
        return dict(self.sources)
