"""Windows Update
=================
Check/list/install Windows Updates. Uses the built-in COM Update Agent
API (Microsoft.Update.Session, via `win32com`/`comtypes` if present,
else a PowerShell -ComObject fallback) for checking/listing, and
`usoclient`/UsoClient.exe (present on every modern Windows build) for
triggering a scan or restart-required check without needing the
optional PSWindowsUpdate module installed.

Installing updates is real system change, so install_updates is
confirm-gated same as everywhere else in this package, and additionally
refuses to auto-restart the machine - ULTRON will report if a restart
is required and let the user decide separately (restart_pc is already
its own separately-gated tool elsewhere in the codebase).
"""

import json
import subprocess
from typing import Dict, List


class WindowsUpdate:
    """Check for / list / install Windows Updates via the COM Update Agent, PowerShell-driven."""

    def _run_ps(self, cmd: str, timeout: float = 120.0) -> Dict:
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
            return {"error": f"Windows Update command timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    # The Update Agent COM object works without any extra module install,
    # unlike PSWindowsUpdate which most machines don't have - kept as the
    # primary path, with a clear error if COM itself isn't reachable.
    _SEARCH_SCRIPT = (
        "$session = New-Object -ComObject Microsoft.Update.Session; "
        "$searcher = $session.CreateUpdateSearcher(); "
        "$result = $searcher.Search(\"IsInstalled=0 and Type='Software'\"); "
        "$updates = @(); "
        "foreach ($u in $result.Updates) { "
        "  $updates += [PSCustomObject]@{ Title=$u.Title; KBArticleIDs=($u.KBArticleIDs -join ','); "
        "  Description=$u.Description; IsDownloaded=$u.IsDownloaded; "
        "  SizeMB=[math]::Round($u.MaxDownloadSize/1MB,1) }; "
        "} "
        "$updates | ConvertTo-Json -Depth 3"
    )

    def check_for_updates(self) -> Dict:
        """Search for available (not-yet-installed) software updates."""
        result = self._run_ps(self._SEARCH_SCRIPT, timeout=90.0)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Update search failed - Windows Update service may be stopped"}
        try:
            raw = result["stdout"]
            updates: List[Dict] = json.loads(raw) if raw else []
            if isinstance(updates, dict):
                updates = [updates]
        except Exception as e:
            return {"error": f"Could not parse update search output: {e}", "raw": result["stdout"]}
        return {"success": True, "updates_available": updates, "count": len(updates)}

    def list_update_history(self, count: int = 20) -> Dict:
        """List recently installed updates (Get-HotFix, plus Update Agent
        history for anything Get-HotFix misses)."""
        cmd = (
            f"Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First {int(count)} "
            f"HotFixID,Description,InstalledOn | ConvertTo-Json"
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not read update history"}
        try:
            raw = result["stdout"]
            history = json.loads(raw) if raw else []
            if isinstance(history, dict):
                history = [history]
        except Exception as e:
            return {"error": f"Could not parse history output: {e}", "raw": result["stdout"]}
        return {"success": True, "history": history, "count": len(history)}

    def is_restart_required(self) -> Dict:
        """Check whether a pending update needs a restart to finish applying."""
        cmd = (
            "$key = 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired'; "
            "Test-Path $key"
        )
        result = self._run_ps(cmd, timeout=15.0)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not check restart status"}
        return {"success": True, "restart_required": result["stdout"].strip().lower() == "true"}

    def install_updates(self, confirm: bool = False) -> Dict:
        """Download and install all available software updates found by
        check_for_updates. Confirm-gated, needs admin, and will NOT
        auto-restart even if the install requires one - call
        is_restart_required() afterward and handle restart separately."""
        if not confirm:
            preview = self.check_for_updates()
            count = preview.get("count", "an unknown number of")
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would download and install {count} update(s). This needs admin and can take a while.",
                "message": "Call again with confirm=true to apply.",
            }
        script = (
            "$session = New-Object -ComObject Microsoft.Update.Session; "
            "$searcher = $session.CreateUpdateSearcher(); "
            "$result = $searcher.Search(\"IsInstalled=0 and Type='Software'\"); "
            'if ($result.Updates.Count -eq 0) { Write-Output \'{"installed":0,"titles":[]}\'; exit 0 } '
            "$toInstall = New-Object -ComObject Microsoft.Update.UpdateColl; "
            "foreach ($u in $result.Updates) { $toInstall.Add($u) | Out-Null } "
            "$downloader = $session.CreateUpdateDownloader(); "
            "$downloader.Updates = $toInstall; $downloader.Download() | Out-Null; "
            "$installer = $session.CreateUpdateInstaller(); "
            "$installer.Updates = $toInstall; $installResult = $installer.Install(); "
            "$titles = @($toInstall | ForEach-Object { $_.Title }); "
            "[PSCustomObject]@{ installed=$toInstall.Count; resultCode=$installResult.ResultCode; "
            "rebootRequired=$installResult.RebootRequired; titles=$titles } | ConvertTo-Json"
        )
        result = self._run_ps(script, timeout=1800.0)
        if "error" in result:
            return result
        if not result["success"]:
            err = result["stderr"] or "Install failed"
            if "access" in err.lower() or "denied" in err.lower() or "administrat" in err.lower():
                err += " - installing updates needs ULTRON running as Administrator."
            return {"error": err}
        try:
            data = json.loads(result["stdout"]) if result["stdout"] else {}
        except Exception as e:
            return {"error": f"Could not parse install output: {e}", "raw": result["stdout"]}
        return {
            "success": True,
            **data,
            "note": "Did not restart automatically - check reboot_required and restart separately if needed.",
        }

    def pause_updates(self, days: int = 7, confirm: bool = False) -> Dict:
        """Pause Windows Update for up to 35 days (Windows's own cap)."""
        days = max(1, min(int(days), 35))
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would pause Windows Update for {days} day(s)",
                "message": "Call again with confirm=true to apply.",
            }
        cmd = (
            "$pause = (Get-Date).AddDays(%d).ToString('yyyy-MM-ddTHH:mm:ssZ'); "
            "New-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings' "
            "-Name 'PauseUpdatesExpiryTime' -Value $pause -PropertyType String -Force | Out-Null; "
            "Write-Output $pause" % days
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            err = result["stderr"] or "Pause failed"
            if "access" in err.lower() or "denied" in err.lower():
                err += " - pausing updates needs ULTRON running as Administrator."
            return {"error": err}
        return {"success": True, "paused_until": result["stdout"].strip(), "days": days}
