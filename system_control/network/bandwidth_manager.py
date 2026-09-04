"""Bandwidth Manager
=====================
Per-adapter throughput/usage stats (Get-NetAdapterStatistics) and
per-app bandwidth throttling via Windows' built-in QoS Packet Scheduler
(New-NetQosPolicy -ThrottleRateActionBitsPerSecond) - the same
mechanism Group Policy-based bandwidth limits use, no third-party
dependency needed. Distinct from network/ethernet_manager.py (adapter
admin state/IP config, not traffic volume) and from network/
firewall_manager.py (allow/block, not rate limiting).

Creating/removing a QoS policy is confirm-gated - a bad throttle can
make an app or the whole machine feel broken until the policy is found
and removed.
"""

import subprocess
import json
from typing import Dict, Optional


class BandwidthManager:
    """Adapter throughput stats and QoS-based per-app bandwidth limits."""

    def _run_ps(self, script: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "powershell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_bandwidth_usage(self, adapter: Optional[str] = None) -> Dict:
        """Cumulative received/sent bytes per adapter since it was last
        reset (link up, or driver reload) - a snapshot, not a live rate.
        Call twice a known interval apart to derive a rate."""
        filt = f"-Name '{adapter}'" if adapter else ""
        script = (
            f"Get-NetAdapterStatistics {filt} | "
            "Select-Object Name, ReceivedBytes, SentBytes, ReceivedUnicastPackets, "
            "SentUnicastPackets | ConvertTo-Json -Depth 2"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-NetAdapterStatistics failed"}
        if not result["stdout"]:
            return {"success": True, "adapters": []}
        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse adapter statistics"}
        items = data if isinstance(data, list) else [data]
        return {
            "success": True,
            "adapters": [
                {
                    "name": a.get("Name"),
                    "received_bytes": a.get("ReceivedBytes"),
                    "sent_bytes": a.get("SentBytes"),
                    "received_packets": a.get("ReceivedUnicastPackets"),
                    "sent_packets": a.get("SentUnicastPackets"),
                }
                for a in items
            ],
        }

    def list_qos_policies(self) -> Dict:
        """List all NetQosPolicy entries currently defined (ULTRON's own
        throttles and any pre-existing ones)."""
        result = self._run_ps(
            "Get-NetQosPolicy | Select-Object Name, AppPathNameMatchCondition, "
            "IPProtocolMatchCondition, IPDstPortStartMatchCondition, "
            "ThrottleRateActionBitsPerSecond | ConvertTo-Json -Depth 2"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-NetQosPolicy failed"}
        if not result["stdout"]:
            return {"success": True, "policies": []}
        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse QoS policy list"}
        items = data if isinstance(data, list) else [data]
        return {
            "success": True,
            "policies": [
                {
                    "name": p.get("Name"),
                    "app_path": p.get("AppPathNameMatchCondition"),
                    "protocol": p.get("IPProtocolMatchCondition"),
                    "port": p.get("IPDstPortStartMatchCondition"),
                    "throttle_bps": p.get("ThrottleRateActionBitsPerSecond"),
                }
                for p in items
            ],
        }

    def create_bandwidth_limit(
        self,
        policy_name: str,
        limit_mbps: float,
        app_path: Optional[str] = None,
        port: Optional[int] = None,
        confirm: bool = False,
    ) -> Dict:
        """Create a QoS policy throttling traffic to limit_mbps, matched
        by app_path and/or port (at least one required - an unscoped
        policy would throttle everything). Needs admin. Confirm-gated."""
        if not app_path and not port:
            return {"error": "at least one of app_path or port is required to scope the limit"}
        bps = int(limit_mbps * 1_000_000)
        if not confirm:
            scope = f"app {app_path}" if app_path else f"port {port}"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would create QoS policy '{policy_name}' throttling {scope} " f"to {limit_mbps} Mbps.",
                "message": "Call again with confirm=true to create.",
            }
        parts = [f"-Name '{policy_name}'", f"-ThrottleRateActionBitsPerSecond {bps}"]
        if app_path:
            parts.append(f"-AppPathNameMatchCondition '{app_path}'")
        if port:
            parts.append(f"-IPDstPortStartMatchCondition {port} -IPDstPortEndMatchCondition {port}")
        script = "New-NetQosPolicy " + " ".join(parts)
        result = self._run_ps(script)
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "policy_name": policy_name,
            "limit_mbps": limit_mbps,
            "error": None if result["success"] else result["stderr"],
        }

    def remove_bandwidth_limit(self, policy_name: str, confirm: bool = False) -> Dict:
        """Delete a QoS bandwidth-limit policy by name. Needs admin.
        Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would remove QoS policy '{policy_name}'.",
                "message": "Call again with confirm=true to remove.",
            }
        result = self._run_ps(f"Remove-NetQosPolicy -Name '{policy_name}' -Confirm:$false")
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "policy_name": policy_name,
            "error": None if result["success"] else result["stderr"],
        }
