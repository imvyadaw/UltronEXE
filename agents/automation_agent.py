"""
Automation agent
================
Thin wrapper over input automation (keyboard/mouse/clipboard) and the
higher-level macro/workflow/scheduler modules, for direct control
without going through the LLM tool-calling loop.
"""

from automation.keyboard.keyboard import KeyboardControl
from automation.clipboard.clipboard import ClipboardControl
from automation.mouse.mouse import MouseControl
from automation.macro.macro import MacroRecorder
from automation.workflow.workflow import WorkflowRunner
from agents.base_agent import BaseAgent


class AutomationAgent(BaseAgent):
    capabilities = ["automation", "keyboard", "mouse", "macro", "workflow"]

    def __init__(self):
        super().__init__("automation", "Keyboard/mouse/clipboard control and macro/workflow playback")
        self.keyboard = KeyboardControl()
        self.clipboard = ClipboardControl()
        self.mouse = MouseControl()
        self.macro = MacroRecorder()
        self.workflow = WorkflowRunner()

    def run_workflow(self, workflow_name: str):
        return self.workflow.run_workflow(workflow_name)

    def play_macro(self, macro_name: str):
        return self.macro.play_macro(macro_name)
