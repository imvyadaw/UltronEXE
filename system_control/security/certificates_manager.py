"""Certificates Manager
========================
Windows Certificate Store inspection and management via PowerShell's
Cert: drive (equivalent to the certmgr.msc GUI) - list certs in a
store, inspect one by thumbprint, flag ones expiring soon, and
export/import/remove certificates. Distinct from
system_control/security/bitlocker_manager.py (volume encryption, not
PKI) and networking/ssh_client.py (SSH keys, a different credential
type entirely).

Deliberately public-certificate-only: export_certificate() writes a
.cer (DER, public key only) and there is no private-key export path
(no .pfx/.p12 support) - a private key is the actual secret behind a
certificate's identity, and giving an assistant a one-call way to
export it would let it silently clone that identity or defeat TLS/
code-signing trust elsewhere. Importing is limited to trusted root/
intermediate/publisher certs for the same reason working the other
direction (installing a *trusted* cert is how MITM proxies get set
up) - it is confirm-gated and needs admin for machine stores.

Listing/inspecting certs are plain reads. Export (of the public cert),
import, and removal are confirm-gated; import and removal from
machine-wide stores (LocalMachine) additionally need admin.
"""

import subprocess
from typing import Dict, Optional


class CertificatesManager:
    """Inspect and manage Windows certificate stores (public certs only)."""

    _VALID_STORES = {
        "my": "My",
        "root": "Root",
        "ca": "CA",
        "trustedpublisher": "TrustedPublisher",
        "disallowed": "Disallowed",
        "trustedpeople": "TrustedPeople",
    }
    _VALID_LOCATIONS = {"currentuser", "localmachine"}

    def _run_ps(self, script: str, timeout: float = 30.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "powershell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "elevat" in err.lower() or "access is denied" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def _resolve(self, store: str, location: str) -> Optional[str]:
        s = self._VALID_STORES.get(store.lower().replace(" ", ""))
        loc = location.lower().replace(" ", "")
        if not s or loc not in self._VALID_LOCATIONS:
            return None
        loc_name = "CurrentUser" if loc == "currentuser" else "LocalMachine"
        return f"Cert:\\{loc_name}\\{s}"

    def list_stores(self) -> Dict:
        """List the recognized store names and locations this module can
        target (e.g. store='root', location='currentuser')."""
        return {"stores": sorted(self._VALID_STORES.keys()), "locations": sorted(self._VALID_LOCATIONS)}

    def list_certificates(self, store: str = "my", location: str = "currentuser") -> Dict:
        """List certificates in a given store, with subject/issuer/
        thumbprint/expiry. No admin needed for CurrentUser stores; reading
        LocalMachine stores generally doesn't need admin either, only
        modifying them does."""
        path = self._resolve(store, location)
        if not path:
            return {"error": "Unknown store/location. Call list_stores() for valid values."}
        script = f"Get-ChildItem -Path '{path}' | Select-Object Subject, Issuer, Thumbprint, NotBefore, NotAfter, HasPrivateKey | ConvertTo-Json"
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not list certificates in {path}.")}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            if isinstance(data, dict):
                data = [data]
        except Exception:
            return {"error": "Could not parse certificate list.", "raw": result["stdout"]}
        certs = [
            {
                "subject": c.get("Subject"),
                "issuer": c.get("Issuer"),
                "thumbprint": c.get("Thumbprint"),
                "valid_from": c.get("NotBefore"),
                "valid_until": c.get("NotAfter"),
                "has_private_key": c.get("HasPrivateKey"),
            }
            for c in data
        ]
        return {"store": store, "location": location, "certificates": certs, "count": len(certs)}

    def get_certificate(self, thumbprint: str, store: str = "my", location: str = "currentuser") -> Dict:
        """Get full detail for a single certificate by thumbprint."""
        path = self._resolve(store, location)
        if not path:
            return {"error": "Unknown store/location. Call list_stores() for valid values."}
        safe_thumb = thumbprint.replace("'", "").strip()
        script = (
            f"Get-ChildItem -Path '{path}\\{safe_thumb}' -ErrorAction Stop | "
            "Select-Object Subject, Issuer, Thumbprint, SerialNumber, NotBefore, NotAfter, "
            "HasPrivateKey, SignatureAlgorithm, Version | ConvertTo-Json"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Certificate {thumbprint} not found in {path}.")}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else {}
        except Exception:
            return {"error": "Could not parse certificate detail.", "raw": result["stdout"]}
        return {
            "subject": data.get("Subject"),
            "issuer": data.get("Issuer"),
            "thumbprint": data.get("Thumbprint"),
            "serial_number": data.get("SerialNumber"),
            "valid_from": data.get("NotBefore"),
            "valid_until": data.get("NotAfter"),
            "has_private_key": data.get("HasPrivateKey"),
            "signature_algorithm": (
                (data.get("SignatureAlgorithm") or {}).get("FriendlyName")
                if isinstance(data.get("SignatureAlgorithm"), dict)
                else data.get("SignatureAlgorithm")
            ),
            "version": data.get("Version"),
        }

    def list_expiring_soon(self, days: int = 30, store: str = "my", location: str = "currentuser") -> Dict:
        """List certificates in a store expiring within the given number
        of days - useful for flagging things that need renewal."""
        listed = self.list_certificates(store, location)
        if "error" in listed:
            return listed
        from datetime import datetime, timedelta

        cutoff = datetime.now() + timedelta(days=days)
        expiring = []
        for c in listed["certificates"]:
            try:
                # PowerShell ConvertTo-Json emits .NET date strings; best-effort parse.
                until = c.get("valid_until")
                if until and "/Date(" in str(until):
                    ms = int(str(until).split("(")[1].split(")")[0].split("+")[0].split("-")[0])
                    exp_date = datetime.fromtimestamp(ms / 1000)
                else:
                    exp_date = datetime.fromisoformat(str(until).replace("Z", ""))
                if exp_date <= cutoff:
                    expiring.append({**c, "expires_in_days": (exp_date - datetime.now()).days})
            except Exception:
                continue
        return {
            "store": store,
            "location": location,
            "expiring_within_days": days,
            "certificates": expiring,
            "count": len(expiring),
        }

    def export_certificate(
        self, thumbprint: str, export_path: str, store: str = "my", location: str = "currentuser", confirm: bool = False
    ) -> Dict:
        """Export the PUBLIC certificate (DER-encoded .cer) for a
        thumbprint. Public key only - there is no private-key export
        method in this module. Confirm-gated."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will export the public certificate {thumbprint} to '{export_path}'. "
                f"Public key only, no private key material.",
            }
        path = self._resolve(store, location)
        if not path:
            return {"error": "Unknown store/location. Call list_stores() for valid values."}
        safe_thumb = thumbprint.replace("'", "").strip()
        safe_export = export_path.replace("'", "''")
        script = f"Export-Certificate -Cert '{path}\\{safe_thumb}' -FilePath '{safe_export}' -Type CERT"
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Export failed.")}
        return {"success": True, "exported_to": export_path, "thumbprint": thumbprint}

    def import_certificate(
        self, cert_path: str, store: str = "root", location: str = "currentuser", confirm: bool = False
    ) -> Dict:
        """Import a public certificate file (.cer/.crt/.der) into a store.
        Importing into 'root' or 'ca' marks it as trusted for this user
        or machine - a mistrusted/malicious root cert here can enable
        traffic interception, so this is always confirm-gated and needs
        admin for LocalMachine stores. .pfx/.p12 (private-key-bearing)
        files are rejected outright - this module never imports private
        keys."""
        lower_path = cert_path.lower()
        if lower_path.endswith(".pfx") or lower_path.endswith(".p12"):
            return {
                "error": "Refusing to import a .pfx/.p12 file - it may contain a private key. "
                "This module only handles public certificates (.cer/.crt/.der)."
            }
        path = self._resolve(store, location)
        if not path:
            return {"error": "Unknown store/location. Call list_stores() for valid values."}
        if not confirm:
            trust_note = (
                " This marks it as a TRUSTED ROOT/CA for this "
                + ("machine" if location.lower() == "localmachine" else "user")
                + " - a malicious cert here can intercept traffic that trusts it."
                if store.lower() in ("root", "ca")
                else ""
            )
            return {
                "requires_confirmation": True,
                "preview": f"This will import the certificate at '{cert_path}' into {store}/{location}.{trust_note}",
            }
        safe_cert = cert_path.replace("'", "''")
        script = f"Import-Certificate -FilePath '{safe_cert}' -CertStoreLocation '{path}'"
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Import failed.")}
        return {"success": True, "imported_from": cert_path, "store": store, "location": location}

    def remove_certificate(
        self, thumbprint: str, store: str = "my", location: str = "currentuser", confirm: bool = False
    ) -> Dict:
        """Delete a certificate from a store by thumbprint. Confirm-gated;
        needs admin for LocalMachine stores."""
        path = self._resolve(store, location)
        if not path:
            return {"error": "Unknown store/location. Call list_stores() for valid values."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will permanently remove certificate {thumbprint} from {store}/{location}. "
                f"Anything relying on it (TLS, code signing, auth) will stop trusting/working.",
            }
        safe_thumb = thumbprint.replace("'", "").strip()
        script = f"Remove-Item -Path '{path}\\{safe_thumb}' -Force -ErrorAction Stop"
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Removal failed.")}
        return {"success": True, "removed_thumbprint": thumbprint, "store": store, "location": location}
