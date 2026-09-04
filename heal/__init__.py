"""
HEAL (Phase 18.9.2)
=======================
Self-monitoring bookkeeping over whatever other code or a person
reports in - nothing here probes, executes, restarts, or deploys
anything on its own:

    health_check.py - latest-status board; report() logs a
                      component's ("ok"/"warn"/"fail", detail),
                      run_check() rolls up the overall picture.
    auto_fix.py     - registry of known (component -> candidate fix)
                      descriptions plus an attempt log; never
                      executes a fix, only suggests and records.
    restart.py      - gatekeeper for restart requests with a
                      flap-loop guard (MIN_RESTART_INTERVAL_SECONDS /
                      MAX_RESTARTS_PER_WINDOW); never restarts
                      anything itself.
    update_self.py  - version history and rollback-point
                      bookkeeping; never pulls code or deploys.

auto_fix.py optionally reads health_check.py's failing_components()
via an import-guarded hook; every other cross-module link here is a
caller explicitly composing two modules itself.

All local state lives under data/self_management/ by default, each
path overridable via its own SELF_MANAGEMENT_*_ENV variable.

Purely additive - nothing in Phase 1-18.9.1 imports from here.
"""

from heal.health_check import get_health_check
from heal.auto_fix import get_auto_fix
from heal.restart import get_restart
from heal.update_self import get_update_self

__all__ = [
    "get_health_check",
    "get_auto_fix",
    "get_restart",
    "get_update_self",
]
