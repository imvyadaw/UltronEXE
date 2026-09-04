# storage/backups/

Snapshot copies of Ultron's SQLite databases (memory/, ai few-shot store,
security/vault.db, security/audit_log.db, etc.) for point-in-time
recovery. Not auto-populated by any module yet - back up storage/sqlite/*.db
here before risky migrations or upgrades.

Note: storage/secure/ (the encryption key + auth salt) is NOT meant to
live here - back that up separately and more carefully, since losing it
makes storage/sqlite/vault.db unreadable even if vault.db itself is backed up.

Safe to delete individual backup files; nothing reads from this folder
automatically.
