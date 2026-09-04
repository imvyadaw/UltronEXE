"""Crash Analyzer (system_control)
===================================
OS-recorded crash history - distinct from self_healing/crash_analyzer.py,
which only ever parses ULTRON's own local log files for Python
tracebacks and never touches system-wide logs. This module instead
reads what Windows itself recorded: application crashes (Windows
Error Reporting, Event ID 1000 in the Application log), the specific
faulting-module signature for each, unexpected shutdowns/BSODs
(Event ID 41 in the System log, from Kernel-Power), and the BugCheck
record when one exists (Event ID 1001, "Windows Error Reporting"
source), so questions like "what crashed recently, and how often"
can be answered about the whole system, not just ULTRON.

Reading the Application/System event logs needs no special
permission for a local machine; nothing here changes system state, so
nothing is confirm-gated.
"""

import subprocess
from collections import Counter
from typing import Dict


class WindowsCrashAnalyzer:
    """Application-crash and unexpected-shutdown history from the
    Windows Event Log, with a simple frequency rollup by faulting
    module - the OS-wide counterpart to self_healing's ULTRON-only
    log scanner."""

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

    def get_application_crashes(self, limit: int = 25) -> Dict:
        """Recent application-crash records (Event ID 1000, "Application
        Error" source) from the Application log - faulting app,
        faulting module, and exception code, the same data Reliability
        Monitor's "application crashed" rows come from. No admin
        needed."""
        result = self._run_ps(
            "Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Error'; Id=1000} "
            f"-MaxEvents {int(limit)} -ErrorAction SilentlyContinue | ForEach-Object {{ "
            "[PSCustomObject]@{ Time = $_.TimeCreated; "
            "FaultingApp = $_.Properties[0].Value; "
            "AppVersion = $_.Properties[1].Value; "
            "FaultingModule = $_.Properties[3].Value; "
            "ExceptionCode = $_.Properties[7].Value } "
            "} | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "success": True,
                "crashes": [],
                "count": 0,
                "note": result["stderr"] or "No application-crash events found.",
            }
        if not result["stdout"]:
            return {"success": True, "crashes": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse application crash data"}
        rows = data if isinstance(data, list) else [data]
        return {"success": True, "crashes": rows, "count": len(rows)}

    def get_unexpected_shutdowns(self, limit: int = 15) -> Dict:
        """Recent unexpected/dirty shutdowns and BSODs: Kernel-Power
        Event ID 41 (power loss without a clean shutdown) and, when
        present, the matching BugCheck record (Event ID 1001,
        "Windows Error Reporting" source) with the stop code. Needs
        admin for the System log's full detail on most systems."""
        result = self._run_ps(
            "Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; Id=41} "
            f"-MaxEvents {int(limit)} -ErrorAction SilentlyContinue | "
            "Select-Object TimeCreated, Id, Message | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "success": True,
                "shutdowns": [],
                "count": 0,
                "note": result["stderr"] or "No unexpected-shutdown events found, or admin is needed to read them.",
            }
        if not result["stdout"]:
            return {"success": True, "shutdowns": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse shutdown event data"}
        rows = data if isinstance(data, list) else [data]
        shutdowns = [{"time": r.get("TimeCreated"), "event_id": r.get("Id"), "message": r.get("Message")} for r in rows]
        return {"success": True, "shutdowns": shutdowns, "count": len(shutdowns)}

    def summarize_crash_frequency(self, limit: int = 50) -> Dict:
        """Roll up get_application_crashes() by faulting module, most-
        frequent first - "what's actually crashing repeatedly" at a
        glance instead of a flat event list."""
        crashes = self.get_application_crashes(limit=limit)
        if "error" in crashes:
            return crashes
        modules = Counter(c.get("FaultingModule") or "unknown" for c in crashes.get("crashes", []))
        apps = Counter(c.get("FaultingApp") or "unknown" for c in crashes.get("crashes", []))
        return {
            "success": True,
            "total_crashes_scanned": crashes.get("count", 0),
            "by_faulting_module": [{"module": m, "count": n} for m, n in modules.most_common(10)],
            "by_faulting_app": [{"app": a, "count": n} for a, n in apps.most_common(10)],
        }
