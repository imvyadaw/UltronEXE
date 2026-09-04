"""system_control.hardware
==========================
Physical-component control: CPU power/performance state, RAM
diagnostics and memory-pressure relief, GPU info and performance
mode, thermal/fan policy, USB power/policy management, and the
human-input/AV peripherals - camera, microphone, speakers, keyboard,
mouse, and touchpad (device enable/disable, per-device state, and the
input-behavior settings not already owned by cursor_manager.py,
sound_manager.py, accessibility.py, or the automation/* input-
simulation modules).

Distinct from system_control/process/background_apps.py (which already
owns "list/sort/kill running processes" - modules here do not
duplicate that; cpu_control.py's process-level methods are limited to
priority/affinity, which background_apps.py doesn't cover) and from
system_control/system_config/device_manager.py (generic PnP device
enable/disable for *any* device class - usb_control.py builds on top
of that for USB-specific power/policy concerns instead of re-
implementing enable/disable).

Same conventions as the rest of system_control/*:
  - Every public method returns a plain Dict - never raises.
  - Anything that changes state is confirm-gated: first call
    (confirm=False, default) returns a preview; the caller repeats
    with confirm=True to apply.
  - Methods that touch HKLM, powercfg system-wide settings, or drivers
    are documented as needing admin, with an admin hint surfaced on
    access-denied errors.
  - Windows-only (PowerShell/WMI/powercfg-backed); methods return a
    clear {"error": ...} on non-Windows hosts rather than raising.

Lazily imported by callers - importing this package itself does no I/O.
"""

from system_control.hardware.cpu_control import CPUControl
from system_control.hardware.ram_optimizer import RAMOptimizer
from system_control.hardware.gpu_control import GPUControl
from system_control.hardware.fan_control import FanControl
from system_control.hardware.usb_control import USBControl
from system_control.hardware.camera_control import CameraControl
from system_control.hardware.microphone_control import MicrophoneControl
from system_control.hardware.speaker_control import SpeakerControl
from system_control.hardware.keyboard_control import KeyboardHardwareControl
from system_control.hardware.mouse_control import MouseHardwareControl
from system_control.hardware.touchpad_control import TouchpadControl
from system_control.hardware.printer_manager import PrinterManager
from system_control.hardware.scanner_manager import ScannerManager

__all__ = [
    "CPUControl",
    "RAMOptimizer",
    "GPUControl",
    "FanControl",
    "USBControl",
    "CameraControl",
    "MicrophoneControl",
    "SpeakerControl",
    "KeyboardHardwareControl",
    "MouseHardwareControl",
    "TouchpadControl",
    "PrinterManager",
    "ScannerManager",
]
