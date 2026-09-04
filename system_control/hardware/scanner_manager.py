"""Scanner Manager
=================
Windows scanner (WIA - Windows Image Acquisition) management -
enumeration, status, and scan-to-file, via the pywin32 WIA COM
automation interface (win32com.client, the same wia.DeviceManager
apps like Windows Fax and Scan use under the hood). No other module
in the codebase touches scanning; this is new coverage.

WIA COM automation needs the optional pywin32 package - unlike
core dependencies elsewhere in system_control/*, this degrades to a
clear {"error": ...} explaining that rather than raising when it's
missing, same policy as media_control.py's now-playing info needing
winsdk. Device enumeration falls back to a plain PnP device list
(Get-PnpDevice -Class Image) when pywin32 isn't available, so at least
"is a scanner attached" still works without the extra dependency.

open_scan_app() launches the legacy Windows Fax and Scan app (wfs.exe,
still shipped on current Windows) as the reliable manual fallback -
same role as default_apps.py's open_default_apps_settings() when a
scripted path can't or shouldn't be trusted to just work.

scan_document() is confirm-gated: it can overwrite an existing file at
output_path and physically operates hardware (lid/feeder) that may
take real time.
"""

import os
import subprocess
from typing import Dict

try:
    import win32com.client

    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False

_WIA_FORMATS = {
    "png": "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}",
    "jpg": "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}",
    "bmp": "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}",
    "tiff": "{B96B3CB1-0728-11D3-9D7B-0000F81EF32E}",
}


class ScannerManager:
    """Enumerate scanners and scan to a file via WIA COM automation,
    with a PnP-only fallback for listing and a manual-app fallback for
    scanning when pywin32 isn't installed."""

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

    def list_scanners(self) -> Dict:
        """All currently-attached scanner devices. Uses WIA
        DeviceManager when pywin32 is available (gives WIA device IDs
        usable with scan_document()); otherwise falls back to a plain
        PnP imaging-device list (identification only, not directly
        usable for scanning)."""
        if HAS_PYWIN32:
            try:
                manager = win32com.client.Dispatch("WIA.DeviceManager")
                scanners = []
                for i in range(1, manager.DeviceInfos.Count + 1):
                    info = manager.DeviceInfos.Item(i)
                    if info.Type == 1:  # WiaDeviceType.ScannerDeviceType
                        scanners.append({"device_id": info.DeviceID, "name": info.Properties("Name").Value})
                return {"success": True, "source": "wia", "scanners": scanners, "count": len(scanners)}
            except Exception as e:
                return {"error": f"WIA enumeration failed: {e}"}

        result = self._run_ps(
            "Get-PnpDevice -Class Image -ErrorAction SilentlyContinue | "
            "Select-Object FriendlyName, InstanceId, Status | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-PnpDevice failed"}
        if not result["stdout"]:
            return {
                "success": True,
                "source": "pnp",
                "scanners": [],
                "count": 0,
                "note": "pywin32 not installed - this is a PnP-only listing; install pywin32 to enable scan_document().",
            }
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse device list"}
        devices = data if isinstance(data, list) else [data]
        return {
            "success": True,
            "source": "pnp",
            "scanners": devices,
            "count": len(devices),
            "note": "pywin32 not installed - this is a PnP-only listing; install pywin32 to enable scan_document().",
        }

    def get_scanner_status(self, device_id: str) -> Dict:
        """Whether a given WIA device_id (from list_scanners) is
        currently reachable/ready. Needs pywin32."""
        if not HAS_PYWIN32:
            return {"error": "pywin32 not installed - run: pip install pywin32"}
        if not device_id:
            return {"error": "device_id must be non-empty"}
        try:
            manager = win32com.client.Dispatch("WIA.DeviceManager")
            for i in range(1, manager.DeviceInfos.Count + 1):
                info = manager.DeviceInfos.Item(i)
                if info.DeviceID == device_id:
                    return {"success": True, "device_id": device_id, "ready": True}
            return {"error": f"No scanner found with device_id '{device_id}' - it may be disconnected."}
        except Exception as e:
            return {"error": str(e)}

    def scan_document(self, device_id: str, output_path: str, image_format: str = "png", confirm: bool = False) -> Dict:
        """Scan one page from the given scanner (device_id from
        list_scanners) to output_path in the given format ('png',
        'jpg', 'bmp', or 'tiff'). Confirm-gated - overwrites an
        existing file at output_path and operates physical hardware
        that takes real time to complete. Needs pywin32."""
        if not HAS_PYWIN32:
            return {
                "error": "pywin32 not installed - run: pip install pywin32. "
                "As a fallback, use open_scan_app() to scan manually."
            }
        if not device_id or not output_path:
            return {"error": "device_id and output_path must both be non-empty"}
        fmt = image_format.lower()
        if fmt not in _WIA_FORMATS:
            return {"error": f"Unknown image_format '{image_format}'. Valid: {sorted(_WIA_FORMATS.keys())}"}
        if not confirm:
            overwrite_note = " (this will overwrite an existing file)" if os.path.exists(output_path) else ""
            return {
                "requires_confirmation": True,
                "preview": f"This will scan a page from device '{device_id}' to '{output_path}'{overwrite_note}. "
                f"The scanner will physically activate and this may take several seconds.",
            }
        try:
            manager = win32com.client.Dispatch("WIA.DeviceManager")
            device = None
            for i in range(1, manager.DeviceInfos.Count + 1):
                info = manager.DeviceInfos.Item(i)
                if info.DeviceID == device_id:
                    device = info.Connect()
                    break
            if device is None:
                return {"error": f"No scanner found with device_id '{device_id}' - it may be disconnected."}
            item = device.Items.Item(1)
            image = item.Transfer(_WIA_FORMATS[fmt])
            if os.path.exists(output_path):
                os.remove(output_path)
            image.SaveFile(output_path)
            return {"success": True, "device_id": device_id, "output_path": output_path, "format": fmt}
        except Exception as e:
            return {"error": f"Scan failed: {e}"}

    def open_scan_app(self) -> Dict:
        """Launch the built-in Windows Fax and Scan app (wfs.exe) for
        manual scanning - the reliable fallback when pywin32 isn't
        installed, or when the user just wants to drive the scan
        themselves (multi-page documents, custom DPI/color settings,
        etc. that this module's single-page scan_document() doesn't
        expose)."""
        try:
            subprocess.Popen(["wfs.exe"])
            return {"success": True, "opened": "Windows Fax and Scan"}
        except FileNotFoundError:
            return {
                "error": "wfs.exe not found - Windows Fax and Scan may not be installed on this edition of Windows."
            }
        except Exception as e:
            return {"error": str(e)}
