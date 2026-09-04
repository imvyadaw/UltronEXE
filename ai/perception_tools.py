r"""
Perception tool wiring
=========================
perception/ (Phase 22) was a fully built, zero-external-references
package - `grep -rn "perception\." .` outside perception/ itself came
back empty before this file, same dormant-island bug class as
docs/TASK6_DORMANT_AUDIT.md's other 11 packages.

Each module wraps an already-wired subsystem (voice/, vision/,
monitoring/, proactive/monitors/) and offers two shapes of method:
  - a one-off snapshot/analyze/detect call - answers "what's true right
    now", same risk class as tools already wired elsewhere (e.g.
    get_system_info, describe_screen).
  - start_polling()/stop_polling() - a background thread that keeps
    reading on an interval, for continuous monitoring.

Only the one-off calls are wired here. The polling/continuous-
monitoring methods are deliberately NOT wired - turning any of these
into an always-on background watcher (especially voice/screen/emotion)
is a materially different, higher-sensitivity capability than "check
right now when asked", and per this project's own established practice
(docs/TASK6_DORMANT_AUDIT.md) that needs an explicit go-ahead first,
not a default-on wiring pass.

perception/voice_processor.py's listen_and_process() is also left
unwired here on purpose: it opens the mic itself, which would give the
model a second, harder-to-reason-about way to start listening
alongside the existing wake-word/voice-input pipeline that already
owns that decision. Its composite value (transcript + speaker ID +
emotion in one call) is real but out of scope for this pass - ask
explicitly if you want it wired too.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's _tool() - duplicated on
    purpose (see ai/new_skills_tools.py's docstring for why: avoids a
    circular import since tools_schema.py imports *from* this module)."""
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


_activity_monitor = None
_emotion_detector = None
_screen_analyzer = None
_system_listener = None


def _get_activity_monitor():
    global _activity_monitor
    if _activity_monitor is None:
        from perception.activity_monitor import ActivityMonitor

        _activity_monitor = ActivityMonitor()
    return _activity_monitor


def _get_emotion_detector():
    global _emotion_detector
    if _emotion_detector is None:
        from perception.emotion_detector import EmotionDetector

        _emotion_detector = EmotionDetector()
    return _emotion_detector


def _get_screen_analyzer():
    global _screen_analyzer
    if _screen_analyzer is None:
        from perception.screen_analyzer import ScreenAnalyzer

        _screen_analyzer = ScreenAnalyzer()
    return _screen_analyzer


def _get_system_listener():
    global _system_listener
    if _system_listener is None:
        from perception.system_listener import SystemListener

        _system_listener = SystemListener()
    return _system_listener


PERCEPTION_TOOLS = [
    _tool(
        "get_activity_snapshot",
        "One-off reading of what the user is currently doing: active window "
        "title and idle time, optionally the top CPU-consuming processes.",
        {"include_processes": {"type": "boolean", "description": "Also include top processes (slightly heavier)"}},
    ),
    _tool(
        "detect_text_emotion",
        "Analyze the emotional tone of a piece of text (e.g. what the user "
        "just typed or said) - sentiment/emotion label with confidence.",
        {"text": {"type": "string"}},
        ["text"],
    ),
    _tool(
        "analyze_screen",
        "Look at what's currently on screen and answer a question about it, "
        "or describe it if no question is given. Uses a vision-LLM read when "
        "available, falls back to OCR text.",
        {"question": {"type": "string", "description": "Defaults to a general description if omitted"}},
    ),
    _tool(
        "locate_on_screen",
        "Find where something is on screen right now, in pixel coordinates "
        "(needs the vision-LLM tier). Use for 'click the X button'-style "
        "grounding before a click/type automation.",
        {"target": {"type": "string", "description": "What to find, e.g. 'the Save button'"}},
        ["target"],
    ),
    _tool(
        "get_system_perception_snapshot",
        "One-off reading of machine load (CPU/RAM/disk) plus whether the " "machine is currently online.",
        {},
    ),
]


PERCEPTION_DIRECT_HANDLERS: Dict = {
    "get_activity_snapshot": lambda a: _get_activity_monitor().snapshot(
        include_processes=a.get("include_processes", False)
    ),
    "detect_text_emotion": lambda a: _get_emotion_detector().detect(text=a.get("text", "")),
    "analyze_screen": lambda a: _get_screen_analyzer().analyze(
        question=a.get("question", "Describe what's currently on screen.")
    ),
    "locate_on_screen": lambda a: _get_screen_analyzer().locate(a.get("target", "")),
    "get_system_perception_snapshot": lambda a: _get_system_listener().snapshot(),
}
