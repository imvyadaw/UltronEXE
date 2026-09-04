"""Monitoring Control tool registry
====================================
Wires system_control/monitoring/* (deep, Windows-specific OS
instrumentation - temperature, event log, reliability index, per-
process resource I/O, adapter link health, disk health, battery
wear, startup/boot impact, OS-recorded crash history, and the
combined performance report) into the AI tool-calling loop. Same
pattern as ai/network_control_tools.py and ai/file_control_tools.py:
lazy singletons + a flat MONITORING_CONTROL_TOOLS /
MONITORING_CONTROL_DIRECT_HANDLERS pair, merged at the bottom of
ai/tools_schema.py and ai/tool_runtime.py respectively.

Naming: every tool is prefixed `monctl_` to avoid colliding with the
cross-platform, ULTRON-self-health tools backed by the top-level
monitoring/*.py package (health_check, alerts, performance) and with
self_healing/crash_analyzer.py's own-log-only tools, if/when either
of those gets its own AI tool registry.

Everything in system_control/monitoring/ is read-only (nothing here
changes system state), so none of these tools are confirm-gated.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's `_tool()` helper. Duplicated
    on purpose - see ai/network_control_tools.py's docstring for why (avoids
    a circular import since tools_schema.py imports *from* this module)."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


def _pick(d: dict, keys: list) -> dict:
    """Filter a raw tool-call args dict down to the keys a method accepts,
    dropping missing/None entries so the method's own defaults apply."""
    return {k: d[k] for k in keys if k in d and d[k] is not None}


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------
_instances: Dict[str, object] = {}


def _get(key: str):
    if key in _instances:
        return _instances[key]

    if key == "temperature":
        from system_control.monitoring.temperature_monitor import TemperatureMonitor

        obj = TemperatureMonitor()
    elif key == "event_viewer":
        from system_control.monitoring.event_viewer import EventViewer

        obj = EventViewer()
    elif key == "reliability":
        from system_control.monitoring.reliability_monitor import ReliabilityMonitor

        obj = ReliabilityMonitor()
    elif key == "resource":
        from system_control.monitoring.resource_monitor import SystemResourceMonitor

        obj = SystemResourceMonitor()
    elif key == "network":
        from system_control.monitoring.network_monitor import NetworkMonitor

        obj = NetworkMonitor()
    elif key == "disk":
        from system_control.monitoring.disk_health import DiskHealthMonitor

        obj = DiskHealthMonitor()
    elif key == "battery":
        from system_control.monitoring.battery_health import BatteryHealthMonitor

        obj = BatteryHealthMonitor()
    elif key == "startup":
        from system_control.monitoring.startup_impact import StartupImpactAnalyzer

        obj = StartupImpactAnalyzer()
    elif key == "crash":
        from system_control.monitoring.crash_analyzer import WindowsCrashAnalyzer

        obj = WindowsCrashAnalyzer()
    elif key == "report":
        from system_control.monitoring.performance_reports import PerformanceReportGenerator

        obj = PerformanceReportGenerator()
    else:
        raise KeyError(f"Unknown monitoring_control tool key: {key}")

    _instances[key] = obj
    return obj


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
MONITORING_CONTROL_TOOLS = [
    # -- TemperatureMonitor --
    _tool(
        "monctl_temp_get_all",
        "Read current CPU/GPU/ACPI temperatures in one combined snapshot.",
    ),
    _tool(
        "monctl_temp_get_history",
        "Get recent temperature readings taken so far this session.",
        {"limit": {"type": "integer"}},
    ),
    _tool(
        "monctl_temp_check_thresholds",
        "Take a fresh temperature reading and report anything over the given CPU/GPU thresholds.",
        {"cpu_max_c": {"type": "number"}, "gpu_max_c": {"type": "number"}},
    ),
    # -- EventViewer --
    _tool(
        "monctl_events_list_logs",
        "List available Windows Event Log channels.",
    ),
    _tool(
        "monctl_events_get",
        "Get recent events from a named log, optionally filtered by level/source/lookback window.",
        {
            "log_name": {"type": "string"},
            "max_events": {"type": "integer"},
            "level": {"type": "string", "enum": ["critical", "error", "warning", "information", "verbose"]},
            "source": {"type": "string"},
            "since_hours": {"type": "number"},
        },
    ),
    _tool(
        "monctl_events_get_recent_errors",
        "Get recent critical/error-level events across the system within a lookback window.",
        {"max_events": {"type": "integer"}, "since_hours": {"type": "number"}},
    ),
    # -- ReliabilityMonitor --
    _tool(
        "monctl_reliability_get_index",
        "Get the current Windows Reliability Monitor stability index (0-10).",
    ),
    _tool(
        "monctl_reliability_get_history",
        "Get the Reliability Monitor stability index history over a number of days.",
        {"days": {"type": "integer"}},
    ),
    _tool(
        "monctl_reliability_get_recent_failures",
        "Get recent Reliability Monitor failure records, optionally filtered by category.",
        {"max_events": {"type": "integer"}, "category": {"type": "string"}},
    ),
    _tool(
        "monctl_reliability_get_crash_summary",
        "Get a Reliability-Monitor-sourced crash summary over a number of days.",
        {"days": {"type": "integer"}},
    ),
    # -- SystemResourceMonitor --
    _tool(
        "monctl_resource_top_disk_consumers",
        "Top processes by current disk I/O (bytes/sec).",
        {"limit": {"type": "integer"}},
    ),
    _tool(
        "monctl_resource_top_network_consumers",
        "Top processes by current network throughput.",
        {"limit": {"type": "integer"}},
    ),
    _tool(
        "monctl_resource_get_disk_activity",
        "Get current disk queue length and percent-active for a given drive.",
        {"drive": {"type": "string"}},
    ),
    _tool(
        "monctl_resource_get_handle_thread_counts",
        "Get system-wide open handle/thread totals plus the top processes by handle count.",
        {"limit": {"type": "integer"}},
    ),
    # -- NetworkMonitor --
    _tool(
        "monctl_net_get_adapter_statistics",
        "Get sent/received bytes plus error and discard counters for one or all network adapters.",
        {"name": {"type": "string"}},
    ),
    _tool(
        "monctl_net_get_link_quality",
        "Get negotiated link speed and media connection state for one or all network adapters.",
        {"name": {"type": "string"}},
    ),
    _tool(
        "monctl_net_get_connection_history",
        "Get recent Wi-Fi connect/disconnect history from the OS event log.",
        {"limit": {"type": "integer"}},
    ),
    _tool(
        "monctl_net_check_packet_loss",
        "Ping a target host and report packet loss percentage and average latency.",
        {"target": {"type": "string"}, "count": {"type": "integer"}},
    ),
    # -- DiskHealthMonitor --
    _tool(
        "monctl_disk_get_physical_disks",
        "List physical disks with Windows' rollup health status, media type, and size.",
    ),
    _tool(
        "monctl_disk_get_reliability_counters",
        "Get per-disk SMART-equivalent reliability counters (temperature, wear, error totals). Usually needs admin.",
        {"disk_id": {"type": "string"}},
    ),
    _tool(
        "monctl_disk_get_volume_space",
        "Get free/used space per volume/drive letter.",
    ),
    _tool(
        "monctl_disk_check_health_alerts",
        "Roll up disk health status and reliability counters into a flat list of alerts.",
        {"wear_warn_percent": {"type": "number"}},
    ),
    # -- BatteryHealthMonitor --
    _tool(
        "monctl_battery_get_current_status",
        "Get live battery charge percentage, status, and estimated runtime. Reports unavailable on desktops.",
    ),
    _tool(
        "monctl_battery_generate_wear_report",
        "Generate a battery wear report (design vs full-charge capacity) via powercfg. Reports unavailable on desktops.",
    ),
    # -- StartupImpactAnalyzer --
    _tool(
        "monctl_startup_get_boot_history",
        "Get recent measured boot durations from the Diagnostics-Performance event log. Usually needs admin.",
        {"limit": {"type": "integer"}},
    ),
    _tool(
        "monctl_startup_get_entry_count",
        "Get the current count of enabled/total logon-time startup entries.",
    ),
    _tool(
        "monctl_startup_estimate_impact",
        "Get a heuristic low/moderate/heavy startup-impact verdict from boot history and startup entry count.",
    ),
    # -- WindowsCrashAnalyzer --
    _tool(
        "monctl_crash_get_application_crashes",
        "Get recent Windows-recorded application-crash events (faulting app/module/exception code).",
        {"limit": {"type": "integer"}},
    ),
    _tool(
        "monctl_crash_get_unexpected_shutdowns",
        "Get recent unexpected shutdown/BSOD events (Kernel-Power Event ID 41). Usually needs admin.",
        {"limit": {"type": "integer"}},
    ),
    _tool(
        "monctl_crash_summarize_frequency",
        "Get a frequency rollup of recent application crashes by faulting module and faulting app.",
        {"limit": {"type": "integer"}},
    ),
    # -- PerformanceReportGenerator --
    _tool(
        "monctl_report_generate",
        "Generate a combined system performance/diagnostic report (resources, temps, disk health, "
        "reliability, crash summary, startup impact) with a flagged issues list.",
        {"include_crash_history": {"type": "boolean"}, "include_startup": {"type": "boolean"}},
    ),
    _tool(
        "monctl_report_generate_summary_text",
        "Generate the same combined performance report reduced to short plain-English summary lines.",
    ),
]

# ---------------------------------------------------------------------------
# Direct handlers
# ---------------------------------------------------------------------------
MONITORING_CONTROL_DIRECT_HANDLERS = {
    # -- TemperatureMonitor --
    "monctl_temp_get_all": lambda d, _k="temperature", _m="get_all_temperatures", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "monctl_temp_get_history": lambda d, _k="temperature", _m="get_history", _p=["limit"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "monctl_temp_check_thresholds": lambda d, _k="temperature", _m="check_thresholds", _p=[
        "cpu_max_c",
        "gpu_max_c",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- EventViewer --
    "monctl_events_list_logs": lambda d, _k="event_viewer", _m="list_logs", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "monctl_events_get": lambda d, _k="event_viewer", _m="get_events", _p=[
        "log_name",
        "max_events",
        "level",
        "source",
        "since_hours",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "monctl_events_get_recent_errors": lambda d, _k="event_viewer", _m="get_recent_errors", _p=[
        "max_events",
        "since_hours",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- ReliabilityMonitor --
    "monctl_reliability_get_index": lambda d, _k="reliability", _m="get_stability_index", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "monctl_reliability_get_history": lambda d, _k="reliability", _m="get_stability_history", _p=["days"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "monctl_reliability_get_recent_failures": lambda d, _k="reliability", _m="get_recent_failures", _p=[
        "max_events",
        "category",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "monctl_reliability_get_crash_summary": lambda d, _k="reliability", _m="get_crash_summary", _p=["days"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- SystemResourceMonitor --
    "monctl_resource_top_disk_consumers": lambda d, _k="resource", _m="get_top_disk_consumers", _p=["limit"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "monctl_resource_top_network_consumers": lambda d, _k="resource", _m="get_top_network_consumers", _p=[
        "limit"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "monctl_resource_get_disk_activity": lambda d, _k="resource", _m="get_disk_activity", _p=["drive"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "monctl_resource_get_handle_thread_counts": lambda d, _k="resource", _m="get_handle_thread_counts", _p=[
        "limit"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- NetworkMonitor --
    "monctl_net_get_adapter_statistics": lambda d, _k="network", _m="get_adapter_statistics", _p=["name"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "monctl_net_get_link_quality": lambda d, _k="network", _m="get_link_quality", _p=["name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "monctl_net_get_connection_history": lambda d, _k="network", _m="get_connection_history", _p=["limit"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "monctl_net_check_packet_loss": lambda d, _k="network", _m="check_packet_loss", _p=["target", "count"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- DiskHealthMonitor --
    "monctl_disk_get_physical_disks": lambda d, _k="disk", _m="get_physical_disks", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "monctl_disk_get_reliability_counters": lambda d, _k="disk", _m="get_reliability_counters", _p=["disk_id"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "monctl_disk_get_volume_space": lambda d, _k="disk", _m="get_volume_space_summary", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "monctl_disk_check_health_alerts": lambda d, _k="disk", _m="check_health_alerts", _p=["wear_warn_percent"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- BatteryHealthMonitor --
    "monctl_battery_get_current_status": lambda d, _k="battery", _m="get_current_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "monctl_battery_generate_wear_report": lambda d, _k="battery", _m="generate_wear_report", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- StartupImpactAnalyzer --
    "monctl_startup_get_boot_history": lambda d, _k="startup", _m="get_boot_history", _p=["limit"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "monctl_startup_get_entry_count": lambda d, _k="startup", _m="get_startup_entry_count", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "monctl_startup_estimate_impact": lambda d, _k="startup", _m="estimate_startup_impact", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- WindowsCrashAnalyzer --
    "monctl_crash_get_application_crashes": lambda d, _k="crash", _m="get_application_crashes", _p=["limit"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "monctl_crash_get_unexpected_shutdowns": lambda d, _k="crash", _m="get_unexpected_shutdowns", _p=["limit"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "monctl_crash_summarize_frequency": lambda d, _k="crash", _m="summarize_crash_frequency", _p=["limit"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- PerformanceReportGenerator --
    "monctl_report_generate": lambda d, _k="report", _m="generate_report", _p=[
        "include_crash_history",
        "include_startup",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "monctl_report_generate_summary_text": lambda d, _k="report", _m="generate_summary_text", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
}
