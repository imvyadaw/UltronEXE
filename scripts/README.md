# scripts/

Operational scripts. All run standalone (`python scripts/<name>.py`),
all accept `--root` to target a different checkout (mainly so
`testing/` can exercise them against a temp directory instead of the
real one), and all expose a `run(root=...)` function so tests import
and call them directly instead of shelling out.

- **setup.py** - first-run setup: creates `storage/`'s subdirectories
  (per `config/default.yaml`'s `storage:` block) and copies
  `config/secrets.yaml.template` -> `config/secrets.yaml` if missing.
  Idempotent, safe to re-run.
- **update.py** - `git pull` (skipped if the checkout isn't a git
  repo) then `pip install -r` every requirements file found
  (`requirements.txt` at root if present, `ui/requirements-ui.txt`).
- **backup.py** - snapshots every `*.db` file under `storage/` into
  `storage/backups/<UTC timestamp>/`, per
  `storage/backups/README.md`. Currently a no-op - no module in this
  checkout writes a `.db` file yet. Deliberately skips
  `storage/secure/`, same as the README specifies.
- **maintenance.py** - clears `storage/temp/` (per its README, safe
  to clear anytime) and prints a size summary of each `storage/`
  subdirectory so growth in `backups/`/`exports/` is easy to spot.
  Supports `--dry-run`.

None of these run automatically yet (no cron/scheduler wiring) - run
them by hand, or wire one into `monitoring/` or a scheduler later.
