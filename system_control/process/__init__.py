"""system_control.process
==========================
Process/startup control surface: what launches at logon (startup_manager),
what's currently running and how to stop/inspect it (background_apps),
and the native Windows Task Scheduler (task_scheduler) - distinct from
automation/scheduler/task_scheduler.py's TaskScheduler, which is an
in-process background-thread timer for ULTRON's own internal jobs, not
a wrapper around Windows' own Task Scheduler service. Import this one
as `system_control.process.task_scheduler.WindowsTaskScheduler` to
keep the two apart.

Same conventions as system_control/system_config/*:
  - Every public method returns a plain Dict - never raises.
  - Anything that changes state (add/remove/enable/disable/kill/create/
    delete/run) is confirm-gated: first call (confirm=False, default)
    returns a preview; the caller repeats with confirm=True to apply.
  - Methods that touch HKLM / need elevated rights are documented as
    needing admin, with an admin hint surfaced on access-denied errors.

Lazily imported by ai/process_control_tools.py - importing this package
itself does no I/O.
"""

from system_control.process.startup_manager import StartupManager
from system_control.process.background_apps import BackgroundApps
from system_control.process.task_scheduler import WindowsTaskScheduler

__all__ = [
    "StartupManager",
    "BackgroundApps",
    "WindowsTaskScheduler",
]
