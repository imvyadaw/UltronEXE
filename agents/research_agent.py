class ResearchAgent:
    def __init__(self):
        from agents.web_agent import WebAgent

        self.backend = WebAgent()

    def describe(self):
        return {"name": "research", "backend": "ULTRON WebAgent"}
