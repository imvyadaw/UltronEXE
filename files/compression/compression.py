"""Compression tools
==================
Zip/unzip files and folders, list archive contents. Pure stdlib
(zipfile + shutil), no extra dependencies needed.
"""

import zipfile
import shutil
from pathlib import Path
from typing import Dict, List


class CompressionTools:
    """Zip/unzip files and folders."""

    def _resolve(self, path: str) -> Path:
        return Path(path).expanduser().resolve()

    def compress(self, source_path: str, output_path: str = None) -> Dict:
        """Zip a file or folder. If output_path is omitted, uses source name + .zip."""
        try:
            source = self._resolve(source_path)
            if not source.exists():
                return {"error": f"Path does not exist: {source}"}

            if output_path:
                out = self._resolve(output_path)
                if out.suffix == ".zip":
                    out = out.with_suffix("")
            else:
                out = source.with_suffix("")

            if source.is_dir():
                archive = shutil.make_archive(str(out), "zip", root_dir=str(source))
            else:
                archive = str(out) + ".zip"
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(source, arcname=source.name)

            return {"success": True, "archive": archive, "source": str(source)}
        except Exception as e:
            return {"error": str(e)}

    def extract(self, archive_path: str, output_dir: str = None) -> Dict:
        """Extract a .zip archive into output_dir (defaults to same folder)."""
        try:
            archive = self._resolve(archive_path)
            if not archive.exists():
                return {"error": f"Archive not found: {archive}"}
            if not zipfile.is_zipfile(archive):
                return {"error": f"Not a valid zip archive: {archive}"}

            out_dir = self._resolve(output_dir) if output_dir else archive.parent / archive.stem
            out_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(out_dir)
                names = zf.namelist()

            return {"success": True, "extracted_to": str(out_dir), "file_count": len(names)}
        except Exception as e:
            return {"error": str(e)}

    def list_contents(self, archive_path: str) -> Dict:
        """List the files inside a .zip archive without extracting."""
        try:
            archive = self._resolve(archive_path)
            if not archive.exists():
                return {"error": f"Archive not found: {archive}"}
            if not zipfile.is_zipfile(archive):
                return {"error": f"Not a valid zip archive: {archive}"}

            with zipfile.ZipFile(archive, "r") as zf:
                infos = zf.infolist()
                contents: List[Dict] = [
                    {"name": info.filename, "size": info.file_size, "compressed_size": info.compress_size}
                    for info in infos
                ]

            return {"archive": str(archive), "file_count": len(contents), "contents": contents}
        except Exception as e:
            return {"error": str(e)}

    def add_to_archive(self, archive_path: str, file_path: str) -> Dict:
        """Add a single file into an existing (or new) zip archive."""
        try:
            archive = self._resolve(archive_path)
            file_to_add = self._resolve(file_path)
            if not file_to_add.exists():
                return {"error": f"File not found: {file_to_add}"}

            mode = "a" if archive.exists() else "w"
            with zipfile.ZipFile(archive, mode, zipfile.ZIP_DEFLATED) as zf:
                zf.write(file_to_add, arcname=file_to_add.name)

            return {"success": True, "archive": str(archive), "added": file_to_add.name}
        except Exception as e:
            return {"error": str(e)}
