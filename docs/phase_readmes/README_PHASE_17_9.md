# PHASE 17.9 — SECURITY — build notes

All 6 files from your tree got built, exactly as named.

## Install

```bash
pip install cryptography
```

Everything else (biometrics, intrusion detection, privacy filtering,
sandbox executor, audit logger) is pure standard library.

## What's protective vs. what's not

Worth being precise about, since "security module" invites reading
more into it than is there:

- **`behavior_biometrics.py`** stores only keystroke-interval timing
  statistics (mean/stdev in ms), never key identities or content - it
  can't reconstruct what you typed, only whether the *rhythm* still
  looks like you. It's a continuous secondary signal alongside real
  auth, not a replacement for it, and it only ever raises a
  `ProfileMismatch` for you to react to - it never locks anything out
  by itself.
- **`intrusion_detector.py`** only detects and reports. Its one piece
  of "enforcement" is a local, self-expiring `is_locked_out()`
  cooldown that other auth code can *choose* to consult - it doesn't
  block network traffic, ban IPs, or touch anything outside ULTRON's
  own process.
- **`secure_enclave.py`** is Fernet (AES + HMAC) encryption at rest
  for secrets, with the key file locked to owner-only permissions -
  not a hardware enclave. Losing the key file means losing the
  secrets; there's no recovery path, by design.
- **`privacy_filter.py`** is regex pattern-matching, not semantic
  understanding. It's a safety-net layer in front of logs/outbound
  text, meant to sit alongside - not replace - discipline like
  `secure_enclave` never logging values in the first place.
- **`sandbox_executor.py`** is an allowlist, not a sandbox in the
  container/VM sense: only executables you named in a `Policy` can
  run at all, arguments are always a list (never `shell=True`), and
  timeouts/resource limits cap what a permitted command can do once
  it starts. It complements, but is a different tool from,
  Phase 17.8's `SKILL_CREATOR.sandbox_tester` (which trial-runs
  generated *Python source*, not external commands).
- **`audit_logger.py`** is tamper-*evident* (a broken hash chain
  proves something changed) not tamper-*proof* (it doesn't stop
  someone with filesystem access from editing the file - just makes
  it detectable afterward).

## How the six pieces fit together

```
BehaviorBiometrics.check(sample)         ──► ProfileMismatch? ──┐
IntrusionDetector.record_event(...)      ──► IntrusionEvent?  ──┼──► your callback
  .is_locked_out(source) consulted by auth code before accepting─┘    (alert, re-auth,
                                                                        notify, etc.)
                                                                       │
                                                                       ▼
                                                        AuditLogger.record(...)
                                                        (append-only, hash-chained)

SecureEnclave.put()/.get()   ◄── secrets in, secrets out, encrypted at rest
PrivacyFilter.redact()        ◄── wrap around logging calls / outbound messages
SandboxExecutor.run(policy)   ◄── the only path for ULTRON to shell out to a real CLI
```

## Wiring into the rest of ULTRON

1. Enroll a typing profile during a period you're sure it's really
   you (`BehaviorBiometrics.enroll()` right after a real login), then
   call `.check()` periodically and route any `ProfileMismatch` to
   wherever you want a second factor prompted.
2. Define rules on `IntrusionDetector` for the events you actually
   care about (`device_manager.authenticate` failures,
   `remote_controller` "not granted" attempts, etc.), feed them via
   `record_event()`, and have `device_manager`/`companion_api`
   consult `is_locked_out()` before accepting new attempts from the
   same source.
3. Move any secret currently sitting in a plain env var or JSON file
   (API keys generated skills read, pairing-related secrets) into
   `SecureEnclave`.
4. Attach `PrivacyFilter.make_logging_filter()` to your root logger,
   or call `.redact()` explicitly before anything goes out via
   `notification_router` or a companion API response.
5. Route any place that currently shells out directly through a
   `SandboxExecutor` with an explicit `Policy` instead.
6. Call `AuditLogger.record()` from the other five whenever something
   security-relevant happens, and run `verify_integrity()` on a
   schedule (or at startup) to catch tampering early.

All storage is local (JSON, JSONL, or Fernet-encrypted blobs) under
`ultron_data/shield/` by default, same as every earlier phase - no
network calls, no telemetry.
