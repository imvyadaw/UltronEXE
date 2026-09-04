from pathlib import Path


class CodingTool:
    def read(self, path):
        return Path(path).read_text(encoding="utf-8")

    def write(self, path, content):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(p)}
