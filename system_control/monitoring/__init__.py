"""system_control.monitoring
============================
Deep, Windows-specific system instrumentation - distinct from the
top-level monitoring/*.py package, which is deliberately cross-
platform (psutil-based) and scoped to "is ULTRON itself healthy"
(monitoring/health_check.py, monitoring/resource_monitor.py,
monitoring/alerts.py, monitoring/performance.py all answer questions
about ULTRON's own process and its host machine's basic load).

Modules here instead surface what Windows itself tracks about the
whole system, using Windows-only sources with no cross-platform
equivalent: aggregated hardware temperatures (across ACPI, GPU, and
optionally LibreHardwareMonitor sensors), the Event Viewer log,
the Reliability Monitor history/stability index, and Performance-
Monitor-style (resmon.exe) per-process resource breakdowns. None of
these duplicate the top-level monitoring/ package's job of watching
ULTRON itself - they watch the OS.

Same conventions as the rest of system_control/*: every public method
returns a plain Dict and never raises; state-changing methods are
confirm-gated; methods needing admin document that and surface an
admin hint on access-denied; everything degrades to a clear
{"error": ...} on non-Windows hosts or missing optional dependencies
rather than raising.
"""

from system_control.monitoring.temperature_monitor import TemperatureMonitor
from system_control.monitoring.event_viewer import EventViewer
from system_control.monitoring.reliability_monitor import ReliabilityMonitor
from system_control.monitoring.resource_monitor import SystemResourceMonitor
from system_control.monitoring.network_monitor import NetworkMonitor
from system_control.monitoring.disk_health import DiskHealthMonitor
from system_control.monitoring.battery_health import BatteryHealthMonitor
from system_control.monitoring.startup_impact import StartupImpactAnalyzer
from system_control.monitoring.crash_analyzer import WindowsCrashAnalyzer
from system_control.monitoring.performance_reports import PerformanceReportGenerator

__all__ = [
    "TemperatureMonitor",
    "EventViewer",
    "ReliabilityMonitor",
    "SystemResourceMonitor",
    "NetworkMonitor",
    "DiskHealthMonitor",
    "BatteryHealthMonitor",
    "StartupImpactAnalyzer",
    "WindowsCrashAnalyzer",
    "PerformanceReportGenerator",
]
