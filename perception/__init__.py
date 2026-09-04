"""
Perception (Phase 22)
======================
Five senses feeding the Phase 21 unified core: hearing (voice_processor),
what-the-user-is-doing (activity_monitor), sight (screen_analyzer),
system health/environment (system_listener), and affect
(emotion_detector). Nothing in here replaces the underlying capture
code in voice/, vision/, monitoring/, proactive/monitors/ - each module
is a thin orchestration layer that calls into those, normalizes the
result into one small event shape, and emits it on
core.event_bus so consciousness/unified_context/autonomous_engine can
react without importing five different subsystems directly.

Common event shape emitted by every perceive_*() call:
    {"modality": "voice"|"activity"|"screen"|"system"|"emotion",
     "timestamp": float, "data": {...}, "source": "<module>"}

Call register_capabilities() once at startup (idempotent) to make every
perception action visible to core.capability_registry, so
action_pipeline/autonomous_engine can invoke "perceive_screen",
"perceive_emotion", etc. like any other capability.
"""

from typing import List


def register_capabilities() -> List[str]:
    """Best-effort registration of every perception module's primary
    action with core.capability_registry. Safe to call more than once
    (registry.register() overwrites by name) and safe if core/ isn't
    importable yet (returns an empty list rather than raising)."""
    try:
        from core.capability_registry import get_capability_registry
    except Exception:
        return []

    registry = get_capability_registry()
    registered = []

    from perception.voice_processor import get_voice_processor
    from perception.activity_monitor import get_activity_monitor
    from perception.screen_analyzer import get_screen_analyzer
    from perception.system_listener import get_system_listener
    from perception.emotion_detector import get_emotion_detector

    entries = [
        ("perceive_voice", "listen once and transcribe speech", get_voice_processor().listen_and_process),
        ("perceive_activity", "read the active window and idle time", get_activity_monitor().snapshot),
        ("perceive_screen", "capture and describe the current screen", get_screen_analyzer().analyze),
        ("perceive_system", "read CPU/RAM/disk/network state", get_system_listener().snapshot),
        ("perceive_emotion", "estimate the user's current emotional state", get_emotion_detector().detect),
    ]
    for name, description, handler in entries:
        registry.register(name, category="perception", description=description, handler=handler, source="perception")
        registered.append(name)
    return registered
