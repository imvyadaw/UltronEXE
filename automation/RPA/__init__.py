"""RPA (Robotic Process Automation) package
==========================================
A step-based automation engine, distinct from automation/macro/macro.py's
raw click/key event capture: RPA scripts are lists of named, editable
steps (click, type_text, key, wait, open_app, run_tool, screenshot) that
can be inspected and edited step-by-step before replay, not just
recorded and blindly replayed.
"""
