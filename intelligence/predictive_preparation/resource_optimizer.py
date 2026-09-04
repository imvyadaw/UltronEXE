"""
Resource Optimizer (Phase 20.2 - Predictive Preparation)
==================================================
Gatekeeper every other module in predictive_preparation/ calls before
actually spending anything - launching a process, hitting the local
model server, or running a context provider. Predicting what the
user will do next is cheap; acting on that prediction (preloading an
app, warming a model, prefetching data) is not, and doing it wrong
is worse than not doing it at all - a background app launch that
steals focus, or a model warm-up that pegs the CPU while the user is
on a video call, defeats the entire point of "preparation" being
invisible.

Deliberately simple/heuristic, same spirit as urgency_calculator.py:
a handful of concrete signals (CPU, memory, battery, a caller-supplied
context dict) combine into an allow/deny decision plus reasons, never
a hard-coded guess. Unlike urgency_calculator.py this module also
keeps a small amount of in-memory state - a per-kind cooldown, same
spirit as event_detector.py's dedup cache - so three eager preloaders
can't all fire back-to-back the moment a prediction clears confidence.

check() is read-only and safe to call speculatively; register_spend()
is the caller's job to call afterward, and only after the action
actually happened, so cooldowns reflect real spend rather than
attempts that were themselves denied.

Optional-dependency guard: uses psutil for real CPU/memory/battery
readings when available. Without it, falls open to conservative
defaults (low/medium cost allowed, high cost denied) rather than
either blocking everything or trusting the caller blindly - same
"purely additive, degrade gracefully" posture as the rest of this
build's optional-dependency modules (offline TTS fallback, etc).

Stateless w.r.t. persistence - no database table. In-memory cooldown
state only, resets harmlessly on restart, same as event_detector.py.
"""

import threading
import time
from typing import Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None

from core.logger import get_logger

logger = get_logger("ultron.resource_optimizer")

_instance: Optional["ResourceOptimizer"] = None
_instance_lock = threading.Lock()

KIND_APP = "app"
KIND_MODEL = "model"
KIND_CONTEXT = "context"

COST_LOW = "low"
COST_MEDIUM = "medium"
COST_HIGH = "high"

_VALID_KINDS = (KIND_APP, KIND_MODEL, KIND_CONTEXT)
_VALID_COSTS = (COST_LOW, COST_MEDIUM, COST_HIGH)

# minimum spacing between two allowed actions of the same kind - keeps
# app_preloader.py/model_preloader.py/context_preloader.py from all
# firing on the same prediction and stacking their cost together
_KIND_COOLDOWN_SECONDS = {
    KIND_APP: 60.0,
    KIND_MODEL: 120.0,
    KIND_CONTEXT: 20.0,
}

# threshold pairs are (max_allowed_for_low_cost, max_allowed_for_medium_cost,
# max_allowed_for_high_cost) - stricter as cost goes up. High-cost work
# needs more headroom to be worth speculatively doing at all.
_CPU_PERCENT_CEILING = {COST_LOW: 85.0, COST_MEDIUM: 70.0, COST_HIGH: 55.0}
_MIN_FREE_MEMORY_PERCENT = {COST_LOW: 10.0, COST_MEDIUM: 15.0, COST_HIGH: 25.0}
_MIN_BATTERY_PERCENT_ON_BATTERY = {COST_LOW: 15.0, COST_MEDIUM: 25.0, COST_HIGH: 40.0}


class ResourceOptimizer:
    """check(kind, cost) -> {"allowed", "reasons", "current_load"};
    register_spend(kind) records that an allowed action actually ran."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_spend: Dict[str, float] = {}

    def check(self, kind: str, cost: str = COST_LOW, context: Optional[Dict] = None) -> Dict:
        context = context or {}
        reasons = []

        if kind not in _VALID_KINDS:
            return {"allowed": False, "reasons": [f"unknown kind '{kind}'"], "current_load": {}}
        if cost not in _VALID_COSTS:
            cost = COST_MEDIUM
            reasons.append("unrecognized cost, defaulting to 'medium'")

        now = time.time()
        cooldown = _KIND_COOLDOWN_SECONDS.get(kind, 60.0)
        with self._lock:
            last = self._last_spend.get(kind)
        if last is not None and (now - last) < cooldown:
            remaining = cooldown - (now - last)
            reasons.append(f"cooldown active for kind '{kind}', {remaining:.0f}s remaining")
            return {"allowed": False, "reasons": reasons, "current_load": self._snapshot()}

        if context.get("low_power_mode") and cost != COST_LOW:
            reasons.append("low_power_mode is active - only low-cost preloads allowed")
            return {"allowed": False, "reasons": reasons, "current_load": self._snapshot()}

        if context.get("in_call") or context.get("fullscreen_active"):
            if cost == COST_HIGH:
                reasons.append("user is in a call/fullscreen app - deferring high-cost preload")
                return {"allowed": False, "reasons": reasons, "current_load": self._snapshot()}
            reasons.append("user is in a call/fullscreen app - proceeding, cost is not high")

        load = self._snapshot()

        if psutil is None:
            reasons.append("psutil not available - assuming moderate load")
            if cost == COST_HIGH:
                reasons.append("declining high-cost preload without real resource readings")
                return {"allowed": False, "reasons": reasons, "current_load": load}
            reasons.append(f"allowing {cost}-cost preload on conservative defaults")
            return {"allowed": True, "reasons": reasons, "current_load": load}

        cpu = load.get("cpu_percent")
        if cpu is not None:
            ceiling = _CPU_PERCENT_CEILING[cost]
            if cpu >= ceiling:
                reasons.append(f"CPU at {cpu:.0f}% >= {ceiling:.0f}% ceiling for {cost}-cost work")
                return {"allowed": False, "reasons": reasons, "current_load": load}
            reasons.append(f"CPU at {cpu:.0f}%, under {ceiling:.0f}% ceiling")

        mem_free_pct = load.get("memory_free_percent")
        if mem_free_pct is not None:
            floor = _MIN_FREE_MEMORY_PERCENT[cost]
            if mem_free_pct < floor:
                reasons.append(f"free memory at {mem_free_pct:.0f}% < {floor:.0f}% floor for {cost}-cost work")
                return {"allowed": False, "reasons": reasons, "current_load": load}
            reasons.append(f"free memory at {mem_free_pct:.0f}%, above {floor:.0f}% floor")

        if load.get("on_battery"):
            battery_pct = load.get("battery_percent")
            if battery_pct is not None:
                floor = _MIN_BATTERY_PERCENT_ON_BATTERY[cost]
                if battery_pct < floor:
                    reasons.append(f"on battery at {battery_pct:.0f}% < {floor:.0f}% floor for {cost}-cost work")
                    return {"allowed": False, "reasons": reasons, "current_load": load}
                reasons.append(f"on battery at {battery_pct:.0f}%, above {floor:.0f}% floor")

        reasons.append(f"resource headroom sufficient for {cost}-cost '{kind}' preload")
        return {"allowed": True, "reasons": reasons, "current_load": load}

    def register_spend(self, kind: str) -> None:
        """Call only after an allowed action actually ran, so the
        cooldown reflects real spend rather than a denied attempt."""
        with self._lock:
            self._last_spend[kind] = time.time()

    def get_current_load(self) -> Dict:
        return self._snapshot()

    @staticmethod
    def _snapshot() -> Dict:
        if psutil is None:
            return {"psutil_available": False}
        load = {"psutil_available": True}
        try:
            load["cpu_percent"] = psutil.cpu_percent(interval=0.0)
        except Exception as e:
            logger.debug(f"resource_optimizer: cpu_percent read failed: {e}")
        try:
            vm = psutil.virtual_memory()
            load["memory_free_percent"] = 100.0 - vm.percent
        except Exception as e:
            logger.debug(f"resource_optimizer: virtual_memory read failed: {e}")
        try:
            battery = psutil.sensors_battery()
            if battery is not None:
                load["on_battery"] = not battery.power_plugged
                load["battery_percent"] = battery.percent
            else:
                load["on_battery"] = False
        except Exception as e:
            logger.debug(f"resource_optimizer: sensors_battery read failed: {e}")
            load["on_battery"] = False
        try:
            disk = psutil.disk_usage("/")
            load["disk_free_percent"] = 100.0 - disk.percent
        except Exception as e:
            logger.debug(f"resource_optimizer: disk_usage read failed: {e}")
        return load


def get_resource_optimizer() -> ResourceOptimizer:
    """Process-wide ResourceOptimizer singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ResourceOptimizer()
    return _instance
