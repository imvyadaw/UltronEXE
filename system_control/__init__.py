"""system_control
================
Top-level package for deep Windows system-control modules:
system_config/ (registry, env vars, system properties, device manager,
Windows Update, System Restore, BIOS/UEFI), process/ (startup manager,
running/background processes, native Windows Task Scheduler), and
files/ (encryption, NTFS permissions, network sharing, folder sync,
backup/recovery), storage/ (disk/partition management, volume
formatting and filesystem control), applications/ (installed
application lifecycle: package discovery/install, uninstall, updates,
per-app compatibility settings, appdata backup, and cache cleanup),
hardware/ (CPU/RAM/GPU/fan/USB physical control, human-input/AV
peripherals - camera, microphone, speakers, keyboard, mouse,
touchpad - plus printer/scanner management), monitoring/ (deep
Windows-specific instrumentation: aggregated hardware temperatures,
Event Viewer, Reliability Monitor, and resmon.exe-style per-process
resource breakdowns - distinct from the top-level, cross-platform
monitoring/ package that watches ULTRON's own health), security/
(privacy, UAC, app permissions, certificates, BitLocker), network/
(bandwidth, firewall), and ui/ (sound, cursor) - more subpackages can
be added the same way later without touching existing ones.
"""
