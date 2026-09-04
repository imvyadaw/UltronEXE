"""
COMPUTER_VISION
=================
Screen understanding and control on top of Phase 16's vision/ and
automation/ packages (vision/screen, vision/ocr, vision/object_detection,
vision/ui_detection, automation/mouse, automation/ui - all reused, none
replaced).

    omni_parser.py       - merges vision/ui_detection's text regions and
                            vision/object_detection's icon detections
                            into one indexed list of on-screen elements
                            (an OmniParser-style unified screen parse),
                            the shared input every other module in this
                            sub-package builds on.
    ui_element_detector.py - classifies each omni_parser element as
                            button/text_field/icon/link/label from box
                            shape + text heuristics.
    screen_grounding.py  - natural-language grounding: "the blue submit
                            button" -> the matching element's (x, y).
    visual_automator.py  - click/type/hover on a grounded element via
                            automation/mouse + automation/keyboard.
    anomaly_detector.py  - flags likely error dialogs, crash indicators,
                            or unexpected popups by OCR keyword scan and
                            frame-to-frame screen diffing.
    scene_understanding.py - a phase-level wrapper that adds continuous
                            "narrate what changed since last look" on top
                            of vision/scene_understanding.py's single-shot
                            synthesis.
"""
