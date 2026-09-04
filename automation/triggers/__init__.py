"""Triggers package
=================
Event-driven automation: fire a Ultron tool call (same {"tool", "arguments"}
shape used everywhere else - core/executor.py, automation/workflow/workflow.py)
in response to a filesystem change, a clock time, or a system-state
condition (CPU/battery/process/USB), instead of the user having to ask
for it explicitly. Complements core/scheduler.py (which fires once/every
N seconds on a fixed delay) with condition- and event-based firing.
"""
