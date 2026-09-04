"""Visual Studio Code automation (drives the `code` CLI, which the VS
Code installer adds to PATH - far more reliable than GUI automation)."""

from typing import Dict, Optional

from apps.base_app import BaseApp


class VSCodeApp(BaseApp):
    """Open folders/files and manage extensions via the `code` CLI."""

    APP_NAME = "vscode"
    PROCESS_NAMES = ["code.exe", "code"]
    EXE_HINTS = ["code", "code.cmd", "code.exe"]

    def open_folder(self, path: str) -> Dict:
        exe = self.resolve_executable() or "code"
        return self.run_command([exe, path])

    def open_file(self, path: str, line: Optional[int] = None) -> Dict:
        exe = self.resolve_executable() or "code"
        if line:
            return self.run_command([exe, "-g", f"{path}:{line}"])
        return self.run_command([exe, path])

    def new_window(self) -> Dict:
        exe = self.resolve_executable() or "code"
        return self.run_command([exe, "-n"])

    def install_extension(self, extension_id: str) -> Dict:
        exe = self.resolve_executable() or "code"
        return self.run_and_capture([exe, "--install-extension", extension_id])

    def list_extensions(self) -> Dict:
        exe = self.resolve_executable() or "code"
        result = self.run_and_capture([exe, "--list-extensions"])
        if result.get("success"):
            result["extensions"] = [line for line in result["stdout"].splitlines() if line.strip()]
        return result

    def diff(self, file1: str, file2: str) -> Dict:
        exe = self.resolve_executable() or "code"
        return self.run_command([exe, "--diff", file1, file2])
