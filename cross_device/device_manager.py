"""
device_manager.py
====================
The registry every other CROSS_DEVICE module reads from. A device
only exists here after it goes through `pair()` with a code you
generated and handed to it yourself (QR code, typed code, whatever
your companion app shows). Nothing auto-discovers or auto-trusts a
device on the network.

Pure standard library.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger("ultron.device_manager")

DEFAULT_STORE_PATH = "ultron_data/cross_device/devices.json"
PAIRING_CODE_TTL_SECONDS = 300  # 5 minutes


class DeviceType(str, Enum):
    PHONE = "phone"
    TABLET = "tablet"
    DESKTOP = "desktop"
    LAPTOP = "laptop"
    WATCH = "watch"
    OTHER = "other"


@dataclass
class Device:
    device_id: str
    name: str
    device_type: DeviceType
    token: str
    capabilities: List[str] = field(default_factory=list)  # e.g. ["notifications", "clipboard", "remote"]
    registered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_seen: Optional[str] = None
    revoked: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["device_type"] = self.device_type.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Device":
        d = dict(d)
        d["device_type"] = DeviceType(d["device_type"])
        return cls(**d)


@dataclass
class _PendingPairing:
    code: str
    device_type: DeviceType
    created_at: float


class DeviceManager:
    """Registry of trusted devices. Pairing is explicit and two-step:

    1. `start_pairing()` on the ULTRON host produces a short-lived code.
    2. The device sends that same code back via `pair(code, name)`,
       which mints the device its own long-lived token.

    Nothing is trusted until step 2 completes with a code that hasn't expired.
    """

    def __init__(self, store_path: str = DEFAULT_STORE_PATH):
        self.store_path = store_path
        self._devices: Dict[str, Device] = {}
        self._pending: Dict[str, _PendingPairing] = {}  # code -> pending
        self._load()

    # ---------------------------------------------------------------- pairing
    def start_pairing(self, device_type: DeviceType = DeviceType.OTHER) -> str:
        """Generate a short-lived pairing code to show/scan on the new device."""
        code = f"{secrets.randbelow(1_000_000):06d}"
        self._pending[code] = _PendingPairing(code=code, device_type=device_type, created_at=time.time())
        logger.info("Pairing code issued (expires in %ss)", PAIRING_CODE_TTL_SECONDS)
        return code

    def pair(self, code: str, name: str) -> Optional[Device]:
        """Complete pairing. Returns the new Device (with its token) or None if
        the code is invalid/expired."""
        pending = self._pending.get(code)
        if not pending:
            logger.warning("Pairing attempt with unknown code")
            return None
        if time.time() - pending.created_at > PAIRING_CODE_TTL_SECONDS:
            logger.warning("Pairing attempt with expired code")
            del self._pending[code]
            return None

        del self._pending[code]
        device = Device(
            device_id=secrets.token_hex(8),
            name=name,
            device_type=pending.device_type,
            token=secrets.token_urlsafe(32),
        )
        self._devices[device.device_id] = device
        self._save()
        logger.info("Paired new device '%s' (%s)", name, device.device_type.value)
        return device

    def revoke(self, device_id: str) -> bool:
        device = self._devices.get(device_id)
        if not device:
            return False
        device.revoked = True
        self._save()
        logger.info("Revoked device %s", device_id)
        return True

    # ---------------------------------------------------------------- lookups
    def authenticate(self, device_id: str, token: str) -> Optional[Device]:
        device = self._devices.get(device_id)
        if not device or device.revoked or not secrets.compare_digest(device.token, token):
            return None
        device.last_seen = datetime.now().isoformat()
        self._save()
        return device

    def set_capabilities(self, device_id: str, capabilities: List[str]) -> None:
        device = self._devices.get(device_id)
        if device:
            device.capabilities = capabilities
            self._save()

    def list_devices(self, include_revoked: bool = False) -> List[Device]:
        return [d for d in self._devices.values() if include_revoked or not d.revoked]

    def get(self, device_id: str) -> Optional[Device]:
        return self._devices.get(device_id)

    def devices_with_capability(self, capability: str) -> List[Device]:
        return [d for d in self._devices.values() if not d.revoked and capability in d.capabilities]

    # ---------------------------------------------------------------- storage
    def _load(self) -> None:
        if not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path, "r") as f:
                raw = json.load(f)
            for entry in raw.get("devices", []):
                dev = Device.from_dict(entry)
                self._devices[dev.device_id] = dev
        except (json.JSONDecodeError, OSError, KeyError, ValueError) as exc:
            logger.error("Failed to load device store: %s", exc)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        with open(self.store_path, "w") as f:
            json.dump({"devices": [d.to_dict() for d in self._devices.values()]}, f, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dm = DeviceManager(store_path="ultron_data/cross_device/_demo_devices.json")
    code = dm.start_pairing(DeviceType.PHONE)
    print(f"Pairing code: {code}")
    dev = dm.pair(code, "My Phone")
    print("Paired:", dev)
    dm.set_capabilities(dev.device_id, ["notifications", "clipboard"])
    print("Devices with notifications capability:", dm.devices_with_capability("notifications"))
