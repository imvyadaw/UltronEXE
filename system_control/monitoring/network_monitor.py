"""Network Monitor (system_control)
====================================
Windows adapter-level link health and OS-recorded connection history -
distinct from deep_os_integration/network_monitor.py (per-process
psutil bandwidth/connections, Task Manager's "App history" view) and
from the read-only status calls already in system_control/network/*
(wifi_manager.get_current_connection, ethernet_manager.get_adapter_status),
which report current state, not link quality or history.

This module answers "is the link itself healthy" - negotiated speed
vs adapter capability, error/discard counters (the NIC-level signal
of a bad cable or driver, invisible to psutil), and a chronological
connect/disconnect history pulled from the Wlan-AutoConfig and
Kernel-Network-related Event Log channels - plus a simple ping-based
packet-loss check.

All reads; nothing here changes system state, so nothing is
confirm-gated.
"""

import subprocess
from typing import Dict, Optional


class NetworkMonitor:
    """Adapter link-quality counters, OS connection history, and
    packet-loss checks - the link-health surface, distinct from the
    per-process bandwidth/connection tools elsewhere in the codebase."""

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

    def get_adapter_statistics(self, name: Optional[str] = None) -> Dict:
        """Sent/received bytes plus error and discard counters per
        adapter (Get-NetAdapterStatistics) - the NIC-level signal of a
        failing cable, bad driver, or duplex mismatch that psutil's
        cross-platform counters don't expose. No admin needed."""
        filt = f"-Name '{name}'" if name else ""
        result = self._run_ps(
            f"Get-NetAdapterStatistics {filt} -ErrorAction SilentlyContinue | "
            "Select-Object Name, ReceivedBytes, SentBytes, ReceivedUnicastPackets, SentUnicastPackets, "
            "ReceivedDiscardedPackets, ReceivedPacketErrors, OutboundDiscardedPackets, OutboundPacketErrors | "
            "ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"] or not result["stdout"]:
            return {"error": result["stderr"] or f"No adapter statistics found{f' for {name}' if name else ''}."}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse adapter statistics"}
        rows = data if isinstance(data, list) else [data]
        return {"success": True, "adapters": rows, "count": len(rows)}

    def get_link_quality(self, name: Optional[str] = None) -> Dict:
        """Negotiated link speed, media connection state, and whether
        that speed matches the adapter's rated capability - a mismatch
        (e.g. gigabit NIC negotiating 100 Mbps) usually means a bad
        cable or port. No admin needed."""
        filt = f"-Name '{name}'" if name else ""
        result = self._run_ps(
            f"Get-NetAdapter {filt} -ErrorAction SilentlyContinue | "
            "Select-Object Name, Status, LinkSpeed, MediaConnectionState, MacAddress, InterfaceDescription | "
            "ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"] or not result["stdout"]:
            return {"error": result["stderr"] or f"No adapter found{f' named {name}' if name else ''}."}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse adapter data"}
        rows = data if isinstance(data, list) else [data]
        return {"success": True, "adapters": rows, "count": len(rows)}

    def get_connection_history(self, limit: int = 20) -> Dict:
        """Recent Wi-Fi connect/disconnect events (WLAN-AutoConfig
        Event IDs 8001/8003) from the OS event log - a real history of
        what the machine actually joined and dropped, distinct from
        wifi_manager's live-only current-connection snapshot. No admin
        needed; returns empty (not an error) if the channel has
        nothing recent."""
        result = self._run_ps(
            "Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-WLAN-AutoConfig/Operational'; "
            "Id=8001,8003,8011} "
            f"-MaxEvents {int(limit)} -ErrorAction SilentlyContinue | "
            "Select-Object TimeCreated, Id, Message | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "success": True,
                "events": [],
                "count": 0,
                "note": "WLAN event channel unavailable or empty (no Wi-Fi adapter, or channel not enabled).",
            }
        if not result["stdout"]:
            return {"success": True, "events": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse event log data"}
        rows = data if isinstance(data, list) else [data]
        events = [{"time": r.get("TimeCreated"), "event_id": r.get("Id"), "message": r.get("Message")} for r in rows]
        return {"success": True, "events": events, "count": len(events)}

    def check_packet_loss(self, target: str = "8.8.8.8", count: int = 4) -> Dict:
        """Simple ping-based packet-loss and round-trip-time check
        against a target host. No admin needed."""
        safe_target = target.replace("'", "''")
        result = self._run_ps(
            f"$r = Test-Connection -ComputerName '{safe_target}' -Count {max(1, int(count))} -ErrorAction SilentlyContinue; "
            "if ($r) { "
            "[PSCustomObject]@{ Sent = $r.Count; Received = ($r | Where-Object { $_.StatusCode -eq 0 -or $_.ResponseTime -ne $null }).Count; "
            "AvgLatencyMs = [math]::Round((($r | Measure-Object ResponseTime -Average).Average), 1) } | ConvertTo-Json "
            "} else { '{}' }"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Could not ping {target}."}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else {}
        except json.JSONDecodeError:
            return {"error": "Could not parse ping results"}
        sent = data.get("Sent", count)
        received = data.get("Received", 0)
        loss_pct = round((1 - (received / sent)) * 100, 1) if sent else 100.0
        return {
            "success": True,
            "target": target,
            "sent": sent,
            "received": received,
            "packet_loss_percent": loss_pct,
            "avg_latency_ms": data.get("AvgLatencyMs"),
        }
