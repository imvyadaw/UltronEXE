"""
audit_logger.py
====================
An append-only log for security-relevant events across all of Shield
(and anything else you point at it - deployments, pairing, remote
commands) where each entry embeds the SHA-256 hash of the entry
before it. That makes the log tamper-evident: editing or deleting an
entry anywhere but the very end breaks the hash chain from that point
forward, and `verify_integrity()` will say exactly where.

This is tamper-*evidence*, not tamper-*prevention* - it doesn't stop
someone with filesystem access from editing the file; it guarantees
that if they do, it's detectable. For real prevention you'd want this
file's directory on a write-once/append-only volume or shipped off-
host - out of scope for a local module, but worth knowing the limit.

Pure standard library.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List

logger = logging.getLogger("ultron.audit_logger")

DEFAULT_LOG_PATH = "ultron_data/shield/audit_log.jsonl"
GENESIS_HASH = "0" * 64


@dataclass
class AuditEntry:
    seq: int
    event_type: str
    detail: str
    actor: str  # who/what triggered it, e.g. a device_id or "system"
    prev_hash: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    entry_hash: str = ""  # computed after the rest of the fields are set

    def compute_hash(self) -> str:
        payload = json.dumps(
            {
                "seq": self.seq,
                "event_type": self.event_type,
                "detail": self.detail,
                "actor": self.actor,
                "prev_hash": self.prev_hash,
                "timestamp": self.timestamp,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IntegrityIssue:
    seq: int
    reason: str


class AuditLogger:
    """Hash-chained, append-only audit log. Every entry's hash depends on
    the entry before it, so the chain can be independently re-verified."""

    def __init__(self, log_path: str = DEFAULT_LOG_PATH):
        self.log_path = log_path
        self._last_hash = GENESIS_HASH
        self._next_seq = 0
        self._bootstrap_from_existing_log()

    def record(self, event_type: str, detail: str, actor: str = "system") -> AuditEntry:
        entry = AuditEntry(
            seq=self._next_seq, event_type=event_type, detail=detail, actor=actor, prev_hash=self._last_hash
        )
        entry.entry_hash = entry.compute_hash()

        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

        self._last_hash = entry.entry_hash
        self._next_seq += 1
        logger.info("Audit: [%s] %s (actor=%s)", event_type, detail, actor)
        return entry

    def read_all(self) -> List[AuditEntry]:
        if not os.path.exists(self.log_path):
            return []
        entries = []
        with open(self.log_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(AuditEntry(**json.loads(line)))
        return entries

    def verify_integrity(self) -> List[IntegrityIssue]:
        """Walks the whole chain from genesis and reports every point where
        it breaks. An empty list means the log is intact end to end."""
        issues: List[IntegrityIssue] = []
        expected_prev = GENESIS_HASH

        for entry in self.read_all():
            if entry.prev_hash != expected_prev:
                issues.append(
                    IntegrityIssue(
                        entry.seq,
                        f"prev_hash mismatch (expected {expected_prev[:12]}..., got {entry.prev_hash[:12]}...)",
                    )
                )
            recomputed = entry.compute_hash()
            if recomputed != entry.entry_hash:
                issues.append(
                    IntegrityIssue(
                        entry.seq, "entry_hash does not match recomputed hash - " "this entry's content was altered"
                    )
                )
            expected_prev = entry.entry_hash

        return issues

    def _bootstrap_from_existing_log(self) -> None:
        entries = self.read_all()
        if entries:
            self._last_hash = entries[-1].entry_hash
            self._next_seq = entries[-1].seq + 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    audit = AuditLogger(log_path="ultron_data/shield/_demo_audit_log.jsonl")

    audit.record("device_paired", "Paired 'My Phone'", actor="system")
    audit.record("skill_deployed", "Deployed 'greeter' v1.0.0", actor="local_user")
    audit.record("intrusion_lockout", "Locked out 192.168.1.50 after 3 auth failures", actor="intrusion_detector")

    print("Integrity check (should be empty):", audit.verify_integrity())

    # Simulate tampering: hand-edit one line's detail without recomputing its hash.
    with open("ultron_data/shield/_demo_audit_log.jsonl", "r") as f:
        lines = f.readlines()
    tampered = json.loads(lines[1])
    tampered["detail"] = "Deployed 'totally-different-skill' v9.9.9"
    lines[1] = json.dumps(tampered) + "\n"
    with open("ultron_data/shield/_demo_audit_log.jsonl", "w") as f:
        f.writelines(lines)

    print("Integrity check after tampering:", audit.verify_integrity())
