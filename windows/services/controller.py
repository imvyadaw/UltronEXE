"""Windows services controller
============================
List, query, start, stop, and restart Windows services. Uses psutil's
win_service_* API where available, with an `sc.exe` subprocess
fallback for start/stop/restart (which need admin rights either way).

Renamed from services/services.py (ServiceTools) as part of Phase 8's
windows/ restructure. Only windows/__init__.py imported the old
module, so this is a clean rename. Adds restart_service (stop then
start) to round out the "controller" name.
"""

import subprocess
import time
from typing import Dict

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def _admin_aware_error(base_error: str) -> str:
    """Same reasoning as windows/firewall/rules.py's helper of the same
    name - replaces the old generic "(try running as admin)" suffix
    with a hint that actually tells the user how to fix it."""
    try:
        from windows.system_info.admin import is_admin, permission_denied_hint

        if not is_admin():
            return base_error + permission_denied_hint("Service control")
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("windows.services.controller._admin_aware_error")
    return base_error


class ServiceController:
    """List/query/start/stop/restart Windows services."""

    def list_services(self, filter_status: str = None, limit: int = 50) -> Dict:
        """List Windows services, optionally filtered by status ('running'/'stopped')."""
        if not HAS_PSUTIL or not hasattr(psutil, "win_service_iter"):
            return {"error": "Service listing is only available on Windows (needs psutil)"}
        try:
            services = []
            for s in psutil.win_service_iter():
                info = s.as_dict()
                if filter_status and info["status"] != filter_status:
                    continue
                services.append(
                    {
                        "name": info["name"],
                        "display_name": info["display_name"],
                        "status": info["status"],
                        "start_type": info["start_type"],
                    }
                )
            return {"count": len(services), "services": services[:limit]}
        except Exception as e:
            return {"error": str(e)}

    def get_service_status(self, service_name: str) -> Dict:
        """Get the status of a single service by its short name (e.g. 'wuauserv')."""
        if not HAS_PSUTIL or not hasattr(psutil, "win_service_get"):
            return {"error": "Service query is only available on Windows (needs psutil)"}
        try:
            s = psutil.win_service_get(service_name)
            info = s.as_dict()
            return {
                "name": info["name"],
                "display_name": info["display_name"],
                "status": info["status"],
                "start_type": info["start_type"],
                "pid": info.get("pid"),
            }
        except Exception as e:
            return {"error": str(e)}

    def start_service(self, service_name: str) -> Dict:
        """Start a Windows service (needs admin rights)."""
        try:
            result = subprocess.run(["sc", "start", service_name], capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                return {"success": True, "service": service_name, "output": result.stdout.strip()}
            return {
                "error": _admin_aware_error(result.stderr.strip() or result.stdout.strip() or "Failed to start service")
            }
        except Exception as e:
            return {"error": str(e)}

    def stop_service(self, service_name: str, confirm: bool = False) -> Dict:
        """Stop a Windows service (needs admin rights). Safety-gated: needs confirm=true."""
        if not confirm:
            return {"error": f"This will stop the '{service_name}' service. Call again with confirm=true to proceed."}
        try:
            result = subprocess.run(["sc", "stop", service_name], capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                return {"success": True, "service": service_name, "output": result.stdout.strip()}
            return {
                "error": _admin_aware_error(result.stderr.strip() or result.stdout.strip() or "Failed to stop service")
            }
        except Exception as e:
            return {"error": str(e)}

    def restart_service(self, service_name: str, confirm: bool = False, wait_seconds: float = 2.0) -> Dict:
        """Stop then start a Windows service (needs admin rights). Safety-gated: needs confirm=true."""
        if not confirm:
            return {
                "error": f"This will restart the '{service_name}' service. Call again with confirm=true to proceed."
            }
        stop_result = self.stop_service(service_name, confirm=True)
        if "error" in stop_result:
            return {"error": f"Restart failed at stop step: {stop_result['error']}"}
        time.sleep(wait_seconds)
        start_result = self.start_service(service_name)
        if "error" in start_result:
            return {"error": f"Restart failed at start step: {start_result['error']}"}
        return {"success": True, "service": service_name, "restarted": True}
