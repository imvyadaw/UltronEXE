"""Reliability Monitor
=====================
Read access to Windows' Reliability Monitor (perfmon /rel) - the
System Stability Index (0-10, higher is more stable) and the
underlying timeline of application failures, Windows failures, and
miscellaneous failures/warnings it's computed from. Distinct from
event_viewer.py (raw, high-volume Event Log entries covering
everything, no stability scoring) - this module reads the specific,
pre-curated, already-scored reliability history Windows itself
maintains in the RacWmiProvider WMI classes (the same data source the
Reliability Monitor GUI reads), which is a much shorter, higher-
signal list of "things that actually affected stability" than the
full Event Log.

Read-only; nothing here changes system state, so nothing is
confirm-gated. Some Windows builds only populate this data after a
few days of uptime/history - an empty result on a fresh install or
recently-reset machine is expected, not an error, and is reported as
such rather than as a failure.
"""

import subprocess
from typing import Dict, List, Optional


class ReliabilityMonitor:
    """Read Windows' System Stability Index and reliability history
    (RacWmiProvider), the curated counterpart to event_viewer.py's
    raw Event Log."""

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

    def get_stability_index(self) -> Dict:
        """Current System Stability Index (0.0-10.0, higher = more
        stable) and the date it was computed for - the single number
        shown at the top of the Reliability Monitor graph. No admin
        needed."""
        result = self._run_ps(
            "Get-CimInstance Win32_ReliabilityStabilityMetrics -ErrorAction SilentlyContinue | "
            "Sort-Object TimeGenerated -Descending | Select-Object -First 1 "
            "SystemStabilityIndex, TimeGenerated | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not query stability metrics"}
        if not result["stdout"]:
            return {
                "success": True,
                "available": False,
                "reason": "No stability history yet - typical on a fresh install or recently-reset machine.",
            }
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse stability metrics"}
        return {
            "success": True,
            "available": True,
            "stability_index": data.get("SystemStabilityIndex"),
            "as_of": data.get("TimeGenerated"),
        }

    def get_stability_history(self, days: int = 30) -> Dict:
        """Daily Stability Index values over the last N days, the same
        series the Reliability Monitor line graph plots. No admin
        needed."""
        result = self._run_ps(
            f"Get-CimInstance Win32_ReliabilityStabilityMetrics -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.TimeGenerated -ge (Get-Date).AddDays(-{int(days)}) }} | "
            "Sort-Object TimeGenerated | Select-Object TimeGenerated, SystemStabilityIndex | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not query stability history"}
        if not result["stdout"]:
            return {"success": True, "history": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse stability history"}
        history = data if isinstance(data, list) else [data]
        return {"success": True, "history": history, "count": len(history)}

    def get_recent_failures(self, max_events: int = 25, category: Optional[str] = None) -> Dict:
        """The individual failure/warning records the stability index
        is computed from - each one is what shows as a red/yellow icon
        on a given day in the Reliability Monitor GUI. Optionally
        filter by category ('application_failure', 'windows_failure',
        'miscellaneous_failure', 'application_install',
        'application_uninstall', 'hardware_failure'). No admin
        needed."""
        where = ""
        if category:
            safe_cat = category.replace("'", "''")
            where = f" | Where-Object {{ $_.SourceName -match '{safe_cat}' }}"
        result = self._run_ps(
            f"Get-CimInstance Win32_ReliabilityRecords -ErrorAction SilentlyContinue{where} | "
            f"Sort-Object TimeGenerated -Descending | Select-Object -First {int(max_events)} "
            "TimeGenerated, SourceName, Message, ProductName | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not query reliability records"}
        if not result["stdout"]:
            return {"success": True, "failures": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse reliability records"}
        failures = data if isinstance(data, list) else [data]
        return {"success": True, "failures": failures, "count": len(failures)}

    def get_crash_summary(self, days: int = 7) -> Dict:
        """Convenience rollup: how many application failures vs
        Windows/OS failures occurred in the last N days, plus which
        apps crashed most - a quick answer to 'has anything been
        crashing lately' without reading the raw record list. No admin
        needed."""
        result = self._run_ps(
            f"Get-CimInstance Win32_ReliabilityRecords -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.TimeGenerated -ge (Get-Date).AddDays(-{int(days)}) }} | "
            "Select-Object SourceName, ProductName | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not query reliability records"}
        if not result["stdout"]:
            return {"success": True, "total": 0, "by_source": {}, "top_products": []}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse reliability records"}
        records: List[Dict] = data if isinstance(data, list) else [data]

        by_source: Dict[str, int] = {}
        by_product: Dict[str, int] = {}
        for r in records:
            src = r.get("SourceName") or "unknown"
            by_source[src] = by_source.get(src, 0) + 1
            product = r.get("ProductName")
            if product:
                by_product[product] = by_product.get(product, 0) + 1

        top_products = sorted(by_product.items(), key=lambda kv: kv[1], reverse=True)[:10]
        return {
            "success": True,
            "total": len(records),
            "by_source": by_source,
            "top_products": [{"product": p, "count": c} for p, c in top_products],
        }
