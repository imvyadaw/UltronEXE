"""
FTP client
==========
Wrapper around the standard-library `ftplib` for the (increasingly rare,
but still real - some NAS/router/legacy-server admin panels only expose
FTP) case of transferring files to/from an FTP or FTPS server. Prefer
networking/ssh_client.py's SFTP support for anything that supports it -
plain FTP sends credentials in cleartext unless FTPS (`use_tls=True`)
is used.
"""

import ftplib
from pathlib import Path
from typing import Dict, Optional


class FTPClient:
    """Connect to an FTP(S) server and transfer files / list directories."""

    def __init__(self):
        self._ftp: Optional[ftplib.FTP] = None
        self.connected_host: Optional[str] = None

    def connect(
        self,
        hostname: str,
        username: str = "anonymous",
        password: str = "",
        port: int = 21,
        use_tls: bool = True,
        timeout: int = 10,
    ) -> Dict:
        """Connect and log in. use_tls=True (default) uses FTPS - plain FTP
        sends the password in cleartext, so only set this False for a
        server you know doesn't support TLS."""
        try:
            ftp_cls = ftplib.FTP_TLS if use_tls else ftplib.FTP
            ftp = ftp_cls(timeout=timeout)
            ftp.connect(hostname, port)
            ftp.login(username, password)
            if use_tls:
                ftp.prot_p()  # secure the data channel too, not just login

            self._ftp = ftp
            self.connected_host = hostname
            return {"success": True, "host": hostname, "tls": use_tls}
        except ftplib.all_errors as e:
            return {"error": str(e)}

    def list_directory(self, remote_path: str = ".") -> Dict:
        if not self._ftp:
            return {"error": "Not connected - call connect() first"}
        try:
            entries = list(self._ftp.mlsd(remote_path))
            return {
                "path": remote_path,
                "entries": [{"name": name, "type": facts.get("type", "unknown")} for name, facts in entries],
            }
        except ftplib.all_errors:
            # Some servers don't support MLSD - fall back to plain NLST.
            try:
                names = self._ftp.nlst(remote_path)
                return {"path": remote_path, "entries": [{"name": n, "type": "unknown"} for n in names]}
            except ftplib.all_errors as e:
                return {"error": str(e)}

    def upload_file(self, local_path: str, remote_path: str) -> Dict:
        if not self._ftp:
            return {"error": "Not connected - call connect() first"}
        try:
            local = Path(local_path)
            if not local.exists():
                return {"error": f"Local file not found: {local_path}"}
            with open(local, "rb") as f:
                self._ftp.storbinary(f"STOR {remote_path}", f)
            return {"success": True, "local_path": local_path, "remote_path": remote_path}
        except ftplib.all_errors as e:
            return {"error": str(e)}

    def download_file(self, remote_path: str, local_path: str) -> Dict:
        if not self._ftp:
            return {"error": "Not connected - call connect() first"}
        try:
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as f:
                self._ftp.retrbinary(f"RETR {remote_path}", f.write)
            return {"success": True, "remote_path": remote_path, "local_path": local_path}
        except ftplib.all_errors as e:
            return {"error": str(e)}

    def delete_file(self, remote_path: str) -> Dict:
        if not self._ftp:
            return {"error": "Not connected - call connect() first"}
        try:
            self._ftp.delete(remote_path)
            return {"success": True, "deleted": remote_path}
        except ftplib.all_errors as e:
            return {"error": str(e)}

    def close(self) -> Dict:
        try:
            if self._ftp:
                self._ftp.quit()
                self._ftp = None
            self.connected_host = None
            return {"success": True}
        except Exception as e:
            # quit() can fail if the connection already dropped - force-close either way.
            try:
                if self._ftp:
                    self._ftp.close()
            finally:
                self._ftp = None
            return {"success": True, "note": f"connection force-closed after: {e}"}
