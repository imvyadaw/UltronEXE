"""System-level automation
==========================
Native-Windows automation: a saved-script library for PowerShell and
batch files, OS-level (not simple threshold-polling) event triggers,
a dependency-light pipeline runner for chaining native jobs, a macro
engine for chaining system_control state changes, and schedulers for
recurring file backups, OS-health maintenance (SFC/DISM/Optimize-
Volume), Windows Update checks/installs, and disk cleanup (temp files/
Recycle Bin/Storage Sense) - plus a priority/quiet-hours rule engine
for routing toast notifications.

Every module here has a same- or similar-named counterpart elsewhere
in the project (automation/triggers/event_triggers.py,
automation/workflow/engine.py, automation/macro/macro.py,
system_control/process/task_scheduler.py,
system_control/files/backup.py, system_control/system_config/
windows_update.py, system_control/storage/storage_sense.py,
system_control/ui/notification_manager.py, windows/notifications/
toasts.py, intelligence/proactive_intelligence/notification_manager.py)
- each module's docstring spells out exactly how it differs and why
both exist. Import the classes directly (e.g. `from
system_control.automation.powershell_manager import
PowerShellScriptManager`) to avoid any ambiguity at the call site.
"""
