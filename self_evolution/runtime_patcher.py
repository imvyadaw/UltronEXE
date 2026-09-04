"""Reactive runtime code self-patcher
======================================
Different from a proactive "rewrite itself every day" loop (deliberately
NOT built - see conversation: unreviewed daily self-rewriting of a
1,300+ file, OS-controlling project is a real risk, not just caution for
its own sake). This is narrower and reactive: only when a *real* error
actually happens while a tool runs, and only after it happens more than
once (so a one-off network blip never triggers a patch attempt), does
this fire self_evolution/evolution_manager.py's existing sandbox-test-
then-record pipeline, scoped to just the file the traceback points at.

Flow per repeated error signature (tool_name + exception type + file +
line, from the traceback):
    1st occurrence  -> logged only, no action.
    2nd occurrence  -> background thread runs EvolutionManager().evaluate()
                       (existing: analyze -> patch -> sandbox compile ->
                       sandbox test -> accept/reject - see
                       self_evolution/evolution_manager.py's own
                       docstring). Only if the WHOLE sandbox run is
                       accepted (compiled + tests passed) is anything
                       taken from it - and even then, only the one file
                       this error pointed at gets copied back to the
                       real project. Original is backed up first, so
                       this is always instantly reversible.
    error recurs
    after a patch
    was applied     -> treated as a failed fix, not tried again: the
                       backup is restored immediately and this exact
                       error signature is permanently marked
                       "do not auto-patch again" - escalated for a human
                       to look at instead.

Hard exclusions - files/dirs this will NEVER auto-patch, only log and
escalate, regardless of error count: the permission/action/capability
gates themselves (patching your own safety gate based on an AI's guess
about what broke is exactly backwards), plus approval/, security/,
ultron_shield/, and self_evolution/ itself.

Storage: storage/self_evolution/runtime_patches.db (its own table) +
storage/self_evolution/backups/ (one timestamped copy of each file
right before it was auto-patched, kept until manually cleaned up).
"""

import os
import shutil
import sqlite3
import threading
import time
import traceback as tb_module
from pathlib import Path
from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.runtime_patcher")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "storage" / "self_evolution" / "runtime_patches.db"
BACKUP_DIR = PROJECT_ROOT / "storage" / "self_evolution" / "backups"

REPEAT_THRESHOLD = 2  # occurrences before a patch attempt fires
MAX_HISTORY = 50

# Never auto-patch these, no matter how many times they error - only
# log + escalate. Relative-path prefixes, matched against the
# project-relative path of the erroring file.
EXCLUDED_PATH_PREFIXES = (
    "core/permissions.py",
    "core/action_pipeline.py",
    "core/capability_registry.py",
    "approval",
    "safety",
    "security",
    "ultron_shield",
    "self_evolution",
)

_instance: Optional["RuntimePatcher"] = None
_instance_lock = threading.Lock()


class RuntimePatcher:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS error_signatures(
                signature TEXT PRIMARY KEY,
                tool_name TEXT,
                error_type TEXT,
                file_rel TEXT,
                line INTEGER,
                occurrences INTEGER NOT NULL DEFAULT 0,
                first_seen REAL,
                last_seen REAL,
                patch_attempted INTEGER NOT NULL DEFAULT 0,
                patch_applied INTEGER NOT NULL DEFAULT 0,
                backup_path TEXT,
                disabled INTEGER NOT NULL DEFAULT 0,
                note TEXT
            )"""
        )
        self._conn.commit()
        self._history: list = []

    # -- public entry point, called from ai/tool_runtime.py -------------
    def record_error(self, tool_name: str, error: BaseException) -> None:
        """Best-effort - never raises, so a bug here can never take down
        the original error path it's observing."""
        try:
            file_rel, line = self._locate_project_frame(error)
            if file_rel is None:
                return  # error didn't originate in our own project code
            error_type = type(error).__name__
            signature = f"{tool_name}:{error_type}:{file_rel}:{line}"
            row = self._touch_signature(signature, tool_name, error_type, file_rel, line)

            if self._is_excluded(file_rel):
                if row["occurrences"] == 1:
                    logger.warning(
                        f"runtime_patcher: '{file_rel}' is in the never-auto-patch list - "
                        f"error will only be logged, not patched."
                    )
                return

            if row["patch_applied"] and row["occurrences"] > 1:
                # Same exact error came back after we already "fixed" it.
                self._rollback(signature)
                return

            if row["occurrences"] == REPEAT_THRESHOLD and not row["patch_attempted"] and not row["disabled"]:
                threading.Thread(
                    target=self._attempt_patch, args=(signature, file_rel), daemon=True
                ).start()
        except Exception:
            logger.exception("runtime_patcher: record_error itself failed")

    # -- internals --------------------------------------------------------
    @staticmethod
    def _locate_project_frame(error: BaseException):
        """Deepest traceback frame that's inside our own project (not
        stdlib/site-packages), so a patch never gets proposed against a
        third-party library file we don't own."""
        tb = error.__traceback__
        frames = tb_module.extract_tb(tb)
        for frame in reversed(frames):
            try:
                abs_path = Path(frame.filename).resolve()
                if PROJECT_ROOT in abs_path.parents and "site-packages" not in abs_path.parts:
                    return str(abs_path.relative_to(PROJECT_ROOT)).replace("\\", "/"), frame.lineno
            except Exception:
                continue
        return None, None

    @staticmethod
    def _is_excluded(file_rel: str) -> bool:
        return any(file_rel == p or file_rel.startswith(p + "/") for p in EXCLUDED_PATH_PREFIXES)

    def _touch_signature(self, signature, tool_name, error_type, file_rel, line) -> Dict:
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                "SELECT occurrences,patch_attempted,patch_applied,backup_path,disabled "
                "FROM error_signatures WHERE signature=?",
                (signature,),
            ).fetchone()
            if row:
                occurrences = row[0] + 1
                self._conn.execute(
                    "UPDATE error_signatures SET occurrences=?,last_seen=? WHERE signature=?",
                    (occurrences, now, signature),
                )
                result = {
                    "occurrences": occurrences,
                    "patch_attempted": bool(row[1]),
                    "patch_applied": bool(row[2]),
                    "backup_path": row[3],
                    "disabled": bool(row[4]),
                }
            else:
                self._conn.execute(
                    "INSERT INTO error_signatures(signature,tool_name,error_type,file_rel,line,"
                    "occurrences,first_seen,last_seen) VALUES(?,?,?,?,?,1,?,?)",
                    (signature, tool_name, error_type, file_rel, line, now, now),
                )
                result = {"occurrences": 1, "patch_attempted": False, "patch_applied": False,
                          "backup_path": None, "disabled": False}
            self._conn.commit()
        return result

    def _attempt_patch(self, signature: str, file_rel: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE error_signatures SET patch_attempted=1 WHERE signature=?", (signature,))
            self._conn.commit()

        entry: Dict = {"signature": signature, "file": file_rel, "started_at": time.time()}
        try:
            from self_evolution.evolution_manager import EvolutionManager

            result = EvolutionManager().evaluate(str(PROJECT_ROOT))
            entry["accepted"] = bool(result.get("accepted"))
            sandbox_root = result.get("sandbox")

            if not entry["accepted"] or not sandbox_root:
                entry["applied"] = False
                entry["reason"] = "sandbox evaluation not accepted (compile/tests failed) - nothing applied"
                logger.info(f"runtime_patcher: {entry['reason']} for '{file_rel}'")
                self._record_history(entry)
                return

            match = None
            for patch in result.get("patches", []):
                if patch.get("status") == "proposed" and patch.get("applied"):
                    try:
                        patch_rel = os.path.relpath(patch["file"], sandbox_root).replace("\\", "/")
                    except Exception:
                        continue
                    if patch_rel == file_rel:
                        match = patch
                        break

            if match is None:
                entry["applied"] = False
                entry["reason"] = "sandbox run was accepted but had no applied patch for this specific file"
                self._record_history(entry)
                return

            real_file = PROJECT_ROOT / file_rel
            backup_path = BACKUP_DIR / f"{int(time.time())}_{file_rel.replace('/', '__')}.bak"
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(real_file, backup_path)
            shutil.copy2(sandbox_root / file_rel if isinstance(sandbox_root, Path) else Path(sandbox_root) / file_rel, real_file)

            with self._lock:
                self._conn.execute(
                    "UPDATE error_signatures SET patch_applied=1,backup_path=? WHERE signature=?",
                    (str(backup_path), signature),
                )
                self._conn.commit()

            entry["applied"] = True
            entry["backup_path"] = str(backup_path)
            entry["diff"] = match.get("diff", "")[:4000]
            logger.info(
                f"runtime_patcher: applied a tested patch to '{file_rel}' after repeated "
                f"'{signature}' errors. Backup at {backup_path}."
            )
        except Exception as e:
            entry["applied"] = False
            entry["error"] = str(e)
            logger.exception(f"runtime_patcher: patch attempt for '{file_rel}' failed")
        finally:
            self._record_history(entry)

    def _rollback(self, signature: str) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT file_rel,backup_path FROM error_signatures WHERE signature=?", (signature,)
            ).fetchone()
        if not row or not row[1]:
            return
        file_rel, backup_path = row
        try:
            shutil.copy2(backup_path, PROJECT_ROOT / file_rel)
            with self._lock:
                self._conn.execute(
                    "UPDATE error_signatures SET disabled=1,note=? WHERE signature=?",
                    ("auto-patch reverted: same error recurred after fix - escalated to human", signature),
                )
                self._conn.commit()
            logger.warning(
                f"runtime_patcher: '{file_rel}' errored again after being auto-patched - "
                f"reverted from {backup_path} and disabled further auto-patch attempts for this error."
            )
            self._record_history({
                "signature": signature, "file": file_rel, "rolled_back": True,
                "reason": "same error recurred post-patch", "at": time.time(),
            })
        except Exception:
            logger.exception(f"runtime_patcher: rollback for '{file_rel}' failed")

    def _record_history(self, entry: Dict) -> None:
        self._history.append(entry)
        self._history = self._history[-MAX_HISTORY:]

    # -- status/history for the tool layer -------------------------------
    def status(self) -> Dict:
        with self._lock:
            rows = self._conn.execute(
                "SELECT signature,file_rel,occurrences,patch_attempted,patch_applied,disabled "
                "FROM error_signatures ORDER BY last_seen DESC LIMIT 20"
            ).fetchall()
        return {
            "tracked_error_signatures": [
                {
                    "signature": r[0], "file": r[1], "occurrences": r[2],
                    "patch_attempted": bool(r[3]), "patch_applied": bool(r[4]), "disabled": bool(r[5]),
                }
                for r in rows
            ],
            "recent_actions": self._history[-10:][::-1],
        }


def get_runtime_patcher() -> RuntimePatcher:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = RuntimePatcher()
    return _instance
