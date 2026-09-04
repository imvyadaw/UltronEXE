"""system_control/special
========================
System-level orchestration layer for capabilities that already have a
core implementation living elsewhere in the codebase (face/gesture
vision models, proactive prediction, habit memory, per-user trait
model, Windows OS accounts/RDP/SSH). Modules in this package do NOT
re-implement that core logic - they wire the OS-facing/control-surface
half of each feature (device toggles, scheduling, confirm-gated state
changes, cross-subsystem orchestration) and delegate the actual
AI/analysis work to the existing owner module. Each file's docstring
names exactly which existing module it delegates to and what it adds
on top, the same convention system_control/security/__init__.py
already uses to distinguish itself from the top-level security/
package.
"""
