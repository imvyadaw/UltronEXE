"""Cleanup scheduler
====================
Schedules recurring ULTRON-controlled disk cleanup jobs: sweeping the
user's %TEMP%/Windows Temp folders, emptying the Recycle Bin, and
(optionally) triggering system_control/storage/storage_sense.py's
own run_now() as one more step in the same job.

Deliberately not a duplicate of storage_sense.py: that module
configures Windows' own *automatic, policy-driven* background cleanup
(different schedule engine entirely, owned by the OS). This module is
a ULTRON-native job with its own independently configurable schedule
and target list ('temp_files', 'recycle_bin', 'storage_sense'), for
cases where the user wants cleanup on a cadence Storage Sense itself
doesn't offer (e.g. "every logon") or wants it bundled with other
ULTRON automation. Same glue pattern as backup_scheduler.py /
maintenance_scheduler.py / update_scheduler.py in this same package:
a named "cleanup job" persisted to
storage/cache/cleanup_jobs/<job_name>.json, with a real native
Scheduled Task registered alongside it via
WindowsTaskScheduler.create_task so the job still runs even with
ULTRON closed.

Emptying the Recycle Bin and deleting temp files are both irreversible,
so creating/deleting a job and running one immediately are all
confirm-gated, matching this package's own precedent (backup_scheduler.py
gates create/delete/run for exactly the same "real system change"
reason).
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

from system_control.process.task_scheduler import WindowsTaskScheduler
from system_control.storage.storage_sense import StorageSense

JOBS_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "cleanup_jobs"
TASK_NAME_PREFIX = "Ultron_Cleanup_"
_VALID_TARGETS = ("temp_files", "recycle_bin", "storage_sense")


class CleanupScheduler:
    """Create, list, run, and delete recurring native cleanup jobs
    (temp files / Recycle Bin / Storage Sense trigger) backed by the
    native Windows Task Scheduler."""

    def __init__(self):
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        self._scheduler = WindowsTaskScheduler()
        self._storage_sense = StorageSense()

    def _path_for(self, job_name: str) -> Path:
        safe = "".join(c for c in job_name if c.isalnum() or c in ("_", "-"))[:100]
        return JOBS_DIR / f"{safe}.json"

    def create_job(
        self, job_name: str, targets: List[str], trigger_type: str = "logon", time: str = "05:00", confirm: bool = False
    ) -> Dict:
        """Create a recurring cleanup job running one or more of
        'temp_files', 'recycle_bin', 'storage_sense'. trigger_type is
        'daily' (at `time`, HH:MM) or 'logon'. Confirm-gated - this
        also registers a real native Scheduled Task, and the job's own
        runs are irreversible (deleted temp files / emptied Recycle
        Bin are not recoverable through this module)."""
        if not job_name or not targets:
            return {"error": "job_name and targets must both be non-empty"}
        bad = [t for t in targets if t not in _VALID_TARGETS]
        if bad:
            return {"error": f"Unknown target(s) {bad}. Valid: {list(_VALID_TARGETS)}"}
        if trigger_type not in ("daily", "logon"):
            return {"error": "trigger_type must be 'daily' or 'logon'"}
        path = self._path_for(job_name)
        if not confirm:
            trig_desc = f"daily at {time}" if trigger_type == "daily" else "at logon"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": (
                    f"Would create cleanup job '{job_name}' running {targets} ({trig_desc}) - "
                    "deleted temp files and an emptied Recycle Bin cannot be recovered"
                ),
                "message": "Call again with confirm=true to apply.",
            }
        job = {"job_name": job_name, "targets": targets, "trigger_type": trigger_type, "time": time, "enabled": True}
        try:
            path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        except Exception as e:
            return {"error": str(e)}
        runner_cmd = f'"{sys.executable}" -m system_control.automation.cleanup_scheduler'
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
        return {"success": True, "job_name": job_name, "targets": targets, "scheduled_task": task_result}

    def list_jobs(self) -> Dict:
        """List all cleanup jobs."""
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
        """View one cleanup job's configuration."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No cleanup job named '{job_name}'"}
        try:
            return {"success": True, "job": json.loads(path.read_text(encoding="utf-8"))}
        except Exception as e:
            return {"error": str(e)}

    def delete_job(self, job_name: str, confirm: bool = False) -> Dict:
        """Delete a cleanup job and its underlying native scheduled
        task. Confirm-gated."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No cleanup job named '{job_name}'"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete cleanup job '{job_name}' and its scheduled task",
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
        """Enable/disable a cleanup job's underlying scheduled task
        without deleting the job. Confirm-gated."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No cleanup job named '{job_name}'"}
        if not confirm:
            action = "enable" if enabled else "disable"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would {action} cleanup job '{job_name}'",
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
        """Run a cleanup job's targets immediately (outside its
        schedule). Confirm-gated - irreversible."""
        path = self._path_for(job_name)
        if not path.exists():
            return {"error": f"No cleanup job named '{job_name}'"}
        job = json.loads(path.read_text(encoding="utf-8"))
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would run cleanup targets {job['targets']} for job '{job_name}' now",
                "message": "Call again with confirm=true to apply.",
            }
        return self._execute(job)

    def _execute(self, job: Dict) -> Dict:
        results = {}
        for target in job["targets"]:
            if target == "temp_files":
                r = self._clean_temp_files()
            elif target == "recycle_bin":
                r = self._empty_recycle_bin()
            elif target == "storage_sense":
                r = self._storage_sense.run_now()
            else:
                r = {"error": f"Unknown target '{target}'"}
            results[target] = r
        ok = all("error" not in r for r in results.values())
        return {"success": ok, "job_name": job["job_name"], "results": results}

    def _clean_temp_files(self) -> Dict:
        """Delete everything under the current user's %TEMP% directory.
        Best-effort - files locked by a running process are skipped
        rather than treated as a hard failure."""
        temp_dir = Path(tempfile.gettempdir())
        deleted, skipped = 0, 0
        try:
            for item in temp_dir.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    deleted += 1
                except Exception:
                    skipped += 1
        except Exception as e:
            return {"error": str(e)}
        return {"success": True, "temp_dir": str(temp_dir), "deleted": deleted, "skipped": skipped}

    def _empty_recycle_bin(self) -> Dict:
        """Empty the Recycle Bin via Clear-RecycleBin."""
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Clear-RecycleBin -Force -ErrorAction Stop",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "Clear-RecycleBin failed"}
            return {"success": True, "emptied": True}
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Clear-RecycleBin timed out"}
        except Exception as e:
            return {"error": str(e)}


def run_job_by_name(job_name: str) -> Dict:
    """CLI-friendly entry point with no confirm prompt - the target a
    native Scheduled Task actually invokes, so it must run unattended
    with no interactive caller available to confirm."""
    scheduler = CleanupScheduler()
    job_result = scheduler.get_job(job_name)
    if "error" in job_result:
        return job_result
    return scheduler._execute(job_result["job"])


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(run_job_by_name(sys.argv[1]), indent=2))
    else:
        print("Usage: python -m system_control.automation.cleanup_scheduler <job_name>")
