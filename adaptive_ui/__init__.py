"""
ADAPTIVE_UI
=============
UI that reacts to what's actually happening, on top of Phase 16's ui/
package (ui/widgets/TkWindow, ui/orb, ui/dashboard - all reused, none
replaced) and this phase's own VOICE_INTELLIGENCE/COMPUTER_VISION
signals.

    generative_ui_builder.py    - renders a tkinter panel at runtime from
                                   a small JSON spec (e.g. one the brain
                                   composes on the fly), instead of every
                                   new panel needing its own hand-written
                                   ui/widgets code.
    context_aware_dashboard.py  - wraps ui/dashboard.py, choosing which
                                   cards/panels to show based on what's
                                   currently active (voice turn, swarm
                                   task, vision watch) instead of always
                                   showing every panel.
    holographic_orb.py          - extends ui/orb/orb.py with states this
                                   phase adds: barge-in, diarized speaker
                                   label, detected mood.
    gesture_controller.py       - maps vision/gestures/recognizer.py
                                   output to concrete actions (stop,
                                   confirm, dismiss) dispatched on the
                                   unified event bus.
    multi_modal_input.py        - fuses voice/gesture/screen-click events
                                   from across this phase into one input
                                   stream, so a caller doesn't have to
                                   watch three separate sources itself.
"""
