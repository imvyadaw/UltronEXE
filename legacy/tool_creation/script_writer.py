from pathlib import Path


class ScriptWriter:
    def write(self, path, source):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(source, encoding="utf-8")
        return {"success": True}
