class Conversation:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    def handle(self, text):
        return self.orchestrator.run(text)
