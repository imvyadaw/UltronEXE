"""Maintenance scheduler
========================
Schedules recurring native Windows system-health maintenance: an SFC
(System File Checker) scan, a DISM component-store health check, and
a drive Optimize-Volume pass (defrag for HDDs, TRIM for SSDs - the
cmdlet picks the right one per-drive automatically). None of these
have a home elsewhere in the project - system_config/system_restore.py
is about restore points, not integrity scans, and
system_control/storage/format_manager.py is about
partition/volume-level formatting, not routine drive optimization.

Same glue pattern as backup_scheduler.py in this same package: a named
"maintenance job" is {tasks[], trigger_type, time, drive_letter},
persisted to storage/cache/maintenance_jobs/<job_name>.json, with a
real native Scheduled Task (via WindowsTaskScheduler.create_task)
registered alongside it so the job still runs overnight even if
ULTRON isn't. The scheduled task's action re-invokes this module's
own CLI entry point, exactly like backup_scheduler.py's does.

sfc/DISM/Optimize-Volume all require Administrator and can run for
several minutes to hours, so creating/deleting a job and running one
immediately are all confirm-gated; listing/viewing are not.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from system_control.process.task_scheduler import WindowsTaskScheduler

JOBS_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "maintenance_jobs"
TASK_NAME_PREFIX = "Ultron_Maintenance_"
_VALID_TASKS = ("sfc_scan", "dism_health", "optimize_volume")


class MaintenanceScheduler:
    """Create, list, run, and delete recurring native maintenance jobs
    (SFC / DISM / Optimize-Volume) backed by the native Windows Task
    Scheduler."""

    def __init__(self):
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        self._scheduler = WindowsTaskScheduler()

    def _path_for(self, job_name: str) -> Path:
        safe = "".join(c for c in job_name if c.isalnum() or c in ("_", "-"))[:100]
        return JOBS_DIR / f"{safe}.json"

    def _run_ps(self, cmd: str, timeout: float = 600.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    def create_job(
        self,
        job_name: str,
        tasks: List[str],
        trigger_type: str = "logon",
        time: str = "03:00",
        drive_letter: str = "C",
        confirm: bool = False,
    ) -> Dict:
        """Create a recurring maintenance job running one or more of
        'sfc_scan', 'dism_health', 'optimize_volume' (drive_letter only
        applies to optimize_volume). trigger_type is 'daily' (at `time`,
        HH:MM) or 'logon'. Confirm-gated - this also registers a real
        native Scheduled Task running as Administrator."""
        if not job_name or not tasks:
            return {"error": "job_name and tasks must both be non-empty"}
        bad = [t for t in tasks if t not in _VALID_TASKS]
        if bad:
            return {"error": f"Unknown task(s) {bad}. Valid: {list(_VALID_TASKS)}"}
        if trigger_type not in ("daily", "logon"):
            return {"error": "trigger_type must be 'daily' or 'logon'"}
        path = self._path_for(job_name)
        if not confirm:
            trig_desc = f"daily at {time}" if trigger_type == "daily" else "at logon"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would create maintenance job '{job_name}' running {tasks} ({trig_desc})",
                "message": "Call again with confirm=true to apply.",
            }
        job = {
            "job_name": job_name,
            "tasks": tasks,
            "trigger_type": trigger_type,
            "time": time,
            "drive_letter": drive_letter,
            "enabled": True,
        }
        try:
            path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        except Exception as e:
            return {"error": str(e)}
        runner_cmd = f'"{sys.executable}" -m system_control.automation.maintenance_scheduler'
        task_result = self._scheduler.create_task(
            name=TASK_NAME_PREFIX + job_name,
            command=runner_cmd,
            arguments=job_name,
            trigger_type=trigger_type,
            time=time,
            confirm=True,
        )
        if "error" in task_result:
            path.unlink(missing_ok=True)
            return {"error": f"Job saved locally but native task creation failed: {task_result['error']}"}
        return {"success": True, "job_name": job_name, "tasks": tasks, "scheduled_task": task_result}

    def list_jobs(self) -> Dict:
        """List all maintenance jobs."""
        try:
            jobs = []
            for p in sorted(JOBS_DIR.glob("*.json")):
                try:
                    jobs.append(json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    continue
            return {"success": True, "jobs": jobs, "count": len(jobs)}
        except Exception as e:
            return {"error": str(e)}

    def get_job(self, job_name: str) -> Dict:
        """View one maintenance job's configuration."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No maintenance job named '{job_name}'"}
        try:
            return {"success": True, "job": json.loads(path.read_text(encoding="utf-8"))}
        except Exception as e:
            return {"error": str(e)}

    def delete_job(self, job_name: str, confirm: bool = False) -> Dict:
        """Delete a maintenance job and its underlying native scheduled
        task. Confirm-gated."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No maintenance job named '{job_name}'"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete maintenance job '{job_name}' and its scheduled task",
                "message": "Call again with confirm=true to apply.",
            }
        task_result = self._scheduler.delete_task(TASK_NAME_PREFIX + job_name, confirm=True)
        path.unlink()
        return {
            "success": True,
            "job_name": job_name,
            "deleted": True,
            "scheduled_task_deleted": "error" not in task_result,
        }

    def set_job_enabled(self, job_name: str, enabled: bool, confirm: bool = False) -> Dict:
        """Enable/disable a maintenance job's underlying scheduled task
        without deleting the job. Confirm-gated."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No maintenance job named '{job_name}'"}
        if not confirm:
            action = "enable" if enabled else "disable"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would {action} maintenance job '{job_name}'",
                "message": "Call again with confirm=true to apply.",
            }
        task_result = (self._scheduler.enable_task if enabled else self._scheduler.disable_task)(
            TASK_NAME_PREFIX + job_name, confirm=True
        )
        if "error" in task_result:
            return task_result
        job = json.loads(path.read_text(encoding="utf-8"))
        job["enabled"] = enabled
        path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        return {"success": True, "job_name": job_name, "enabled": enabled}

    def run_job_now(self, job_name: str, confirm: bool = False) -> Dict:
        """Run a maintenance job's tasks immediately (outside its
        schedule). Confirm-gated - SFC/DISM/Optimize-Volume can take a
        long time and need Administrator."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No maintenance job named '{job_name}'"}
        job = json.loads(path.read_text(encoding="utf-8"))
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would run maintenance tasks {job['tasks']} for job '{job_name}' now",
                "message": "Call again with confirm=true to apply.",
            }
        return self._execute(job)

    def _execute(self, job: Dict) -> Dict:
        results = {}
        for task in job["tasks"]:
            if task == "sfc_scan":
                r = self._run_sfc()
            elif task == "dism_health":
                r = self._run_dism()
            elif task == "optimize_volume":
                r = self._run_optimize(job.get("drive_letter", "C"))
            else:
                r = {"error": f"Unknown task '{task}'"}
            results[task] = r
        ok = all("error" not in r for r in results.values())
        return {"success": ok, "job_name": job["job_name"], "results": results}

    def _run_sfc(self) -> Dict:
        """Run `sfc /scannow`. Requires Administrator."""
        try:
            result = subprocess.run(["sfc", "/scannow"], capture_output=True, text=True, timeout=1800)
            return {"success": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "sfc.exe not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "sfc /scannow timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _run_dism(self) -> Dict:
        """Run `DISM /Online /Cleanup-Image /RestoreHealth`. Requires Administrator."""
        try:
            result = subprocess.run(
                ["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"],
                capture_output=True,
                text=True,
                timeout=1800,
            )
            return {"success": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "DISM.exe not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "DISM RestoreHealth timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _run_optimize(self, drive_letter: str) -> Dict:
        """Run Optimize-Volume on one drive - defrags an HDD or TRIMs
        an SSD, whichever applies. Requires Administrator."""
        safe = drive_letter.rstrip(":").upper()
        if len(safe) != 1 or not safe.isalpha():
            return {"error": f"Invalid drive letter: {drive_letter!r}"}
        return self._run_ps(f"Optimize-Volume -DriveLetter {safe} -Verbose", timeout=1800)


def run_job_by_name(job_name: str) -> Dict:
    """CLI-friendly entry point with no confirm prompt - the target a
    native Scheduled Task actually invokes, so it must run unattended
    with no interactive caller available to confirm."""
    scheduler = MaintenanceScheduler()
    job_result = scheduler.get_job(job_name)
    if "error" in job_result:
        return job_result
    return scheduler._execute(job_result["job"])


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(run_job_by_name(sys.argv[1]), indent=2))
    else:
        print("Usage: python -m system_control.automation.maintenance_scheduler <job_name>")
