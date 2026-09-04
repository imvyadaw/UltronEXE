"""Windows Defender scanner
=========================
Query Windows Defender status, trigger scans, and check for updated
virus signatures via PowerShell's Defender cmdlets (Get-MpComputerStatus /
Start-MpScan / Update-MpSignature). Deliberately monitoring/scanning
only - no method here turns real-time protection off, since that's
the kind of action a script silently doing on a user's behalf is more
often a liability than a convenience.

Renamed from defender/defender.py (DefenderTools) as part of Phase 8's
windows/ restructure. Only windows/__init__.py imported the old
module, so this is a clean rename.
"""

import subprocess
from typing import Dict


class DefenderScanner:
    """Query Windows Defender status and trigger scans via PowerShell cmdlets."""

    def _run_ps(self, script: str, timeout: int = 30) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def get_status(self) -> Dict:
        """Get real-time protection / antivirus status summary."""
        try:
            script = (
                "Get-MpComputerStatus | Select-Object "
                "AntivirusEnabled,RealTimeProtectionEnabled,AntispywareEnabled,"
                "AntivirusSignatureLastUpdated,QuickScanAge | ConvertTo-Json"
            )
            result = self._run_ps(script)
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "Failed to query Defender status (needs admin PowerShell)"}
            return {"raw_output": result.stdout.strip()}
        except FileNotFoundError:
            return {"error": "PowerShell not found - Defender control is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}

    def start_quick_scan(self) -> Dict:
        """Kick off a Windows Defender quick scan (runs in the background)."""
        try:
            script = "Start-MpScan -ScanType QuickScan"
            subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
            return {"success": True, "message": "Quick scan started in the background"}
        except FileNotFoundError:
            return {"error": "PowerShell not found - Defender control is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}

    def start_full_scan(self) -> Dict:
        """Kick off a Windows Defender full scan (runs in the background - can take a long time)."""
        try:
            script = "Start-MpScan -ScanType FullScan"
            subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
            return {"success": True, "message": "Full scan started in the background - this can take a while"}
        except FileNotFoundError:
            return {"error": "PowerShell not found - Defender control is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}

    def update_signatures(self) -> Dict:
        """Trigger a Windows Defender virus definition update."""
        try:
            script = "Update-MpSignature"
            result = self._run_ps(script, timeout=60)
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "Failed to update signatures (needs admin PowerShell)"}
            return {"success": True, "message": "Virus definitions updated"}
        except FileNotFoundError:
            return {"error": "PowerShell not found - Defender control is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Signature update timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_threat_history(self) -> Dict:
        """List recently detected threats, if any."""
        try:
            script = "Get-MpThreatDetection | Select-Object -First 20 | ConvertTo-Json"
            result = self._run_ps(script)
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "Failed to query threat history"}
            return {"raw_output": result.stdout.strip() or "No threats detected"}
        except FileNotFoundError:
            return {"error": "PowerShell not found - Defender control is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}
