"""system_control/network - Wi-Fi, Ethernet, VPN, firewall, DNS, IP config,
bandwidth, hotspot, Bluetooth, airplane mode, mapped network drives, remote
desktop (inbound), SSH server (inbound), and port control (netsh/rasdial/
PowerShell/net-backed). Distinct from the top-level networking/ package
(ssh, ftp, websocket, http *protocol clients* this machine initiates) and
from proactive/monitors/network_status.py + deep_os_integration/
network_monitor.py (passive read-only monitoring) - these classes actively
change adapter/connection/radio/access state.
"""
