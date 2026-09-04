"""Emergency Mode Control
==========================
Unlike every other module in this package, no existing subsystem owns
this - it's a genuinely new "panic button" that chains several
already-built primitives that otherwise never talk to each other:
windows.system_info.power.PowerControl (lock the workstation),
vision.screen.capture.ScreenCapture / OpenCV (grab a webcam frame as
evidence), system_control.network.remote_desktop.RemoteDesktop and
system_control.network.ssh_manager.SshManager (cut off remote access),
system_control.security.bitlocker_manager.BitLockerManager (lock an
encrypted volume), and skills.communication.sms.SMSClient /
actions.call_phone.CallPhone (alert the owner) - plus an incident log
this module owns outright.

trigger() itself is confirm-gated by default but accepts an
already-confirmed "silent" panic path (confirm=True passed straight
through) since a real emergency shouldn't need a second round-trip;
callers building a physical panic hotkey/phrase should pass
confirm=True directly. Individual exit_emergency_mode() actions
(re-enabling remote access) are confirm-gated normally.
"""
import logging

import json
import time
from pathlib import Path
from typing import Dict, Optional

_LOG_PATH = Path(__file__).resolve().parent / "_emergency_log.jsonl"
_STATE_PATH = Path(__file__).resolve().parent / "_emergency_state.json"


class EmergencyModeControl:
    def _log(self, event: Dict) -> None:
        event["timestamp"] = time.time()
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def get_incident_log(self, limit: int = 20) -> Dict:
        if not _LOG_PATH.exists():
            return {"incidents": []}
        lines = _LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        return {"incidents": [json.loads(line) for line in lines[-limit:]]}

    def _snapshot_webcam(self) -> Dict:
        try:
            import cv2
            import tempfile

            cap = cv2.VideoCapture(0)
            ok, frame = cap.read()
            cap.release()
            if not ok:
                return {"error": "Could not read webcam frame."}
            path = str(Path(tempfile.gettempdir()) / f"ultron_emergency_{int(time.time())}.jpg")
            cv2.imwrite(path, frame)
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}

    def _lock_remote_access(self) -> Dict:
        results = {}
        try:
            from system_control.network.remote_desktop import RemoteDesktop

            results["rdp"] = RemoteDesktop().set_enabled(False, confirm=True)
        except Exception as e:
            results["rdp"] = {"error": str(e)}
        try:
            from system_control.network.ssh_manager import SshManager

            results["ssh"] = SshManager().stop_service(confirm=True)
        except Exception as e:
            results["ssh"] = {"error": str(e)}
        return results

    def _lock_bitlocker(self, drive_letter: str) -> Dict:
        try:
            from system_control.security.bitlocker_manager import BitLockerManager

            return BitLockerManager().lock_volume(drive_letter, confirm=True)
        except Exception as e:
            return {"error": str(e)}

    def _alert_contact(self, phone: Optional[str], message: str) -> Dict:
        if not phone:
            return {"skipped": "no contact phone configured"}
        results = {}
        try:
            from skills.communication.sms import SMSClient

            sms = SMSClient()
            results["sms"] = (
                sms.send_sms(phone, message) if sms.is_configured() else {"error": "SMS client not configured"}
            )
        except Exception as e:
            results["sms"] = {"error": str(e)}
        try:
            from actions.call_phone import get_call_phone

            call = get_call_phone()
            results["call"] = call.call(phone) if call.is_available() else {"error": "call service not available"}
        except Exception as e:
            results["call"] = {"error": str(e)}
        return results

    def trigger(
        self,
        reason: str = "manual",
        lock_workstation: bool = True,
        snapshot_webcam: bool = True,
        lock_remote_access: bool = True,
        lock_bitlocker_drive: Optional[str] = None,
        alert_phone: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will trigger EMERGENCY MODE (reason: {reason}): "
                    f"{'lock the workstation, ' if lock_workstation else ''}"
                    f"{'take a webcam snapshot, ' if snapshot_webcam else ''}"
                    f"{'disable RDP/SSH remote access, ' if lock_remote_access else ''}"
                    f"{'BitLocker-lock drive ' + lock_bitlocker_drive + ', ' if lock_bitlocker_drive else ''}"
                    f"{'alert ' + alert_phone if alert_phone else 'no alert contact set'}."
                ),
            }
        report: Dict = {"reason": reason}
        if snapshot_webcam:
            report["webcam_snapshot"] = self._snapshot_webcam()
        if lock_remote_access:
            report["remote_access"] = self._lock_remote_access()
        if lock_bitlocker_drive:
            report["bitlocker"] = self._lock_bitlocker(lock_bitlocker_drive)
        if alert_phone:
            report["alert"] = self._alert_contact(alert_phone, f"ULTRON emergency mode triggered: {reason}")
        if lock_workstation:
            try:
                from windows.system_info.power import PowerControl

                report["lock_screen"] = PowerControl().lock_screen()
            except Exception as e:
                report["lock_screen"] = {"error": str(e)}
        _STATE_PATH.write_text(
            json.dumps({"active": True, "reason": reason, "triggered_at": time.time()}), encoding="utf-8"
        )
        self._log({"event": "trigger", "reason": reason, "report_keys": list(report.keys())})
        return {"success": True, "report": report}

    def get_status(self) -> Dict:
        if _STATE_PATH.exists():
            try:
                return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            except Exception:
                logging.getLogger(__name__).exception("Suppressed Exception")
        return {"active": False}

    def exit_emergency_mode(self, restore_remote_access: bool = False, confirm: bool = False) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will clear emergency mode{' and re-enable RDP/SSH' if restore_remote_access else ''}.",
            }
        results = {}
        if restore_remote_access:
            try:
                from system_control.network.remote_desktop import RemoteDesktop

                results["rdp"] = RemoteDesktop().set_enabled(True, confirm=True)
            except Exception as e:
                results["rdp"] = {"error": str(e)}
            try:
                from system_control.network.ssh_manager import SshManager

                results["ssh"] = SshManager().start_service(confirm=True)
            except Exception as e:
                results["ssh"] = {"error": str(e)}
        _STATE_PATH.write_text(json.dumps({"active": False}), encoding="utf-8")
        self._log({"event": "exit", "restored_remote_access": restore_remote_access})
        return {"success": True, "results": results}


_instance: Optional[EmergencyModeControl] = None


def get_emergency_mode_control() -> EmergencyModeControl:
    global _instance
    if _instance is None:
        _instance = EmergencyModeControl()
    return _instance
