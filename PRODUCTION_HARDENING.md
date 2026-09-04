# ULTRON 5.0 — Production Hardening Pass

This build applies a first production-hardening pass without rewriting the existing architecture.

## Applied changes

- Removed the distributable `.env` file containing credentials.
- Added `.env.example` with empty secret placeholders.
- Added credential/key/runtime-artifact exclusions to `.gitignore`.
- Removed the checked-in local encryption key from the distributable tree.
- Added Flask to the main runtime dependency set because the shipped dashboard/mobile API are first-class features.
- Kept the mobile API dependency explicit in the main runtime requirements and hardened its request boundary.
- Changed mobile API authentication to fail closed by default. `ULTRON_MOBILE_API_AUTH_REQUIRED=true` is the secure default; a missing key returns configuration error instead of exposing an open API.
- Replaced the duplicate root `verification_engine` implementation with compatibility wrappers pointing to the canonical `hardening.verification_engine` implementation.
- Added automatic credential redaction to the central logger.
- Updated stale vision-loader unit expectations to match the real implemented error contract.
- Added regression tests for the production-hardening changes, including release-artifact checks and mobile API boundary checks.

## Verification performed

- Python bytecode compilation completed successfully for the modified modules.
- Core/phase test suite: **119 passed, 1 skipped** in the isolated environment used for this pass.
- The complete UI test collection requires Flask; the build now declares Flask in `requirements.txt`, but the sandbox used for this audit has no network access to install missing third-party packages.

## Important deployment action

Any credentials that were present in the original `.env` must be considered exposed and should be rotated before the hardened build is used outside the local machine.

## Release candidate follow-up

- Restored the missing `storage/cache/usage_tracker.py` required by the cloud-model and tool-runtime paths.
- Mobile API API-key comparison uses constant-time comparison and rejects oversized request bodies.
- Runtime databases, logs, bytecode, caches, and local secrets are excluded from the final distributable.

A production claim remains evidence-based: deployment-specific load, restore, rollback, monitoring, and infrastructure checks must be executed in the target environment before go-live.
