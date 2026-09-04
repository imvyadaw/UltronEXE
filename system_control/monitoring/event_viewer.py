"""Event Viewer
==============
Read access to the Windows Event Log (eventvwr.msc) - Application,
System, and Security logs, plus arbitrary named logs - via
PowerShell's Get-WinEvent, the modern replacement for the older
Get-EventLog cmdlet (which cannot read the newer .evtx-based logs at
all). No other module in the codebase reads the event log; this is
new coverage, not a consolidation of something that existed
elsewhere.

Security log entries about logon/logoff/privilege use often need
admin to read even though Application/System usually don't - this is
a Windows ACL quirk on that specific log, not a bug here, so
get_admin_hint surfaces it plainly instead of guessing which logs
need elevation on a given machine.

Everything here is read-only. Clearing a log is destructive and
irreversible (event history cannot be recovered afterward), so
clear_log is confirm-gated and needs admin.
"""

import subprocess
from typing import Dict, List, Optional

_VALID_LEVELS = {"critical": 1, "error": 2, "warning": 3, "information": 4, "verbose": 5}


class EventViewer:
    """Query, filter, and (carefully) clear Windows Event Log entries."""

    def _run_ps(self, cmd: str, timeout: float = 30.0) -> Dict:
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

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "elevat" in err.lower()):
            return err + " - some logs (notably Security) need ULTRON running as Administrator to read."
        return err

    def list_logs(self) -> Dict:
        """All named event logs on this machine and their current
        record count - use a name from here with get_events() below.
        No admin needed for the listing itself."""
        result = self._run_ps(
            "Get-WinEvent -ListLog * -ErrorAction SilentlyContinue | "
            "Where-Object { $_.RecordCount -gt 0 } | "
            "Select-Object LogName, RecordCount, IsEnabled | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-WinEvent -ListLog failed")}
        if not result["stdout"]:
            return {"success": True, "logs": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse log list"}
        logs = data if isinstance(data, list) else [data]
        return {"success": True, "logs": logs, "count": len(logs)}

    def get_events(
        self,
        log_name: str = "Application",
        max_events: int = 25,
        level: Optional[str] = None,
        source: Optional[str] = None,
        since_hours: Optional[float] = None,
    ) -> Dict:
        """Recent entries from a named log (default 'Application'),
        newest first, optionally filtered by level ('critical',
        'error', 'warning', 'information', 'verbose'), event source,
        and/or a lookback window in hours. No admin needed for
        Application/System; Security usually requires it."""
        if not log_name:
            return {"error": "log_name must be non-empty"}
        filters = [f"LogName='{log_name}'"]
        if level:
            level_id = _VALID_LEVELS.get(level.lower())
            if level_id is None:
                return {"error": f"Unknown level '{level}'. Valid: {sorted(_VALID_LEVELS.keys())}"}
            filters.append(f"Level={level_id}")
        if source:
            safe_source = source.replace("'", "''")
            filters.append(f"ProviderName='{safe_source}'")
        if since_hours:
            filters.append(f"StartTime=(Get-Date).AddHours(-{float(since_hours)})")
        filter_hash = "; ".join(filters)
        cmd = (
            f"Get-WinEvent -FilterHashtable @{{{filter_hash}}} -MaxEvents {int(max_events)} -ErrorAction SilentlyContinue | "
            "Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, "
            "@{N='Message';E={$_.Message -replace '[\\r\\n]+',' '}} | ConvertTo-Json"
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            err = result["stderr"] or "Get-WinEvent failed"
            if "no events" in err.lower():
                return {"success": True, "events": [], "count": 0}
            return {"error": self._admin_hint(err)}
        if not result["stdout"]:
            return {"success": True, "events": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse event data"}
        events = data if isinstance(data, list) else [data]
        return {"success": True, "log_name": log_name, "events": events, "count": len(events)}

    def get_recent_errors(self, max_events: int = 25, since_hours: float = 24.0) -> Dict:
        """Convenience shortcut: critical+error entries from the
        Application and System logs combined, from the last N hours -
        the two logs someone troubleshooting 'something crashed
        recently' usually wants first, without picking a log name."""
        combined: List[Dict] = []
        for log_name in ("Application", "System"):
            for level in ("critical", "error"):
                result = self.get_events(log_name=log_name, max_events=max_events, level=level, since_hours=since_hours)
                if result.get("success"):
                    combined.extend(result.get("events", []))
        combined.sort(key=lambda e: e.get("TimeCreated", ""), reverse=True)
        return {"success": True, "events": combined[:max_events], "count": len(combined[:max_events])}

    def clear_log(self, log_name: str, confirm: bool = False) -> Dict:
        """Permanently clear every entry in a named log. Confirm-gated
        and irreversible - once cleared, that history cannot be
        recovered. Needs admin."""
        if not log_name:
            return {"error": "log_name must be non-empty"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will PERMANENTLY clear all entries in the '{log_name}' event log. This cannot be undone.",
            }
        safe_name = log_name.replace("'", "''")
        result = self._run_ps(f"Clear-EventLog -LogName '{safe_name}' -ErrorAction Stop")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not clear log '{log_name}'")}
        return {"success": True, "log_name": log_name, "cleared": True}
