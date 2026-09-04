"""Airplane Mode Manager
=========================
Windows has no documented CLI/registry flag that flips the single
"Airplane mode" toggle atomically - the actual OS mechanism is the
WinRT Windows.Devices.Radios API, which the Settings toggle itself
calls to switch every radio (Wi-Fi, Bluetooth, cellular) at once.
This module reproduces that behaviour from PowerShell via the same
WinRT projection, rather than guessing at an undocumented registry
key - keeps this correct across Windows versions instead of silently
breaking on the next feature update.

Distinct from wifi_manager.set_wifi_enabled/bluetooth_manager.
set_radio_enabled, which flip a single radio - this flips all radios
Windows knows about in one call, matching what the physical toggle
(or Fn-key) does.

get_status() is a plain read. set_enabled() is confirm-gated since it
can drop every wireless connection (Wi-Fi, Bluetooth, mobile) at once.
"""

import subprocess
from typing import Dict

_PS_RADIO_STATE_TEMPLATE = """
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetGenericArguments().Count -eq 1
}})[0]
Function Await($WinRtTask, $ResultType) {{
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}}
[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
$access = Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus])
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
{action}
"""

_ACTION_LIST = '$radios | ForEach-Object { "$($_.Name)|$($_.Kind)|$($_.State)" }'

_ACTION_SET = (
    "foreach ($r in $radios) {{ Await ($r.SetStateAsync({state})) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null }}\n"
    '$radios | ForEach-Object {{ "$($_.Name)|$($_.Kind)|$($_.State)" }}'
)


class AirplaneMode:
    """Read and toggle Windows airplane mode via the Windows.Devices.Radios WinRT API."""

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
        if err and ("denied" in err.lower() or "access" in err.lower() and "radio" in err.lower()):
            return err + " - radio access may need to be allowed in Settings > Privacy > Radios."
        return err

    def _parse_radios(self, stdout: str) -> list:
        radios = []
        for line in stdout.splitlines():
            parts = line.strip().split("|")
            if len(parts) == 3:
                radios.append({"name": parts[0], "kind": parts[1], "state": parts[2]})
        return radios

    def get_status(self) -> Dict:
        """List every radio Windows knows about and its state (On/Off/Disabled),
        and report whether the machine is effectively in airplane mode
        (all radios Off)."""
        script = _PS_RADIO_STATE_TEMPLATE.format(action=_ACTION_LIST)
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "PowerShell radio query failed")}
        radios = self._parse_radios(result["stdout"])
        if not radios:
            return {"error": "No radios reported by Windows."}
        airplane_mode_on = all(r["state"] != "On" for r in radios)
        return {"radios": radios, "airplane_mode_on": airplane_mode_on}

    def set_enabled(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn airplane mode on (all radios Off) or off (all radios On).
        Confirm-gated - this can drop Wi-Fi, Bluetooth, and mobile connections
        simultaneously."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    "This will turn ON airplane mode - Wi-Fi, Bluetooth, and any "
                    "mobile radio will all be switched off."
                    if enabled
                    else "This will turn OFF airplane mode - Wi-Fi, Bluetooth, and any "
                    "mobile radio will all be switched back on."
                ),
            }
        # enabled=True (airplane mode ON) means radios go Off (state value 1);
        # enabled=False (airplane mode OFF) means radios go On (state value 2).
        state_value = (
            "([Windows.Devices.Radios.RadioState]::Off)" if enabled else "([Windows.Devices.Radios.RadioState]::On)"
        )
        script = _PS_RADIO_STATE_TEMPLATE.format(action=_ACTION_SET.format(state=state_value))
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Setting radio state failed")}
        radios = self._parse_radios(result["stdout"])
        return {"success": True, "airplane_mode_on": enabled, "radios": radios}
