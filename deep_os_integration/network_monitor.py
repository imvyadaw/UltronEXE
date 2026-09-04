"""
network_monitor.py
===================
Bandwidth usage, interface status and active outbound connections
(process, remote host, remote port) - the same information Task
Manager's "Resource usage" / "App history" tabs show you.

Scope note: this reports connection METADATA (who's connected to
what), not packet contents. It deliberately does not do raw packet
capture/sniffing - that's a different tool with a different risk
profile (intercepting other traffic on the network, including other
people's), and it's not something this module does even for your own
machine's own traffic.

Dependencies: pip install psutil
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import psutil

logger = logging.getLogger("ultron.network_monitor")


@dataclass
class BandwidthSample:
    bytes_sent: int
    bytes_recv: int
    upload_kbps: float
    download_kbps: float


@dataclass
class ConnectionInfo:
    pid: Optional[int]
    process_name: Optional[str]
    local_addr: str
    remote_addr: Optional[str]
    status: str


class NetworkMonitor:
    def __init__(self):
        self._last_counters = psutil.net_io_counters()
        self._last_time = time.time()

    def bandwidth_sample(self) -> BandwidthSample:
        """Call periodically (e.g. every 1-2s) to get current throughput."""
        now = time.time()
        counters = psutil.net_io_counters()
        elapsed = max(now - self._last_time, 1e-6)

        up_kbps = (counters.bytes_sent - self._last_counters.bytes_sent) / 1024 / elapsed
        down_kbps = (counters.bytes_recv - self._last_counters.bytes_recv) / 1024 / elapsed

        self._last_counters = counters
        self._last_time = now

        return BandwidthSample(
            bytes_sent=counters.bytes_sent,
            bytes_recv=counters.bytes_recv,
            upload_kbps=round(up_kbps, 1),
            download_kbps=round(down_kbps, 1),
        )

    def active_connections(self, established_only: bool = True) -> List[ConnectionInfo]:
        results = []
        for c in psutil.net_connections(kind="inet"):
            if established_only and c.status != psutil.CONN_ESTABLISHED:
                continue
            proc_name = None
            if c.pid:
                try:
                    proc_name = psutil.Process(c.pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    proc_name = None
            results.append(
                ConnectionInfo(
                    pid=c.pid,
                    process_name=proc_name,
                    local_addr=f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "",
                    remote_addr=f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else None,
                    status=c.status,
                )
            )
        return results

    def interface_status(self) -> Dict[str, dict]:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        out = {}
        for iface, st in stats.items():
            out[iface] = {
                "is_up": st.isup,
                "speed_mbps": st.speed,
                "addresses": [a.address for a in addrs.get(iface, [])],
            }
        return out

    def is_online(self, host: str = "8.8.8.8", port: int = 53, timeout: float = 2.0) -> bool:
        import socket

        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except OSError:
            return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mon = NetworkMonitor()
    print("Online:", mon.is_online())
    time.sleep(1)
    print(mon.bandwidth_sample())
    for conn in mon.active_connections()[:10]:
        print(conn)
