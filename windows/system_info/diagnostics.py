"""System diagnostics
===================
Battery, CPU/RAM/disk usage, uptime, network info, and a one-shot
full diagnostic report. Shutdown/restart/lock/sign-out live separately
in system_info/power.py (PowerControl) - that module is about taking
power *actions*, this one is purely read-only reporting, so they stay
split even though they share the system_info/ package.

Renamed from system_info/status.py (SystemStatus) as part of Phase 8's
windows/ restructure, and expanded with disk usage, uptime, network
I/O counters, and a get_full_report() aggregator to actually earn the
"diagnostics" name. Only windows/__init__.py imported the old module,
so this is a clean rename.
"""

import platform
import socket
import time
from pathlib import Path
from typing import Dict

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class SystemDiagnostics:
    """Battery, CPU/RAM/disk, uptime, network info, and a full diagnostic report."""

    def __init__(self):
        self.home_dir = Path.home()

    def get_battery_status(self) -> Dict:
        """Get battery status (laptops only)."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return {"error": "No battery detected (desktop PC?)"}
            return {
                "percentage": battery.percent,
                "charging": battery.power_plugged,
                "raw": f"{battery.percent}% {'(charging)' if battery.power_plugged else '(on battery)'}",
            }
        except Exception as e:
            return {"error": str(e)}

    def get_system_info(self) -> Dict:
        """Get system information."""
        return {
            "os": f"{platform.system()} {platform.release()} (build {platform.version()})",
            "machine": platform.machine(),
            "hostname": platform.node(),
            "home": str(self.home_dir),
            "processor": platform.processor(),
        }

    def get_cpu_ram_usage(self) -> Dict:
        """Get current CPU and RAM usage."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            mem = psutil.virtual_memory()
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.5),
                "cpu_cores_logical": psutil.cpu_count(logical=True),
                "cpu_cores_physical": psutil.cpu_count(logical=False),
                "ram_percent": mem.percent,
                "ram_used": self._format_size(mem.used),
                "ram_total": self._format_size(mem.total),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_disk_usage(self, drive: str = None) -> Dict:
        """Get disk usage for the home drive (default) or a specific drive letter, e.g. 'D:\\'."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            target = drive or str(self.home_dir.anchor or "C:\\")
            usage = psutil.disk_usage(target)
            return {
                "drive": target,
                "total": self._format_size(usage.total),
                "used": self._format_size(usage.used),
                "free": self._format_size(usage.free),
                "percent_used": usage.percent,
            }
        except Exception as e:
            return {"error": str(e)}

    def get_uptime(self) -> Dict:
        """Get how long the system has been running since last boot."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            boot_time = psutil.boot_time()
            uptime_seconds = time.time() - boot_time
            days, rem = divmod(uptime_seconds, 86400)
            hours, rem = divmod(rem, 3600)
            minutes, _ = divmod(rem, 60)
            return {
                "boot_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(boot_time)),
                "uptime_readable": f"{int(days)}d {int(hours)}h {int(minutes)}m",
                "uptime_seconds": int(uptime_seconds),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_network_info(self) -> Dict:
        """Get bytes sent/received since boot and per-interface stats."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            io = psutil.net_io_counters()
            interfaces = {}
            for name, stats in psutil.net_if_stats().items():
                interfaces[name] = {"up": stats.isup, "speed_mbps": stats.speed}
            return {
                "bytes_sent": self._format_size(io.bytes_sent),
                "bytes_received": self._format_size(io.bytes_recv),
                "interfaces": interfaces,
            }
        except Exception as e:
            return {"error": str(e)}

    def get_ip_address(self) -> Dict:
        """Get local IP address and hostname."""
        try:
            hostname = socket.gethostname()
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
            finally:
                s.close()
            return {"hostname": hostname, "local_ip": local_ip}
        except Exception as e:
            return {"error": str(e)}

    def get_full_report(self) -> Dict:
        """One-shot diagnostic snapshot combining system info, CPU/RAM, disk,
        battery, uptime, and network - useful for a single 'how's my PC doing' query."""
        return {
            "system": self.get_system_info(),
            "cpu_ram": self.get_cpu_ram_usage(),
            "disk": self.get_disk_usage(),
            "battery": self.get_battery_status(),
            "uptime": self.get_uptime(),
            "network": self.get_ip_address(),
        }

    def _format_size(self, size: float) -> str:
        """Format a byte count as a human-readable string (B/KB/MB/GB/TB)."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
