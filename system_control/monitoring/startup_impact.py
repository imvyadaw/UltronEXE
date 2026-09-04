"""Startup Impact Analyzer
==========================
Boot-time performance - distinct from process/startup_manager.py,
which lists/adds/removes/enables/disables logon entries but never
measures how much any of them actually cost. This module reads the
Diagnostics-Performance operational event log (Event ID 100, the same
source Task Manager and Windows' own "Recent boots" performance
troubleshooter use) for actual measured boot duration and its
breakdown, plus the raw startup-entry count from StartupManager as a
cheap correlating signal.

Honesty note, same policy as hardware/fan_control.py: Windows has no
documented, generally-available API that returns Task Manager's
per-app "Startup impact: High/Medium/Low" rating directly - that
rating is computed internally by Explorer and not exposed. Rather
than guess at it, this module reports the real boot-duration
breakdown Windows does expose and leaves the per-app estimate to a
simple, clearly-labeled heuristic (startup entry count vs boot time
trend), never presented as if it were Task Manager's own number.

All reads; nothing here changes system state, so nothing is
confirm-gated.
"""

import subprocess
from typing import Dict, List


class StartupImpactAnalyzer:
    """Measured boot-duration history from the Diagnostics-Performance
    event log, plus a labeled heuristic correlating it with the
    current startup-entry count."""

    def _run_ps(self, cmd: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_boot_history(self, limit: int = 10) -> Dict:
        """Recent boot durations (main path + boot/logon/post-boot
        breakdown, in milliseconds) from Event ID 100 in the
        Diagnostics-Performance operational log. Needs admin (this
        channel is admin-only to read). Empty (not an error) if
        nothing recent is logged."""
        result = self._run_ps(
            "Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Diagnostics-Performance/Operational'; "
            "Id=100} "
            f"-MaxEvents {int(limit)} -ErrorAction SilentlyContinue | ForEach-Object {{ "
            "[PSCustomObject]@{ Time = $_.TimeCreated; "
            "BootTimeMs = $_.Properties[0].Value; "
            "MainPathBootTimeMs = $_.Properties[9].Value; "
            "BootPostBootTimeMs = $_.Properties[15].Value } "
            "} | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "success": True,
                "boots": [],
                "count": 0,
                "note": result["stderr"] or "Diagnostics-Performance channel unavailable - usually needs admin.",
            }
        if not result["stdout"]:
            return {"success": True, "boots": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse boot performance data"}
        rows = data if isinstance(data, list) else [data]
        return {"success": True, "boots": rows, "count": len(rows)}

    def get_startup_entry_count(self) -> Dict:
        """Raw count of current logon-time startup entries, reusing
        StartupManager.list_startup_items() rather than re-querying
        WMI a second time."""
        try:
            from system_control.process.startup_manager import StartupManager
        except ImportError as e:
            return {"error": f"Could not import StartupManager: {e}"}
        items = StartupManager().list_startup_items()
        if "error" in items:
            return items
        entries = items.get("items", items.get("startup_items", []))
        enabled = [e for e in entries if str(e.get("state", "")).lower() != "disabled"]
        return {"success": True, "total_entries": len(entries), "enabled_entries": len(enabled)}

    def estimate_startup_impact(self) -> Dict:
        """Combine get_boot_history() + get_startup_entry_count() into
        a single, clearly-labeled heuristic verdict (low/moderate/
        heavy) - explicitly NOT Task Manager's internal per-app impact
        score, which Windows does not expose via any public API."""
        history = self.get_boot_history(limit=5)
        counts = self.get_startup_entry_count()

        boots = history.get("boots", []) if "error" not in history else []
        avg_boot_ms = None
        if boots:
            vals = [b.get("BootTimeMs") for b in boots if isinstance(b.get("BootTimeMs"), (int, float))]
            if vals:
                avg_boot_ms = round(sum(vals) / len(vals))

        enabled = counts.get("enabled_entries") if "error" not in counts else None

        verdict = "unknown"
        reasons: List[str] = []
        if avg_boot_ms is not None:
            if avg_boot_ms > 60000:
                verdict = "heavy"
                reasons.append(f"average measured boot time is {avg_boot_ms} ms (over 60s)")
            elif avg_boot_ms > 30000:
                verdict = "moderate"
                reasons.append(f"average measured boot time is {avg_boot_ms} ms (over 30s)")
            else:
                verdict = "low"
                reasons.append(f"average measured boot time is {avg_boot_ms} ms")
        if isinstance(enabled, int):
            if enabled > 15:
                reasons.append(f"{enabled} enabled startup entries is high")
            else:
                reasons.append(f"{enabled} enabled startup entries")

        return {
            "success": True,
            "verdict": verdict,
            "reasons": reasons,
            "average_boot_time_ms": avg_boot_ms,
            "enabled_startup_entries": enabled,
            "note": "Heuristic only - not Windows' own internal Task Manager impact score, "
            "which is not exposed via any documented API.",
        }
