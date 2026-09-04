"""
COMMAND (Phase 18.2)
=====================
    dashboard.py      - read-only aggregated snapshot of CORE + MEMORY
    history.py         - read-only merged timeline (focus/habit/forget/fact)
    reports.py          - daily/weekly digests built from MEMORY data,
                          delivered through personality.speak()
    control_panel.py   - single dispatcher tying all of the above plus
                          personality.adjust() and forget.* together;
                          the recommended entry point for a UI, debug
                          console, or fixed-vocabulary voice command

Import order: dashboard has no dependency on the other three; history
is independent of dashboard; reports depends on MEMORY only (not on
dashboard/history); control_panel depends on all three plus
CORE.personality and MEMORY.forget. Every cross-module import is done
lazily inside each method (not at module load) to keep every module
importable even if a sibling isn't available yet, matching
decision_maker.py's own lazy-import choice for autonomous_executor.

Purely additive - nothing in Phase 1-18.1 or MEMORY/ imports from here.
"""

from command.dashboard import get_dashboard
from command.history import get_history
from command.reports import get_report_generator
from command.control_panel import get_control_panel

__all__ = [
    "get_dashboard",
    "get_history",
    "get_report_generator",
    "get_control_panel",
]
