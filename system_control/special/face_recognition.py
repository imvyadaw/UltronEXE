"""Face Recognition Control
============================
System-facing control surface for face recognition. The actual face
encoding/matching math lives in vision.face.recognition.FaceRecognition
(enroll/recognize against a pickled encodings store) and
security.face_lock.FaceLock (a separate, tolerance-tuned store used
specifically to unlock ULTRON itself). This module does NOT duplicate
either - it adds the OS/device-facing half: camera enumeration,
capture-then-identify against BOTH stores in one call, and the
system policy of what happens on an unknown face (webcam privacy
toggle, auto-lock-on-unknown-face).

State-changing methods (enrolling a face, changing the unknown-face
policy, toggling the camera privacy switch) are confirm-gated.
"""

import subprocess
from typing import Dict, Optional


class FaceRecognitionControl:
    def _run_ps(self, script: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "powershell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def list_cameras(self) -> Dict:
        """Enumerate camera devices via PnP (distinct from actually opening one)."""
        result = self._run_ps(
            "Get-PnpDevice -Class Camera,Image | Select-Object FriendlyName, InstanceId, Status | ConvertTo-Json"
        )
        if "error" in result:
            return result
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            if isinstance(data, dict):
                data = [data]
            return {"cameras": data, "count": len(data)}
        except Exception:
            return {"error": "Could not parse camera list.", "raw": result["stdout"]}

    def get_camera_privacy_status(self) -> Dict:
        """Whether the OS-level 'let apps use camera' switch is on."""
        result = self._run_ps(
            "Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam' "
            "-Name Value -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Value"
        )
        if "error" in result:
            return result
        val = (result.get("stdout") or "").strip()
        return {"camera_access_allowed": val != "Deny"}

    def set_camera_privacy(self, allowed: bool, confirm: bool = False) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {'ALLOW' if allowed else 'BLOCK'} apps from using the camera (affects ULTRON's own face recognition too).",
            }
        value = "Allow" if allowed else "Deny"
        result = self._run_ps(
            "New-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam' "
            f"-Name Value -Value '{value}' -PropertyType String -Force | Out-Null"
        )
        if "error" in result:
            return result
        return {"success": True, "camera_access_allowed": allowed}

    def capture_and_identify(self, camera_index: int = 0, use_lock_store: bool = False) -> Dict:
        """Grab a frame and identify it against vision.face.recognition's
        general store (default) or security.face_lock's unlock-specific
        store (use_lock_store=True). Delegates the actual match."""
        try:
            import cv2  # noqa
        except ImportError:
            return {"error": "opencv-python not installed - camera capture unavailable."}
        try:
            cap = cv2.VideoCapture(camera_index)
            ok, frame = cap.read()
            cap.release()
            if not ok:
                return {"error": f"Could not read a frame from camera index {camera_index}."}
        except Exception as e:
            return {"error": str(e)}

        if use_lock_store:
            from security.face_lock import get_face_lock
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                cv2.imwrite(tmp.name, frame)
                return get_face_lock().verify(tmp.name)
        else:
            from vision.face.recognition import get_face_recognition

            return get_face_recognition().recognize(image=frame)

    def enroll_face(self, name: str, camera_index: int = 0, for_unlock: bool = False, confirm: bool = False) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will enroll a new face for '{name}' into the {'unlock-specific' if for_unlock else 'general recognition'} store.",
            }
        try:
            import cv2  # noqa
        except ImportError:
            return {"error": "opencv-python not installed - camera capture unavailable."}
        cap = cv2.VideoCapture(camera_index)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return {"error": f"Could not read a frame from camera index {camera_index}."}
        if for_unlock:
            from security.face_lock import get_face_lock
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                cv2.imwrite(tmp.name, frame)
                return get_face_lock().enroll(name, tmp.name)
        else:
            from vision.face.recognition import get_face_recognition

            return get_face_recognition().enroll(name, image=frame)

    def list_known_faces(self) -> Dict:
        from vision.face.recognition import get_face_recognition
        from security.face_lock import get_face_lock

        return {
            "general_store": get_face_recognition().list_known(),
            "unlock_store": get_face_lock().enrolled_names(),
        }

    def set_unknown_face_policy(self, action: str, confirm: bool = False) -> Dict:
        """action: 'ignore' | 'notify' | 'lock_workstation'. Stored as a
        simple flag file the caller (e.g. a monitoring loop) reads before
        acting on an unrecognized face - this module doesn't run that loop
        itself, it just owns the policy setting."""
        if action not in ("ignore", "notify", "lock_workstation"):
            return {"error": "action must be 'ignore', 'notify', or 'lock_workstation'"}
        if not confirm:
            return {"requires_confirmation": True, "preview": f"This will set the unknown-face policy to '{action}'."}
        from pathlib import Path

        cfg = Path(__file__).resolve().parent / "_unknown_face_policy.txt"
        cfg.write_text(action, encoding="utf-8")
        return {"success": True, "policy": action}

    def get_unknown_face_policy(self) -> Dict:
        from pathlib import Path

        cfg = Path(__file__).resolve().parent / "_unknown_face_policy.txt"
        return {"policy": cfg.read_text(encoding="utf-8").strip() if cfg.exists() else "ignore"}


_instance: Optional[FaceRecognitionControl] = None


def get_face_recognition_control() -> FaceRecognitionControl:
    global _instance
    if _instance is None:
        _instance = FaceRecognitionControl()
    return _instance
