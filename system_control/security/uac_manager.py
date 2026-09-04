"""UAC Manager
==============
Reads and sets Windows User Account Control (UAC) behavior via the
registry keys under HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\
Policies\\System (EnableLUA, ConsentPromptBehaviorAdmin,
PromptOnSecureDesktop). This is the same "Change User Account Control
settings" slider in Control Panel, exposed as four discrete levels
(0-3) instead of a slider position. Distinct from app_permissions.py
(per-app camera/mic/location grants) and from top-level
security/authentication.py (ULTRON's OWN unlock layer) - this
controls whether/how Windows itself prompts for elevation.

get_status()/get_level() are plain reads, no admin needed. Every
setter changes how much friction stands between a running process and
admin rights on this whole machine, so all of them are confirm-gated,
need admin, and a sign-out/restart to fully apply - the preview text
says so.
"""

import subprocess
from typing import Dict


class UACManager:
    """Inspect and control Windows User Account Control behavior."""

    _KEY = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"

    # The four Control Panel slider positions, expressed as the
    # (ConsentPromptBehaviorAdmin, PromptOnSecureDesktop) pair Windows
    # actually stores. EnableLUA must be 1 for any of these to matter.
    _LEVELS = {
        0: {"ConsentPromptBehaviorAdmin": 0, "PromptOnSecureDesktop": 0, "label": "Never notify"},
        1: {
            "ConsentPromptBehaviorAdmin": 5,
            "PromptOnSecureDesktop": 0,
            "label": "Notify me only when apps try to make changes (no dimming)",
        },
        2: {
            "ConsentPromptBehaviorAdmin": 5,
            "PromptOnSecureDesktop": 1,
            "label": "Notify me only when apps try to make changes (default)",
        },
        3: {"ConsentPromptBehaviorAdmin": 2, "PromptOnSecureDesktop": 1, "label": "Always notify"},
    }

    def _run_ps(self, script: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
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
            return {"error": "powershell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "elevat" in err.lower() or "access is denied" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def get_status(self) -> Dict:
        """Read the raw UAC registry values: whether UAC is on at all
        (EnableLUA), the admin consent-prompt behavior, and whether
        prompts use the dimmed secure desktop."""
        script = (
            f"$k = '{self._KEY}'; "
            "[PSCustomObject]@{"
            'EnableLUA = (Get-ItemProperty -Path "Registry::$k" -Name EnableLUA -ErrorAction SilentlyContinue).EnableLUA; '
            'ConsentPromptBehaviorAdmin = (Get-ItemProperty -Path "Registry::$k" -Name ConsentPromptBehaviorAdmin -ErrorAction SilentlyContinue).ConsentPromptBehaviorAdmin; '
            'PromptOnSecureDesktop = (Get-ItemProperty -Path "Registry::$k" -Name PromptOnSecureDesktop -ErrorAction SilentlyContinue).PromptOnSecureDesktop '
            "} | ConvertTo-Json"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Could not read UAC registry values.")}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else {}
        except Exception:
            return {"error": "Could not parse UAC status.", "raw": result["stdout"]}
        return {
            "uac_enabled": bool(data.get("EnableLUA")) if data.get("EnableLUA") is not None else None,
            "consent_prompt_behavior_admin": data.get("ConsentPromptBehaviorAdmin"),
            "prompt_on_secure_desktop": data.get("PromptOnSecureDesktop"),
        }

    def get_level(self) -> Dict:
        """Map the raw registry values to one of the four familiar
        Control Panel slider levels (0=Never notify .. 3=Always notify)."""
        status = self.get_status()
        if "error" in status:
            return status
        if status["uac_enabled"] is False:
            return {"level": 0, "label": self._LEVELS[0]["label"], "uac_enabled": False}
        cpba = status["consent_prompt_behavior_admin"]
        pod = status["prompt_on_secure_desktop"]
        for level, spec in self._LEVELS.items():
            if spec["ConsentPromptBehaviorAdmin"] == cpba and spec["PromptOnSecureDesktop"] == pod:
                return {"level": level, "label": spec["label"], "uac_enabled": True}
        return {
            "level": None,
            "label": "Custom (non-standard combination)",
            "uac_enabled": True,
            "consent_prompt_behavior_admin": cpba,
            "prompt_on_secure_desktop": pod,
        }

    def set_level(self, level: int, confirm: bool = False) -> Dict:
        """Set UAC to one of the four standard slider levels (0-3).
        Confirm-gated, needs admin, and a sign-out or restart to fully
        take effect."""
        if level not in self._LEVELS:
            return {"error": "level must be 0 (Never notify), 1, 2 (default), or 3 (Always notify)."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will set UAC to level {level} ('{self._LEVELS[level]['label']}'), "
                    f"changing how much warning you get before anything runs with admin rights "
                    f"on this machine. Level 0 disables the secure desktop and grants elevation "
                    f"silently. Takes effect after sign-out/restart."
                ),
            }
        spec = self._LEVELS[level]
        script = (
            f"$k = '{self._KEY}'; "
            f'Set-ItemProperty -Path "Registry::$k" -Name EnableLUA -Value {1 if level != 0 else 1} -Type DWord; '
            f"Set-ItemProperty -Path \"Registry::$k\" -Name ConsentPromptBehaviorAdmin -Value {spec['ConsentPromptBehaviorAdmin']} -Type DWord; "
            f"Set-ItemProperty -Path \"Registry::$k\" -Name PromptOnSecureDesktop -Value {spec['PromptOnSecureDesktop']} -Type DWord"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to set UAC level.")}
        return {
            "success": True,
            "level": level,
            "label": spec["label"],
            "note": "Sign out and back in (or restart) for this to fully apply.",
        }

    def set_enabled(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn UAC entirely on or off (EnableLUA). Disabling UAC removes
        elevation prompts machine-wide - a significant reduction in this
        machine's security posture. Confirm-gated, needs admin + restart."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will {'ENABLE' if enabled else 'DISABLE'} User Account Control. "
                    + (
                        "Disabling UAC means any process can silently gain admin rights with no prompt - "
                        "a significant reduction in this machine's security. "
                        if not enabled
                        else ""
                    )
                    + "Requires a restart to take effect."
                ),
            }
        script = (
            f'Set-ItemProperty -Path "Registry::{self._KEY}" -Name EnableLUA '
            f"-Value {1 if enabled else 0} -Type DWord"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to set EnableLUA.")}
        return {"success": True, "uac_enabled": enabled, "note": "Restart required to take effect."}
