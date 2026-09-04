"""system_control.files
========================
File-level control surface: at-rest encryption, NTFS permissions/ACLs,
native SMB network sharing, folder sync (robocopy-driven), and
backup/recovery for arbitrary user-chosen files and folders.

Not to be confused with the top-level files/ package (files/manager,
files/pdf, files/office, files/compression, files/search - imported by
windows/__init__.py), which is ULTRON's everyday file-operations layer
(open/move/convert/search files). This subpackage is the deeper,
often-destructive control surface: changing who can access a file,
whether it's encrypted, whether it's shared on the network, and how
it's backed up/restored - same "deep OS control" tier as
system_control/system_config/* and system_control/process/*.

Same conventions as the rest of system_control/*:
  - Every public method returns a plain Dict - never raises.
  - Anything that changes state is confirm-gated: first call
    (confirm=False, default) returns a preview; the caller repeats with
    confirm=True to apply.
  - Methods that need elevated rights are documented as needing admin,
    with an admin hint surfaced on access-denied errors.

Lazily imported by ai/file_control_tools.py - importing this package
itself does no I/O.
"""

from system_control.files.encryption import FileEncryption
from system_control.files.permissions import FilePermissions
from system_control.files.sharing import FileSharing
from system_control.files.sync import FileSync
from system_control.files.backup import FileBackup
from system_control.files.recovery import FileRecovery

__all__ = [
    "FileEncryption",
    "FilePermissions",
    "FileSharing",
    "FileSync",
    "FileBackup",
    "FileRecovery",
]
