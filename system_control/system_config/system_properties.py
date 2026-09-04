"""System Properties
====================
Read-heavy wrapper around the "System Properties" surface (the classic
sysdm.cpl dialog: computer name, OS/hardware info, performance options,
virtual memory) plus the one write ULTRON is allowed to make here
(computer description - cosmetic, HKLM but a well-known safe value).
Renaming the actual computer *name* needs a reboot and can break domain/
network trust, so that stays read-only-plus-launch-the-dialog rather
than something ULTRON does unattended.

All info methods shell out to PowerShell/WMI (Get-CimInstance) - same
approach windows/system_info/diagnostics.py already uses - rather than
re-parsing systeminfo.exe's text output.
"""

import subprocess
import json
from typing import Dict


class SystemProperties:
    """Computer name/info, performance options, virtual memory - read-heavy."""

    def _run_ps(self, cmd: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "PowerShell command failed"}
            return {"success": True, "stdout": result.stdout.strip()}
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_computer_info(self) -> Dict:
        """Computer name, domain/workgroup, OS version/build, manufacturer/model."""
        cmd = (
            "$cs = Get-CimInstance Win32_ComputerSystem; "
            "$os = Get-CimInstance Win32_OperatingSystem; "
            "[PSCustomObject]@{ ComputerName=$cs.Name; Domain=$cs.Domain; "
            "PartOfDomain=$cs.PartOfDomain; Manufacturer=$cs.Manufacturer; "
            "Model=$cs.Model; TotalPhysicalMemoryGB=[math]::Round($cs.TotalPhysicalMemory/1GB,2); "
            "OSName=$os.Caption; OSVersion=$os.Version; OSBuild=$os.BuildNumber; "
            "Architecture=$os.OSArchitecture } | ConvertTo-Json"
        )
        result = self._run_ps(cmd)
        if not result.get("success"):
            return result
        try:
            return {"success": True, "computer_info": json.loads(result["stdout"])}
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}

    def get_performance_options(self) -> Dict:
        """Visual-effects performance setting (best appearance / best
        performance / custom) - read from the same registry value the
        sysdm.cpl > Advanced > Performance dialog uses."""
        try:
            import winreg
        except ImportError:
            return {"error": "winreg is only available on Windows"}
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
            ) as key:
                try:
                    value, _ = winreg.QueryValueEx(key, "VisualFXSetting")
                except FileNotFoundError:
                    value = None
            labels = {0: "Let Windows choose", 1: "Best appearance", 2: "Best performance", 3: "Custom"}
            return {"success": True, "visual_fx_setting": value, "label": labels.get(value, "Unknown")}
        except FileNotFoundError:
            return {"success": True, "visual_fx_setting": None, "label": "Default (never customized)"}
        except Exception as e:
            return {"error": str(e)}

    def get_virtual_memory_info(self) -> Dict:
        """Current page file(s): location, allocated/current size."""
        cmd = (
            "Get-CimInstance Win32_PageFileUsage | Select-Object Name,AllocatedBaseSize,CurrentUsage "
            "| ConvertTo-Json"
        )
        result = self._run_ps(cmd)
        if not result.get("success"):
            return result
        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            page_files = data if isinstance(data, list) else [data]
            return {"success": True, "page_files": page_files, "count": len(page_files)}
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}

    def get_system_protection_status(self) -> Dict:
        """System Restore protection status per drive."""
        cmd = "Get-ComputerRestorePoint | Select-Object -First 5 Description,CreationTime | ConvertTo-Json"
        result = self._run_ps(cmd)
        if not result.get("success"):
            return result
        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            points = data if isinstance(data, list) else [data]
            return {"success": True, "recent_restore_points": points}
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}

    def set_computer_description(self, description: str, confirm: bool = False) -> Dict:
        """Set the cosmetic 'computer description' field (sysdm.cpl's
        description box) - safe, does not require a reboot, unlike
        renaming the computer itself. HKLM but this specific value is
        low-risk (display text only)."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would set computer description to {description!r}",
                "message": "Call again with confirm=true to apply.",
            }
        cmd = (
            f"Set-ItemProperty -Path "
            f"'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\LanmanServer\\Parameters' "
            f"-Name 'srvcomment' -Value '{description}'"
        )
        result = self._run_ps(cmd)
        if not result.get("success"):
            err = result.get("error", "")
            if "access" in err.lower() or "denied" in err.lower():
                err += " - this needs ULTRON running as Administrator."
            return {"error": err}
        return {"success": True, "description": description}

    def open_system_properties_dialog(self, tab: str = "general") -> Dict:
        """Launch the classic System Properties dialog (sysdm.cpl), optionally
        jumping to a specific tab: general, hardware, advanced (aka
        performance/virtual-memory), computer_name, system_protection, remote."""
        tab_map = {
            "general": None,
            "computer_name": "1",
            "hardware": "2",
            "advanced": "3",
            "system_protection": "4",
            "remote": "5",
        }
        page = tab_map.get(tab.lower())
        try:
            cmd = ["control.exe", "sysdm.cpl"]
            if page:
                cmd += [",,", page]
            subprocess.Popen(cmd, shell=False)
            return {"success": True, "opened": True, "tab": tab}
        except FileNotFoundError:
            return {"error": "control.exe not found - this is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}
