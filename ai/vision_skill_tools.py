"""
Camera+vision skill tool wiring
=================================
skills/vision/camera_skill.py (VisionSkill) is a real, working facade -
but skills/ itself is never imported by the AI tool-calling loop (see
ai/tools_schema.py/ai/tool_runtime.py's dispatch, which core/executor.py
and every ai/*_tools.py module call into directly instead). Without a
tools_schema.py entry + tool_runtime.py dispatch entry, this would be
the exact same "Unknown tool" bug class already found and fixed for 33+
tools elsewhere in this project (see ai/self_management_tools.py,
ai/vision_agent_tools.py, etc.) - so it's wired here from day one instead
of shipping it already-orphaned.

Calls skills/vision/vision_engine.py's VisionEngine, object_detector.py's
CameraObjectDetector, ocr_engine.py's CameraOCR, and scene_analyzer.py's
SceneAnalyzer directly rather than round-tripping through their
BaseSkill facades' execute(action, **kwargs) dict-dispatch - same choice
ai/vision_agent_tools.py made for VisionAgent.

6 tools, deliberately not more:
  - camera_see            - capture + describe in one call (the common
                             case: "what do you see", "what's in front
                             of me")
  - camera_snapshot        - capture only, no description (e.g. "take a
                             photo")
  - camera_status          - "is my webcam working" / "is vision set up" -
                             checks camera, local vision-model, AND
                             remote (Gemini) vision availability
                             separately so the answer can say exactly
                             which one is missing
  - camera_detect_objects  - "what objects are in front of me" - 80-class
                             YOLOv8n detection on a fresh camera frame
  - camera_read_text       - "read this label/page/sign" - Tesseract OCR
                             on a fresh camera frame
  - camera_analyze_scene   - description + objects + text together, from
                             ONE shared capture - use when the user wants
                             the fuller picture rather than one of the
                             three narrower tools above (and to avoid
                             three separate frames possibly disagreeing)

Distinct from the existing screen-based Vision:OCR tools
(read_screen_text/detect_faces_on_screen/detect_objects_on_screen,
describe_screen) and from VISION_AGENT_TOOLS (enroll_face/
recognize_faces/find_icon_buttons/screen recording) - those all look at
the screen. These six look through the physical camera instead.
"""

from typing import Dict


def _engine():
    from skills.vision.vision_engine import get_vision_engine

    return get_vision_engine()


def _object_detector():
    from skills.vision.object_detector import get_camera_object_detector

    return get_camera_object_detector()


def _ocr():
    from skills.vision.ocr_engine import get_camera_ocr

    return get_camera_ocr()


def _scene_analyzer():
    from skills.vision.scene_analyzer import get_scene_analyzer

    return get_scene_analyzer()


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


VISION_SKILL_TOOLS = [
    _tool(
        "camera_see",
        "Look through the physical webcam right now and describe what it sees, in plain "
        'language. Use this for "what do you see"/"what\'s in front of me"/"look at this" - '
        "the actual camera, NOT the screen (use describe_screen for the screen instead). "
        "Requires a webcam plus a vision backend: tries the local model (Ollama + LLaVA) "
        "first, falls back to Gemini if that's unavailable; if neither is set up, this "
        "returns a clear error instead of guessing.",
        {
            "prompt": {
                "type": "string",
                "description": "Optional - what to focus on describing (e.g. 'is anyone at the door', "
                "'read any text visible'). Omit for a general description.",
            }
        },
    ),
    _tool(
        "camera_snapshot",
        "Take a photo with the physical webcam and save it, without describing it. Use this "
        'for "take a photo"/"snap a picture", not for describing what\'s currently visible '
        "(use camera_see for that).",
        {
            "save_path": {
                "type": "string",
                "description": "Optional file path to save the photo to. Omit to auto-generate a " "timestamped path.",
            }
        },
    ),
    _tool(
        "camera_status",
        "Check whether the physical camera, the local vision model, and the remote (Gemini) "
        "vision backend are each currently available, separately (so a failure can say exactly "
        "which one is missing). Use before camera_see if the user is troubleshooting, or when "
        'asked "is my camera/vision working".',
    ),
    _tool(
        "camera_detect_objects",
        "Detect objects visible to the physical webcam right now (80 COCO classes: person, "
        'car, dog, laptop, chair, etc. via YOLOv8n). Use for "what objects are in front of '
        'me"/"is there a person there" - the actual camera, NOT the screen (use '
        "detect_objects_on_screen for the screen instead).",
        {
            "confidence_threshold": {
                "type": "number",
                "description": "Optional minimum detection confidence, 0-1. Omit to use the default (0.4).",
            }
        },
    ),
    _tool(
        "camera_read_text",
        'Read any text visible to the physical webcam right now, via OCR. Use for "read this '
        'label/page/sign" - the actual camera, NOT the screen (use read_screen_text for the '
        "screen instead).",
        {
            "lang": {
                "type": "string",
                "description": "Optional Tesseract language code (e.g. 'eng', 'hin'). Omit to default to English.",
            }
        },
    ),
    _tool(
        "camera_analyze_scene",
        "Capture one frame from the physical webcam and return description + object detection "
        "+ text (OCR) together, all from that same frame. Use when the user wants the fuller "
        "picture of what's in front of them rather than just a description, just objects, or "
        'just text - e.g. "tell me everything you see", "analyze the scene".',
        {
            "prompt": {
                "type": "string",
                "description": "Optional - what to focus the description part on. Omit for a general description.",
            },
            "confidence_threshold": {
                "type": "number",
                "description": "Optional minimum object-detection confidence, 0-1. Omit to use the default (0.4).",
            },
        },
    ),
]

VISION_SKILL_DIRECT_HANDLERS: Dict = {
    "camera_see": lambda a: _engine().see(prompt=a.get("prompt")),
    "camera_snapshot": lambda a: _engine().snapshot(save_path=a.get("save_path")),
    "camera_status": lambda a: _engine().status(),
    "camera_detect_objects": lambda a: _object_detector().detect(
        confidence_threshold=a.get("confidence_threshold", 0.4)
    ),
    "camera_read_text": lambda a: _ocr().read(lang=a.get("lang", "eng")),
    "camera_analyze_scene": lambda a: _scene_analyzer().analyze(
        prompt=a.get("prompt"), confidence_threshold=a.get("confidence_threshold", 0.4)
    ),
}
