"""Proxy Manager
================
Windows' system-wide Internet proxy settings (the ones under Settings >
Network > Proxy, backed by WinINet's registry keys under HKCU
...\\Internet Settings). Covers manual proxy server + bypass list and
the PAC/auto-config-script URL. This is the OS-level HTTP/HTTPS proxy
every WinINet-based app picks up (browsers, most desktop apps) - not a
per-connection SOCKS tunnel and not ULTRON's own outbound requests.

Every setter is confirm-gated: a bad proxy value (or forgetting to set
a bypass list) can silently break internet access for every app that
honors it.
"""
import logging

import ctypes
from typing import Dict, List

try:
    import winreg

    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

# Constants for notifying WinINet that settings changed, so open apps
# pick up the new proxy without a reboot/relogin.
INTERNET_OPTION_SETTINGS_CHANGED = 39
INTERNET_OPTION_REFRESH = 37


class ProxyManager:
    """Read/write the system HTTP proxy and PAC auto-config settings."""

    def _notify_change(self) -> None:
        try:
            ctypes.windll.Wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
            ctypes.windll.Wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
        except Exception:
            pass  # best-effort; the registry change itself already took effect

    def get_proxy_settings(self) -> Dict:
        """Current proxy enable state, server, port, bypass list, and
        auto-config URL, if any."""
        if not HAS_WINREG:
            return {"error": "winreg not available - this is only available on Windows"}
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY_PATH)

            def _val(name, default=None):
                try:
                    v, _ = winreg.QueryValueEx(key, name)
                    return v
                except FileNotFoundError:
                    return default

            enabled = bool(_val("ProxyEnable", 0))
            server = _val("ProxyServer", "")
            bypass = _val("ProxyOverride", "")
            auto_config_url = _val("AutoConfigURL", "")
            winreg.CloseKey(key)
            host, port = (server.split(":", 1) + [None])[:2] if server and ":" in server else (server, None)
            return {
                "success": True,
                "enabled": enabled,
                "server": server,
                "host": host or None,
                "port": int(port) if port and port.isdigit() else None,
                "bypass_list": [b for b in bypass.split(";") if b] if bypass else [],
                "auto_config_url": auto_config_url or None,
            }
        except Exception as e:
            return {"error": str(e)}

    def set_proxy(self, host: str, port: int, confirm: bool = False) -> Dict:
        """Set and enable a manual proxy server (applies to HTTP/HTTPS/
        FTP alike, as WinINet doesn't distinguish by default). Confirm-gated."""
        if not HAS_WINREG:
            return {"error": "winreg not available - this is only available on Windows"}
        if not host or not port:
            return {"error": "host and port are required"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would enable proxy {host}:{port} for this user.",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY_PATH, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"{host}:{port}")
            winreg.CloseKey(key)
            self._notify_change()
            return {"success": True, "server": f"{host}:{port}", "enabled": True}
        except Exception as e:
            return {"error": str(e)}

    def set_proxy_bypass(self, bypass_list: List[str], confirm: bool = False) -> Dict:
        """Set the list of hosts/domains that skip the proxy (e.g.
        ['localhost', '*.internal.company.com']). Confirm-gated."""
        if not HAS_WINREG:
            return {"error": "winreg not available - this is only available on Windows"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would set proxy bypass list to: {', '.join(bypass_list) or '(empty)'}.",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY_PATH, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, ";".join(bypass_list))
            winreg.CloseKey(key)
            self._notify_change()
            return {"success": True, "bypass_list": bypass_list}
        except Exception as e:
            return {"error": str(e)}

    def set_auto_config_url(self, pac_url: str, confirm: bool = False) -> Dict:
        """Set a PAC (proxy auto-config) script URL instead of a manual
        proxy. Confirm-gated."""
        if not HAS_WINREG:
            return {"error": "winreg not available - this is only available on Windows"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would set the proxy auto-config script URL to {pac_url}.",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY_PATH, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, pac_url)
            winreg.CloseKey(key)
            self._notify_change()
            return {"success": True, "auto_config_url": pac_url}
        except Exception as e:
            return {"error": str(e)}

    def disable_proxy(self, confirm: bool = False) -> Dict:
        """Turn off the manual proxy (leaves the server/bypass values in
        place, just flips ProxyEnable off). Confirm-gated."""
        if not HAS_WINREG:
            return {"error": "winreg not available - this is only available on Windows"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": "Would disable the system proxy.",
                "message": "Call again with confirm=true to disable.",
            }
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY_PATH, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            self._notify_change()
            return {"success": True, "enabled": False}
        except Exception as e:
            return {"error": str(e)}

    def clear_proxy(self, confirm: bool = False) -> Dict:
        """Disable the proxy AND clear the server/bypass/PAC values
        entirely, back to a clean no-proxy state. Confirm-gated."""
        if not HAS_WINREG:
            return {"error": "winreg not available - this is only available on Windows"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": "Would clear all proxy settings (server, bypass list, PAC URL) " "and disable the proxy.",
                "message": "Call again with confirm=true to clear.",
            }
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY_PATH, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, "")
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "")
            try:
                winreg.DeleteValue(key, "AutoConfigURL")
            except FileNotFoundError:
                logging.getLogger(__name__).exception("Suppressed FileNotFoundError")
            winreg.CloseKey(key)
            self._notify_change()
            return {"success": True, "cleared": True}
        except Exception as e:
            return {"error": str(e)}
