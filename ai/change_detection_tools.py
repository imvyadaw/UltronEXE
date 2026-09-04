"""
Change-detection skill tool wiring
=====================================
skills/vision/change_detection_skill.py (ChangeDetectionSkill) is a real,
working facade - but skills/ itself is never imported by the AI
tool-calling loop (see ai/tools_schema.py/ai/tool_runtime.py's dispatch).
Without a tools_schema.py entry + tool_runtime.py dispatch entry this
would ship already-orphaned, same bug class documented in
ai/vision_skill_tools.py's docstring - so it's wired here from day one.

Calls skills/vision/change_detector.py's ChangeDetector directly rather
than round-tripping through the BaseSkill facade's execute(action,
**kwargs) dict-dispatch - same choice ai/vision_skill_tools.py made for
VisionEngine/CameraObjectDetector/CameraOCR/SceneAnalyzer.

4 tools:
  - camera_set_change_baseline - "remember what it looks like right now" -
                                  capture a frame and store it as the
                                  reference point for future checks
  - camera_check_change        - "has anything changed" - capture a new
                                  frame, diff it against the stored
                                  baseline, report changed/not + percent.
                                  The new frame becomes the baseline for
                                  the *next* check.
  - camera_change_status        - is a baseline set, when, camera available
  - camera_change_history        - recent detected-change events

Distinct from camera_see/camera_analyze_scene (ai/vision_skill_tools.py):
those describe *what* the camera currently sees; these only answer
*whether* the scene has changed since a reference point, which is a
different (cheaper, no vision-model-required) question.
"""

from typing import Dict


def _detector():
    from skills.vision.change_detector import get_change_detector

    return get_change_detector()


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


CHANGE_DETECTION_TOOLS = [
    _tool(
        "camera_set_change_baseline",
        "Capture a frame from the physical webcam right now and remember it as the reference "
        'point for future change checks. Use this when the user says something like "remember '
        'how this looks"/"start watching"/"keep an eye on this" before they later ask '
        '"has anything changed".',
    ),
    _tool(
        "camera_check_change",
        "Capture a new frame from the physical webcam and check whether the scene has changed "
        "since the last baseline/check (a percentage of pixels differing beyond normal camera "
        'noise). Use for "has anything changed"/"did anything move"/"what changed while I '
        'was gone". Requires camera_set_change_baseline to have been called first - if not, '
        "this returns a clear error saying so instead of guessing. Each check becomes the new "
        "baseline for the next one.",
        {
            "threshold_percent": {
                "type": "number",
                "description": "Optional minimum changed-pixel percentage to count as a real change. "
                "Omit to use the configured default.",
            }
        },
    ),
    _tool(
        "camera_change_status",
        "Check whether a change-detection baseline is currently set, when it was set, and "
        'whether the camera is available. Use when the user asks "is change detection running" '
        "or before camera_check_change if troubleshooting.",
    ),
    _tool(
        "camera_change_history",
        "List the most recent detected change events (timestamp, change percentage, snapshot "
        'path). Use for "what changed earlier"/"show me the change log".',
        {
            "limit": {
                "type": "integer",
                "description": "Optional max number of recent events to return. Omit to use the default (10).",
            }
        },
    ),
]

CHANGE_DETECTION_DIRECT_HANDLERS: Dict = {
    "camera_set_change_baseline": lambda a: _detector().set_baseline(),
    "camera_check_change": lambda a: _detector().check(threshold_percent=a.get("threshold_percent")),
    "camera_change_status": lambda a: _detector().status(),
    "camera_change_history": lambda a: _detector().history(limit=a.get("limit", 10)),
}
