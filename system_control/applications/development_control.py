"""Development Control
======================
OS-level, category-wide developer-tooling management - distinct from
apps/development/*.py (docker.py, vscode.py, git.py, pycharm.py,
postman.py, terminal.py), which each drive one already-open tool
instance to do something (open a folder, list containers, run a git
command). This module instead operates one layer up: which dev tools
are installed on this machine at all, the OS-level developer features
that no single tool owns (Windows Developer Mode, WSL), and bulk
process actions across every known dev tool at once - the same split
office_control.py/browser_control.py/communication_control.py already
use for their own categories.

Tool-presence checks use `where` (fast, no admin) rather than
duplicating each apps/development/*.py's own resolve_executable()
logic. Git config reading is read-only (`git config --global --list`)
- actually changing git config isn't this module's job and belongs
with git.py's own automation surface if added there. Environment
variable *reads* here are dev-focused convenience filtering (PATH
entries, JAVA_HOME/ANDROID_HOME/etc.); reading/writing arbitrary env
vars is system_control/system_config/environment_variables.py's job
and isn't duplicated here.

Windows Developer Mode and WSL feature install are confirm-gated and
need admin: Developer Mode relaxes app-sideloading/symlink
restrictions machine-wide, and installing the WSL feature typically
requires a reboot to finish.
"""
import logging

import os
import shutil
import subprocess
import winreg
from typing import Dict, List

# tool name -> the command used to check for it and report a version.
_DEV_TOOLS = {
    "git": ["git", "--version"],
    "node": ["node", "--version"],
    "npm": ["npm", "--version"],
    "python": ["python", "--version"],
    "docker": ["docker", "--version"],
    "java": ["java", "-version"],
    "dotnet": ["dotnet", "--version"],
    "code": ["code", "--version"],
    "gcc": ["gcc", "--version"],
    "go": ["go", "version"],
    "rustc": ["rustc", "--version"],
    "cargo": ["cargo", "--version"],
}

# Common dev-specific environment variables worth surfacing, beyond
# the generic PATH scan.
_DEV_ENV_VARS = [
    "JAVA_HOME",
    "ANDROID_HOME",
    "ANDROID_SDK_ROOT",
    "GOPATH",
    "GOROOT",
    "CARGO_HOME",
    "RUSTUP_HOME",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "NODE_PATH",
    "M2_HOME",
    "GRADLE_HOME",
]

# Known dev-tool processes for bulk close - IDEs and Docker Desktop
# only; deliberately excludes cmd.exe/powershell.exe/wsl.exe since
# force-closing a shell can kill unrelated, unsaved terminal work.
_DEV_TOOL_PROCESSES = {
    "code.exe": "VS Code",
    "pycharm64.exe": "PyCharm",
    "idea64.exe": "IntelliJ IDEA",
    "Docker Desktop.exe": "Docker Desktop",
    "Postman.exe": "Postman",
    "WindowsTerminal.exe": "Windows Terminal",
}

_DEV_MODE_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock"
_DEV_MODE_VALUE = "AllowDevelopmentWithoutDevLicense"


class DevelopmentControl:
    """Dev-tool discovery, dev-focused environment inspection, git
    config (read-only), Windows Developer Mode, WSL management, and
    bulk process actions across known dev tools."""

    def _run_ps(self, cmd: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def discover_dev_tools(self) -> Dict:
        """Which known dev CLIs are on PATH, and their reported
        version. No admin needed."""
        found: List[Dict] = []
        for tool, version_cmd in _DEV_TOOLS.items():
            path = shutil.which(tool)
            if not path:
                continue
            version = None
            try:
                result = subprocess.run(version_cmd, capture_output=True, text=True, timeout=10)
                out = (result.stdout or result.stderr).strip()
                version = out.splitlines()[0] if out else None
            except Exception:
                logging.getLogger(__name__).exception("Suppressed Exception")
            found.append({"tool": tool, "path": path, "version": version})
        return {"success": True, "installed": found, "count": len(found)}

    def get_dev_environment(self) -> Dict:
        """PATH entries that look development-related (contain the
        name of a known dev tool or common install folder), plus
        whichever well-known dev environment variables are currently
        set. No admin needed. Setting/removing env vars is
        system_control/system_config/environment_variables.py's job,
        not this method's."""
        path_entries = os.environ.get("PATH", "").split(os.pathsep)
        markers = ("python", "node", "git", "java", "jdk", "sdk", "cargo", "go", "dotnet", "npm")
        dev_path_entries = [p for p in path_entries if p and any(m in p.lower() for m in markers)]
        dev_vars = {name: os.environ[name] for name in _DEV_ENV_VARS if name in os.environ}
        return {
            "success": True,
            "dev_related_path_entries": dev_path_entries,
            "dev_environment_variables": dev_vars,
            "total_path_entries": len([p for p in path_entries if p]),
        }

    def get_git_global_config(self) -> Dict:
        """Read-only dump of `git config --global --list` (user.name,
        user.email, core.editor, etc). Actually changing git config
        is out of scope here - see apps/development/git.py."""
        if not shutil.which("git"):
            return {"error": "git not found on PATH"}
        try:
            result = subprocess.run(["git", "config", "--global", "--list"], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "No global git config found."}
            config = {}
            for line in result.stdout.strip().splitlines():
                if "=" in line:
                    key, _, value = line.partition("=")
                    config[key] = value
            return {"success": True, "config": config}
        except subprocess.TimeoutExpired:
            return {"error": "git config timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_developer_mode_status(self) -> Dict:
        """Whether Windows Developer Mode (sideloading apps, symlinks
        without admin, Device Portal) is enabled. No admin needed to read."""
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DEV_MODE_PATH) as key:
                try:
                    value, _ = winreg.QueryValueEx(key, _DEV_MODE_VALUE)
                    return {"success": True, "developer_mode_enabled": bool(value)}
                except FileNotFoundError:
                    return {"success": True, "developer_mode_enabled": False}
        except FileNotFoundError:
            return {"success": True, "developer_mode_enabled": False}
        except OSError as e:
            return {"error": str(e)}

    def set_developer_mode(self, enabled: bool, confirm: bool = False) -> Dict:
        """Enable/disable Windows Developer Mode. Confirm-gated and
        needs admin - this is a machine-wide security-relevant
        setting (relaxes app-sideloading and unprivileged-symlink
        restrictions), not scoped to any one app."""
        if not confirm:
            action = "enable" if enabled else "disable"
            return {
                "requires_confirmation": True,
                "preview": f"This will {action} Windows Developer Mode machine-wide (affects app sideloading "
                f"and unprivileged symlink creation). Needs Administrator.",
            }
        try:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, _DEV_MODE_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, _DEV_MODE_VALUE, 0, winreg.REG_DWORD, 1 if enabled else 0)
            return {"success": True, "developer_mode_enabled": enabled}
        except PermissionError:
            return {"error": "Access denied - run ULTRON as Administrator to change Developer Mode."}
        except OSError as e:
            return {"error": str(e)}

    def list_wsl_distros(self) -> Dict:
        """Installed WSL distros, their state (Running/Stopped), and
        WSL version (1 or 2), via `wsl -l -v`. No admin needed."""
        if not shutil.which("wsl"):
            return {"error": "wsl.exe not found - WSL isn't installed on this machine."}
        try:
            result = subprocess.run(["wsl", "-l", "-v"], capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "wsl -l -v failed"}
            distros = []
            lines = [l for l in result.stdout.replace("\x00", "").splitlines() if l.strip()]
            for line in lines[1:]:  # skip header row
                is_default = line.strip().startswith("*")
                parts = line.replace("*", "", 1).split()
                if len(parts) >= 3:
                    distros.append(
                        {"name": parts[0], "state": parts[1], "wsl_version": parts[2], "default": is_default}
                    )
            return {"success": True, "distros": distros, "count": len(distros)}
        except subprocess.TimeoutExpired:
            return {"error": "wsl -l -v timed out"}
        except Exception as e:
            return {"error": str(e)}

    def set_default_wsl_distro(self, name: str, confirm: bool = False) -> Dict:
        """Set which WSL distro `wsl` launches by default. Confirm-gated."""
        if not confirm:
            return {"requires_confirmation": True, "preview": f"This will set '{name}' as the default WSL distro."}
        try:
            result = subprocess.run(["wsl", "--set-default", name], capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return {"error": result.stderr.strip() or f"Could not set '{name}' as default"}
            return {"success": True, "default_distro": name}
        except Exception as e:
            return {"error": str(e)}

    def stop_wsl_distro(self, name: str, confirm: bool = False) -> Dict:
        """Terminate a running WSL distro (`wsl --terminate`).
        Confirm-gated - ends every process running inside it, same as
        closing a VM without a graceful shutdown."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will forcibly terminate the '{name}' WSL distro and everything running inside it.",
            }
        try:
            result = subprocess.run(["wsl", "--terminate", name], capture_output=True, text=True, timeout=20)
            if result.returncode != 0:
                return {"error": result.stderr.strip() or f"Could not terminate '{name}'"}
            return {"success": True, "terminated": name}
        except Exception as e:
            return {"error": str(e)}

    def install_wsl(self, confirm: bool = False) -> Dict:
        """Install the WSL feature and default Linux distro
        (`wsl --install`). Confirm-gated, needs admin, and typically
        requires a reboot to finish."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will install the Windows Subsystem for Linux feature and a default distro. "
                "Needs Administrator and typically requires a reboot to complete.",
            }
        try:
            result = subprocess.run(["wsl", "--install"], capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip() or "wsl --install failed"
                if "access" in err.lower() or "denied" in err.lower():
                    err += " - run ULTRON as Administrator."
                return {"error": err}
            return {"success": True, "installed": True, "reboot_required": True, "output": result.stdout.strip()}
        except subprocess.TimeoutExpired:
            return {
                "error": "wsl --install timed out - it may still be running in the background; check `wsl -l -v` after a reboot."
            }
        except Exception as e:
            return {"error": str(e)}

    def close_all_dev_tools(self, confirm: bool = False) -> Dict:
        """Force-close every running known dev-tool process (IDEs,
        Docker Desktop, Postman, Windows Terminal). Deliberately
        excludes cmd/PowerShell/WSL shells - see module docstring.
        Confirm-gated: unsaved work in an IDE is lost, no save prompt."""
        if not confirm:
            names = ", ".join(sorted(set(_DEV_TOOL_PROCESSES.values())))
            return {
                "requires_confirmation": True,
                "preview": f"This will force-close every running dev tool ({names}). Unsaved changes will be lost.",
            }
        closed = []
        for exe, friendly in _DEV_TOOL_PROCESSES.items():
            result = self._run_ps(
                f"Get-Process -Name '{exe[:-4]}' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
            )
            if "error" not in result:
                closed.append(friendly)
        return {"success": True, "attempted": closed}
