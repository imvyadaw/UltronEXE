"""
Screenshot Verifier (Phase 19.4 - Verification)
===================================================
Verifies screen state by comparing image files - either two
screenshots against each other ("did the screen actually change
after that action") or a screenshot against a named, stored baseline
("does the screen still look like it did when I saved this
baseline"). Uses Pillow for a real pixel-difference percentage when
it's installed; falls back to a byte-hash equality check (identical
or not, no partial similarity) when it isn't, so this module never
hard-fails just because Pillow is missing.

Storage: database/verification.db, table screenshot_baselines.
"""

import hashlib
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Union

try:
    from PIL import Image

    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "verification.db"

PathLike = Union[str, Path]

_instance: Optional["ScreenshotVerifier"] = None
_instance_lock = threading.Lock()


class ScreenshotVerifier:
    """Baseline registry + image comparison for screenshots."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS screenshot_baselines (
                label TEXT PRIMARY KEY,
                file_path TEXT,
                file_hash TEXT,
                width INTEGER,
                height INTEGER,
                saved_at REAL
            )""")
        self._conn.commit()

    # -- low-level comparison -----------------------------------------------------
    @staticmethod
    def _hash_file(path: PathLike) -> Optional[str]:
        p = Path(path)
        if not p.is_file():
            return None
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def compare_images(self, path_a: PathLike, path_b: PathLike) -> Dict:
        """{"identical": bool, "similarity": float 0-1, "method": "pixel"|"hash"}.
        similarity is an exact 0.0/1.0 under the hash fallback since a
        byte hash can't express partial difference."""
        pa, pb = Path(path_a), Path(path_b)
        if not pa.is_file() or not pb.is_file():
            return {"identical": False, "similarity": 0.0, "method": "none", "error": "one or both images missing"}

        if _PIL_AVAILABLE:
            try:
                with Image.open(pa) as img_a, Image.open(pb) as img_b:
                    img_a = img_a.convert("RGB")
                    img_b = img_b.convert("RGB")
                    if img_a.size != img_b.size:
                        img_b = img_b.resize(img_a.size)
                    pixels_a = list(img_a.getdata())
                    pixels_b = list(img_b.getdata())
                    total = len(pixels_a)
                    diff = sum(1 for pa_px, pb_px in zip(pixels_a, pixels_b) if pa_px != pb_px)
                    similarity = round(1.0 - (diff / total), 4) if total else 1.0
                    return {"identical": diff == 0, "similarity": similarity, "method": "pixel"}
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("intelligence.verification.screenshot_verifier.compare_images")

        hash_a, hash_b = self._hash_file(pa), self._hash_file(pb)
        identical = hash_a is not None and hash_a == hash_b
        return {"identical": identical, "similarity": 1.0 if identical else 0.0, "method": "hash"}

    # -- baselines --------------------------------------------------------------------
    def save_baseline(self, label: str, image_path: PathLike) -> Dict:
        p = Path(image_path)
        if not p.is_file():
            return {"error": f"image not found: {p}"}
        width = height = None
        if _PIL_AVAILABLE:
            try:
                with Image.open(p) as img:
                    width, height = img.size
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("intelligence.verification.screenshot_verifier.save_baseline")
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO screenshot_baselines (label, file_path, file_hash, width, height, saved_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(label) DO UPDATE SET
                       file_path = excluded.file_path, file_hash = excluded.file_hash,
                       width = excluded.width, height = excluded.height, saved_at = excluded.saved_at""",
                (label, str(p), self._hash_file(p), width, height, now),
            )
            self._conn.commit()
        return self.get_baseline(label)

    def get_baseline(self, label: str) -> Dict:
        with self._lock:
            cur = self._conn.execute(
                "SELECT label, file_path, file_hash, width, height, saved_at FROM screenshot_baselines WHERE label = ?",
                (label,),
            )
            row = cur.fetchone()
        if row is None:
            return {"error": f"no baseline with label {label}"}
        return {
            "label": row[0],
            "file_path": row[1],
            "file_hash": row[2],
            "width": row[3],
            "height": row[4],
            "saved_at": row[5],
        }

    # -- checks ---------------------------------------------------------------------
    def verify_against_baseline(self, label: str, current_path: PathLike, similarity_threshold: float = 0.95) -> Dict:
        baseline = self.get_baseline(label)
        if baseline.get("error"):
            return {"check": "matches_baseline", "label": label, "passed": False, "reason": baseline["error"]}
        comparison = self.compare_images(baseline["file_path"], current_path)
        passed = comparison.get("similarity", 0.0) >= similarity_threshold
        return {
            "check": "matches_baseline",
            "label": label,
            "passed": passed,
            "similarity_threshold": similarity_threshold,
            **comparison,
        }

    def verify_changed(self, before_path: PathLike, after_path: PathLike, min_difference: float = 0.02) -> Dict:
        """Confirms the screen actually changed - useful right after an
        action that's supposed to visibly do something."""
        comparison = self.compare_images(before_path, after_path)
        difference = round(1.0 - comparison.get("similarity", 1.0), 4)
        passed = difference >= min_difference
        return {
            "check": "screen_changed",
            "passed": passed,
            "difference": difference,
            "min_difference": min_difference,
            **comparison,
        }


def get_screenshot_verifier() -> ScreenshotVerifier:
    """Process-wide ScreenshotVerifier singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ScreenshotVerifier()
    return _instance
