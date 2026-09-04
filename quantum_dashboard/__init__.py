"""
QUANTUM_DASHBOARD
==================
Five widgets, five files. Each is standalone and returns plain
dicts/dataclasses, so any UI layer (the ADAPTIVE_UI dashboard from
Phase 17.5, a web view, a CLI) can just render whatever these return.

cognitive_load_monitor.py needs pywin32 (foreground-window tracking is
Windows-only); its import is guarded so the other four - all plain
psutil/stdlib - still work on Linux/Mac. CognitiveLoadMonitor is None
there.
"""

from .real_time_metrics import RealTimeMetrics
from .usage_analytics import UsageAnalytics
from .energy_efficiency import EnergyEfficiency
from .predictive_maintenance import PredictiveMaintenance

try:
    from .cognitive_load_monitor import CognitiveLoadMonitor
except ImportError:
    CognitiveLoadMonitor = None

__all__ = [
    "RealTimeMetrics",
    "UsageAnalytics",
    "CognitiveLoadMonitor",
    "EnergyEfficiency",
    "PredictiveMaintenance",
]
