"""
Conflict Resolution Engine (P4)
================================
Detects and (auto- or manually) resolves contradictions between two
sources' claims about the same subject - a gap nothing else in the
build covers. Best-effort feeds off intelligence/evidence_ledger/'s
per-source reliability scores to auto-resolve when the gap is clear.

    conflict_store.py    - sqlite CRUD for logged conflicts
    conflict_resolver.py - detect / auto_resolve / manual_resolve

Usage:
    from intelligence.conflict_resolution import get_conflict_resolver
    cr = get_conflict_resolver()
    cr.detect_conflict("meeting time", "3pm", "calendar", "4pm", "email")
    cr.auto_resolve(conflict_id)

Purely additive - intelligence/evidence_ledger/ is unmodified; this
only reads its reliability scores best-effort.
"""

from intelligence.conflict_resolution.conflict_store import ConflictStore, get_conflict_store
from intelligence.conflict_resolution.conflict_resolver import ConflictResolver, get_conflict_resolver

__all__ = ["ConflictStore", "get_conflict_store", "ConflictResolver", "get_conflict_resolver"]
