"""Power control
==============
Lock, shutdown, restart, sign-out (confirmation-gated, 30s grace period).
"""

import ctypes
import subprocess
from typing import Dict


class PowerControl:
    """Lock/shutdown/restart/sign-out. Destructive actions require confirm=True
    and give a 30-second cancellable grace period."""

    def lock_screen(self) -> Dict:
        """Lock the Windows screen immediately."""
        try:
            ctypes.windll.user32.LockWorkStation()
            return {"success": True, "message": "Screen locked"}
        except Exception as e:
            return {"error": str(e)}

    def shutdown_pc(self, confirm: bool = False) -> Dict:
        """Shut down the PC after a 30s grace period. Safety-gated: needs confirm=true."""
        if not confirm:
            return {
                "error": "This shuts down the PC. Call again with confirm=true to proceed (you'll have 30s to cancel_shutdown)."
            }
        try:
            subprocess.run(["shutdown", "/s", "/t", "30"], check=True, timeout=10)
            return {"success": True, "message": "Shutting down in 30 seconds - say 'cancel shutdown' to stop it"}
        except Exception as e:
            return {"error": str(e)}

    def restart_pc(self, confirm: bool = False) -> Dict:
        """Restart the PC after a 30s grace period. Safety-gated: needs confirm=true."""
        if not confirm:
            return {
                "error": "This restarts the PC. Call again with confirm=true to proceed (you'll have 30s to cancel_shutdown)."
            }
        try:
            subprocess.run(["shutdown", "/r", "/t", "30"], check=True, timeout=10)
            return {"success": True, "message": "Restarting in 30 seconds - say 'cancel shutdown' to stop it"}
        except Exception as e:
            return {"error": str(e)}

    def sign_out(self, confirm: bool = False) -> Dict:
        """Sign out of Windows immediately. Safety-gated: needs confirm=true."""
        if not confirm:
            return {
                "error": "This signs out immediately and closes open apps. Call again with confirm=true to proceed."
            }
        try:
            subprocess.run(["shutdown", "/l"], check=True, timeout=10)
            return {"success": True, "message": "Signing out"}
        except Exception as e:
            return {"error": str(e)}

    def cancel_shutdown(self) -> Dict:
        """Cancel a pending shutdown/restart."""
        try:
            result = subprocess.run(["shutdown", "/a"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return {"success": True, "message": "Pending shutdown/restart cancelled"}
            return {"success": False, "error": "No pending shutdown/restart to cancel"}
        except Exception as e:
            return {"error": str(e)}
