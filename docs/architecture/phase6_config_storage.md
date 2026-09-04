# Phase 6: config and storage

## config/

Layered YAML config: `default.yaml` holds every key at its baseline
value; `development.yaml` and `production.yaml` only list what they
override. A loader would apply them in that order (default -> env ->
secrets) - see the note below on what exists today vs. what's still
manual.

New in this phase: `security:`, `networking:`, and `monitoring:`
sections mirroring the constants currently hardcoded in Phase 5's
modules (`security/authentication.py`'s `DEFAULT_SESSION_TTL_SECONDS`,
`networking/http_client.py`'s retry/timeout defaults,
`monitoring/health_check.py`'s warning thresholds, etc.) so those
values are documented and environment-tunable in one place instead of
buried in each module.

**Not yet wired in:** as with Phase 5's yaml files, there is no
`core/config_loader.py` yet actually reading these - the modules still
use their own hardcoded defaults (e.g. `AuthManager`'s
`DEFAULT_SESSION_TTL_SECONDS = 15 * 60`). Treat `config/*.yaml` as the
documented target values; wiring a loader that merges
default -> environment -> `config/secrets.yaml` and passes the results
into each module's `__init__` is the natural next step.

`config/secrets.yaml.template` - copy to `config/secrets.yaml` (git-ignored)
for real values. Phase 5's vault/auth don't need static secrets here
(the passphrase is set at runtime via `security.authentication.AuthManager.set_passphrase()`,
never stored in a config file) - this template stays focused on
external-service credentials (Groq, Telegram, etc.).

## storage/

Three plain data directories, each with a README explaining what does
and doesn't belong there:

- `storage/backups/` - manual point-in-time snapshots of the SQLite
  databases (including the Phase 5 `security/vault.db` and
  `security/audit_log.db`). Explicitly does NOT include
  `storage/secure/` (the encryption key + auth salt) - that needs its
  own, more careful backup process, since losing it makes vault.db
  unreadable even with vault.db itself backed up.
- `storage/exports/` - user-facing output files.
- `storage/temp/` - scratch space, safe to clear anytime.

None of these are created or written to automatically yet by any
Phase 5/6 module - `.gitkeep` placeholders keep the empty directories
present in version control until something does.
