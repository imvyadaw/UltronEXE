"""
Skills package
===============
Phase 4: every skill category now exposes one BaseSkill-derived facade -
app_control/controller.py, email/handler.py, calendar/manager.py,
web/scraper.py (WebScraperSkill), data/processor.py,
communication/messaging.py, browser/automation.py, windows/manager.py,
utilities/tools.py, and vision/camera_skill.py - so callers can look a skill up by name through
get_skill()/execute_skill() instead of importing each category's
internals directly.

Construction is lazy: importing `skills` does NOT import every facade
(and therefore doesn't require every optional dependency - google-api-
python-client, msal, openpyxl, bs4, pygetwindow, ... - to be installed
up front). A given skill's real import/construction error only surfaces
the first time that specific skill is actually requested.

Example:
    from skills import get_skill, execute_skill

    result = execute_skill("app_control", "open", app_name="notepad")
    # or, keeping a handle to reuse:
    email = get_skill("email")
    email.execute("send", to="a@b.com", subject="Hi", body="...")
"""

from typing import Dict, List

from skills.base_skill import BaseSkill

# name -> zero-arg callable returning the skill's class (imported lazily,
# on first get_skill() call, so a missing optional dependency for one
# skill can't break importing the whole `skills` package).
_LOADERS = {
    "app_control": lambda: _load("skills.app_control.controller", "AppController"),
    "email": lambda: _load("skills.email.handler", "EmailHandler"),
    "calendar": lambda: _load("skills.calendar.manager", "CalendarManager"),
    "web_scraper": lambda: _load("skills.web.scraper", "WebScraperSkill"),
    "data_processor": lambda: _load("skills.data.processor", "DataProcessor"),
    "messaging": lambda: _load("skills.communication.messaging", "MessagingHandler"),
    "browser_automation": lambda: _load("skills.browser.automation", "BrowserAutomationSkill"),
    "windows_manager": lambda: _load("skills.windows.manager", "WindowsManager"),
    "utilities": lambda: _load("skills.utilities.tools", "UtilityTools"),
    "vision": lambda: _load("skills.vision.camera_skill", "VisionSkill"),
    "camera_object_detection": lambda: _load("skills.vision.object_detection_skill", "CameraObjectDetectionSkill"),
    "camera_ocr": lambda: _load("skills.vision.ocr_skill", "CameraOCRSkill"),
    "camera_scene": lambda: _load("skills.vision.scene_skill", "CameraSceneSkill"),
    "camera_change_detection": lambda: _load("skills.vision.change_detection_skill", "ChangeDetectionSkill"),
}

_instances: Dict[str, BaseSkill] = {}


def _load(module_path: str, class_name: str):
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)


def list_skills() -> List[str]:
    """Names of every registered skill (whether or not it's been constructed yet)."""
    return sorted(_LOADERS.keys())


def get_skill(name: str) -> BaseSkill:
    """Return a cached instance of the named skill, importing and
    constructing it on first use. Raises KeyError for an unknown name, or
    whatever error the skill's own import/constructor raises (e.g. a
    missing optional dependency) the first time it's built."""
    if name not in _LOADERS:
        raise KeyError(f"Unknown skill '{name}'. Available: {', '.join(list_skills())}")
    if name not in _instances:
        skill_cls = _LOADERS[name]()
        _instances[name] = skill_cls()
    return _instances[name]


def execute_skill(name: str, action: str, **kwargs) -> Dict:
    """Convenience one-liner: get_skill(name).execute(action, **kwargs).
    Lookup/construction failures are wrapped in the same result-dict shape
    every skill action already returns, so callers never need a separate
    try/except just to handle "skill not available"."""
    try:
        skill = get_skill(name)
    except Exception as e:
        return {"success": False, "error": str(e), "_skill": name, "_action": action}
    return skill.execute(action, **kwargs)


def describe_all() -> List[Dict]:
    """Describe every registered skill (name, category, description,
    available actions). Constructs any skill not yet instantiated, so a
    skill missing an optional dependency shows up as an error entry
    instead of raising."""
    out = []
    for name in list_skills():
        try:
            out.append(get_skill(name).describe())
        except Exception as e:
            out.append({"name": name, "error": str(e)})
    return out
