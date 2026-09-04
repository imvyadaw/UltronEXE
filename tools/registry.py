import logging
class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name, handler, description="", risk="LOW"):
        self.tools[name] = {"handler": handler, "description": description, "risk": risk}

    def get(self, name):
        return self.tools.get(name)

    def list(self):
        return [{"name": k, "description": v["description"], "risk": v["risk"]} for k, v in self.tools.items()]

    def discover_ultron(self):
        import importlib

        for n, m in {
            "ultron_brain": "core.brain",
            "ultron_router": "ai.ai_router",
            "ultron_workflow": "core.workflow_engine",
        }.items():
            try:
                self.tools[n] = {
                    "handler": importlib.import_module(m),
                    "description": "Existing ULTRON subsystem",
                    "risk": "LOW",
                }
            except Exception:
                logging.getLogger(__name__).exception("Suppressed Exception")
        return self.list()
