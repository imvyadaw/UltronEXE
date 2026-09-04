"""
Consciousness (compat shim - DO NOT add new logic here)
=========================================================
FIXED (split-brain bug): this module used to define its OWN
ConsciousnessState class and its OWN module-level `_state` singleton,
completely separate from core/consciousness.py's. core/consciousness.py's
own docstring already said it "supersedes" this file as the process-wide
instance from Phase 21 on - but 8 files (ai/local_router.py, display/orb.py,
command/history.py, command/dashboard.py, core/brain_p18.py,
core/decision_maker.py, and core/assistant.py itself) were still importing
get_consciousness() from THIS file, while core/autonomous_engine.py,
core/action_pipeline.py, core/unified_context.py, and the perception/*
modules were importing it from core/consciousness.py. That meant two
live ConsciousnessState objects existed side by side at runtime: e.g.
core/decision_maker.py's confidence-based "run vs clarify" check was
reading a confidence score that core/autonomous_engine.py's outcome
reports never actually updated, because they were writing to a
different object. Any feature relying on confidence/focus/introspection
being consistent across those two groups of files was silently broken.

Fix: this file no longer defines its own state. It re-exports
core/consciousness.py's ConsciousnessState and get_consciousness()
directly, so every one of the 8 old importers now transparently shares
the exact same singleton as everything else - zero call-site changes
needed, since the public API (push_focus/pop_focus/current_focus/
attention_depth/note_outcome/confidence/recent_notes/reflect) is
identical between the two (core/consciousness.py's reflect() is a
strict superset - it adds active_goal/registered_capabilities on top
of this file's fields).

New code should import from core.consciousness directly - this shim
exists only so the 8 existing call sites above didn't need to be
touched to fix the split-brain bug. Do not add any new state or logic
to this file; add it to core/consciousness.py instead.
"""

from core.consciousness import ConsciousnessState, get_consciousness

__all__ = ["ConsciousnessState", "get_consciousness"]
