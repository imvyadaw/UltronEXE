"""
Base agent
==========
Common base class for everything in agents/: a focused wrapper around
one subsystem (browser, windows, memory, vision, ...) exposing a
handful of direct-call methods for use without going through the LLM
tool-calling loop (core/executor.py is the tool-calling path; agents/
is the "just call it from code" path - both end up hitting the same
underlying skills/windows/browser/etc. modules underneath).

Doesn't force much structure - every agents/ class is still just
__init__ + a few plain methods, whatever makes sense for what it wraps
- but gives every agent, for free:

  - a shared, correctly-namespaced logger (self.logger, via
    core.logger.get_logger("ultron.agents.<name>"))
  - a consistent error shape for calls that might raise
    (self.safe_call wraps a callable and returns {"error": str(e)} on
    exception instead of propagating it, matching the
    {"result": ...} / {"error": ...} dict shape agents/coding_agent.py
    and agents/email_agent.py already return directly)
  - describe(), so router.skill_router (or a future agent registry)
    can list what an agent is for and what it claims to handle without
    needing to import every skills/* backend an agent's __init__
    might otherwise pull in

Subclass it and call super().__init__("name", "one-line description")
from your own __init__ - that's the entire contract.
"""

from typing import Any, Callable, Dict, List

from core.logger import get_logger


class BaseAgent:
    """Common parent for agents/*.py. See module docstring."""

    #: Short capability tags for router.skill_router / a future agent
    #: registry to match a message against, e.g. ["email", "gmail",
    #: "outlook"]. Override as a class attribute in each subclass;
    #: defaults to empty (agent just won't be matched by tag lookups).
    capabilities: List[str] = []

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.logger = get_logger(f"ultron.agents.{name}")

    def safe_call(self, fn: Callable, *args, **kwargs) -> Dict[str, Any]:
        """Run `fn(*args, **kwargs)`, catching any exception, logging it,
        and returning {"error": str(e)} instead of letting it propagate.
        If `fn` already returns a dict (most agent methods do), it's
        passed through unchanged; any other return value is wrapped as
        {"result": <value>}. Optional - existing agent methods that
        already return their own {"error": ...} dicts don't need to
        route through this to stay consistent.
        """
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            self.logger.error(f"{self.name}: {getattr(fn, '__name__', fn)} failed: {e}")
            return {"error": str(e)}
        if isinstance(result, dict):
            return result
        return {"result": result}

    def describe(self) -> Dict[str, Any]:
        """What this agent is for - name, description, capability tags -
        without requiring the caller to have constructed (or even fully
        imported) it first."""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": list(self.capabilities),
        }
