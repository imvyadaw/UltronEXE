"""Windows Device Manager automation (opens devmgmt.msc; listing devices
via PowerShell's Get-PnpDevice, which is far more reliable than reading
the Device Manager GUI)."""

import subprocess
from typing import Dict

from apps.base_app import BaseApp


class DeviceManagerApp(BaseApp):
    """Open Device Manager and list connected devices."""

    APP_NAME = "device manager"
    PROCESS_NAMES = ["mmc.exe"]
    EXE_HINTS = []

    def open(self) -> Dict:
        try:
            subprocess.Popen(["devmgmt.msc"], shell=True)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def list_devices(self, only_problems: bool = False) -> Dict:
        cmd = "Get-PnpDevice | Select-Object FriendlyName,Status,Class | ConvertTo-Json"
        if only_problems:
            cmd = "Get-PnpDevice | Where-Object {$_.Status -ne 'OK'} | Select-Object FriendlyName,Status,Class | ConvertTo-Json"
        result = self.run_and_capture(["powershell", "-NoProfile", "-Command", cmd], timeout=30.0)
        if result.get("success") and result.get("stdout"):
            try:
                import json

                data = json.loads(result["stdout"])
                result["devices"] = data if isinstance(data, list) else [data]
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("apps.system.device_manager.list_devices")
        return result
