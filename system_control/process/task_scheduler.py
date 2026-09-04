"""Windows Task Scheduler
=========================
Wraps the native Windows Task Scheduler (the ScheduledTask PowerShell
cmdlets / schtasks.exe) - list, inspect, create, enable/disable, run
now, and delete scheduled tasks at the OS level.

Not to be confused with automation/scheduler/task_scheduler.py's
TaskScheduler, which is an in-process background-thread timer for
ULTRON's own internal jobs and knows nothing about the Windows Task
Scheduler service; that one keeps running only while ULTRON itself is
running, this one persists and fires independently of ULTRON (even
across reboots). Import this class as WindowsTaskScheduler to keep the
two apart at the call site.

create_task/delete_task/run_task_now/enable_task/disable_task are all
confirm-gated the same way as the rest of system_control - a scheduled
task is arbitrary-command execution on a timer, so create_task and
run_task_now in particular deserve a careful look at the command
before confirming.
"""

import json
import subprocess
from typing import Dict


class WindowsTaskScheduler:
    """List/inspect/create/enable/disable/run/delete native Windows Scheduled Tasks."""

    def _run_ps(self, cmd: str, timeout: float = 30.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("access" in err.lower() or "denied" in err.lower() or "administrat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def list_tasks(self, only_enabled: bool = False, path_filter: str = "") -> Dict:
        """List scheduled tasks (name, path, state), optionally only
        enabled ones and/or filtered to tasks whose TaskPath contains
        path_filter."""
        filters = []
        if only_enabled:
            filters.append("$_.State -eq 'Ready' -or $_.State -eq 'Running'")
        if path_filter:
            safe = path_filter.replace("'", "''")
            filters.append(f"$_.TaskPath -like '*{safe}*'")
        where = f" | Where-Object {{{' -and '.join(filters)}}}" if filters else ""
        cmd = f"Get-ScheduledTask{where} | Select-Object TaskName,TaskPath,State | ConvertTo-Json"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-ScheduledTask failed")}
        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            tasks = data if isinstance(data, list) else [data]
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "tasks": tasks, "count": len(tasks)}

    def get_task_info(self, task_name: str, task_path: str = "\\") -> Dict:
        """Full detail for one task: state, triggers, actions, and
        last/next run info."""
        if not task_name:
            return {"error": "task_name must be non-empty"}
        safe_name = task_name.replace("'", "''")
        safe_path = task_path.replace("'", "''")
        cmd = (
            f"$t = Get-ScheduledTask -TaskName '{safe_name}' -TaskPath '{safe_path}'; "
            f"$i = $t | Get-ScheduledTaskInfo; "
            f"[PSCustomObject]@{{ TaskName=$t.TaskName; TaskPath=$t.TaskPath; State=$t.State; "
            f'Actions=($t.Actions | ForEach-Object {{ "$($_.Execute) $($_.Arguments)" }}); '
            f"Triggers=($t.Triggers | ForEach-Object {{ $_.CimClass.CimClassName }}); "
            f"LastRunTime=$i.LastRunTime; LastTaskResult=$i.LastTaskResult; NextRunTime=$i.NextRunTime "
            f"}} | ConvertTo-Json"
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Task not found: {task_name}")}
        try:
            info = json.loads(result["stdout"]) if result["stdout"] else {}
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "task": info}

    def create_task(
        self,
        name: str,
        command: str,
        arguments: str = "",
        trigger_type: str = "daily",
        time: str = "09:00",
        confirm: bool = False,
    ) -> Dict:
        """Create a scheduled task that runs `command arguments` on a
        trigger: 'daily' or 'logon' (at `time`, HH:MM, for 'daily';
        `time` is ignored for 'logon'). Runs in the current user's
        context via schtasks.exe. Confirm-gated - review the command
        carefully, this is arbitrary code execution on a timer."""
        if not name or not command:
            return {"error": "name and command must both be non-empty"}
        if trigger_type not in ("daily", "logon"):
            return {"error": "trigger_type must be 'daily' or 'logon'"}
        full_cmd = f"{command} {arguments}".strip()
        if not confirm:
            trig_desc = f"daily at {time}" if trigger_type == "daily" else "at logon"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would create scheduled task {name!r} running {full_cmd!r} ({trig_desc})",
                "message": "Call again with confirm=true to apply.",
            }
        args = ["schtasks", "/Create", "/TN", name, "/TR", full_cmd, "/F"]
        if trigger_type == "daily":
            args += ["/SC", "DAILY", "/ST", time]
        else:
            args += ["/SC", "ONLOGON"]
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return {"error": self._admin_hint(result.stderr.strip() or "schtasks /Create failed")}
            return {"success": True, "name": name, "command": full_cmd, "trigger_type": trigger_type}
        except FileNotFoundError:
            return {"error": "schtasks.exe not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def delete_task(self, task_name: str, task_path: str = "\\", confirm: bool = False) -> Dict:
        """Delete a scheduled task. Confirm-gated."""
        if not task_name:
            return {"error": "task_name must be non-empty"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete scheduled task {task_name!r}",
                "message": "Call again with confirm=true to apply.",
            }
        safe_name = task_name.replace("'", "''")
        safe_path = task_path.replace("'", "''")
        cmd = f"Unregister-ScheduledTask -TaskName '{safe_name}' -TaskPath '{safe_path}' -Confirm:$false"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not delete task: {task_name}")}
        return {"success": True, "task_name": task_name, "deleted": True}

    def enable_task(self, task_name: str, task_path: str = "\\", confirm: bool = False) -> Dict:
        """Enable a disabled scheduled task. Confirm-gated."""
        return self._toggle_task(task_name, task_path, enable=True, confirm=confirm)

    def disable_task(self, task_name: str, task_path: str = "\\", confirm: bool = False) -> Dict:
        """Disable a scheduled task without deleting it. Confirm-gated."""
        return self._toggle_task(task_name, task_path, enable=False, confirm=confirm)

    def _toggle_task(self, task_name: str, task_path: str, enable: bool, confirm: bool) -> Dict:
        if not task_name:
            return {"error": "task_name must be non-empty"}
        action = "enable" if enable else "disable"
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would {action} scheduled task {task_name!r}",
                "message": "Call again with confirm=true to apply.",
            }
        safe_name = task_name.replace("'", "''")
        safe_path = task_path.replace("'", "''")
        verb = "Enable-ScheduledTask" if enable else "Disable-ScheduledTask"
        cmd = f"{verb} -TaskName '{safe_name}' -TaskPath '{safe_path}'"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"{verb} failed")}
        return {"success": True, "task_name": task_name, "action": action}

    def run_task_now(self, task_name: str, task_path: str = "\\", confirm: bool = False) -> Dict:
        """Trigger a scheduled task to run immediately, outside its
        normal schedule. Confirm-gated - this executes whatever the
        task's action is, right now."""
        if not task_name:
            return {"error": "task_name must be non-empty"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would run scheduled task {task_name!r} immediately",
                "message": "Call again with confirm=true to apply.",
            }
        safe_name = task_name.replace("'", "''")
        safe_path = task_path.replace("'", "''")
        cmd = f"Start-ScheduledTask -TaskName '{safe_name}' -TaskPath '{safe_path}'"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not start task: {task_name}")}
        return {"success": True, "task_name": task_name, "started": True}
