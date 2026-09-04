"""Defender Manager
====================
Windows Defender antivirus/real-time-protection control via the
`Defender` PowerShell module (Get-MpComputerStatus, Set-MpPreference,
Start-MpScan, Update-MpSignature). Distinct from the top-level
security/ package (Ultron's OWN internal auth/encryption/voice-lock/
privacy layer) - this controls the Windows OS's built-in antivirus,
not Ultron itself.

Status reads and running a scan don't change protection state.
Disabling real-time protection, adding exclusions, and toggling
cloud-delivered protection are confirm-gated as state-changing -
each one is a genuine reduction in this machine's malware defenses
and needs admin.
"""

import subprocess
from typing import Dict


class DefenderManager:
    """Inspect and control Windows Defender via the Defender PowerShell module."""

    def _run_ps(self, script: str, timeout: float = 60.0) -> Dict:
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

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower() or "elevat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def get_status(self) -> Dict:
        """Get overall Defender status: real-time protection, antivirus/antispyware
        enabled, signature age, last scan times."""
        script = (
            "Get-MpComputerStatus | Select-Object AMServiceEnabled, AntispywareEnabled, "
            "AntivirusEnabled, RealTimeProtectionEnabled, IoavProtectionEnabled, "
            "NISEnabled, AntivirusSignatureLastUpdated, QuickScanAge, FullScanAge, "
            "IsTamperProtected | ConvertTo-Json"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-MpComputerStatus failed")}
        import json

        try:
            return json.loads(result["stdout"])
        except Exception:
            return {"error": "Could not parse Defender status.", "raw": result["stdout"]}

    def set_realtime_protection(self, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable real-time protection. Confirm-gated - disabling this
        is a genuine reduction in malware defense and needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    "This will turn ON Defender real-time protection."
                    if enabled
                    else "This will turn OFF Defender real-time protection - the machine will "
                    "be unprotected from new threats until it's re-enabled."
                ),
            }
        val = "$false" if enabled else "$true"
        result = self._run_ps(f"Set-MpPreference -DisableRealtimeMonitoring {val}")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Set-MpPreference failed")}
        return {"success": True, "realtime_protection_enabled": enabled}

    def set_cloud_protection(self, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable cloud-delivered protection (MAPS). Confirm-gated, needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will turn {'ON' if enabled else 'OFF'} cloud-delivered protection.",
            }
        map_value = "Advanced" if enabled else "Disabled"
        result = self._run_ps(f"Set-MpPreference -MAPSReporting {map_value}")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Set-MpPreference failed")}
        return {"success": True, "cloud_protection_enabled": enabled}

    def start_scan(self, scan_type: str = "QuickScan", confirm: bool = False) -> Dict:
        """Start a Defender scan. scan_type is 'QuickScan' or 'FullScan'. Confirm-gated
        only because a FullScan can take a long time and use significant CPU/disk."""
        scan_type = scan_type if scan_type in ("QuickScan", "FullScan") else "QuickScan"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will start a Defender {scan_type} (may take a while and use CPU/disk).",
            }
        result = self._run_ps(f"Start-MpScan -ScanType {scan_type}")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Start-MpScan failed")}
        return {"success": True, "scan_type": scan_type, "message": "Scan started (runs in background)."}

    def update_signatures(self) -> Dict:
        """Update Defender's virus/spyware definitions. Not confirm-gated -
        purely additive/safe, same class as any other update check."""
        result = self._run_ps("Update-MpSignature")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Update-MpSignature failed")}
        return {"success": True, "message": "Signatures updated."}

    def list_threat_history(self, limit: int = 20) -> Dict:
        """List recently detected threats from Defender's history."""
        script = (
            f"Get-MpThreatDetection | Sort-Object InitialDetectionTime -Descending | "
            f"Select-Object -First {int(limit)} ThreatID, ProcessName, InitialDetectionTime, Resources | ConvertTo-Json"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-MpThreatDetection failed")}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            if isinstance(data, dict):
                data = [data]
            return {"threats": data, "count": len(data)}
        except Exception:
            return {"threats": [], "count": 0, "raw": result["stdout"]}

    def list_exclusions(self) -> Dict:
        """List current Defender path/process/extension exclusions."""
        script = "Get-MpPreference | Select-Object ExclusionPath, ExclusionProcess, ExclusionExtension | ConvertTo-Json"
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-MpPreference failed")}
        import json

        try:
            return json.loads(result["stdout"])
        except Exception:
            return {"error": "Could not parse exclusions.", "raw": result["stdout"]}

    def add_exclusion_path(self, path: str, confirm: bool = False) -> Dict:
        """Add a folder/file path Defender should skip scanning. Confirm-gated -
        every exclusion is a blind spot in malware coverage."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will tell Defender to STOP scanning '{path}' - anything malicious placed there won't be detected.",
            }
        result = self._run_ps(f"Add-MpPreference -ExclusionPath '{path}'")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Add-MpPreference failed")}
        return {"success": True, "excluded_path": path}

    def remove_exclusion_path(self, path: str, confirm: bool = False) -> Dict:
        """Remove a previously added path exclusion. Confirm-gated."""
        if not confirm:
            return {"requires_confirmation": True, "preview": f"This will resume Defender scanning of '{path}'."}
        result = self._run_ps(f"Remove-MpPreference -ExclusionPath '{path}'")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Remove-MpPreference failed")}
        return {"success": True, "removed_exclusion": path}
