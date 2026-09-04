"""
Generic third-party antivirus status
=======================================
Queries the Windows Security Center (WMI SecurityCenter2) for whatever
antivirus product is currently registered, rather than assuming
Defender - useful when the user runs Norton/McAfee/etc alongside or
instead of it.
"""

from typing import Dict

from apps.base_app import BaseApp


class AntivirusApp(BaseApp):
    """Query which antivirus product(s) Windows Security Center sees."""

    APP_NAME = "antivirus"
    PROCESS_NAMES = []
    EXE_HINTS = []

    def get_status(self) -> Dict:
        result = self.run_and_capture(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | "
                "Select-Object displayName,productState | ConvertTo-Json",
            ]
        )
        if result.get("success") and result.get("stdout"):
            try:
                import json

                data = json.loads(result["stdout"])
                result["products"] = data if isinstance(data, list) else [data]
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("apps.security.antivirus.get_status")
        return result
