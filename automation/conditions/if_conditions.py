"""If conditions
=============
Evaluates simple conditions against live system state (app running,
file exists, time of day, battery level, CPU/RAM usage, process
running) and, given a "then"/"else" tool call, runs whichever branch
applies. Used by RPA scripts and workflows to add branching without
needing actual code.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class ConditionEvaluator:
    """Evaluate a condition dict against current system state, and
    optionally run a then/else tool call based on the result."""

    def evaluate(self, condition: Dict) -> Dict:
        """condition shape: {"type": <kind>, ...kind-specific fields}.
        Supported types: app_running, file_exists, time_between,
        battery_below, battery_above, cpu_above, ram_above, process_running."""
        try:
            kind = condition.get("type")
            handler = getattr(self, f"_check_{kind}", None)
            if handler is None:
                return {"error": f"Unknown condition type: {kind}"}
            result = handler(condition)
            return {"condition": condition, "result": bool(result)}
        except Exception as e:
            return {"error": str(e)}

    def _check_app_running(self, c: Dict) -> bool:
        if not HAS_PSUTIL:
            raise RuntimeError("psutil not installed")
        name = c.get("app_name", "").lower()
        return any(name in (p.info.get("name") or "").lower() for p in psutil.process_iter(["name"]))

    def _check_process_running(self, c: Dict) -> bool:
        return self._check_app_running({"app_name": c.get("process_name", "")})

    def _check_file_exists(self, c: Dict) -> bool:
        return Path(os.path.expanduser(c.get("path", ""))).exists()

    def _check_time_between(self, c: Dict) -> bool:
        """c: {"start": "HH:MM", "end": "HH:MM"} - handles ranges crossing midnight."""
        now = datetime.now().strftime("%H:%M")
        start, end = c.get("start", "00:00"), c.get("end", "23:59")
        if start <= end:
            return start <= now <= end
        return now >= start or now <= end  # wraps past midnight

    def _check_battery_below(self, c: Dict) -> bool:
        if not HAS_PSUTIL:
            raise RuntimeError("psutil not installed")
        battery = psutil.sensors_battery()
        if battery is None:
            raise RuntimeError("No battery detected (desktop system?)")
        return battery.percent < c.get("percent", 20)

    def _check_battery_above(self, c: Dict) -> bool:
        if not HAS_PSUTIL:
            raise RuntimeError("psutil not installed")
        battery = psutil.sensors_battery()
        if battery is None:
            raise RuntimeError("No battery detected (desktop system?)")
        return battery.percent > c.get("percent", 80)

    def _check_cpu_above(self, c: Dict) -> bool:
        if not HAS_PSUTIL:
            raise RuntimeError("psutil not installed")
        return psutil.cpu_percent(interval=0.5) > c.get("percent", 80)

    def _check_ram_above(self, c: Dict) -> bool:
        if not HAS_PSUTIL:
            raise RuntimeError("psutil not installed")
        return psutil.virtual_memory().percent > c.get("percent", 80)

    def run_if(self, condition: Dict, then_step: Dict, else_step: Optional[Dict] = None) -> Dict:
        """Evaluate `condition`; run then_step's tool if true, else_step's
        tool if false (and provided). Step shape: {"tool": name, "arguments": {...}}."""
        from ai.tool_runtime import execute_tool_call as execute_tool
        import json

        evaluation = self.evaluate(condition)
        if "error" in evaluation:
            return evaluation

        branch = then_step if evaluation["result"] else else_step
        if branch is None:
            return {"condition_result": evaluation["result"], "branch_taken": None, "note": "No matching branch to run"}

        raw = execute_tool(branch.get("tool", ""), branch.get("arguments", {}))
        return {
            "condition_result": evaluation["result"],
            "branch_taken": "then" if evaluation["result"] else "else",
            "tool_result": json.loads(raw),
        }
