"""
Windows Firewall automation
==============================
Wraps `netsh advfirewall` for the local machine's own firewall - status
checks and profile enable/disable, which the OS already requires admin
rights for.
"""

from typing import Dict

from apps.base_app import BaseApp


class FirewallApp(BaseApp):
    """Check status and toggle Windows Firewall profiles."""

    APP_NAME = "windows defender firewall"
    PROCESS_NAMES = ["mpssvc"]
    EXE_HINTS = []

    def get_status(self) -> Dict:
        return self.run_and_capture(["netsh", "advfirewall", "show", "allprofiles", "state"])

    def enable(self, profile: str = "allprofiles") -> Dict:
        return self.run_and_capture(["netsh", "advfirewall", "set", profile, "state", "on"])

    def disable(self, profile: str = "allprofiles") -> Dict:
        return self.run_and_capture(["netsh", "advfirewall", "set", profile, "state", "off"])

    def list_rules(self) -> Dict:
        result = self.run_and_capture(["netsh", "advfirewall", "firewall", "show", "rule", "name=all"], timeout=30.0)
        return result

    def open_console(self) -> Dict:
        return self.run_command(["wf.msc"])
