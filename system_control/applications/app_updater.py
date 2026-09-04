"""App Updater
==============
Checks for and applies updates to already-installed applications via
`winget upgrade`. Windows Update itself (system_config/windows_update.py)
covers OS/driver/Store-platform updates; this module is specifically
about third-party application versions winget tracks (Chrome, VS Code,
7-Zip, etc.) - the same list Settings > Apps > Installed apps' "Update
available" flags are increasingly backed by.

Distinct from package_manager.py (installing something new the machine
has never had) - this module only ever operates on packages winget
already recognizes as installed.

update_app/update_all are confirm-gated since they run vendor
installers unattended; list/check operations are read-only.
"""

import subprocess
from typing import Dict, List


class AppUpdater:
    """Check for and apply application updates via winget."""

    def _run_winget(self, args: List[str], timeout: float = 60.0) -> Dict:
        try:
            result = subprocess.run(
                ["winget"] + args + ["--accept-source-agreements", "--disable-interactivity"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
            }
        except FileNotFoundError:
            return {"error": "winget not found - requires App Installer from the Microsoft Store"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _parse_table(stdout: str) -> List[Dict]:
        import re

        lines = stdout.splitlines()
        sep_idx = next((i for i, l in enumerate(lines) if re.match(r"^-+\s", l) or set(l.strip()) == {"-"}), None)
        if sep_idx is None or sep_idx == 0:
            return []
        header = lines[sep_idx - 1]
        sep = lines[sep_idx]
        bounds = [m.start() for m in re.finditer(r"(?:^|(?<= ))-+", sep)]
        bounds.append(len(header) + 1)
        cols = [header[bounds[i] : bounds[i + 1]].strip() for i in range(len(bounds) - 1)]
        rows = []
        for line in lines[sep_idx + 1 :]:
            if not line.strip():
                continue
            values = [line[bounds[i] : bounds[i + 1]].strip() for i in range(len(bounds) - 1)]
            rows.append(dict(zip(cols, values)))
        return rows

    def list_available_updates(self) -> Dict:
        """List every installed package winget has a newer version
        for. No admin needed."""
        result = self._run_winget(["upgrade"])
        if "error" in result:
            return result
        text = result["stdout"] + result["stderr"]
        if "No applicable update" in text or "No installed package" in text:
            return {"updates": [], "count": 0}
        if not result["success"] and not result["stdout"]:
            return {"error": result["stderr"] or "winget upgrade (list) failed."}
        rows = self._parse_table(result["stdout"])
        return {"updates": rows, "count": len(rows)}

    def check_app_update(self, package_id: str) -> Dict:
        """Check whether one specific package (by winget Id) has an
        update available."""
        data = self.list_available_updates()
        if "error" in data:
            return data
        match = next((u for u in data["updates"] if u.get("Id", "").lower() == package_id.lower()), None)
        if not match:
            return {"package_id": package_id, "update_available": False}
        return {"package_id": package_id, "update_available": True, "details": match}

    def update_app(self, package_id: str, confirm: bool = False) -> Dict:
        """Upgrade one package to its latest version via winget.
        Confirm-gated - runs the vendor's updated installer."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will upgrade '{package_id}' to its latest available version via winget.",
            }
        result = self._run_winget(["upgrade", "--id", package_id, "--exact", "--silent"], timeout=600.0)
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": result["stderr"] or result["stdout"] or "winget upgrade failed.",
                "returncode": result["returncode"],
            }
        return {"success": True, "package_id": package_id, "updated": True, "output": result["stdout"][-2000:]}

    def update_all(self, confirm: bool = False) -> Dict:
        """Upgrade every package winget reports an update for.
        Confirm-gated - runs multiple vendor installers unattended;
        prefer update_app for anything you want to review individually
        first."""
        if not confirm:
            pending = self.list_available_updates()
            count = pending.get("count", 0) if "error" not in pending else "unknown"
            return {
                "requires_confirmation": True,
                "preview": f"This will upgrade all ({count}) packages winget reports updates for.",
            }
        result = self._run_winget(["upgrade", "--all", "--silent"], timeout=1800.0)
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": result["stderr"] or result["stdout"] or "winget upgrade --all failed.",
                "returncode": result["returncode"],
            }
        return {"success": True, "updated_all": True, "output": result["stdout"][-3000:]}

    def update_sources(self) -> Dict:
        """Refresh winget's local package source indexes (equivalent
        to `winget source update`) so subsequent list/check calls see
        the latest catalog. No admin needed."""
        result = self._run_winget(["source", "update"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "winget source update failed."}
        return {"success": True, "output": result["stdout"]}
