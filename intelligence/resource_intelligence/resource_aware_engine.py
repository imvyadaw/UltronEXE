"""
Resource-Aware Intelligence Engine (P3)
========================================
monitoring/resource_monitor.py answers "how loaded is the PC right
now". intelligence/predictive_preparation/resource_optimizer.py
answers "is it safe to speculatively preload something in the
background right now". Neither answers the question this engine
exists for: given a task Ultron is about to actually run for the
user, and what similar tasks have empirically cost before, which
execution tier should it use - full local processing, a lighter
local path, deferred until load drops, or offloaded to cloud.

Deliberately heuristic (current load + a caller-supplied cost
estimate + this task type's own history from resource_store.py),
same spirit as resource_optimizer.py's allow/deny gate. Read-only
recommend_execution_tier() is always safe to call speculatively;
track_task_execution() is the caller's job to call afterward with the
real measured cost, so the historical profile reflects reality.

Falls open (never blocks) if psutil / resource_monitor is unavailable
- recommends "run_now_full" with a note that load data wasn't
available, same "degrade gracefully" posture as resource_optimizer.py.
"""

import time
from typing import Dict, Optional

from intelligence.resource_intelligence.resource_store import get_resource_store

CPU_HIGH_THRESHOLD = 85.0
MEM_HIGH_THRESHOLD = 90.0
CPU_MODERATE_THRESHOLD = 60.0


class ResourceAwareEngine:
    def __init__(self):
        self._store = get_resource_store()

    def _current_load(self) -> Optional[Dict]:
        try:
            from monitoring.resource_monitor import ResourceMonitor

            snap = ResourceMonitor().snapshot()
            return snap
        except Exception:
            try:
                import psutil

                return {
                    "cpu_percent": psutil.cpu_percent(interval=0.1),
                    "memory_percent": psutil.virtual_memory().percent,
                }
            except Exception:
                return None

    def recommend_execution_tier(self, task_type: str, estimated_cost: str = "medium") -> Dict:
        """estimated_cost: 'low' | 'medium' | 'high' - caller's rough
        guess of how heavy the task is, combined with real load and
        this task type's own history if any."""
        load = self._current_load()
        profile = self._store.get_profile(task_type)

        if load is None:
            return {
                "tier": "run_now_full",
                "reason": "system load unavailable, defaulting to full local run",
                "task_type": task_type,
                "load": None,
                "profile": profile,
            }

        cpu = load.get("cpu_percent", 0)
        mem = load.get("memory_percent", 0)

        if cpu >= CPU_HIGH_THRESHOLD or mem >= MEM_HIGH_THRESHOLD:
            if estimated_cost == "high":
                tier, reason = "defer", f"system under heavy load (cpu={cpu}%, mem={mem}%) and task is high-cost"
            else:
                tier, reason = "run_now_light", f"system under heavy load (cpu={cpu}%, mem={mem}%), using lighter path"
        elif cpu >= CPU_MODERATE_THRESHOLD and estimated_cost == "high":
            tier, reason = (
                "run_now_cloud_offload",
                f"moderate local load (cpu={cpu}%) and task is high-cost, offload preferred",
            )
        else:
            tier, reason = "run_now_full", f"system load is fine (cpu={cpu}%, mem={mem}%)"

        if profile.get("samples", 0) >= 5 and profile.get("avg_duration_ms", 0) > 5000 and tier == "run_now_full":
            reason += f"; note: {task_type} has historically averaged {profile['avg_duration_ms']:.0f}ms over {profile['samples']} runs"

        return {"tier": tier, "reason": reason, "task_type": task_type, "load": load, "profile": profile}

    def should_defer(self, task_type: str, estimated_cost: str = "medium") -> Dict:
        rec = self.recommend_execution_tier(task_type, estimated_cost)
        return {"defer": rec["tier"] == "defer", "reason": rec["reason"]}

    def track_task_execution(
        self,
        task_type: str,
        duration_ms: float,
        cpu_before: float = 0.0,
        cpu_after: float = 0.0,
        mem_before: float = 0.0,
        mem_after: float = 0.0,
    ) -> Dict:
        self._store.record(task_type, duration_ms, cpu_after - cpu_before, mem_after - mem_before)
        return {"recorded": True, "task_type": task_type, "duration_ms": duration_ms}

    def get_resource_report(self) -> Dict:
        load = self._current_load()
        return {
            "current_load": load,
            "checked_at": time.time(),
            "costliest_task_types": self._store.get_costliest_task_types(10),
        }


_instance: Optional[ResourceAwareEngine] = None


def get_resource_aware_engine() -> ResourceAwareEngine:
    global _instance
    if _instance is None:
        _instance = ResourceAwareEngine()
    return _instance
