"""Self Optimization Control
=============================
Machine-wide performance tuning distinct from
system_control.hardware.ram_optimizer.RAMOptimizer (which is RAM/
pagefile-specific). This module chains three separate existing
controls into one "optimization pass": power plan (powercfg, new
here), background process trimming (delegates to
system_control.process.background_apps.BackgroundApps), and startup
item impact (delegates to
system_control.process.startup_manager.StartupManager). It also
raises ULTRON's own process priority when the user is on a performance
push.

run_optimization_pass() and anything that changes running state
(killing a process, disabling a startup item, switching the power
plan) is confirm-gated - status/listing calls are not.
"""

import os
import subprocess
from typing import Dict, List, Optional

_POWER_PLANS = {
    "power_saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
    "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
    "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
}


class SelfOptimizationControl:
    def _run(self, cmd: List[str], timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": f"{cmd[0]} not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_active_power_plan(self) -> Dict:
        result = self._run(["powercfg", "/getactivescheme"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "powercfg failed"}
        return {"raw": result["stdout"]}

    def set_power_plan(self, plan: str, confirm: bool = False) -> Dict:
        """plan: 'power_saver' | 'balanced' | 'high_performance'."""
        if plan not in _POWER_PLANS:
            return {"error": f"plan must be one of {list(_POWER_PLANS)}"}
        if not confirm:
            return {"requires_confirmation": True, "preview": f"This will switch the active power plan to '{plan}'."}
        result = self._run(["powercfg", "/setactive", _POWER_PLANS[plan]])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "powercfg /setactive failed"}
        return {"success": True, "power_plan": plan}

    def get_top_resource_consumers(self, limit: int = 10) -> Dict:
        from system_control.process.background_apps import BackgroundApps

        return BackgroundApps().list_running_processes(sort_by="memory", top_n=limit)

    def trim_background_process(self, pid: int, confirm: bool = False) -> Dict:
        from system_control.process.background_apps import BackgroundApps

        return BackgroundApps().kill_process(pid, confirm=confirm)

    def get_startup_impact(self) -> Dict:
        from system_control.process.startup_manager import StartupManager

        return StartupManager().list_startup_items()

    def disable_startup_item(self, name: str, confirm: bool = False) -> Dict:
        from system_control.process.startup_manager import StartupManager

        return StartupManager().disable_startup_item(name, confirm=confirm)

    def boost_ultron_priority(self, confirm: bool = False) -> Dict:
        """Raise this ULTRON process's own CPU priority to 'above normal'."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will raise ULTRON's own process priority to Above Normal.",
            }
        try:
            import psutil

            p = psutil.Process(os.getpid())
            p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
            return {"success": True, "pid": os.getpid(), "priority": "above_normal"}
        except Exception as e:
            return {"error": str(e)}

    def run_optimization_pass(
        self,
        kill_top_n_background: int = 0,
        disable_startup_items: Optional[List[str]] = None,
        target_power_plan: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict:
        """One chained pass: optionally kill the top N non-essential
        background processes by memory, disable named startup items, and
        switch power plan. Each step reuses the confirm-gated methods
        above so the individual preview text still applies; this method's
        own confirm is the pass-level go-ahead."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This optimization pass will: kill top {kill_top_n_background} background processes by memory, "
                    f"disable startup items {disable_startup_items or []}, "
                    f"and set power plan to '{target_power_plan}' (if given)."
                ),
            }
        steps: Dict = {}
        if kill_top_n_background:
            top = self.get_top_resource_consumers(limit=kill_top_n_background)
            killed = []
            for proc in (top.get("processes") or [])[:kill_top_n_background]:
                pid = proc.get("pid")
                if pid:
                    killed.append(self.trim_background_process(pid, confirm=True))
            steps["killed_processes"] = killed
        if disable_startup_items:
            steps["disabled_startup_items"] = [
                self.disable_startup_item(n, confirm=True) for n in disable_startup_items
            ]
        if target_power_plan:
            steps["power_plan"] = self.set_power_plan(target_power_plan, confirm=True)
        return {"success": True, "steps": steps}


_instance: Optional[SelfOptimizationControl] = None


def get_self_optimization_control() -> SelfOptimizationControl:
    global _instance
    if _instance is None:
        _instance = SelfOptimizationControl()
    return _instance
