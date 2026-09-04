"""Password Policy Manager
============================
Local Windows password/account-lockout policy control via `net
accounts` - minimum password length/age, password history, and
account lockout threshold/duration for this machine's local accounts.
Distinct from user_accounts.py (individual account creation/removal/
privileges/password resets) - this is the machine-wide RULES those
accounts' passwords and lockouts have to follow, not any one
account's own state.

get_policy() is a plain read. Every setter changes machine-wide
security posture and is confirm-gated, needing admin.
"""

import subprocess
import re
from typing import Dict, Optional


class PasswordPolicy:
    """Inspect and control local password/lockout policy via net accounts."""

    def _run(self, cmd: list, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "net not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower() or "elevat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def get_policy(self) -> Dict:
        """Get current local password and lockout policy (min length/age, history,
        lockout threshold/duration)."""
        result = self._run(["net", "accounts"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net accounts failed")}
        text = result["stdout"]

        def grab(pattern):
            m = re.search(pattern, text)
            return m.group(1).strip() if m else None

        return {
            "min_password_age_days": grab(r"Minimum password age \(days\):\s*(.+)"),
            "max_password_age_days": grab(r"Maximum password age \(days\):\s*(.+)"),
            "min_password_length": grab(r"Minimum password length:\s*(.+)"),
            "password_history_count": grab(r"Length of password history maintained:\s*(.+)"),
            "lockout_threshold": grab(r"Lockout threshold:\s*(.+)"),
            "lockout_duration_minutes": grab(r"Lockout duration \(minutes\):\s*(.+)"),
            "lockout_observation_window_minutes": grab(r"Lockout observation window \(minutes\):\s*(.+)"),
        }

    def set_min_password_length(self, length: int, confirm: bool = False) -> Dict:
        """Set the minimum required password length for local accounts. Confirm-gated, needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will set the minimum local password length to {length} characters.",
            }
        result = self._run(["net", "accounts", f"/minpwlen:{length}"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net accounts /minpwlen failed")}
        return {"success": True, "min_password_length": length}

    def set_max_password_age(self, days: int, confirm: bool = False) -> Dict:
        """Set how many days a password stays valid before requiring a change
        (use 'unlimited' semantics with days=0 for no expiry). Confirm-gated, needs admin."""
        if not confirm:
            desc = "never expire" if days == 0 else f"expire after {days} days"
            return {"requires_confirmation": True, "preview": f"This will set local passwords to {desc}."}
        value = "UNLIMITED" if days == 0 else str(days)
        result = self._run(["net", "accounts", f"/maxpwage:{value}"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net accounts /maxpwage failed")}
        return {"success": True, "max_password_age_days": days}

    def set_min_password_age(self, days: int, confirm: bool = False) -> Dict:
        """Set the minimum days before a password can be changed again (prevents
        rapid history cycling). Confirm-gated, needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will require local passwords to be at least {days} day(s) old before they can be changed again.",
            }
        result = self._run(["net", "accounts", f"/minpwage:{days}"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net accounts /minpwage failed")}
        return {"success": True, "min_password_age_days": days}

    def set_password_history(self, count: int, confirm: bool = False) -> Dict:
        """Set how many previous passwords are remembered to prevent reuse. Confirm-gated, needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will remember the last {count} password(s) per account to block reuse.",
            }
        result = self._run(["net", "accounts", f"/uniquepw:{count}"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net accounts /uniquepw failed")}
        return {"success": True, "password_history_count": count}

    def set_lockout_policy(
        self,
        threshold: Optional[int] = None,
        duration_minutes: Optional[int] = None,
        observation_window_minutes: Optional[int] = None,
        confirm: bool = False,
    ) -> Dict:
        """Set account-lockout threshold (failed attempts before lockout),
        lockout duration, and/or the observation window that resets the
        failed-attempt counter. Confirm-gated, needs admin - too strict a
        threshold can lock out legitimate users."""
        if threshold is None and duration_minutes is None and observation_window_minutes is None:
            return {"error": "Provide at least one of threshold, duration_minutes, observation_window_minutes."}
        if not confirm:
            parts = []
            if threshold is not None:
                parts.append(f"lockout after {threshold} failed attempts")
            if duration_minutes is not None:
                parts.append(f"lockout duration {duration_minutes} minute(s)")
            if observation_window_minutes is not None:
                parts.append(f"observation window {observation_window_minutes} minute(s)")
            return {"requires_confirmation": True, "preview": "This will set: " + ", ".join(parts) + "."}
        args = ["net", "accounts"]
        if threshold is not None:
            args.append(f"/lockoutthreshold:{threshold}")
        if duration_minutes is not None:
            args.append(f"/lockoutduration:{duration_minutes}")
        if observation_window_minutes is not None:
            args.append(f"/lockoutwindow:{observation_window_minutes}")
        result = self._run(args)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net accounts lockout settings failed")}
        return {
            "success": True,
            "lockout_threshold": threshold,
            "lockout_duration_minutes": duration_minutes,
            "lockout_observation_window_minutes": observation_window_minutes,
        }
