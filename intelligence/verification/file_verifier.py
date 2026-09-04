"""
File Verifier (Phase 19.4 - Verification)
=============================================
Stateless filesystem checks: does a file exist, was it created/
modified after a given time, does it contain some text, does its
hash/size match what was expected. No database of its own - every
method just answers a yes/no (plus details) against the filesystem
right now. action_verifier.py and success_evaluator.py call into
this for any check that boils down to "did a file show up / change
the way it should have".
"""

import hashlib
import threading
from pathlib import Path
from typing import Dict, Optional, Union

_instance: Optional["FileVerifier"] = None
_instance_lock = threading.Lock()

PathLike = Union[str, Path]


class FileVerifier:
    """Filesystem existence/change/content checks, each returning a
    small {"passed": bool, ...details} dict rather than raising."""

    @staticmethod
    def hash_file(path: PathLike, algo: str = "sha256") -> Optional[str]:
        p = Path(path)
        if not p.is_file():
            return None
        h = hashlib.new(algo)
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def verify_exists(self, path: PathLike) -> Dict:
        p = Path(path)
        return {"check": "file_exists", "path": str(p), "passed": p.exists()}

    def verify_is_file(self, path: PathLike) -> Dict:
        p = Path(path)
        return {"check": "is_file", "path": str(p), "passed": p.is_file()}

    def verify_modified_after(self, path: PathLike, timestamp: float) -> Dict:
        p = Path(path)
        if not p.exists():
            return {"check": "modified_after", "path": str(p), "passed": False, "reason": "does not exist"}
        mtime = p.stat().st_mtime
        return {
            "check": "modified_after",
            "path": str(p),
            "passed": mtime > timestamp,
            "mtime": mtime,
            "threshold": timestamp,
        }

    def verify_created_after(self, path: PathLike, timestamp: float) -> Dict:
        p = Path(path)
        if not p.exists():
            return {"check": "created_after", "path": str(p), "passed": False, "reason": "does not exist"}
        ctime = p.stat().st_ctime
        return {
            "check": "created_after",
            "path": str(p),
            "passed": ctime > timestamp,
            "ctime": ctime,
            "threshold": timestamp,
        }

    def verify_contains(self, path: PathLike, substring: str, encoding: str = "utf-8") -> Dict:
        p = Path(path)
        if not p.is_file():
            return {"check": "contains", "path": str(p), "passed": False, "reason": "does not exist"}
        try:
            text = p.read_text(encoding=encoding, errors="ignore")
        except Exception as exc:
            return {"check": "contains", "path": str(p), "passed": False, "reason": str(exc)}
        return {"check": "contains", "path": str(p), "passed": substring in text, "substring": substring}

    def verify_hash_matches(self, path: PathLike, expected_hash: str, algo: str = "sha256") -> Dict:
        actual = self.hash_file(path, algo=algo)
        return {
            "check": "hash_matches",
            "path": str(path),
            "passed": actual is not None and actual == expected_hash,
            "expected": expected_hash,
            "actual": actual,
        }

    def verify_size_at_least(self, path: PathLike, min_bytes: int) -> Dict:
        p = Path(path)
        if not p.is_file():
            return {"check": "size_at_least", "path": str(p), "passed": False, "reason": "does not exist"}
        size = p.stat().st_size
        return {
            "check": "size_at_least",
            "path": str(p),
            "passed": size >= min_bytes,
            "size": size,
            "min_bytes": min_bytes,
        }

    def verify_not_empty(self, path: PathLike) -> Dict:
        return self.verify_size_at_least(path, 1)


def get_file_verifier() -> FileVerifier:
    """Process-wide FileVerifier singleton (stateless, but shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = FileVerifier()
    return _instance
