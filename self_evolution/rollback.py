from pathlib import Path
import shutil


class Rollback:
    def restore(self, backup, target):
        b, t = Path(backup), Path(target)
        if not b.exists():
            return {"success": False, "error": "backup missing"}
        if t.exists():
            shutil.rmtree(t)
        shutil.copytree(b, t)
        return {"success": True}
