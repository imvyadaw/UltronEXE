import importlib


class HealthCheck:
    def run(self):
        c = {}
        for m in ("core.brain", "ai.ai_router", "core.workflow_engine", "voice", "cognitive_core.autonomous_executor"):
            try:
                importlib.import_module(m)
                c[m] = True
            except Exception:
                c[m] = False
        return {"healthy": all(c.values()), "checks": c}
