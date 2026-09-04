"""system_control/applications
==============================
Installed-application lifecycle, one layer above system_control/files/
and system_control/storage/ (which operate on the filesystem/disks
generically) - this package is specifically about *named applications*
as units: what's installed, adding/removing them, keeping them
current, their per-app compatibility toggles, and their user
data/cache footprint.

- package_manager.py - discovering installed Win32/UWP packages and
  searching/installing new ones via winget.
- app_uninstaller.py - removing Win32 apps (winget or registry
  UninstallString) and UWP packages (Remove-AppxPackage), plus
  leftover scanning/cleanup.
- app_updater.py - checking for and applying updates to already-
  installed packages via `winget upgrade`.
- app_settings.py - per-app compatibility flags (run as administrator),
  execution alias enable/disable, and UWP app reset.
- app_data_backup.py - discovering and archiving an app's AppData
  folders for backup/restore/migration.
- app_cache.py - finding and clearing an app's disposable cache/temp
  folders, plus Microsoft Store cache reset.
- default_apps.py - the whole default-app association profile as a
  unit (DISM export/import), plus reading the current default for a
  handful of common classes (browser, mail).
- app_permissions.py - per-user app-execution allow/blocklist
  (DisallowRun) - whether a program is permitted to launch at all.
- browser_control.py - installed-browser discovery and category-wide
  bulk actions (close all, clear all Chromium caches).
- office_control.py - Office Click-to-Run install info, update
  channel, and bulk close across every Office app.
- media_control.py - OS-wide media-key control (play/pause/skip/
  volume) of whichever app owns the current media session.
- communication_control.py - installed messaging/calling app
  discovery, startup-launch status, and bulk close.
- development_control.py - dev-tool discovery, dev-focused
  environment/git-config reads, Windows Developer Mode, WSL
  management, and bulk close across known dev tools.

Distinct from system_control/files/file_associations.py (a single
file-type/protocol mapping at a time, not the whole default-app
profile) and from system_control/security/app_permissions.py (per-app
privacy *capability* grants like camera/microphone - this package's
own app_permissions.py is execution allow/block, a different axis
entirely; see that file's docstring). Windows Update and OS/driver-
level updates remain in system_control/system_config/
windows_update.py; this package's own update tooling only tracks
winget-known application versions and the Office update channel.

Every module here that duplicates a per-instance automation surface
already in the top-level apps/ package (browsers, office, media,
communication) is deliberately scoped to category-wide/OS-level
concerns instead (install discovery, defaults, bulk process actions) -
see each module's own docstring for the exact boundary.
"""
