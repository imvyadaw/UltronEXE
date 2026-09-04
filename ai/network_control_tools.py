"""Network Control tool registry
=================================
Wires system_control/network/* (Wi-Fi, Ethernet, VPN) into the AI
tool-calling loop. Same pattern as ai/file_control_tools.py and
ai/system_config_tools.py: lazy singletons + a flat NETWORK_CONTROL_TOOLS
/ NETWORK_CONTROL_DIRECT_HANDLERS pair, merged at the bottom of
ai/tools_schema.py and ai/tool_runtime.py respectively (see the two-line
imports there).

Naming: every tool is prefixed `netctl_` to avoid colliding with the
protocol-client tools backed by the top-level networking/ package (ssh,
ftp, websocket, http) and with the read-only proactive/monitors/
network_status.py + deep_os_integration/network_monitor.py tools - those
stay read-only observation; these actively change adapter/connection
state (Wi-Fi connect/disconnect, adapter enable/disable, static IP,
VPN connect).

Every state-changing method on the underlying classes is confirm-gated
(confirm: bool, defaults False) - same pattern as every other
destructive tool in this codebase.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's `_tool()` helper. Duplicated
    on purpose - see ai/new_skills_tools.py's docstring for why (avoids a
    circular import since tools_schema.py imports *from* this module)."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


def _pick(d: dict, keys: list) -> dict:
    """Filter a raw tool-call args dict down to the keys a method accepts,
    dropping missing/None entries so the method's own defaults apply."""
    return {k: d[k] for k in keys if k in d and d[k] is not None}


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------
_instances: Dict[str, object] = {}


def _get(key: str):
    if key in _instances:
        return _instances[key]

    if key == "wifi":
        from system_control.network.wifi_manager import WifiManager

        obj = WifiManager()
    elif key == "ethernet":
        from system_control.network.ethernet_manager import EthernetManager

        obj = EthernetManager()
    elif key == "vpn":
        from system_control.network.vpn_manager import VpnManager

        obj = VpnManager()
    elif key == "proxy":
        from system_control.network.proxy_manager import ProxyManager

        obj = ProxyManager()
    elif key == "firewall":
        from system_control.network.firewall_manager import FirewallManager

        obj = FirewallManager()
    elif key == "dns":
        from system_control.network.dns_manager import DnsManager

        obj = DnsManager()
    elif key == "ip_config":
        from system_control.network.ip_config import IpConfig

        obj = IpConfig()
    elif key == "bandwidth":
        from system_control.network.bandwidth_manager import BandwidthManager

        obj = BandwidthManager()
    elif key == "hotspot":
        from system_control.network.hotspot_manager import HotspotManager

        obj = HotspotManager()
    elif key == "bluetooth":
        from system_control.network.bluetooth_manager import BluetoothManager

        obj = BluetoothManager()
    elif key == "airplane_mode":
        from system_control.network.airplane_mode import AirplaneMode

        obj = AirplaneMode()
    elif key == "network_drives":
        from system_control.network.network_drives import NetworkDrives

        obj = NetworkDrives()
    elif key == "remote_desktop":
        from system_control.network.remote_desktop import RemoteDesktop

        obj = RemoteDesktop()
    elif key == "ssh":
        from system_control.network.ssh_manager import SshManager

        obj = SshManager()
    elif key == "port":
        from system_control.network.port_manager import PortManager

        obj = PortManager()
    else:
        raise KeyError(f"Unknown network_control tool key: {key}")

    _instances[key] = obj
    return obj


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
NETWORK_CONTROL_TOOLS = [
    # -- WifiManager --
    _tool(
        "netctl_wifi_list_networks",
        "List nearby Wi-Fi networks (SSID, signal strength, authentication type).",
    ),
    _tool(
        "netctl_wifi_list_saved_profiles",
        "List Wi-Fi profiles saved on this machine.",
    ),
    _tool(
        "netctl_wifi_get_current_connection",
        "Get the current Wi-Fi interface state (SSID, signal, connection state).",
    ),
    _tool(
        "netctl_wifi_get_saved_password",
        "Reveal the stored password for a saved Wi-Fi profile in clear text. Confirm-gated.",
        {"profile": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["profile"],
    ),
    _tool(
        "netctl_wifi_connect",
        "Connect to a Wi-Fi network by SSID. Confirm-gated.",
        {"ssid": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["ssid"],
    ),
    _tool(
        "netctl_wifi_disconnect",
        "Disconnect from the current Wi-Fi network. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "netctl_wifi_forget_network",
        "Delete a saved Wi-Fi profile, forgetting the network and its password. Confirm-gated.",
        {"profile": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["profile"],
    ),
    _tool(
        "netctl_wifi_set_enabled",
        "Turn the Wi-Fi adapter on or off entirely. Needs admin. Confirm-gated.",
        {"enabled": {"type": "boolean"}, "interface": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    # -- EthernetManager --
    _tool(
        "netctl_eth_list_adapters",
        "List network adapters with admin/connect state and type.",
    ),
    _tool(
        "netctl_eth_get_adapter_status",
        "Get status for one named network adapter.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "netctl_eth_enable_adapter",
        "Enable a network adapter. Needs admin. Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "netctl_eth_disable_adapter",
        "Disable a network adapter. Needs admin. Confirm-gated - can drop the active connection.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "netctl_eth_get_ip_config",
        "Get current IPv4 config (address/mask/gateway/DHCP status) for one adapter or all.",
        {"name": {"type": "string"}},
    ),
    _tool(
        "netctl_eth_set_static_ip",
        "Assign a static IPv4 address to an adapter. Confirm-gated.",
        {
            "name": {"type": "string"},
            "ip": {"type": "string"},
            "subnet_mask": {"type": "string"},
            "gateway": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["name", "ip", "subnet_mask", "gateway"],
    ),
    _tool(
        "netctl_eth_set_dhcp",
        "Switch an adapter back to DHCP (automatic IP). Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "netctl_eth_set_dns",
        "Set static DNS server(s) for an adapter. Confirm-gated.",
        {
            "name": {"type": "string"},
            "dns_servers": {"type": "array", "items": {"type": "string"}},
            "confirm": {"type": "boolean"},
        },
        ["name", "dns_servers"],
    ),
    _tool(
        "netctl_eth_flush_dns",
        "Clear the local DNS resolver cache. Harmless, not confirm-gated.",
    ),
    # -- VpnManager --
    _tool(
        "netctl_vpn_list_connections",
        "List Windows VPN connection profiles configured for this user.",
    ),
    _tool(
        "netctl_vpn_get_status",
        "Get status for one named VPN connection.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "netctl_vpn_add_connection",
        "Create a new Windows VPN profile. Confirm-gated.",
        {
            "name": {"type": "string"},
            "server_address": {"type": "string"},
            "tunnel_type": {"type": "string", "enum": ["Automatic", "Pptp", "L2tp", "Sstp", "Ikev2"]},
            "confirm": {"type": "boolean"},
        },
        ["name", "server_address"],
    ),
    _tool(
        "netctl_vpn_remove_connection",
        "Delete a Windows VPN profile. Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "netctl_vpn_connect",
        "Connect a VPN profile. Omit username/password to use saved credentials (recommended). " "Confirm-gated.",
        {
            "name": {"type": "string"},
            "username": {"type": "string"},
            "password": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["name"],
    ),
    _tool(
        "netctl_vpn_disconnect",
        "Disconnect an active VPN connection. Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
]

# -- ProxyManager --
NETWORK_CONTROL_TOOLS += [
    _tool(
        "netctl_proxy_get_settings",
        "Get current system proxy settings (enabled, server, bypass list, PAC URL).",
    ),
    _tool(
        "netctl_proxy_set",
        "Enable and set a manual system proxy server. Confirm-gated.",
        {"host": {"type": "string"}, "port": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["host", "port"],
    ),
    _tool(
        "netctl_proxy_set_bypass",
        "Set the list of hosts/domains that skip the system proxy. Confirm-gated.",
        {"bypass_list": {"type": "array", "items": {"type": "string"}}, "confirm": {"type": "boolean"}},
        ["bypass_list"],
    ),
    _tool(
        "netctl_proxy_set_auto_config_url",
        "Set a PAC (proxy auto-config) script URL for the system proxy. Confirm-gated.",
        {"pac_url": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["pac_url"],
    ),
    _tool(
        "netctl_proxy_disable",
        "Turn off the system proxy without clearing its saved settings. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "netctl_proxy_clear",
        "Disable the proxy and clear all its settings (server, bypass, PAC URL). Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
]

# -- FirewallManager --
NETWORK_CONTROL_TOOLS += [
    _tool(
        "netctl_firewall_get_status",
        "Get Windows Defender Firewall on/off state for one profile (domain/private/public) or all.",
        {"profile": {"type": "string", "enum": ["domain", "private", "public"]}},
    ),
    _tool(
        "netctl_firewall_enable",
        "Turn the firewall on for a profile or all profiles. Needs admin. Confirm-gated.",
        {"profile": {"type": "string"}, "confirm": {"type": "boolean"}},
    ),
    _tool(
        "netctl_firewall_disable",
        "Turn the firewall off for a profile or all profiles. Needs admin. Confirm-gated.",
        {"profile": {"type": "string"}, "confirm": {"type": "boolean"}},
    ),
    _tool(
        "netctl_firewall_list_rules",
        "List firewall rules, optionally filtered by an exact rule name.",
        {"name_filter": {"type": "string"}},
    ),
    _tool(
        "netctl_firewall_add_rule",
        "Add a custom firewall rule (direction/action/protocol/port/program). Needs admin. " "Confirm-gated.",
        {
            "name": {"type": "string"},
            "direction": {"type": "string", "enum": ["in", "out"]},
            "action": {"type": "string", "enum": ["allow", "block"]},
            "protocol": {"type": "string"},
            "local_port": {"type": "string"},
            "program": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["name", "direction", "action"],
    ),
    _tool(
        "netctl_firewall_remove_rule",
        "Delete firewall rule(s) by exact name. Needs admin. Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "netctl_firewall_set_rule_enabled",
        "Enable or disable an existing firewall rule by name. Needs admin. Confirm-gated.",
        {"name": {"type": "string"}, "enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["name", "enabled"],
    ),
    _tool(
        "netctl_firewall_block_program",
        "Add rules blocking all inbound+outbound traffic for a specific executable. Needs admin. " "Confirm-gated.",
        {"program_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["program_path"],
    ),
    _tool(
        "netctl_firewall_allow_program",
        "Add rules allowing all inbound+outbound traffic for a specific executable. Needs admin. " "Confirm-gated.",
        {"program_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["program_path"],
    ),
]

# -- DnsManager --
NETWORK_CONTROL_TOOLS += [
    _tool(
        "netctl_dns_list_hosts_entries",
        "List current entries in the Windows hosts file.",
    ),
    _tool(
        "netctl_dns_add_hosts_entry",
        "Add an IP -> hostname override to the hosts file. Needs admin. Confirm-gated.",
        {"ip": {"type": "string"}, "hostname": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["ip", "hostname"],
    ),
    _tool(
        "netctl_dns_remove_hosts_entry",
        "Remove all hosts-file entries for a hostname. Needs admin. Confirm-gated.",
        {"hostname": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["hostname"],
    ),
    _tool(
        "netctl_dns_lookup",
        "Resolve a hostname via nslookup (A record by default).",
        {"hostname": {"type": "string"}, "record_type": {"type": "string"}},
        ["hostname"],
    ),
    _tool(
        "netctl_dns_get_suffix_list",
        "Get the DNS suffix search list and per-adapter DNS servers.",
    ),
    _tool(
        "netctl_dns_get_doh_settings",
        "Get current system DNS-over-HTTPS encryption settings (Windows 11 22H2+).",
    ),
    _tool(
        "netctl_dns_set_doh",
        "Configure DNS-over-HTTPS for a resolver IP + template URL. Needs admin, Windows 11 " "22H2+. Confirm-gated.",
        {
            "server_ip": {"type": "string"},
            "doh_template": {"type": "string"},
            "auto_upgrade": {"type": "boolean"},
            "udp_fallback": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["server_ip", "doh_template"],
    ),
]

# -- IpConfig --
NETWORK_CONTROL_TOOLS += [
    _tool(
        "netctl_ip_get_full_config",
        "Get full ipconfig /all output across every adapter (IPv4+IPv6, DNS, DHCP lease).",
    ),
    _tool(
        "netctl_ip_get_public_ip_hint",
        "Explains that public/external IP lookup needs an external service, not this local tool.",
    ),
    _tool(
        "netctl_ip_get_routing_table",
        "Get the current IPv4 routing table.",
    ),
    _tool(
        "netctl_ip_add_route",
        "Add a static IPv4 route. Needs admin for persistent routes. Confirm-gated.",
        {
            "destination": {"type": "string"},
            "mask": {"type": "string"},
            "gateway": {"type": "string"},
            "metric": {"type": "integer"},
            "persistent": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["destination", "mask", "gateway"],
    ),
    _tool(
        "netctl_ip_remove_route",
        "Delete a static route by destination. Needs admin for persistent routes. Confirm-gated.",
        {"destination": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["destination"],
    ),
    _tool(
        "netctl_ip_add_secondary_ip",
        "Add an extra IPv4 address to an adapter that already has a primary one. Needs admin. " "Confirm-gated.",
        {
            "adapter": {"type": "string"},
            "ip": {"type": "string"},
            "subnet_mask": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["adapter", "ip", "subnet_mask"],
    ),
    _tool(
        "netctl_ip_remove_secondary_ip",
        "Remove a secondary IPv4 address from an adapter. Needs admin. Confirm-gated.",
        {"adapter": {"type": "string"}, "ip": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["adapter", "ip"],
    ),
]

# -- BandwidthManager --
NETWORK_CONTROL_TOOLS += [
    _tool(
        "netctl_bandwidth_get_usage",
        "Get cumulative received/sent byte counters for one adapter or all (a snapshot, not a " "live rate).",
        {"adapter": {"type": "string"}},
    ),
    _tool(
        "netctl_bandwidth_list_qos_policies",
        "List current Windows QoS bandwidth-throttle policies.",
    ),
    _tool(
        "netctl_bandwidth_create_limit",
        "Create a QoS policy throttling an app or port to a bandwidth limit in Mbps. Needs " "admin. Confirm-gated.",
        {
            "policy_name": {"type": "string"},
            "limit_mbps": {"type": "number"},
            "app_path": {"type": "string"},
            "port": {"type": "integer"},
            "confirm": {"type": "boolean"},
        },
        ["policy_name", "limit_mbps"],
    ),
    _tool(
        "netctl_bandwidth_remove_limit",
        "Delete a QoS bandwidth-limit policy by name. Needs admin. Confirm-gated.",
        {"policy_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["policy_name"],
    ),
]

# -- HotspotManager --
NETWORK_CONTROL_TOOLS += [
    _tool(
        "netctl_hotspot_get_status",
        "Get current mobile-hotspot (hosted network) status: supported/configured/started, SSID.",
    ),
    _tool(
        "netctl_hotspot_configure",
        "Set the hotspot's SSID and WPA2-PSK passphrase (8-63 chars). Confirm-gated.",
        {"ssid": {"type": "string"}, "key": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["ssid", "key"],
    ),
    _tool(
        "netctl_hotspot_start",
        "Start broadcasting the configured hotspot. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "netctl_hotspot_stop",
        "Stop broadcasting the hotspot (keeps its configuration). Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "netctl_hotspot_get_connected_devices",
        "List devices currently connected to the hotspot.",
    ),
    # -- BluetoothManager --
    _tool(
        "netctl_bt_get_radio_status",
        "Check whether a Bluetooth radio is present and enabled.",
    ),
    _tool(
        "netctl_bt_set_radio_enabled",
        "Enable or disable the Bluetooth radio. Confirm-gated.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "netctl_bt_list_paired_devices",
        "List Bluetooth devices currently paired with this machine.",
    ),
    _tool(
        "netctl_bt_get_device_status",
        "Get connection status for a specific paired Bluetooth device by name.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "netctl_bt_connect_device",
        "Reconnect a previously paired Bluetooth device by name. Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "netctl_bt_disconnect_device",
        "Disconnect (without unpairing) a Bluetooth device by name. Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "netctl_bt_remove_paired_device",
        "Forget/unpair a Bluetooth device entirely. Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "netctl_bt_pair_new_device",
        "Open Windows' Bluetooth 'Add a device' settings page for a new pairing.",
    ),
    # -- AirplaneMode --
    _tool(
        "netctl_airplane_get_status",
        "List every radio Windows knows about and whether the machine is effectively in airplane mode.",
    ),
    _tool(
        "netctl_airplane_set_enabled",
        "Turn airplane mode on (all radios off) or off (all radios on). Confirm-gated.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    # -- NetworkDrives --
    _tool(
        "netctl_drives_list_mapped",
        "List currently mapped network drives (letter, UNC path, connection status).",
    ),
    _tool(
        "netctl_drives_get_status",
        "Get the status/UNC path for a single mapped drive letter.",
        {"drive_letter": {"type": "string"}},
        ["drive_letter"],
    ),
    _tool(
        "netctl_drives_map",
        "Map a drive letter to a UNC path, optionally with credentials. Confirm-gated.",
        {
            "drive_letter": {"type": "string"},
            "unc_path": {"type": "string"},
            "username": {"type": "string"},
            "password": {"type": "string"},
            "persistent": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["drive_letter", "unc_path"],
    ),
    _tool(
        "netctl_drives_unmap",
        "Disconnect a mapped network drive by letter. Confirm-gated.",
        {"drive_letter": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["drive_letter"],
    ),
    _tool(
        "netctl_drives_unmap_all",
        "Disconnect every currently mapped network drive. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    # -- RemoteDesktop --
    _tool(
        "netctl_rdp_get_status",
        "Check whether inbound Remote Desktop connections are currently allowed.",
    ),
    _tool(
        "netctl_rdp_set_enabled",
        "Enable or disable inbound Remote Desktop connections. Confirm-gated, needs admin.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "netctl_rdp_list_sessions",
        "List currently connected RDP (and console) sessions.",
    ),
    _tool(
        "netctl_rdp_log_off_session",
        "Force log off a specific RDP session by its numeric session ID. Confirm-gated.",
        {"session_id": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["session_id"],
    ),
    # -- SshManager (server/host side) --
    _tool(
        "netctl_ssh_get_feature_status",
        "Check whether the OpenSSH Server optional Windows feature is installed.",
    ),
    _tool(
        "netctl_ssh_install_feature",
        "Install the OpenSSH Server optional Windows feature. Confirm-gated, needs admin.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "netctl_ssh_uninstall_feature",
        "Remove the OpenSSH Server optional Windows feature entirely. Confirm-gated, needs admin.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "netctl_ssh_get_service_status",
        "Check the sshd service's run state and startup type.",
    ),
    _tool(
        "netctl_ssh_start_service",
        "Start the sshd service (accept inbound SSH connections now). Confirm-gated, needs admin.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "netctl_ssh_stop_service",
        "Stop the sshd service (reject new inbound SSH connections). Confirm-gated, needs admin.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "netctl_ssh_set_start_type",
        "Set whether sshd starts automatically on boot. Confirm-gated, needs admin.",
        {"auto_start": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["auto_start"],
    ),
    _tool(
        "netctl_ssh_list_authorized_keys",
        "List public keys currently authorized for inbound SSH for a Windows username.",
        {"username": {"type": "string"}},
        ["username"],
    ),
    _tool(
        "netctl_ssh_add_authorized_key",
        "Append a public key to a user's authorized_keys for inbound SSH. Confirm-gated.",
        {"username": {"type": "string"}, "public_key": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["username", "public_key"],
    ),
    # -- PortManager --
    _tool(
        "netctl_port_list_listening",
        "List all TCP ports currently in LISTENING state, with owning PID.",
    ),
    _tool(
        "netctl_port_get_process",
        "Find which process (PID + name) owns a given local port.",
        {"port": {"type": "integer"}},
        ["port"],
    ),
    _tool(
        "netctl_port_kill_process",
        "Kill the process(es) currently listening on a given port. Confirm-gated.",
        {"port": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["port"],
    ),
    _tool(
        "netctl_port_list_forwards",
        "List active netsh interface portproxy forwarding rules.",
    ),
    _tool(
        "netctl_port_add_forward",
        "Add a port-forwarding rule from a listen address:port to a connect address:port. Confirm-gated.",
        {
            "listen_port": {"type": "integer"},
            "connect_port": {"type": "integer"},
            "listen_address": {"type": "string"},
            "connect_address": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["listen_port", "connect_port"],
    ),
    _tool(
        "netctl_port_remove_forward",
        "Remove a port-forwarding rule by its listen address/port. Confirm-gated.",
        {"listen_port": {"type": "integer"}, "listen_address": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["listen_port"],
    ),
    _tool(
        "netctl_port_is_open_locally",
        "Quick TCP connect check for whether something is accepting connections on host:port.",
        {"port": {"type": "integer"}, "host": {"type": "string"}},
        ["port"],
    ),
]

# ---------------------------------------------------------------------------
# Direct handlers - flat name -> lambda(args_dict) -> result dict
# ---------------------------------------------------------------------------
NETWORK_CONTROL_DIRECT_HANDLERS = {
    # -- WifiManager --
    "netctl_wifi_list_networks": lambda d, _k="wifi", _m="list_available_networks", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_wifi_list_saved_profiles": lambda d, _k="wifi", _m="list_saved_profiles", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_wifi_get_current_connection": lambda d, _k="wifi", _m="get_current_connection", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_wifi_get_saved_password": lambda d, _k="wifi", _m="get_saved_password", _p=["profile", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_wifi_connect": lambda d, _k="wifi", _m="connect", _p=["ssid", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_wifi_disconnect": lambda d, _k="wifi", _m="disconnect", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_wifi_forget_network": lambda d, _k="wifi", _m="forget_network", _p=["profile", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_wifi_set_enabled": lambda d, _k="wifi", _m="set_wifi_enabled", _p=[
        "enabled",
        "interface",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- EthernetManager --
    "netctl_eth_list_adapters": lambda d, _k="ethernet", _m="list_adapters", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_eth_get_adapter_status": lambda d, _k="ethernet", _m="get_adapter_status", _p=["name"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_eth_enable_adapter": lambda d, _k="ethernet", _m="enable_adapter", _p=["name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_eth_disable_adapter": lambda d, _k="ethernet", _m="disable_adapter", _p=["name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_eth_get_ip_config": lambda d, _k="ethernet", _m="get_ip_config", _p=["name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_eth_set_static_ip": lambda d, _k="ethernet", _m="set_static_ip", _p=[
        "name",
        "ip",
        "subnet_mask",
        "gateway",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_eth_set_dhcp": lambda d, _k="ethernet", _m="set_dhcp", _p=["name", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_eth_set_dns": lambda d, _k="ethernet", _m="set_dns", _p=["name", "dns_servers", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_eth_flush_dns": lambda d, _k="ethernet", _m="flush_dns", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- VpnManager --
    "netctl_vpn_list_connections": lambda d, _k="vpn", _m="list_vpn_connections", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_vpn_get_status": lambda d, _k="vpn", _m="get_vpn_status", _p=["name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_vpn_add_connection": lambda d, _k="vpn", _m="add_vpn_connection", _p=[
        "name",
        "server_address",
        "tunnel_type",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_vpn_remove_connection": lambda d, _k="vpn", _m="remove_vpn_connection", _p=["name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_vpn_connect": lambda d, _k="vpn", _m="connect_vpn", _p=["name", "username", "password", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_vpn_disconnect": lambda d, _k="vpn", _m="disconnect_vpn", _p=["name", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- ProxyManager --
    "netctl_proxy_get_settings": lambda d, _k="proxy", _m="get_proxy_settings", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_proxy_set": lambda d, _k="proxy", _m="set_proxy", _p=["host", "port", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_proxy_set_bypass": lambda d, _k="proxy", _m="set_proxy_bypass", _p=["bypass_list", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_proxy_set_auto_config_url": lambda d, _k="proxy", _m="set_auto_config_url", _p=[
        "pac_url",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_proxy_disable": lambda d, _k="proxy", _m="disable_proxy", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_proxy_clear": lambda d, _k="proxy", _m="clear_proxy", _p=["confirm"]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- FirewallManager --
    "netctl_firewall_get_status": lambda d, _k="firewall", _m="get_firewall_status", _p=["profile"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_firewall_enable": lambda d, _k="firewall", _m="enable_firewall", _p=["profile", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_firewall_disable": lambda d, _k="firewall", _m="disable_firewall", _p=["profile", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_firewall_list_rules": lambda d, _k="firewall", _m="list_rules", _p=["name_filter"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_firewall_add_rule": lambda d, _k="firewall", _m="add_rule", _p=[
        "name",
        "direction",
        "action",
        "protocol",
        "local_port",
        "program",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_firewall_remove_rule": lambda d, _k="firewall", _m="remove_rule", _p=["name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_firewall_set_rule_enabled": lambda d, _k="firewall", _m="set_rule_enabled", _p=[
        "name",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_firewall_block_program": lambda d, _k="firewall", _m="block_program", _p=[
        "program_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_firewall_allow_program": lambda d, _k="firewall", _m="allow_program", _p=[
        "program_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- DnsManager --
    "netctl_dns_list_hosts_entries": lambda d, _k="dns", _m="list_hosts_entries", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_dns_add_hosts_entry": lambda d, _k="dns", _m="add_hosts_entry", _p=["ip", "hostname", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_dns_remove_hosts_entry": lambda d, _k="dns", _m="remove_hosts_entry", _p=["hostname", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_dns_lookup": lambda d, _k="dns", _m="lookup", _p=["hostname", "record_type"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_dns_get_suffix_list": lambda d, _k="dns", _m="get_dns_suffix_list", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_dns_get_doh_settings": lambda d, _k="dns", _m="get_doh_settings", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_dns_set_doh": lambda d, _k="dns", _m="set_doh", _p=[
        "server_ip",
        "doh_template",
        "auto_upgrade",
        "udp_fallback",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- IpConfig --
    "netctl_ip_get_full_config": lambda d, _k="ip_config", _m="get_full_ip_config", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_ip_get_public_ip_hint": lambda d, _k="ip_config", _m="get_public_ip_hint", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_ip_get_routing_table": lambda d, _k="ip_config", _m="get_routing_table", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_ip_add_route": lambda d, _k="ip_config", _m="add_route", _p=[
        "destination",
        "mask",
        "gateway",
        "metric",
        "persistent",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_ip_remove_route": lambda d, _k="ip_config", _m="remove_route", _p=["destination", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_ip_add_secondary_ip": lambda d, _k="ip_config", _m="add_secondary_ip", _p=[
        "adapter",
        "ip",
        "subnet_mask",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_ip_remove_secondary_ip": lambda d, _k="ip_config", _m="remove_secondary_ip", _p=[
        "adapter",
        "ip",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- BandwidthManager --
    "netctl_bandwidth_get_usage": lambda d, _k="bandwidth", _m="get_bandwidth_usage", _p=["adapter"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_bandwidth_list_qos_policies": lambda d, _k="bandwidth", _m="list_qos_policies", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_bandwidth_create_limit": lambda d, _k="bandwidth", _m="create_bandwidth_limit", _p=[
        "policy_name",
        "limit_mbps",
        "app_path",
        "port",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_bandwidth_remove_limit": lambda d, _k="bandwidth", _m="remove_bandwidth_limit", _p=[
        "policy_name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- HotspotManager --
    "netctl_hotspot_get_status": lambda d, _k="hotspot", _m="get_hotspot_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_hotspot_configure": lambda d, _k="hotspot", _m="configure_hotspot", _p=["ssid", "key", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_hotspot_start": lambda d, _k="hotspot", _m="start_hotspot", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_hotspot_stop": lambda d, _k="hotspot", _m="stop_hotspot", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_hotspot_get_connected_devices": lambda d, _k="hotspot", _m="get_connected_devices", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- BluetoothManager --
    "netctl_bt_get_radio_status": lambda d, _k="bluetooth", _m="get_radio_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_bt_set_radio_enabled": lambda d, _k="bluetooth", _m="set_radio_enabled", _p=["enabled", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_bt_list_paired_devices": lambda d, _k="bluetooth", _m="list_paired_devices", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_bt_get_device_status": lambda d, _k="bluetooth", _m="get_device_status", _p=["name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_bt_connect_device": lambda d, _k="bluetooth", _m="connect_device", _p=["name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_bt_disconnect_device": lambda d, _k="bluetooth", _m="disconnect_device", _p=["name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_bt_remove_paired_device": lambda d, _k="bluetooth", _m="remove_paired_device", _p=[
        "name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_bt_pair_new_device": lambda d, _k="bluetooth", _m="pair_new_device", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- AirplaneMode --
    "netctl_airplane_get_status": lambda d, _k="airplane_mode", _m="get_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_airplane_set_enabled": lambda d, _k="airplane_mode", _m="set_enabled", _p=["enabled", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- NetworkDrives --
    "netctl_drives_list_mapped": lambda d, _k="network_drives", _m="list_mapped_drives", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_drives_get_status": lambda d, _k="network_drives", _m="get_drive_status", _p=["drive_letter"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_drives_map": lambda d, _k="network_drives", _m="map_drive", _p=[
        "drive_letter",
        "unc_path",
        "username",
        "password",
        "persistent",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_drives_unmap": lambda d, _k="network_drives", _m="unmap_drive", _p=["drive_letter", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_drives_unmap_all": lambda d, _k="network_drives", _m="unmap_all", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- RemoteDesktop --
    "netctl_rdp_get_status": lambda d, _k="remote_desktop", _m="get_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_rdp_set_enabled": lambda d, _k="remote_desktop", _m="set_enabled", _p=["enabled", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_rdp_list_sessions": lambda d, _k="remote_desktop", _m="list_active_sessions", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_rdp_log_off_session": lambda d, _k="remote_desktop", _m="log_off_session", _p=[
        "session_id",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- SshManager --
    "netctl_ssh_get_feature_status": lambda d, _k="ssh", _m="get_feature_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_ssh_install_feature": lambda d, _k="ssh", _m="install_feature", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_ssh_uninstall_feature": lambda d, _k="ssh", _m="uninstall_feature", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_ssh_get_service_status": lambda d, _k="ssh", _m="get_service_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_ssh_start_service": lambda d, _k="ssh", _m="start_service", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_ssh_stop_service": lambda d, _k="ssh", _m="stop_service", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_ssh_set_start_type": lambda d, _k="ssh", _m="set_start_type", _p=["auto_start", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_ssh_list_authorized_keys": lambda d, _k="ssh", _m="list_authorized_keys", _p=["username"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_ssh_add_authorized_key": lambda d, _k="ssh", _m="add_authorized_key", _p=[
        "username",
        "public_key",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- PortManager --
    "netctl_port_list_listening": lambda d, _k="port", _m="list_listening_ports", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_port_get_process": lambda d, _k="port", _m="get_process_on_port", _p=["port"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_port_kill_process": lambda d, _k="port", _m="kill_process_on_port", _p=["port", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "netctl_port_list_forwards": lambda d, _k="port", _m="list_port_forwards", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "netctl_port_add_forward": lambda d, _k="port", _m="add_port_forward", _p=[
        "listen_port",
        "connect_port",
        "listen_address",
        "connect_address",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_port_remove_forward": lambda d, _k="port", _m="remove_port_forward", _p=[
        "listen_port",
        "listen_address",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "netctl_port_is_open_locally": lambda d, _k="port", _m="is_port_open_locally", _p=["port", "host"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
}
