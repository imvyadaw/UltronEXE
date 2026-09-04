"""ULTRON Advanced Autonomy Fabric.

Composes existing mission, world-state, research, knowledge, experience and
safe-evolution subsystems into one bounded lifecycle without bypassing the
existing security/approval gates.
"""
from .advanced_engine import AdvancedAutonomy, get_advanced_autonomy

__all__ = ["AdvancedAutonomy", "get_advanced_autonomy"]
