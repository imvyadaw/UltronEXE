from pathlib import Path


class KillSwitch:
    def __init__(self, path="storage/ultron_disabled.flag"):
        self.path = Path(path)

    def activate(self, reason="manual"):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(reason)

    def deactivate(self):
        self.path.unlink(missing_ok=True)

    def active(self):
        return self.path.exists()
