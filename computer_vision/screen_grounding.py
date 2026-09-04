"""
Screen grounding
===================
Turns a natural-language description ("the blue submit button", "close
icon top right", "the search box") into a specific element from
ui_element_detector.py's classified parse - "grounding" referring text
to on-screen coordinates, the step visual_automator.py needs before it
can click/type anything.

No vision-language model is bundled with this project (consistent with
every other vision/ module's "no bundled model" stance), so grounding
here is straightforward lexical scoring against each element's OCR text
plus a few positional keywords (top/bottom/left/right/center), not true
semantic matching - it works well for descriptions that mention visible
text or rough screen position, and is upfront (via the returned `score`)
about how confident a match is rather than silently guessing.
"""

import re
from typing import Dict, List, Optional

from computer_vision.ui_element_detector import get_ui_element_detector
from core.logger import get_logger

logger = get_logger("ultron.interaction.grounding")

_POSITION_WORDS = {
    "top": lambda box, size: box["y"] < size["height"] / 3 if size.get("height") else False,
    "bottom": lambda box, size: box["y"] > 2 * size["height"] / 3 if size.get("height") else False,
    "left": lambda box, size: box["x"] < size["width"] / 3 if size.get("width") else False,
    "right": lambda box, size: box["x"] > 2 * size["width"] / 3 if size.get("width") else False,
    "center": lambda box, size: True,  # weak signal on its own, doesn't disqualify
}

_TYPE_HINTS = {
    "button": "button",
    "click": "button",
    "submit": "button",
    "link": "link",
    "field": "text_field",
    "box": "text_field",
    "input": "text_field",
    "search": "text_field",
    "icon": "icon_button",
}


def _tokenize(s: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", s.lower())]


class ScreenGrounder:
    """Scores parsed/classified elements against a free-text
    description and returns the best match(es). Re-runs the detector
    fresh each call by default, since the screen may have changed since
    the last parse - pass a pre-fetched `parse_result` to ground several
    phrases against the same snapshot instead."""

    def __init__(self):
        self._detector = get_ui_element_detector()

    def ground(self, description: str, parse_result: Optional[Dict] = None, top_k: int = 3) -> Dict:
        if parse_result is None:
            # Parse once here (rather than letting detect() parse
            # internally) so screen_size survives into this method for
            # the position-hint scoring below.
            parse_result = self._detector._parser.parse()
            if isinstance(parse_result, dict) and "error" in parse_result:
                return parse_result

        result = self._detector.detect(parse_result)
        if "error" in result:
            return result

        elements = result["elements"]
        size = parse_result.get("screen_size", {}) if isinstance(parse_result, dict) else {}

        tokens = _tokenize(description)
        position_hints = [t for t in tokens if t in _POSITION_WORDS]
        type_hint = next((_TYPE_HINTS[t] for t in tokens if t in _TYPE_HINTS), None)
        text_tokens = [t for t in tokens if t not in _POSITION_WORDS and t not in _TYPE_HINTS]

        scored = []
        for el in elements:
            score = 0.0
            el_text_tokens = set(_tokenize(el.get("text") or ""))

            overlap = len(set(text_tokens) & el_text_tokens)
            if text_tokens:
                score += overlap / len(text_tokens)
            elif not el_text_tokens:
                score += 0.1  # description has no text terms and element has none either - weak neutral match

            if type_hint and el["type"] == type_hint:
                score += 0.5

            if position_hints and size:
                matched_positions = sum(1 for p in position_hints if _POSITION_WORDS[p](el["box"], size))
                score += 0.3 * (matched_positions / len(position_hints))

            if score > 0:
                scored.append({**el, "score": round(score, 3)})

        scored.sort(key=lambda e: e["score"], reverse=True)
        matches = scored[:top_k]

        if not matches:
            return {"matched": False, "description": description, "candidates": []}

        return {
            "matched": True,
            "description": description,
            "best_match": matches[0],
            "candidates": matches,
        }


_grounder: Optional[ScreenGrounder] = None


def get_screen_grounder() -> ScreenGrounder:
    global _grounder
    if _grounder is None:
        _grounder = ScreenGrounder()
    return _grounder
