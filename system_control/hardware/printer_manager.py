"""Printer Manager
=================
Windows print subsystem management - enumeration, default printer,
print-queue inspection, and job/queue control, via PowerShell's
PrintManagement module (Get-Printer/Get-PrintJob and friends), the
same first-party cmdlets Settings > Bluetooth & devices > Printers &
scanners is built on. No other module in the codebase touches
printing; this is new coverage.

Reading printer/job state and pausing/resuming/canceling a job you
already know the id of are low-risk, easily-reversible actions and
are not confirm-gated. Pausing/resuming an entire printer's queue, and
clearing every job in it, affect every pending job at once (not just
one) and are confirm-gated accordingly. Canceling other users' jobs on
a shared printer needs admin; canceling your own does not - errors
surface that distinction rather than assuming either way.
"""

import subprocess
from typing import Dict


class PrinterManager:
    """Enumerate printers, manage the default, and inspect/control
    print queues and jobs."""

    def _run_ps(self, cmd: str, timeout: float = 20.0) -> Dict:
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
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "elevat" in err.lower()):
            return (
                err
                + " - managing another user's jobs, or a shared printer's queue, may need ULTRON running as Administrator."
            )
        return err

    def list_printers(self) -> Dict:
        """All installed printers: name, driver, port, share status,
        and whether each is the current default. No admin needed."""
        result = self._run_ps(
            "$default = (Get-CimInstance Win32_Printer -ErrorAction SilentlyContinue | Where-Object Default).Name; "
            "Get-Printer -ErrorAction SilentlyContinue | Select-Object Name, DriverName, PortName, Shared, "
            "@{N='PrinterStatus';E={$_.PrinterStatus}}, @{N='IsDefault';E={$_.Name -eq $default}} | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-Printer failed")}
        if not result["stdout"]:
            return {"success": True, "printers": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse printer list"}
        printers = data if isinstance(data, list) else [data]
        return {"success": True, "printers": printers, "count": len(printers)}

    def get_default_printer(self) -> Dict:
        """The current default printer's name. No admin needed."""
        result = self._run_ps(
            "(Get-CimInstance Win32_Printer -ErrorAction SilentlyContinue | Where-Object Default).Name"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not read default printer"}
        name = result["stdout"].strip()
        return {"success": True, "default_printer": name or None}

    def set_default_printer(self, name: str, confirm: bool = False) -> Dict:
        """Set the default printer by name (from list_printers).
        Confirm-gated - changes which printer every app prints to by
        default from now on, machine-wide for this user. No admin
        needed for the user's own default."""
        if not name:
            return {"error": "name must be non-empty"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will set '{name}' as the default printer for all future print jobs.",
            }
        safe_name = name.replace("'", "''")
        result = self._run_ps(
            f"$p = Get-CimInstance Win32_Printer -Filter \"Name='{safe_name}'\" -ErrorAction Stop; "
            "Invoke-CimMethod -InputObject $p -MethodName SetDefaultPrinter | Out-Null"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": self._admin_hint(
                    result["stderr"]
                    or f"Could not set '{name}' as default - check the name matches list_printers() exactly."
                )
            }
        return {"success": True, "default_printer": name}

    def get_printer_status(self, name: str) -> Dict:
        """Current status (idle, printing, paused, error, offline,
        ...) for one printer by name. No admin needed."""
        if not name:
            return {"error": "name must be non-empty"}
        safe_name = name.replace("'", "''")
        result = self._run_ps(f"(Get-Printer -Name '{safe_name}' -ErrorAction Stop).PrinterStatus")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Printer '{name}' not found")}
        return {"success": True, "name": name, "status": result["stdout"].strip()}

    def list_print_jobs(self, name: str) -> Dict:
        """Pending/active jobs in a printer's queue: id, document
        name, submitter, status, and pages. No admin needed to view
        your own jobs; some drivers restrict visibility of other
        users' jobs without elevation."""
        if not name:
            return {"error": "name must be non-empty"}
        safe_name = name.replace("'", "''")
        result = self._run_ps(
            f"Get-PrintJob -PrinterName '{safe_name}' -ErrorAction SilentlyContinue | "
            "Select-Object Id, DocumentName, JobStatus, SubmittedBy, TotalPages | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not list jobs for '{name}'")}
        if not result["stdout"]:
            return {"success": True, "jobs": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse print job list"}
        jobs = data if isinstance(data, list) else [data]
        return {"success": True, "printer": name, "jobs": jobs, "count": len(jobs)}

    def pause_print_job(self, name: str, job_id: int) -> Dict:
        """Pause one specific job by id (from list_print_jobs). Not
        confirm-gated - affects only the one job, reversible with
        resume_print_job()."""
        return self._job_action(name, job_id, "Suspend-PrintJob", "paused")

    def resume_print_job(self, name: str, job_id: int) -> Dict:
        """Resume one specific paused job by id. Not confirm-gated."""
        return self._job_action(name, job_id, "Resume-PrintJob", "resumed")

    def cancel_print_job(self, name: str, job_id: int, confirm: bool = False) -> Dict:
        """Cancel (remove) one specific job by id. Confirm-gated -
        cannot be undone once removed from the queue."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will permanently cancel print job {job_id} on '{name}'.",
            }
        return self._job_action(name, job_id, "Remove-PrintJob", "canceled")

    def _job_action(self, name: str, job_id: int, cmdlet: str, verb: str) -> Dict:
        if not name:
            return {"error": "name must be non-empty"}
        safe_name = name.replace("'", "''")
        result = self._run_ps(f"{cmdlet} -PrinterName '{safe_name}' -ID {int(job_id)} -ErrorAction Stop")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not {verb.rstrip('ed')} job {job_id}")}
        return {"success": True, "printer": name, "job_id": job_id, "status": verb}

    def pause_printer(self, name: str, confirm: bool = False) -> Dict:
        """Pause an entire printer's queue - every pending job stops
        printing, not just one. Confirm-gated. Needs admin."""
        if not name:
            return {"error": "name must be non-empty"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will pause ALL pending jobs on printer '{name}', not just one.",
            }
        safe_name = name.replace("'", "''")
        result = self._run_ps(
            f"$p = Get-CimInstance Win32_Printer -Filter \"Name='{safe_name}'\" -ErrorAction Stop; "
            "Invoke-CimMethod -InputObject $p -MethodName Pause | Out-Null"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not pause '{name}'")}
        return {"success": True, "printer": name, "paused": True}

    def resume_printer(self, name: str, confirm: bool = False) -> Dict:
        """Resume a previously-paused printer's entire queue.
        Confirm-gated for symmetry with pause_printer(). Needs
        admin."""
        if not name:
            return {"error": "name must be non-empty"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will resume ALL pending jobs on printer '{name}'.",
            }
        safe_name = name.replace("'", "''")
        result = self._run_ps(
            f"$p = Get-CimInstance Win32_Printer -Filter \"Name='{safe_name}'\" -ErrorAction Stop; "
            "Invoke-CimMethod -InputObject $p -MethodName Resume | Out-Null"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not resume '{name}'")}
        return {"success": True, "printer": name, "paused": False}

    def clear_print_queue(self, name: str, confirm: bool = False) -> Dict:
        """Cancel every pending job on a printer at once. Confirm-
        gated and irreversible for each removed job. Canceling your
        own jobs needs no admin; canceling other users' jobs on a
        shared printer does."""
        if not name:
            return {"error": "name must be non-empty"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will PERMANENTLY cancel every pending job on printer '{name}'.",
            }
        safe_name = name.replace("'", "''")
        result = self._run_ps(
            f"Get-PrintJob -PrinterName '{safe_name}' -ErrorAction SilentlyContinue | Remove-PrintJob -ErrorAction SilentlyContinue"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not clear queue for '{name}'")}
        return {"success": True, "printer": name, "cleared": True}

    def print_test_page(self, name: str) -> Dict:
        """Print a standard Windows test page to a named printer - the
        same 'Print a test page' button in the printer's Properties
        dialog. Not confirm-gated: consumes one sheet of paper, same
        low-stakes class as printing anything else."""
        if not name:
            return {"error": "name must be non-empty"}
        safe_name = name.replace("'", "''")
        result = self._run_ps(
            f"$p = Get-CimInstance Win32_Printer -Filter \"Name='{safe_name}'\" -ErrorAction Stop; "
            "Invoke-CimMethod -InputObject $p -MethodName PrintTestPage | Out-Null"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not print a test page on '{name}'")}
        return {"success": True, "printer": name, "test_page_sent": True}
