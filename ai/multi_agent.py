"""
Multi-agent orchestrator
=========================
Routes a request to the right specialist in agents/ (web, email,
calendar, task, health, security, plus the existing browser/coding/
vision/windows/automation/memory agents) and can chain several agents
together for a compound request ("check my calendar, then email me a
summary"). Agents are imported lazily so this module has no hard
dependency on optional integrations (e.g. email needs EMAIL_ADDRESS
configured, but importing multi_agent.py shouldn't fail if it isn't).
"""

from typing import Dict, List


class MultiAgentOrchestrator:
    """Lazily-instantiated registry of agents, plus simple keyword routing."""

    # agent name -> (module path, class name)
    _AGENT_PATHS = {
        "web": ("agents.web_agent", "WebAgent"),
        "email": ("agents.email_agent", "EmailAgent"),
        "calendar": ("agents.calendar_agent", "CalendarAgent"),
        "task": ("agents.task_agent", "TaskAgent"),
        "health": ("agents.health_agent", "HealthAgent"),
        "security": ("agents.security_agent", "SecurityAgent"),
        "memory": ("agents.memory_agent", "MemoryAgent"),
        "browser": ("agents.browser_agent", "BrowserAgent"),
        "windows": ("agents.windows_agent", "WindowsAgent"),
        "automation": ("agents.automation_agent", "AutomationAgent"),
        "coding": ("agents.coding_agent", "CodingAgent"),
        "vision": ("agents.vision_agent", "VisionAgent"),
    }

    # Keywords used for zero-cost routing before falling back to the LLM.
    _ROUTE_KEYWORDS = {
        "web": ("search", "google", "internet", "browse", "website", "weather"),
        "email": ("email", "inbox", "gmail", "mail"),
        "calendar": ("calendar", "schedule", "meeting", "appointment", "event"),
        "task": ("todo", "to-do", "task list", "remind me to"),
        "health": ("water", "sleep", "exercise", "workout", "mood", "break"),
        "security": ("password", "permission", "secure", "secret", "vulnerab"),
        "memory": ("remember", "recall", "note", "forget"),
        "coding": ("code", "function", "bug", "script", "program"),
        "vision": ("screen", "screenshot", "see", "detect"),
    }

    def __init__(self):
        self._instances: Dict[str, object] = {}

    def get_agent(self, name: str):
        """Instantiate (once) and return the agent for `name`."""
        if name not in self._AGENT_PATHS:
            raise KeyError(f"Unknown agent: {name}")
        if name not in self._instances:
            module_path, class_name = self._AGENT_PATHS[name]
            import importlib

            module = importlib.import_module(module_path)
            self._instances[name] = getattr(module, class_name)()
        return self._instances[name]

    def route(self, message: str) -> Dict:
        """Guess which agent(s) a free-text message is about, via keyword
        overlap - fast, offline, no LLM call."""
        message_l = message.lower()
        matches: List[str] = []
        for agent_name, keywords in self._ROUTE_KEYWORDS.items():
            if any(kw in message_l for kw in keywords):
                matches.append(agent_name)
        return {"message": message, "matched_agents": matches}

    def dispatch(self, agent_name: str, method: str, *args, **kwargs) -> Dict:
        """Call `method` on the named agent with the given arguments."""
        try:
            agent = self.get_agent(agent_name)
            if not hasattr(agent, method):
                return {"error": f"Agent '{agent_name}' has no method '{method}'"}
            return getattr(agent, method)(*args, **kwargs)
        except Exception as e:
            return {"error": str(e)}

    def run_chain(self, steps: List[Dict]) -> Dict:
        """Run several agent calls in order. Each step is
        {"agent": str, "method": str, "args": [...], "kwargs": {...}}.
        Stops and reports the failure if any step errors."""
        results = []
        for i, step in enumerate(steps):
            agent_name = step.get("agent")
            method = step.get("method")
            args = step.get("args", [])
            kwargs = step.get("kwargs", {})
            result = self.dispatch(agent_name, method, *args, **kwargs)
            results.append({"step": i, "agent": agent_name, "method": method, "result": result})
            if isinstance(result, dict) and "error" in result:
                return {"completed": False, "failed_at_step": i, "results": results}
        return {"completed": True, "results": results}


_orchestrator = None


def get_orchestrator() -> MultiAgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MultiAgentOrchestrator()
    return _orchestrator
