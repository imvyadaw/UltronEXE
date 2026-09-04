"""
Vision-agent tool wiring
==========================
agents/vision_agent.py (VisionAgent) is a real, fully-implemented
9-method wrapper around screen OCR/face/object/UI-icon detection and
screen recording - but it was reachable only through
ai/multi_agent.py's orchestrator.dispatch(), which nothing in the
AI tool-calling loop ever calls. It had no ai/tools_schema.py entry at
all, so the model didn't even know these capabilities existed.

4 of its 9 methods (read_text, detect_faces, detect_objects, and see's
overlap with describe_screen) duplicate tools that already work through
a separate, simpler backend (see ai/tools_schema.py's "Vision: OCR"
section: read_screen_text/detect_faces_on_screen/detect_objects_on_screen,
wired via core/executor.py) - those are intentionally NOT re-added here
to avoid giving the model two different tools that claim to do the same
thing. Only VisionAgent's genuinely new capabilities are wired:

  - enroll_face / recognize_faces - naming a specific person from a
    reference photo and later identifying them on screen (the existing
    detect_faces_on_screen only counts/locates faces, it never says who)
  - find_icon_buttons - locating icon-only UI buttons that have no text
    label for OCR to find (useful for click_ui_element-style tasks where
    the target is a toolbar icon, not a labeled button)
  - start_recording / stop_recording - screen video recording, which
    nothing else in the tool set does at all

Reuses ai.multi_agent's orchestrator (get_orchestrator().get_agent
("vision")) for the lazy singleton instead of importing VisionAgent
directly, so this stays in sync with whatever the orchestrator already
does for agent construction/caching.
"""

from typing import Dict


def _agent():
    from ai.multi_agent import get_orchestrator

    return get_orchestrator().get_agent("vision")


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


VISION_AGENT_TOOLS = [
    _tool(
        "enroll_face",
        "Teach Ultron to recognize a specific named person, so recognize_faces can later "
        "identify them by name instead of just detecting an unnamed face. Uses the current "
        "screen (e.g. a paused video call frame) unless a reference photo file path is given.",
        {
            "name": {"type": "string", "description": "The person's name."},
            "file_path": {
                "type": "string",
                "description": "Optional path to a reference photo. Omit to use the current screen.",
            },
        },
        ["name"],
    ),
    _tool(
        "recognize_faces",
        "Identify WHO is currently visible on screen, by matching against people previously "
        "enrolled with enroll_face. Use this (not detect_faces_on_screen) when the user asks "
        "who is on a call/photo, not just how many faces are there.",
    ),
    _tool(
        "find_icon_buttons",
        "Locate icon-only UI buttons on the current screen - toolbar icons, close/minimize "
        "buttons, and other clickable elements that have no visible text for OCR to find. Use "
        "this before click_ui_element when the target is described by appearance/position "
        "rather than a label.",
    ),
    _tool(
        "start_screen_recording",
        "Start recording the screen to a video file.",
        {
            "filepath": {"type": "string", "description": "Output .mp4 file path."},
            "duration_seconds": {
                "type": "number",
                "description": "Optional - stop automatically after this many seconds. Omit to record until stop_screen_recording is called.",
            },
        },
        ["filepath"],
    ),
    _tool(
        "stop_screen_recording",
        "Stop an in-progress screen recording started with start_screen_recording.",
    ),
]

VISION_AGENT_DIRECT_HANDLERS: Dict = {
    "enroll_face": lambda a: _agent().enroll_face(a.get("name", ""), file_path=a.get("file_path")),
    "recognize_faces": lambda a: _agent().recognize_faces(),
    "find_icon_buttons": lambda a: _agent().find_icon_buttons(),
    "start_screen_recording": lambda a: _agent().start_recording(
        a.get("filepath", ""), duration_seconds=a.get("duration_seconds")
    ),
    "stop_screen_recording": lambda a: _agent().stop_recording(),
}
