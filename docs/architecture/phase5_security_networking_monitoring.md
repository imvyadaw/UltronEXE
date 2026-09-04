# Phase 5: security, networking, monitoring

## security/

Layered, each depending only on the ones before it:

1. `encryption_keys.py` - generates/persists the Fernet key + auth salt under `storage/secure/` (owner-only file permissions where the OS supports it).
2. `encryption.py` - encrypt/decrypt strings and bytes using that key. Optional dependency: `cryptography` (raises a clear error at call time if missing, not import time).
3. `authentication.py` - local passphrase gate. Stores a PBKDF2-HMAC-SHA256 hash (never the passphrase itself) in `storage/sqlite/auth.db`, and tracks a short-lived (15 min default) unlock session.
4. `audit.py` - append-only log of security events in `storage/sqlite/audit_log.db`. No update/delete method by design.
5. `vault.py` - the module everything else should actually call: encrypted secret storage gated by `authentication.py`, logged via `audit.py`.

Typical flow:
```python
from security.authentication import get_auth_manager
from security.vault import get_vault

auth = get_auth_manager()
if not auth.is_configured():
    auth.set_passphrase("some passphrase")
auth.verify("some passphrase")          # unlocks a session

vault = get_vault()
vault.store("home_wifi_password", "...")
vault.retrieve("home_wifi_password")
```

**Not yet wired in:** nothing in `core/executor.py` or `ai/tools_schema.py`
exposes vault/auth as assistant-callable tools yet - today these are
importable modules only. Adding `vault_store` / `vault_retrieve` /
`vault_unlock` tool definitions (following the existing pattern in
`ai/tools_schema.py` + `core/executor.py`'s `tool_map`) is the natural
next step once there's a UI/voice flow for entering a passphrase.

**Operational note:** `storage/secure/` (the key + salt) and
`config/secrets.yaml` (if that loader ever lands, see the earlier config
doc) should be added to `.gitignore` - there wasn't one in this repo yet
to append to.

## networking/

Four independent clients, no shared base class - each wraps a different
underlying library and none depend on the others:

| Module | Library | Notes |
|---|---|---|
| `http_client.py` | `requests` (already a hard dependency) | Retries transient 5xx/429/408, no extra install needed |
| `websocket.py` | `websocket-client` (optional) | Background-threaded, callback-based |
| `ssh_client.py` | `paramiko` (optional) | Host key verification ON by default - `trust_unknown_hosts=True` required to auto-accept an unseen host |
| `ftp_client.py` | stdlib `ftplib` | FTPS (`use_tls=True`) by default; plain FTP sends credentials in cleartext |

## monitoring/

- `performance.py` - named timing samples (`with tracker.track("label"): ...`), summarized as avg/min/max/p95. Pure stdlib, no dependency on the others.
- `resource_monitor.py` - CPU/RAM/disk snapshots via `psutil` (already required project-wide). Keeps a rolling in-memory history.
- `health_check.py` - aggregates internet reachability (`core/internet_monitor.py`), resource pressure (`resource_monitor.py`), and storage writability into one `healthy: bool` + per-check detail.
- `alerts.py` - threshold rules (`AlertRule`) evaluated against `resource_monitor.py` snapshots, with a per-rule cooldown to avoid notification storms. Fires via the existing `windows/notifications/notifications.py` toast, and logs to `security/audit.py` if available.

None of `monitoring/` is scheduled to run automatically yet - `core/scheduler.py`
is the natural place to register a periodic `get_alert_manager().check_now()`
call once that's wanted.
