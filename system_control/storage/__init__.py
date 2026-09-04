"""system_control/storage
=========================
Disk/partition/volume-level storage control:

- partition_manager.py - disks, partitions, resizing, drive letters,
  creating/deleting partitions, disk initialization.
- format_manager.py - formatting, filesystem conversion, volume
  labels, chkdsk.
- storage_sense.py - Windows' automatic disk cleanup policy (temp
  files, Recycle Bin, Downloads, cloud-only files).
- cloud_sync.py - OneDrive/Google Drive/Dropbox client status and
  pause/resume.
- disk_quota.py - NTFS per-user disk quotas via fsutil.
- raid_manager.py - Storage Spaces pools and virtual disks (software
  RAID equivalent).
- iso_vhd_mount.py - mounting/dismounting/creating ISO and VHD/VHDX
  disk images.
- usb_eject.py - listing and safely ejecting removable USB drives.

partition_manager.py, format_manager.py, raid_manager.py, and
iso_vhd_mount.py wrap the Windows Storage PowerShell module (Get-Disk/
Get-Partition/Get-Volume/Get-StoragePool/Mount-DiskImage/etc.);
disk_quota.py wraps `fsutil quota`; usb_eject.py uses the Shell.
Application COM eject verb; storage_sense.py and cloud_sync.py operate
at the registry/process level since neither exposes a first-class
PowerShell cmdlet surface.

Distinct from top-level storage/ (ULTRON's OWN data - cache, logs,
its sqlite/chroma stores - not the Windows disk subsystem) and from
system_control/files/ (file/folder-level operations - permissions,
sharing, encryption, backup - once a filesystem already exists on top
of a volume; this package operates one layer below, on the disks and
volumes themselves).
"""
