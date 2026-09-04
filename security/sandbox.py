from pathlib import Path


class SecuritySandbox:
    def __init__(self, root="storage/sandbox"):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name):
        p = (self.root / name).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError("sandbox escape")
        return p
