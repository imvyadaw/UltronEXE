# PHASE 17.8 — PLATFORM — build notes

All 12 files from your tree got built, exactly as named. This phase
has two independent halves - CROSS_DEVICE and SKILL_CREATOR - that
don't depend on each other; use either without the other.

## Install

```bash
pip install psutil websockets requests pyyaml
```

`pyyaml` is only needed if you feed `api_doc_reader` a YAML OpenAPI
spec instead of JSON. Everything else is standard library.

## CROSS_DEVICE

```
DeviceManager.start_pairing() ──► code shown/scanned on new device
        │
        ▼
DeviceManager.pair(code, name) ──► Device(id, token) minted
        │
        ▼
CompanionWebSocketServer  ◄──────────────────────────────┐
        │  (device connects, sends {device_id, token})   │
        ▼                                                 │
  .on_message(handler) fan-out to:                        │
    - NotificationRouter.route(...)  ──► .send_fn ─────────┘
    - UniversalClipboard.handle_incoming(...)
    - RemoteController.handle_incoming(...)

CompanionAPI  (plain HTTP, localhost)
    - /status, /pair/start, /pair/confirm, /devices/<id>/commands
```

A device only exists in `DeviceManager` after it completes the
two-step pairing handshake - nothing auto-discovers or auto-trusts
anything on the network. `RemoteController` additionally requires a
device be explicitly `grant()`-ed each command name it's allowed to
invoke; there's no generic "run this" command, only whatever you
`register_command()` yourself, same pattern as Phase 17.7's
`auto_recovery.py`.

`websocket_server.py` and `companion_api.py` both default to binding
`127.0.0.1` only. Change `host` only if you understand you're
exposing this to your LAN, and pair it with a firewall rule.

### Wiring in

1. Start `CompanionWebSocketServer` and `CompanionAPI` at boot.
2. Register `notification_router.route`, `universal_clipboard.handle_incoming`,
   and `remote_controller.handle_incoming` as message handlers.
3. Register whatever remote commands you actually want exposed
   (`remote_controller.register_command(...)`), then `grant()` them
   per device as you choose.
4. Whatever your assistant currently does to notify you (TTS, a
   toast, a log line) can now also go through
   `NotificationRouter.route(Notification(...))`.

## SKILL_CREATOR

```
APIDocReader.read_openapi()/.read_markdown()  ──► List[APIEndpoint]
        │
        ▼
SkillCodeGenerator.generate(SkillSpec)  ──► scaffold source (string)
        │
        ▼
SandboxTester.run(source, test_snippet)  ──► SandboxResult (import/crash/hang check)
        │
        ▼
SkillValidator.validate(source)  ──► ValidationReport (CRITICAL / WARNING findings)
        │
        ▼
AutoDeployer.deploy(name, version, source)  ──► writes to skills/ (only if clean)
        │
        ▼
SkillMarketplace.publish() / .install()  (local catalog, checksum-verified,
                                           still routes through AutoDeployer)
```

This pipeline is built so **no stage can be skipped from below it**:
`AutoDeployer.deploy()` always calls the validator itself, and
`SkillMarketplace.install()` always calls the deployer - there's no
shortcut that writes a skill to disk without going through
validation first.

A few things worth calling out explicitly, same spirit as the two
callouts in the 17.7 README:

- **`skill_code_generator.py`** produces template-shaped scaffolds
  (one method per REST endpoint, auth read from an env var you name)
  - not free-form code synthesis. Anything a template can't safely
  express is left as a `# TODO(human):` marker rather than guessed at.
- **`sandbox_tester.py`** is process isolation (timeout, memory/CPU/fd
  limits via `resource` where available), not a security boundary
  against genuinely adversarial code. It catches ordinary bugs -
  infinite loops, crashes, runaway memory - before a human and the
  validator look at it. Don't run anything through it you wouldn't
  also read first.
- **`skill_validator.py`** blocks `eval`/`exec`/`compile`, `os.system`,
  `shell=True` subprocess calls outright (CRITICAL, no override), and
  flags things like `subprocess.run`, `shutil.rmtree`, or unexpected
  network imports as WARNING - those need you to explicitly
  acknowledge them by name before `auto_deployer` will proceed.
- **`auto_deployer.py`** archives the previous version of a skill
  before overwriting it, so `rollback()` always has somewhere to go.
- **`skill_marketplace.py`** never fetches or auto-installs anything.
  `publish()` only writes to your own local catalog; installing
  something (yours or someone else's) always re-checks its SHA-256
  against the catalog entry and still runs the full validator via
  `AutoDeployer` - a good checksum only proves the file wasn't
  corrupted or swapped, not that the code is safe.

### Wiring in

1. Point `APIDocReader` at a spec file you already have locally (or
   your own markdown notes on an API) to get `APIEndpoint`s.
2. Build a `SkillSpec` and run it through `SkillCodeGenerator`.
3. Fill in the `TODO(human)` markers in the generated scaffold - the
   generator won't guess at side-effecting behavior for you.
4. `SandboxTester.run()` it, then `SkillValidator.validate()` it (or
   just call `AutoDeployer.dry_run()`, which does the same
   validation without writing anything).
5. `AutoDeployer.deploy()` once you're satisfied - this is the only
   step that touches your live `skills/` directory.
6. Optionally `SkillMarketplace.publish()` it to your own local
   catalog so other machines/instances you run can `install()` it
   later, checksum-verified.

All storage is local JSON/files under `ultron_data/` by default,
same as every earlier phase - no network calls, no telemetry, no
skill installs or deploys happen without an explicit call from you
or code you wrote.
