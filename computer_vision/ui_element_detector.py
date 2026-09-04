"""
UI element detector
======================
Classifies each raw element from omni_parser.py's merged parse as one of
a small set of interaction-relevant kinds - button / link / text_field /
label / icon_button - using cheap box-shape and text-pattern heuristics,
no additional model. This is the "what is it" layer omni_parser.py's own
docstring calls out as deliberately separate from "where is it".

Heuristics (all best-effort, matching this project's existing "coarse
but zero-dependency" stance for anything without a bundled model - see
vision/scene_understanding.py, voice/emotion_detection.py):
  - short text (<=3 words), roughly button-shaped box (wide, not tall,
    aspect ratio in a normal button range) -> "button"
  - text that looks like a URL or starts with an underline-worthy verb
    pattern is left to the caller; here just aspect+brevity -> "link" is
    not reliably distinguishable from "button" by shape alone, so link
    detection instead keys on common link-ish words (more/details/here/
    learn) layered on the button shape check
  - very wide, short, mostly-empty-looking box with no text of its own
    but adjacent to a text label -> "text_field" (inferred from the icon
    detector's blank rectangular candidates)
  - icon-kind elements from omni_parser -> "icon_button"
  - anything else with text -> "label"
"""

from typing import Dict, List, Optional

from computer_vision.omni_parser import get_omni_parser

_LINK_WORDS = {"more", "details", "here", "learn", "read", "view", "see", "link", "click"}
_BUTTON_MAX_WORDS = 3
_BUTTON_ASPECT_RANGE = (1.5, 8.0)  # width/height typical for a button


def _classify(element: Dict) -> str:
    if element["kind"] == "icon":
        return "icon_button"

    text = (element.get("text") or "").strip()
    if not text:
        return "text_field"

    box = element["box"]
    aspect = box["width"] / box["height"] if box["height"] else 0
    words = text.lower().split()

    if any(w.strip(".,!?") in _LINK_WORDS for w in words):
        return "link"

    if len(words) <= _BUTTON_MAX_WORDS and _BUTTON_ASPECT_RANGE[0] <= aspect <= _BUTTON_ASPECT_RANGE[1]:
        return "button"

    return "label"


class UIElementDetector:
    """Classifies omni_parser.py output. Stateless - takes a parse
    result (or runs one itself) and returns the same elements annotated
    with a `type` field."""

    def __init__(self):
        self._parser = get_omni_parser()

    def detect(self, parse_result: Optional[Dict] = None) -> Dict:
        if parse_result is None:
            parse_result = self._parser.parse()
        if isinstance(parse_result, dict) and "error" in parse_result:
            return parse_result

        elements = parse_result.get("elements", [])
        classified = []
        for el in elements:
            el = dict(el)
            el["type"] = _classify(el)
            classified.append(el)

        by_type: Dict[str, int] = {}
        for el in classified:
            by_type[el["type"]] = by_type.get(el["type"], 0) + 1

        return {"element_count": len(classified), "elements": classified, "by_type": by_type}

    def find_by_type(self, element_type: str, parse_result: Optional[Dict] = None) -> List[Dict]:
        result = self.detect(parse_result)
        if "error" in result:
            return []
        return [el for el in result["elements"] if el["type"] == element_type]


_detector: Optional[UIElementDetector] = None


def get_ui_element_detector() -> UIElementDetector:
    global _detector
    if _detector is None:
        _detector = UIElementDetector()
    return _detector
