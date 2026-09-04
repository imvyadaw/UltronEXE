"""GPU Control
=============
GPU identity, live status, and per-app performance-preference control.

`Win32_VideoController` (via WMI/PowerShell) gives vendor-neutral
identity/driver info that works for any GPU. Live utilization/
temperature/VRAM, however, has no vendor-neutral source on Windows -
those come from `nvidia-smi` when present (NVIDIA only); on AMD/Intel
systems those specific fields come back empty rather than guessed at,
since there's no equivalent first-party CLI this module can rely on
without a vendor SDK.

set_app_graphics_preference writes the per-app "Graphics performance
preference" (System Settings > Display > Graphics) - a supported,
documented Windows registry surface for steering a specific exe to
the high-performance or power-saving GPU on hybrid-graphics laptops.
It is NOT a general overclocking or fan-curve control (those need
vendor tools like MSI Afterburner / NVIDIA/AMD control panels, which
expose no public API this module could drive) - set_app_graphics_
preference is confirm-gated since it changes which GPU a specific app
launches on, which can affect its performance and battery draw.
"""

import shutil
import subprocess
import winreg
from typing import Dict

_GRAPHICS_PREF_PATH = r"Software\Microsoft\DirectX\UserGpuPreferences"
_GRAPHICS_PREF_VALUES = {
    "let_windows_decide": "GpuPreference=0;",
    "power_saving": "GpuPreference=1;",
    "high_performance": "GpuPreference=2;",
}


class GPUControl:
    """GPU identity/driver info, live status (NVIDIA via nvidia-smi),
    and per-app graphics performance preference."""

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

    def get_gpu_info(self) -> Dict:
        """Vendor-neutral GPU identity/driver info for every adapter
        (works for NVIDIA/AMD/Intel/integrated). No admin needed."""
        result = self._run_ps(
            "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterCompatibility, "
            "DriverVersion, DriverDate, VideoModeDescription, AdapterRAM, "
            "CurrentHorizontalResolution, CurrentVerticalResolution, CurrentRefreshRate | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not read GPU info"}
        if not result["stdout"]:
            return {"gpus": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse GPU info"}
        gpus = data if isinstance(data, list) else [data]
        for g in gpus:
            ram = g.get("AdapterRAM")
            if ram and ram > 0:
                g["adapter_ram_gb"] = round(ram / (1024**3), 2)
        return {"success": True, "gpus": gpus, "count": len(gpus)}

    def get_nvidia_status(self) -> Dict:
        """Live utilization, temperature, VRAM usage, and power draw
        via `nvidia-smi`. NVIDIA-only - returns an error (not a guess)
        if nvidia-smi isn't found, e.g. on AMD/Intel-only systems."""
        exe = shutil.which("nvidia-smi")
        if not exe:
            return {"error": "nvidia-smi not found - no NVIDIA GPU/driver detected on this system."}
        try:
            result = subprocess.run(
                [
                    exe,
                    "--query-gpu=name,utilization.gpu,utilization.memory,memory.used,memory.total,"
                    "temperature.gpu,power.draw,power.limit",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "nvidia-smi failed"}
            gpus = []
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) != 8:
                    continue
                name, util_gpu, util_mem, mem_used, mem_total, temp, power_draw, power_limit = parts
                gpus.append(
                    {
                        "name": name,
                        "utilization_gpu_percent": float(util_gpu),
                        "utilization_memory_percent": float(util_mem),
                        "memory_used_mb": float(mem_used),
                        "memory_total_mb": float(mem_total),
                        "temperature_c": float(temp),
                        "power_draw_w": float(power_draw),
                        "power_limit_w": float(power_limit),
                    }
                )
            return {"success": True, "gpus": gpus, "count": len(gpus)}
        except subprocess.TimeoutExpired:
            return {"error": "nvidia-smi timed out"}
        except Exception as e:
            return {"error": str(e)}

    def list_gpu_processes(self) -> Dict:
        """Processes currently using the GPU and how much VRAM each
        holds. NVIDIA-only, via nvidia-smi."""
        exe = shutil.which("nvidia-smi")
        if not exe:
            return {"error": "nvidia-smi not found - no NVIDIA GPU/driver detected on this system."}
        try:
            result = subprocess.run(
                [exe, "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "nvidia-smi failed"}
            procs = []
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) != 3:
                    continue
                pid, name, mem = parts
                procs.append({"pid": int(pid), "name": name, "memory_used_mb": float(mem)})
            return {"success": True, "processes": procs, "count": len(procs)}
        except subprocess.TimeoutExpired:
            return {"error": "nvidia-smi timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_app_graphics_preference(self, exe_path: str) -> Dict:
        """Which GPU (let_windows_decide / power_saving /
        high_performance) an app is currently set to launch on, by
        its full exe path. No admin needed (per-user setting)."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _GRAPHICS_PREF_PATH) as key:
                try:
                    value, _ = winreg.QueryValueEx(key, exe_path)
                except FileNotFoundError:
                    return {
                        "success": True,
                        "exe_path": exe_path,
                        "preference": "let_windows_decide",
                        "explicitly_set": False,
                    }
                for name, raw in _GRAPHICS_PREF_VALUES.items():
                    if raw in value:
                        return {"success": True, "exe_path": exe_path, "preference": name, "explicitly_set": True}
                return {"success": True, "exe_path": exe_path, "preference": "unknown", "raw_value": value}
        except FileNotFoundError:
            return {"success": True, "exe_path": exe_path, "preference": "let_windows_decide", "explicitly_set": False}
        except OSError as e:
            return {"error": str(e)}

    def set_app_graphics_preference(self, exe_path: str, preference: str, confirm: bool = False) -> Dict:
        """Set which GPU a specific app (by full exe path) launches
        on: 'let_windows_decide', 'power_saving', or
        'high_performance'. Confirm-gated - affects that app's
        performance and, on battery, its power draw."""
        if preference not in _GRAPHICS_PREF_VALUES:
            return {"error": f"Unknown preference '{preference}'. Use one of: {sorted(_GRAPHICS_PREF_VALUES)}"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will set '{exe_path}' to launch using the '{preference}' GPU preference.",
            }
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _GRAPHICS_PREF_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, exe_path, 0, winreg.REG_SZ, _GRAPHICS_PREF_VALUES[preference])
            return {"success": True, "exe_path": exe_path, "preference": preference}
        except OSError as e:
            return {"error": str(e)}
