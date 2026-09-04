"""
SSH client
==========
Wrapper around `paramiko` for remote administration tasks the user asks
Ultron to do on a machine they control (e.g. "SSH into my home server
and check disk space", "restart the service on my Pi"). Supports both
password and key-file auth, plus SFTP upload/download.

Host key verification is ON by default (uses the system's known_hosts,
same as the `ssh` CLI) - connect() only auto-trusts an unknown host if
the caller explicitly passes trust_unknown_hosts=True, since silently
accepting any host key defeats the point of host verification (classic
MITM exposure). Only set that for a first connection to a host you
control, the same way you'd verify a fingerprint once with plain ssh.
"""

from pathlib import Path
from typing import Dict, Optional

try:
    import paramiko

    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False


class SSHClient:
    """Connect to a remote host over SSH and run commands / transfer files."""

    def __init__(self):
        self._client: Optional["paramiko.SSHClient"] = None
        self._sftp = None
        self.connected_host: Optional[str] = None

    def connect(
        self,
        hostname: str,
        username: str,
        password: Optional[str] = None,
        key_filename: Optional[str] = None,
        port: int = 22,
        trust_unknown_hosts: bool = False,
        timeout: int = 10,
    ) -> Dict:
        """Open an SSH connection. Provide either `password` or `key_filename`
        (not both required - key auth is preferred when available)."""
        if not HAS_PARAMIKO:
            return {"error": "The 'paramiko' package is required. Install it with: pip install paramiko"}
        if not password and not key_filename:
            return {"error": "Provide either password or key_filename"}

        try:
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(
                paramiko.AutoAddPolicy() if trust_unknown_hosts else paramiko.RejectPolicy()
            )

            client.connect(
                hostname=hostname,
                port=port,
                username=username,
                password=password,
                key_filename=key_filename,
                timeout=timeout,
            )
            self._client = client
            self.connected_host = hostname
            return {"success": True, "host": hostname}
        except paramiko.SSHException as e:
            return {"error": f"SSH error: {e}"}
        except Exception as e:
            return {"error": str(e)}

    def run_command(self, command: str, timeout: int = 30) -> Dict:
        """Run a command on the remote host and return stdout/stderr/exit code."""
        if not self._client:
            return {"error": "Not connected - call connect() first"}
        try:
            stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            return {
                "success": exit_code == 0,
                "exit_code": exit_code,
                "stdout": stdout.read().decode("utf-8", errors="replace"),
                "stderr": stderr.read().decode("utf-8", errors="replace"),
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_sftp(self):
        if self._sftp is None:
            self._sftp = self._client.open_sftp()
        return self._sftp

    def upload_file(self, local_path: str, remote_path: str) -> Dict:
        if not self._client:
            return {"error": "Not connected - call connect() first"}
        try:
            local = Path(local_path)
            if not local.exists():
                return {"error": f"Local file not found: {local_path}"}
            self._get_sftp().put(str(local), remote_path)
            return {"success": True, "local_path": local_path, "remote_path": remote_path}
        except Exception as e:
            return {"error": str(e)}

    def download_file(self, remote_path: str, local_path: str) -> Dict:
        if not self._client:
            return {"error": "Not connected - call connect() first"}
        try:
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            self._get_sftp().get(remote_path, local_path)
            return {"success": True, "remote_path": remote_path, "local_path": local_path}
        except Exception as e:
            return {"error": str(e)}

    def is_connected(self) -> bool:
        return (
            self._client is not None
            and self._client.get_transport() is not None
            and self._client.get_transport().is_active()
        )

    def close(self) -> Dict:
        try:
            if self._sftp:
                self._sftp.close()
                self._sftp = None
            if self._client:
                self._client.close()
                self._client = None
            self.connected_host = None
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
