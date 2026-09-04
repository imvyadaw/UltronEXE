"""MS Paint automation."""

from typing import Dict

from apps.base_app import BaseApp


class PaintApp(BaseApp):
    """Open image files and a blank canvas via Paint."""

    APP_NAME = "paint"
    PROCESS_NAMES = ["mspaint.exe", "mspaint"]
    EXE_HINTS = ["mspaint", "mspaint.exe"]

    def open_file(self, path: str) -> Dict:
        return self.run_command(["mspaint.exe", path])

    def new_canvas(self) -> Dict:
        return self.open()
