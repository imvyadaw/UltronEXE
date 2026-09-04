"""
crash_analyzer.py
====================
Scans ULTRON's own log files (produced by core.logger elsewhere in
the project) for Python tracebacks, groups them by a normalized
signature (exception type + top-of-stack location, with file paths
and line numbers/memory addresses stripped out) so recurring issues
are easy to spot, and tracks first-seen/last-seen/occurrence counts
per signature. This only ever reads ULTRON's own local log files -
never system-wide logs, never anything outside the given directory.

Dependencies: none beyond the standard library.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("ultron.crash_analyzer")

DEFAULT_STORE = Path("ultron_data/self_healing/crash_signatures.json")

_TRACEBACK_START = re.compile(r"^Traceback \(most recent call last\):")
_EXCEPTION_LINE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Warning))\s*:\s*(.*)$")
_FILE_LINE = re.compile(r'^\s*File "(.+?)", line (\d+), in (\S+)')


@dataclass
class CrashSignature:
    signature: str
    exception_type: str
    top_frame: str
    first_seen: str
    last_seen: str
    occurrences: int
    sample_message: str


class CrashAnalyzer:
    """Extracts and groups tracebacks found in ULTRON's own log files."""

    def __init__(self, store_path: Path = DEFAULT_STORE):
        self.store_path = Path(store_path)
        self._lock = threading.Lock()
        self.signatures: Dict[str, CrashSignature] = {}
        self._load()

    def _load(self):
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            self.signatures = {k: CrashSignature(**v) for k, v in data.items()}
        except (json.JSONDecodeError, TypeError, OSError) as exc:
            logger.warning("Could not load crash signatures (%s), starting fresh", exc)

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({k: asdict(v) for k, v in self.signatures.items()}, indent=2), encoding="utf-8")
        tmp.replace(self.store_path)

    def _extract_tracebacks(self, text: str) -> List[List[str]]:
        lines = text.splitlines()
        blocks, current = [], None
        for line in lines:
            if _TRACEBACK_START.match(line):
                current = [line]
            elif current is not None:
                current.append(line)
                if _EXCEPTION_LINE.match(line) and not line.startswith((" ", "\t")):
                    blocks.append(current)
                    current = None
        return blocks

    def _signature_for(self, block: List[str]) -> Optional[CrashSignature]:
        exc_type, exc_msg = None, ""
        for line in reversed(block):
            m = _EXCEPTION_LINE.match(line)
            if m:
                exc_type, exc_msg = m.group(1), m.group(2)
                break
        if not exc_type:
            return None

        top_frame = "unknown"
        for line in block:
            m = _FILE_LINE.match(line)
            if m:
                top_frame = f"{Path(m.group(1)).name}:{m.group(3)}"  # filename + function, no full path/line#
        sig_key = f"{exc_type}@{top_frame}"
        now = datetime.now().isoformat(timespec="seconds")
        return CrashSignature(
            signature=sig_key,
            exception_type=exc_type,
            top_frame=top_frame,
            first_seen=now,
            last_seen=now,
            occurrences=1,
            sample_message=exc_msg[:200],
        )

    def scan_file(self, log_path: Path) -> List[CrashSignature]:
        log_path = Path(log_path)
        if not log_path.exists():
            logger.warning("Log file not found: %s", log_path)
            return []
        text = log_path.read_text(encoding="utf-8", errors="ignore")
        newly_seen = []
        with self._lock:
            for block in self._extract_tracebacks(text):
                sig = self._signature_for(block)
                if not sig:
                    continue
                existing = self.signatures.get(sig.signature)
                if existing:
                    existing.occurrences += 1
                    existing.last_seen = sig.last_seen
                else:
                    self.signatures[sig.signature] = sig
                    newly_seen.append(sig)
            self._save()
        logger.info(
            "Scanned %s: found %d traceback(s), %d new signature(s)",
            log_path,
            len(self._extract_tracebacks(text)),
            len(newly_seen),
        )
        return newly_seen

    def most_frequent(self, top_n: int = 10) -> List[CrashSignature]:
        return sorted(self.signatures.values(), key=lambda s: s.occurrences, reverse=True)[:top_n]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    analyzer = CrashAnalyzer(store_path=Path("ultron_data/self_healing/_demo_crash_signatures.json"))
    demo_log = Path("ultron_data/self_healing/_demo.log")
    demo_log.parent.mkdir(parents=True, exist_ok=True)
    demo_log.write_text(
        "Traceback (most recent call last):\n"
        '  File "ultron/skills/stt.py", line 42, in transcribe\n'
        "    result = engine.run(audio)\n"
        "ValueError: empty audio buffer\n"
    )
    for s in analyzer.scan_file(demo_log):
        print(s)
