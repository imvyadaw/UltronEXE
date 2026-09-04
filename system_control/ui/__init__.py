"""system_control/ui - Windows OS shell-appearance and shell-layout
control: light/dark theme mode, accent color, taskbar layout/behavior,
Start menu content/pinning, desktop icons, fonts/text rendering,
per-monitor resolution/scaling/arrangement/sound device selection,
mouse cursor scheme/speed/accessibility appearance, lock screen
background/auto-lock timing, notification settings/Focus Assist, and
the Windows 11 Widgets board (registry + shell-API/PowerShell/ctypes
backed). Distinct from the top-level ui/ package, which is ULTRON's
OWN orb/overlay/dashboard/tray interface, not the Windows shell -
these classes control how the operating system's desktop looks and
behaves, not Ultron itself.

display_resolution.py/display_scaling.py/multi_display.py extend
(don't replace) windows/display/monitor.py's DisplayMonitor: that
module is primary-display-only (screenshots, sleep, brightness,
combined-geometry list_monitors); these three add per-MONITOR
resolution/refresh-rate control by device name, DPI/text scaling, and
multi-monitor mode/primary-display/arrangement. sound_manager.py
extends (doesn't replace) windows/audio/volume.py's VolumeControl:
that module is master-volume/mute only; this adds device
selection (playback/recording) and the per-app Volume Mixer.
"""
