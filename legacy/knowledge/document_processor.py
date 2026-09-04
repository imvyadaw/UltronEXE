from pathlib import Path


class DocumentProcessor:
    def text(self, path):
        return Path(path).read_text(encoding="utf-8", errors="ignore")
