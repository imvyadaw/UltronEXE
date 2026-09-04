"""
Windows Defender automation
==============================
CLI/PowerShell-driven status checks and scans for the local machine's
own antivirus - legitimate self-administration, not a way to disable
protection on someone else's machine or evade detection.
"""

from typing import Dict

from apps.base_app import BaseApp


class WindowsDefenderApp(BaseApp):
    """Check status and run scans via Windows Defender."""

    APP_NAME = "windows security"
    PROCESS_NAMES = ["msmpeng.exe", "securityhealthservice.exe"]
    EXE_HINTS = []

    def get_status(self) -> Dict:
        result = self.run_and_capture(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-MpComputerStatus | Select-Object AntivirusEnabled,RealTimeProtectionEnabled,AntivirusSignatureLastUpdated | ConvertTo-Json",
            ]
        )
        if result.get("success") and result.get("stdout"):
            try:
                import json

                result["status"] = json.loads(result["stdout"])
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("apps.security.windows_defender.get_status")
        return result

    def run_quick_scan(self) -> Dict:
        return self.run_and_capture(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Start-MpScan -ScanType QuickScan",
            ],
            timeout=300.0,
        )

    def update_definitions(self) -> Dict:
        return self.run_and_capture(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Update-MpSignature",
            ],
            timeout=120.0,
        )

    def open_security_center(self) -> Dict:
        return self.open()
