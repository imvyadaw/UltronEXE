"""Windows Control Panel automation (via control.exe applet shortcuts)."""

import subprocess
from typing import Dict

from apps.base_app import BaseApp

APPLETS = {
    "programs": "appwiz.cpl",
    "network": "ncpa.cpl",
    "sound": "mmsys.cpl",
    "system": "sysdm.cpl",
    "power": "powercfg.cpl",
    "mouse": "main.cpl",
    "date_time": "timedate.cpl",
    "firewall": "firewall.cpl",
    "user_accounts": "nusrmgr.cpl",
    "device_manager": "hdwwiz.cpl",
    "region": "intl.cpl",
}


class ControlPanelApp(BaseApp):
    """Open Control Panel or jump straight to a named applet."""

    APP_NAME = "control panel"
    PROCESS_NAMES = ["control.exe", "explorer.exe"]
    EXE_HINTS = ["control", "control.exe"]

    def open_applet(self, applet_name: str) -> Dict:
        cpl = APPLETS.get(applet_name.lower().replace(" ", "_"))
        if not cpl:
            return {"error": f"Unknown applet '{applet_name}'. Known: {list(APPLETS)}"}
        try:
            subprocess.Popen(["control", cpl])
            return {"success": True, "applet": applet_name}
        except Exception as e:
            return {"error": str(e)}

    def list_applets(self) -> Dict:
        return {"success": True, "applets": list(APPLETS.keys())}
