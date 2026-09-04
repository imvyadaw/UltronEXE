"""
SELF_HEALING
==============
Keeps ULTRON itself running smoothly: detect trouble, understand it,
fix what can be fixed automatically, and flag what can't.

    health_monitor        - polls system + custom probes against thresholds, raises alerts
    crash_analyzer         - parses ULTRON's own logs for tracebacks, groups by signature
    auto_recovery           - runs registered recovery strategies for unhealthy components, with backoff
    dependency_checker      - verifies required packages/executables are present and current
    performance_optimizer   - watches ULTRON's own process, trims caches / flags leaks / thread bloat
"""

from .health_monitor import HealthMonitor, HealthAlert, Severity, Thresholds
from .crash_analyzer import CrashAnalyzer, CrashSignature
from .auto_recovery import AutoRecovery, RecoveryAttempt
from .dependency_checker import DependencyChecker, DependencyStatus
from .performance_optimizer import PerformanceOptimizer, Suggestion

__all__ = [
    "HealthMonitor",
    "HealthAlert",
    "Severity",
    "Thresholds",
    "CrashAnalyzer",
    "CrashSignature",
    "AutoRecovery",
    "RecoveryAttempt",
    "DependencyChecker",
    "DependencyStatus",
    "PerformanceOptimizer",
    "Suggestion",
]
