"""Performance Report Generator
===============================
A single combined diagnostic snapshot - the `perfmon /report`-style
"System Diagnostics" rollup - built by calling the other modules in
this package rather than re-implementing their PowerShell/WMI reads:
SystemResourceMonitor (per-process disk/network I/O, handle/thread
counts), TemperatureMonitor (CPU/GPU/ACPI temps), DiskHealthMonitor
(physical-disk health + volume space), ReliabilityMonitor (stability
index), and CrashAnalyzer/StartupImpactAnalyzer for a short "issues
found" list. Each source module still owns its own reads; this module
only aggregates and flags.

All reads; nothing here changes system state, so nothing is
confirm-gated.
"""

import time
from typing import Dict, List


class PerformanceReportGenerator:
    """Aggregates the other system_control/monitoring/* modules into
    one snapshot report plus a flat 'issues found' list, instead of
    requiring a caller to make five separate calls and cross-reference
    them by hand."""

    def __init__(self):
        self._resource = None
        self._temperature = None
        self._disk = None
        self._reliability = None
        self._crash = None
        self._startup = None

    def _lazy(self, attr: str, cls_path: str, cls_name: str):
        val = getattr(self, attr)
        if val is not None:
            return val
        module = __import__(cls_path, fromlist=[cls_name])
        obj = getattr(module, cls_name)()
        setattr(self, attr, obj)
        return obj

    def generate_report(self, include_crash_history: bool = True, include_startup: bool = True) -> Dict:
        """Build the combined report. Every section degrades to an
        {"error": ...} or {"available": False} entry on its own
        (never raises), so one unavailable source (e.g. no admin for
        reliability counters) doesn't block the rest of the report."""
        report: Dict = {"generated_at": time.time(), "sections": {}}
        issues: List[str] = []

        resource = self._lazy("_resource", "system_control.monitoring.resource_monitor", "SystemResourceMonitor")
        handles = resource.get_handle_thread_counts(limit=5)
        report["sections"]["resource_usage"] = handles
        if "error" not in handles:
            top = handles.get("top_by_handles") or []
            if top and isinstance(top[0].get("Handles"), (int, float)) and top[0]["Handles"] > 10000:
                issues.append(
                    f"{top[0].get('ProcessName')} is holding an unusually high handle count ({top[0]['Handles']})"
                )

        temperature = self._lazy("_temperature", "system_control.monitoring.temperature_monitor", "TemperatureMonitor")
        temp_check = temperature.check_thresholds()
        report["sections"]["temperature"] = temp_check
        if "error" not in temp_check and temp_check.get("count"):
            issues.append(f"{temp_check['count']} sensor(s) over the configured temperature threshold")

        disk = self._lazy("_disk", "system_control.monitoring.disk_health", "DiskHealthMonitor")
        disk_alerts = disk.check_health_alerts()
        volumes = disk.get_volume_space_summary()
        report["sections"]["disk_health"] = disk_alerts
        report["sections"]["disk_space"] = volumes
        if "error" not in disk_alerts and disk_alerts.get("count"):
            issues.append(f"{disk_alerts['count']} disk-health alert(s)")
        if "error" not in volumes:
            for v in volumes.get("volumes", []):
                if isinstance(v.get("used_percent"), (int, float)) and v["used_percent"] >= 90:
                    issues.append(f"Drive {v.get('drive')}: is {v['used_percent']}% full")

        reliability = self._lazy("_reliability", "system_control.monitoring.reliability_monitor", "ReliabilityMonitor")
        try:
            stability = reliability.get_stability_index()
        except AttributeError:
            stability = {"error": "ReliabilityMonitor has no get_stability_index method"}
        report["sections"]["reliability"] = stability

        if include_crash_history:
            crash = self._lazy("_crash", "system_control.monitoring.crash_analyzer", "WindowsCrashAnalyzer")
            crash_summary = crash.summarize_crash_frequency(limit=25)
            report["sections"]["crash_summary"] = crash_summary
            if "error" not in crash_summary and crash_summary.get("total_crashes_scanned", 0) >= 5:
                issues.append(f"{crash_summary['total_crashes_scanned']} application crashes in the scanned window")

        if include_startup:
            startup = self._lazy("_startup", "system_control.monitoring.startup_impact", "StartupImpactAnalyzer")
            startup_est = startup.estimate_startup_impact()
            report["sections"]["startup_impact"] = startup_est
            if startup_est.get("verdict") == "heavy":
                issues.append("Boot time is measured as heavy - see startup_impact section")

        report["success"] = True
        report["issues_found"] = issues
        report["issue_count"] = len(issues)
        return report

    def generate_summary_text(self) -> Dict:
        """Same data as generate_report(), reduced to a short list of
        plain-English lines suitable for reading aloud or dropping
        into a notification, rather than the full nested dict."""
        report = self.generate_report()
        lines = [f"Performance report - {report['issue_count']} issue(s) found."]
        lines += [f"- {i}" for i in report["issues_found"]]
        if not report["issues_found"]:
            lines.append("- No issues detected in the scanned areas.")
        return {"success": True, "summary_lines": lines, "full_report": report}
