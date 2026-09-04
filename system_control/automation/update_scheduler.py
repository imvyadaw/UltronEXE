"""Windows Update scheduler
===========================
Schedules recurring Windows Update *checks* (and, optionally,
unattended installs) on top of system_config/windows_update.py's
WindowsUpdate class, which only checks/lists/installs on-demand and
has no concept of "check every Monday morning". Same glue pattern as
backup_scheduler.py / maintenance_scheduler.py in this same package: a
named "update job" is {trigger_type, time, auto_install}, persisted to
storage/cache/update_jobs/<job_name>.json, with a real native
Scheduled Task (via WindowsTaskScheduler.create_task) registered
alongside it so the check still runs on schedule even with ULTRON
closed. The scheduled task's action re-invokes this module's own CLI
entry point, exactly like the other two schedulers in this package.

auto_install=True means the scheduled run will silently install any
available update it finds - real, unattended system change - so
creating a job with auto_install enabled, and running a job
immediately, are both confirm-gated, matching WindowsUpdate's own
gating on install_updates for exactly the same reason. As with
windows_update.py itself, this never auto-restarts the machine even
if a restart is required after install.
"""

import json
import sys
from pathlib import Path
from typing import Dict

from system_control.process.task_scheduler import WindowsTaskScheduler
from system_control.system_config.windows_update import WindowsUpdate

JOBS_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "update_jobs"
TASK_NAME_PREFIX = "Ultron_WindowsUpdate_"


class UpdateScheduler:
    """Create, list, run, and delete recurring Windows Update check/install
    jobs backed by the native Windows Task Scheduler."""

    def __init__(self):
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        self._update = WindowsUpdate()
        self._scheduler = WindowsTaskScheduler()

    def _path_for(self, job_name: str) -> Path:
        safe = "".join(c for c in job_name if c.isalnum() or c in ("_", "-"))[:100]
        return JOBS_DIR / f"{safe}.json"

    def create_job(
        self,
        job_name: str,
        trigger_type: str = "daily",
        time: str = "04:00",
        auto_install: bool = False,
        confirm: bool = False,
    ) -> Dict:
        """Create a recurring Windows Update job. trigger_type is
        'daily' (at `time`, HH:MM) or 'logon'. If auto_install is
        False (default), the scheduled run only checks/lists available
        updates without installing anything. Confirm-gated whenever
        auto_install=True, since that run will silently install
        updates unattended; also always registers a real native
        Scheduled Task."""
        if not job_name:
            return {"error": "job_name must be non-empty"}
        if trigger_type not in ("daily", "logon"):
            return {"error": "trigger_type must be 'daily' or 'logon'"}
        path = self._path_for(job_name)
        if auto_install and not confirm:
            trig_desc = f"daily at {time}" if trigger_type == "daily" else "at logon"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": (
                    f"Would create Windows Update job '{job_name}' ({trig_desc}) that "
                    "silently INSTALLS any updates it finds"
                ),
                "message": "Call again with confirm=true to apply.",
            }
        job = {
            "job_name": job_name,
            "trigger_type": trigger_type,
            "time": time,
            "auto_install": auto_install,
            "enabled": True,
        }
        try:
            path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        except Exception as e:
            return {"error": str(e)}
        runner_cmd = f'"{sys.executable}" -m system_control.automation.update_scheduler'
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
        return {"success": True, "job_name": job_name, "auto_install": auto_install, "scheduled_task": task_result}

    def list_jobs(self) -> Dict:
        """List all Windows Update jobs."""
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
        """View one Windows Update job's configuration."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No update job named '{job_name}'"}
        try:
            return {"success": True, "job": json.loads(path.read_text(encoding="utf-8"))}
        except Exception as e:
            return {"error": str(e)}

    def delete_job(self, job_name: str, confirm: bool = False) -> Dict:
        """Delete an update job and its underlying native scheduled
        task. Confirm-gated."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No update job named '{job_name}'"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete update job '{job_name}' and its scheduled task",
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
        """Enable/disable an update job's underlying scheduled task
        without deleting the job. Confirm-gated."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No update job named '{job_name}'"}
        if not confirm:
            action = "enable" if enabled else "disable"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would {action} update job '{job_name}'",
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
        """Run an update job immediately (outside its schedule).
        Confirm-gated only when the job's auto_install is True - a
        check-only run needs no confirmation."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No update job named '{job_name}'"}
        job = json.loads(path.read_text(encoding="utf-8"))
        if job.get("auto_install") and not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would check for and INSTALL updates for job '{job_name}' now",
                "message": "Call again with confirm=true to apply.",
            }
        return self._execute(job)

    def _execute(self, job: Dict) -> Dict:
        check_result = self._update.check_for_updates()
        if "error" in check_result:
            return {"success": False, "job_name": job["job_name"], "check": check_result}
        if not job.get("auto_install"):
            return {"success": True, "job_name": job["job_name"], "auto_install": False, "check": check_result}
        install_result = self._update.install_updates(confirm=True)
        return {
            "success": "error" not in install_result,
            "job_name": job["job_name"],
            "auto_install": True,
            "check": check_result,
            "install": install_result,
        }


def run_job_by_name(job_name: str) -> Dict:
    """CLI-friendly entry point with no confirm prompt - the target a
    native Scheduled Task actually invokes, so it must run unattended
    with no interactive caller available to confirm."""
    scheduler = UpdateScheduler()
    job_result = scheduler.get_job(job_name)
    if "error" in job_result:
        return job_result
    return scheduler._execute(job_result["job"])


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(run_job_by_name(sys.argv[1]), indent=2))
    else:
        print("Usage: python -m system_control.automation.update_scheduler <job_name>")
