"""BitLocker automation (via manage-bde) - encryption status for the
local machine's own drives."""

from typing import Dict

from apps.base_app import BaseApp


class BitLockerApp(BaseApp):
    """Check BitLocker encryption status per drive."""

    APP_NAME = "bitlocker"
    PROCESS_NAMES = []
    EXE_HINTS = ["manage-bde", "manage-bde.exe"]

    def get_status(self, drive: str = "C:") -> Dict:
        return self.run_and_capture(["manage-bde", "-status", drive])

    def get_all_status(self) -> Dict:
        return self.run_and_capture(["manage-bde", "-status"])
