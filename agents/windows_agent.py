"""
Windows agent
=============
Thin wrapper over the windows/ facade for callers that want direct
Windows control without going through the LLM tool-calling loop.
"""

from windows import get_system_tools
from agents.base_agent import BaseAgent


class WindowsAgent(BaseAgent):
    capabilities = ["windows", "system", "apps", "processes"]

    def __init__(self):
        super().__init__("windows", "Windows system/app control")
        self.tools = get_system_tools()

    def open_app(self, name: str):
        return self.tools.open_application(name)

    def close_app(self, name: str):
        return self.tools.close_application(name)
