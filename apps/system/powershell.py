"""PowerShell automation (CLI-driven)."""

from typing import Dict

from apps.base_app import BaseApp


class PowerShellApp(BaseApp):
    """Run PowerShell commands/scripts and capture their output."""

    APP_NAME = "powershell"
    PROCESS_NAMES = ["powershell.exe", "pwsh.exe"]
    EXE_HINTS = ["powershell", "pwsh", "powershell.exe"]

    def run_command(self, command: str, timeout: float = 30.0) -> Dict:
        exe = self.resolve_executable() or "powershell"
        return self.run_and_capture([exe, "-NoProfile", "-Command", command], timeout=timeout)

    def run_script(self, script_path: str, timeout: float = 60.0) -> Dict:
        exe = self.resolve_executable() or "powershell"
        return self.run_and_capture([exe, "-NoProfile", "-File", script_path], timeout=timeout)

    def open_console(self) -> Dict:
        exe = self.resolve_executable() or "powershell"
        return super().run_command([exe])
