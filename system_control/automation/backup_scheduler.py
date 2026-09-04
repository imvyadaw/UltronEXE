"""Backup scheduler
===================
Three related-but-distinct pieces already exist and this module
deliberately reuses rather than duplicates them:
  - system_control/files/backup.py's FileBackup does a one-off,
    on-demand backup of a single path. It has no concept of "every day
    at 2 AM" - it only runs when explicitly called.
  - system_control/process/task_scheduler.py's WindowsTaskScheduler
    creates arbitrary native Scheduled Tasks (any command, any
    trigger) but doesn't know anything about backups specifically.
  - automation/scheduler/task_scheduler.py's TaskScheduler is an
    in-process Python timer that stops firing the moment ULTRON's own
    process exits - useless for a backup that must still run overnight
    if the assistant isn't running.

BackupScheduler is the glue: a named "backup job" is {paths[],
trigger_type, time, retention_count}, persisted to
storage/cache/backup_jobs/<job_name>.json, with retention meaning
"keep only the N most recent backups per path, delete older ones".
Creating a job also registers a real native Scheduled Task (via
WindowsTaskScheduler.create_task) whose action re-invokes this same
module's CLI entry point, so the job keeps running on schedule even
with ULTRON closed - the same reason workflow_engine.py's pipelines
are dependency-light rather than routed through the AI tool-calling
stack.

Creating/deleting a job (which registers/removes a native scheduled
task) and running a job immediately are confirm-gated, matching
WindowsTaskScheduler's own gating for exactly the same reasons.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List

from system_control.files.backup import FileBackup
from system_control.process.task_scheduler import WindowsTaskScheduler

JOBS_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "backup_jobs"
TASK_NAME_PREFIX = "Ultron_Backup_"


class BackupScheduler:
    """Create, list, run, and delete recurring backup jobs backed by
    the native Windows Task Scheduler."""

    def __init__(self):
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        self._backup = FileBackup()
        self._scheduler = WindowsTaskScheduler()

    def _path_for(self, job_name: str) -> Path:
        safe = "".join(c for c in job_name if c.isalnum() or c in ("_", "-"))[:100]
        return JOBS_DIR / f"{safe}.json"

    def create_job(
        self,
        job_name: str,
        paths: List[str],
        trigger_type: str = "daily",
        time: str = "02:00",
        retention_count: int = 5,
        confirm: bool = False,
    ) -> Dict:
        """Create a recurring backup job for one or more paths. trigger_type
        is 'daily' (at `time`, HH:MM) or 'logon'. retention_count is how
        many of the most recent backups to keep per path before older
        ones are pruned. Confirm-gated - this also registers a real
        native Scheduled Task."""
        if not job_name or not paths:
            return {"error": "job_name and paths must both be non-empty"}
        if trigger_type not in ("daily", "logon"):
            return {"error": "trigger_type must be 'daily' or 'logon'"}
        path = self._path_for(job_name)
        if not confirm:
            trig_desc = f"daily at {time}" if trigger_type == "daily" else "at logon"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": (
                    f"Would create backup job '{job_name}' for {len(paths)} path(s) "
                    f"({trig_desc}, keeping last {retention_count} backups each)"
                ),
                "message": "Call again with confirm=true to apply.",
            }
        job = {
            "job_name": job_name,
            "paths": paths,
            "trigger_type": trigger_type,
            "time": time,
            "retention_count": retention_count,
            "enabled": True,
        }
        try:
            path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        except Exception as e:
            return {"error": str(e)}
        runner_cmd = f'"{sys.executable}" -m system_control.automation.backup_scheduler'
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
        return {"success": True, "job_name": job_name, "paths": paths, "scheduled_task": task_result}

    def list_jobs(self) -> Dict:
        """List all backup jobs."""
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
        """View one backup job's configuration."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No backup job named '{job_name}'"}
        try:
            return {"success": True, "job": json.loads(path.read_text(encoding="utf-8"))}
        except Exception as e:
            return {"error": str(e)}

    def delete_job(self, job_name: str, confirm: bool = False) -> Dict:
        """Delete a backup job and its underlying native scheduled task.
        Confirm-gated."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No backup job named '{job_name}'"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete backup job '{job_name}' and its scheduled task",
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
        """Enable/disable a backup job's underlying scheduled task without
        deleting the job. Confirm-gated."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No backup job named '{job_name}'"}
        if not confirm:
            action = "enable" if enabled else "disable"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would {action} backup job '{job_name}'",
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
        """Run a backup job's backups immediately (outside its schedule)
        and apply retention. Confirm-gated."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No backup job named '{job_name}'"}
        job = json.loads(path.read_text(encoding="utf-8"))
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would back up {len(job['paths'])} path(s) for job '{job_name}' now",
                "message": "Call again with confirm=true to apply.",
            }
        return self._execute(job)

    def _execute(self, job: Dict) -> Dict:
        results = []
        for src in job["paths"]:
            backup_result = self._backup.backup_path(src, confirm=True)
            results.append({"path": src, "backup": backup_result})
            self._apply_retention(src, job.get("retention_count", 5))
        ok = all("error" not in r["backup"] for r in results)
        return {"success": ok, "job_name": job["job_name"], "results": results}

    def _apply_retention(self, source_path: str, retention_count: int):
        from pathlib import Path as _Path

        source_name = self._backup._safe_name(_Path(source_path))
        listing = self._backup.list_backups(source_filter=source_name)
        if "error" in listing:
            return
        matches = [b for b in listing["backups"] if _Path(b["backup_path"]).name.startswith(source_name + "_")]
        matches.sort(key=lambda b: b["modified"], reverse=True)
        for stale in matches[retention_count:]:
            self._backup.delete_backup(stale["backup_path"], confirm=True)


def run_job_by_name(job_name: str) -> Dict:
    """CLI-friendly entry point with no confirm prompt - this is the
    target a native Scheduled Task actually invokes, so it must run
    unattended with no interactive caller available to confirm."""
    scheduler = BackupScheduler()
    job_result = scheduler.get_job(job_name)
    if "error" in job_result:
        return job_result
    return scheduler._execute(job_result["job"])


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(run_job_by_name(sys.argv[1]), indent=2))
    else:
        print("Usage: python -m system_control.automation.backup_scheduler <job_name>")
