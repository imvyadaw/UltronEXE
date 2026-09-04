"""
Visual automator
===================
Executes clicks/typing against a *grounded* element (from
screen_grounding.py) rather than a raw x,y a caller has to work out
itself - "click the blue submit button" instead of "click at 812,430".
All actual input events go through automation/mouse/mouse.py's
MouseControl and automation/keyboard/keyboard.py's KeyboardControl,
unchanged - this module only resolves *what* to click/type into, then
hands off.

Every action re-grounds against a fresh screenshot right before acting
(rather than trusting a coordinate found seconds ago), since UI can move
or reflow between "find the button" and "click it" - the small extra
OCR/detection cost buys real robustness against stale coordinates,
consistent with omni_parser.py's own "one parse, one screenshot" model
being fast enough to re-run per action.
"""

from typing import Dict, Optional

from computer_vision.screen_grounding import get_screen_grounder
from automation.mouse.mouse import MouseControl
from automation.keyboard.keyboard import KeyboardControl
from core.logger import get_logger

logger = get_logger("ultron.interaction.visual_automator")

MIN_CLICK_SCORE = 0.35  # below this, the grounder's best guess is too weak to act on blind


class VisualAutomator:
    """Ground a description against the live screen, then act on it.
    Every method returns a dict with "success" or "error", plus the
    grounding info that was used, so a caller (e.g. an LLM tool call)
    can see *what* got clicked, not just that something did."""

    def __init__(self):
        self._grounder = get_screen_grounder()
        self._mouse = MouseControl()
        self._keyboard = KeyboardControl()

    def _resolve(self, description: str) -> Dict:
        grounding = self._grounder.ground(description)
        if not grounding.get("matched"):
            return {"error": f"Couldn't find anything on screen matching '{description}'", "grounding": grounding}
        best = grounding["best_match"]
        if best["score"] < MIN_CLICK_SCORE:
            return {
                "error": f"Best match for '{description}' was too uncertain (score={best['score']}) - "
                "try a more specific description",
                "grounding": grounding,
            }
        return {"element": best, "grounding": grounding}

    def click(self, description: str, button: str = "left") -> Dict:
        resolved = self._resolve(description)
        if "error" in resolved:
            return resolved
        center = resolved["element"]["center"]
        result = self._mouse.click(center["x"], center["y"], button=button)
        if "error" in result:
            return result
        logger.info(f"Clicked '{description}' at ({center['x']}, {center['y']})")
        return {
            "success": True,
            "clicked": description,
            "position": [center["x"], center["y"]],
            "matched_element": resolved["element"],
        }

    def double_click(self, description: str) -> Dict:
        resolved = self._resolve(description)
        if "error" in resolved:
            return resolved
        center = resolved["element"]["center"]
        result = self._mouse.double_click(center["x"], center["y"])
        if "error" in result:
            return result
        return {"success": True, "double_clicked": description, "position": [center["x"], center["y"]]}

    def type_into(self, description: str, text: str) -> Dict:
        """Click the described field first (to focus it), then type -
        the ordering automation/web/form_filler.py's own click-then-type
        pattern already relies on for web forms."""
        click_result = self.click(description)
        if "error" in click_result:
            return click_result
        type_result = self._keyboard.type_text(text)
        if "error" in type_result:
            return type_result
        return {"success": True, "typed_into": description, "text": text}

    def hover(self, description: str) -> Dict:
        resolved = self._resolve(description)
        if "error" in resolved:
            return resolved
        center = resolved["element"]["center"]
        result = self._mouse.move_to(center["x"], center["y"])
        if "error" in result:
            return result
        return {"success": True, "hovering": description, "position": [center["x"], center["y"]]}


_automator: Optional[VisualAutomator] = None


def get_visual_automator() -> VisualAutomator:
    global _automator
    if _automator is None:
        _automator = VisualAutomator()
    return _automator
