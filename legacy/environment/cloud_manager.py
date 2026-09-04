"""Real credential-exposure check (no existing scanner elsewhere in ULTRON to
wrap, unlike device_manager/shutdown) - looks for the actual cloud-provider
env vars and default credential file locations, and flags a file as
exposed if it exists with world/group-readable permissions, instead of
returning a hardcoded False regardless of what's on disk."""

import os
import stat
from pathlib import Path

_CRED_ENV_VARS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AZURE_CLIENT_SECRET",
    "AZURE_CLIENT_ID",
)
_CRED_FILES = (
    Path.home() / ".aws" / "credentials",
    Path.home() / ".config" / "gcloud" / "application_default_credentials.json",
    Path.home() / ".azure" / "credentials",
)


class CloudManager:
    def status(self):
        env_present = [v for v in _CRED_ENV_VARS if os.environ.get(v)]
        exposed_files = []
        for f in _CRED_FILES:
            try:
                if f.exists():
                    mode = f.stat().st_mode
                    if mode & (stat.S_IRGRP | stat.S_IROTH):
                        exposed_files.append(str(f))
            except OSError:
                continue
        return {
            "credentials_in_env": env_present,
            "credential_files_world_or_group_readable": exposed_files,
            "credentials_exposed": bool(exposed_files),
        }
