"""
Visual-automator tool wiring
============================
computer_vision/visual_automator.py's VisualAutomator is a real, fully
implemented "act on the screen by description" module - click(desc),
double_click(desc), type_into(desc, text), hover(desc) - each one
re-grounds against a fresh screenshot right before acting (via
screen_grounding.py + ui_element_detector.py) so it stays correct even
if the UI moved since the last look. This is the closest thing this
codebase has to a human's "look at the screen, find the thing, act on
it" loop for desktop apps that have no accessible-control API for
click_ui_element to use (custom-drawn UI, games, some web content).

It had ZERO ai/tools_schema.py entries and ZERO dispatch wiring - the
model had no way to ever call it, despite the module itself working.
Combined with autonomous_web/web_agent_core.py (already wired via
ai/phase30_gated_tools.py) for browser tasks, wiring this closes the
gap: cognitive_core/autonomous_executor.py's existing plan -> decompose
-> execute -> critique loop (via ai.planning.Planner, which reads the
live ai.tools_schema.TOOLS list) can now pick these tools for desktop
tasks the same way it already picks web_agent tools for browser tasks -
one existing loop, two action surfaces, no new architecture needed.

Prefer click_ui_element (accessibility-tree based, in ai/tools_schema.py's
core set) for normal Windows controls - it's faster and doesn't need
OCR/vision. These are the fallback for anything visual that isn't a
labeled, accessible control.
"""

from typing import Dict


def _automator():
    from computer_vision.visual_automator import get_visual_automator

    return get_visual_automator()


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


VISUAL_AUTOMATOR_TOOLS = [
    _tool(
        "click_by_description",
        "Click something on screen described in plain English (e.g. 'the blue Submit button', "
        "'the close icon top right') when it has no accessible label for click_ui_element to use - "
        "canvas-drawn UI, games, custom-rendered widgets. Re-finds the element against a fresh "
        "screenshot right before clicking, so it's safe even if the UI just changed. Prefer "
        "click_ui_element first for normal Windows controls.",
        {
            "description": {"type": "string", "description": "Plain-English description of what to click."},
            "button": {
                "type": "string",
                "enum": ["left", "right", "middle"],
                "description": "Mouse button. Default left.",
            },
        },
        ["description"],
    ),
    _tool(
        "double_click_by_description",
        "Double-click something on screen described in plain English. Same grounding behavior as "
        "click_by_description - use for the same non-accessible-UI cases.",
        {"description": {"type": "string", "description": "Plain-English description of what to double-click."}},
        ["description"],
    ),
    _tool(
        "type_into_by_description",
        "Click a text field/input described in plain English and type text into it - for forms or "
        "inputs with no accessible label. Prefer click_ui_element + normal typing first for labeled "
        "Windows controls.",
        {
            "description": {"type": "string", "description": "Plain-English description of the field to type into."},
            "text": {"type": "string", "description": "Text to type."},
        },
        ["description", "text"],
    ),
    _tool(
        "hover_by_description",
        "Move the mouse to hover over something on screen described in plain English, without "
        "clicking - e.g. to trigger a tooltip or a hover menu.",
        {"description": {"type": "string", "description": "Plain-English description of what to hover over."}},
        ["description"],
    ),
]

VISUAL_AUTOMATOR_DIRECT_HANDLERS: Dict = {
    "click_by_description": lambda a: _automator().click(a.get("description", ""), button=a.get("button", "left")),
    "double_click_by_description": lambda a: _automator().double_click(a.get("description", "")),
    "type_into_by_description": lambda a: _automator().type_into(a.get("description", ""), a.get("text", "")),
    "hover_by_description": lambda a: _automator().hover(a.get("description", "")),
}
