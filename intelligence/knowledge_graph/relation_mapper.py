"""
Relation Mapper (Phase 19.7 - Knowledge Graph)
==================================================
Takes the entities entity_extractor.py found in one piece of text and
decides how each co-occurring pair relates. Same deliberately-simple
heuristic as the rest of this package: entities are paired sentence
by sentence (two things mentioned states apart are weaker evidence of
a real relation than two things in the same sentence), and a small
keyword table maps the phrase sitting between them to a relation
type. No keyword match still produces an edge - just the generic
"mentioned_with" - because co-occurrence itself is signal even when
the exact relationship is unclear.

This module only maps - it never persists nodes/edges (graph_store.py)
or extracts entities in the first place (entity_extractor.py).
"""

import re
import threading
from typing import Dict, List, Optional

_instance: Optional["RelationMapper"] = None
_instance_lock = threading.Lock()

# phrase -> relation_type, longest phrases first so "reports to" wins over "to"
_RELATION_KEYWORDS = [
    ("reports to", "reports_to"),
    ("works with", "colleague_of"),
    ("works on", "works_on"),
    ("working on", "works_on"),
    ("part of", "part_of"),
    ("belongs to", "part_of"),
    ("built by", "created_by"),
    ("created by", "created_by"),
    ("built", "created"),
    ("created", "created"),
    ("manages", "manages"),
    ("managed by", "managed_by"),
    ("uses", "uses"),
    ("using", "uses"),
    ("depends on", "depends_on"),
    ("owns", "owns"),
    ("assigned to", "assigned_to"),
    ("met with", "met_with"),
    ("talked to", "talked_with"),
    ("talked with", "talked_with"),
]

_SENTENCE_SPLIT_PATTERN = re.compile(r"[.!?\n]+")

DEFAULT_RELATION = "mentioned_with"


class RelationMapper:
    """(text, entities) -> list of {"source", "target", "relation_type", "context"} pairs."""

    def map_relations(self, text: str, entities: List[Dict]) -> List[Dict]:
        if len(entities) < 2:
            return []

        relations: List[Dict] = []
        for sentence, sent_start, sent_end in self._sentences(text):
            in_sentence = [e for e in entities if sent_start <= e["start"] < sent_end]
            if len(in_sentence) < 2:
                continue
            in_sentence.sort(key=lambda e: e["start"])
            for i in range(len(in_sentence)):
                for j in range(i + 1, len(in_sentence)):
                    source, target = in_sentence[i], in_sentence[j]
                    if source["name"] == target["name"]:
                        continue
                    between = text[source["end"] : target["start"]]
                    relation_type = self._match_keyword(between)
                    relations.append(
                        {
                            "source": source["name"],
                            "target": target["name"],
                            "relation_type": relation_type,
                            "context": sentence.strip()[:200],
                        }
                    )
        return relations

    @staticmethod
    def _match_keyword(between_text: str) -> str:
        lowered = between_text.lower()
        for phrase, relation_type in _RELATION_KEYWORDS:
            if phrase in lowered:
                return relation_type
        return DEFAULT_RELATION

    @staticmethod
    def _sentences(text: str):
        """Yields (sentence_text, start_offset, end_offset) for each
        rough sentence in text, offsets aligned to the original string
        so they line up with entity_extractor.py's match spans."""
        pos = 0
        for piece in _SENTENCE_SPLIT_PATTERN.split(text):
            start = text.index(piece, pos) if piece else pos
            end = start + len(piece)
            if piece.strip():
                yield piece, start, end
            pos = end


def get_relation_mapper() -> RelationMapper:
    """Process-wide RelationMapper singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = RelationMapper()
    return _instance
