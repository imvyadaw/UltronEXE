"""
Automation package
====================
Phase 5: every automation category exposes one BaseSkill-derived facade
(see skills/base_skill.py) - workflow/engine.py, scheduler (wrapped
in-place below, task_scheduler.py itself is unchanged), macro/recorder.py
+ player.py, mouse/controller.py, keyboard/controller.py,
clipboard/manager.py, ui/element_finder.py, RPA/desktop_rpa.py +
web_rpa.py, triggers/event_triggers.py, and conditions/logic_conditions.py
- so callers can look a facade up by name through
get_automation()/execute_automation() instead of importing each
category's internals directly. Mirrors skills/__init__.py's registry.

Construction is lazy: importing `automation` does NOT import every
facade (and therefore doesn't require every optional dependency -
pynput, pyautogui, pywinauto, watchdog, psutil, selenium, ... - to be
installed up front). A given facade's real import/construction error
only surfaces the first time that specific facade is actually requested.

Example:
    from automation import get_automation, execute_automation

    result = execute_automation("mouse_controller", "click", x=100, y=200)
    workflow = get_automation("workflow_engine")
    workflow.execute("run", workflow_name="morning_routine")
"""

from typing import Dict, List

from skills.base_skill import BaseSkill

# name -> zero-arg callable returning the facade's class (imported
# lazily, on first get_automation() call, so a missing optional
# dependency for one facade can't break importing the whole package).
_LOADERS = {
    "workflow_engine": lambda: _load("automation.workflow.engine", "WorkflowEngine"),
    "scheduler": lambda: _SchedulerSkill,
    "macro_recorder": lambda: _load("automation.macro.recorder", "MacroRecorderSkill"),
    "macro_player": lambda: _load("automation.macro.player", "MacroPlayerSkill"),
    "mouse_controller": lambda: _load("automation.mouse.controller", "MouseControllerSkill"),
    "keyboard_controller": lambda: _load("automation.keyboard.controller", "KeyboardControllerSkill"),
    "clipboard_manager": lambda: _load("automation.clipboard.manager", "ClipboardManagerSkill"),
    "ui_element_finder": lambda: _load("automation.ui.element_finder", "ElementFinderSkill"),
    "desktop_rpa": lambda: _load("automation.RPA.desktop_rpa", "DesktopRPASkill"),
    "web_rpa": lambda: _load("automation.RPA.web_rpa", "WebRPASkill"),
    "event_triggers": lambda: _load("automation.triggers.event_triggers", "EventTriggersSkill"),
    "logic_conditions": lambda: _load("automation.conditions.logic_conditions", "LogicConditionsSkill"),
}

_instances: Dict[str, BaseSkill] = {}


def _load(module_path: str, class_name: str):
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)


class _SchedulerSkill(BaseSkill):
    """BaseSkill wrapper around automation/scheduler/task_scheduler.py's
    singleton TaskScheduler - kept here rather than as its own file since
    task_scheduler.py already IS the requested facade filename."""

    name = "scheduler"
    description = "Run a callback after a delay, at a specific time, or on a repeating interval."
    category = "automation"

    def __init__(self):
        from automation.scheduler.task_scheduler import get_scheduler

        self._scheduler = get_scheduler()
        super().__init__()

    def register_actions(self) -> None:
        s = self._scheduler
        self._actions = {
            "run_after": s.run_after,
            "run_at": s.run_at,
            "run_every": s.run_every,
            "cancel": s.cancel,
            "list_tasks": s.list_tasks,
            "shutdown": s.shutdown,
        }


def list_automations() -> List[str]:
    """Names of every registered automation facade (whether or not it's been constructed yet)."""
    return sorted(_LOADERS.keys())


def get_automation(name: str) -> BaseSkill:
    """Return a cached instance of the named automation facade, importing
    and constructing it on first use. Raises KeyError for an unknown
    name, or whatever error the facade's own import/constructor raises
    (e.g. a missing optional dependency) the first time it's built."""
    if name not in _LOADERS:
        raise KeyError(f"Unknown automation '{name}'. Available: {', '.join(list_automations())}")
    if name not in _instances:
        facade_cls = _LOADERS[name]()
        _instances[name] = facade_cls()
    return _instances[name]


def execute_automation(name: str, action: str, **kwargs) -> Dict:
    """Convenience one-liner: get_automation(name).execute(action, **kwargs).
    Lookup/construction failures are wrapped in the same result-dict shape
    every facade action already returns."""
    try:
        facade = get_automation(name)
    except Exception as e:
        return {"success": False, "error": str(e), "_skill": name, "_action": action}
    return facade.execute(action, **kwargs)


def describe_all() -> List[Dict]:
    """Describe every registered automation facade (name, category,
    description, available actions). Constructs any facade not yet
    instantiated, so one missing an optional dependency shows up as an
    error entry instead of raising."""
    out = []
    for name in list_automations():
        try:
            out.append(get_automation(name).describe())
        except Exception as e:
            out.append({"name": name, "error": str(e)})
    return out
