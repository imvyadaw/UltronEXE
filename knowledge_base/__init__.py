"""Knowledge base
===============
Structured, source-attributed knowledge Ultron has learned by *reading*
things - as opposed to memory/long_term, which holds facts the *user*
told Ultron directly about themselves. Four linked record types, each
its own sub-folder of JSON files:

- facts/         atomic statements ("Delhi is the capital of India")
- concepts/      named entities/topics that facts and relationships attach to
- sources/       where a fact came from, with a trust score/tier
- relationships/ typed edges between two concepts (subject, predicate, object)

learning/knowledge_extractor.py is what populates this from raw text;
learning/source_validator.py and learning/confidence.py decide how much
to trust what goes in. This module is just the storage + linking layer -
it has no opinion on trust or extraction quality.
"""

from typing import Dict, List, Optional

from knowledge_base.store import RecordStore


class KnowledgeBase:
    """Facade over the four record stores, with the cross-references
    between them (fact -> source, fact -> concepts, relationship ->
    concepts) kept in one place instead of scattered across callers."""

    def __init__(self):
        self.facts = RecordStore("facts")
        self.concepts = RecordStore("concepts")
        self.sources = RecordStore("sources")
        self.relationships = RecordStore("relationships")

    # -- sources -------------------------------------------------------
    def add_source(self, name: str, url: Optional[str] = None, trust_score: float = 0.5, tier: str = "neutral") -> Dict:
        """Get the existing source record for `url` (or `name`, if no url)
        if one exists, otherwise create it."""
        existing = self.sources.find(url=url) or self.sources.find(name=name)
        if existing:
            return existing[0]
        return self.sources.add({"name": name, "url": url, "trust_score": trust_score, "tier": tier})

    # -- concepts --------------------------------------------------------
    def get_or_create_concept(self, name: str, description: str = "") -> Dict:
        matches = self.concepts.find(name=name)
        if matches:
            return matches[0]
        return self.concepts.add(
            {
                "name": name,
                "description": description,
                "fact_ids": [],
                "relationship_ids": [],
            }
        )

    def _link_concept_to_fact(self, concept_id: str, fact_id: str) -> None:
        concept = self.concepts.get(concept_id)
        if concept and fact_id not in concept.get("fact_ids", []):
            self.concepts.update(concept_id, fact_ids=concept.get("fact_ids", []) + [fact_id])

    def _link_concept_to_relationship(self, concept_id: str, relationship_id: str) -> None:
        concept = self.concepts.get(concept_id)
        if concept and relationship_id not in concept.get("relationship_ids", []):
            self.concepts.update(concept_id, relationship_ids=concept.get("relationship_ids", []) + [relationship_id])

    # -- facts -------------------------------------------------------
    def add_fact(self, statement: str, source_id: str, confidence: float, concepts: Optional[List[str]] = None) -> Dict:
        concept_ids = [self.get_or_create_concept(name)["id"] for name in (concepts or [])]
        fact = self.facts.add(
            {
                "statement": statement,
                "source_id": source_id,
                "confidence": confidence,
                "concept_ids": concept_ids,
                "corroborating_source_ids": [source_id],
            }
        )
        for cid in concept_ids:
            self._link_concept_to_fact(cid, fact["id"])
        return fact

    def corroborate_fact(self, fact_id: str, source_id: str, new_confidence: float) -> Dict:
        """Record that another source agrees with an existing fact and
        persist its updated confidence (learning/confidence.py computes
        `new_confidence` - this just saves it)."""
        fact = self.facts.get(fact_id)
        if fact is None:
            return {"error": f"No fact {fact_id}"}
        sources = fact.get("corroborating_source_ids", [])
        if source_id not in sources:
            sources.append(source_id)
        return self.facts.update(fact_id, confidence=new_confidence, corroborating_source_ids=sources)

    # -- relationships -----------------------------------------------------
    def add_relationship(
        self, subject: str, predicate: str, obj: str, confidence: float, source_id: Optional[str] = None
    ) -> Dict:
        subject_concept = self.get_or_create_concept(subject)
        object_concept = self.get_or_create_concept(obj)
        rel = self.relationships.add(
            {
                "subject_id": subject_concept["id"],
                "subject": subject,
                "predicate": predicate,
                "object_id": object_concept["id"],
                "object": obj,
                "confidence": confidence,
                "source_id": source_id,
            }
        )
        self._link_concept_to_relationship(subject_concept["id"], rel["id"])
        self._link_concept_to_relationship(object_concept["id"], rel["id"])
        return rel

    # -- query -----------------------------------------------------------
    def facts_about(self, concept_name: str) -> Dict:
        """Everything the knowledge base has linked to a named concept."""
        matches = self.concepts.find(name=concept_name)
        if not matches:
            return {"concept": concept_name, "found": False, "facts": [], "relationships": []}
        concept = matches[0]
        facts = [self.facts.get(fid) for fid in concept.get("fact_ids", [])]
        rels = [self.relationships.get(rid) for rid in concept.get("relationship_ids", [])]
        return {
            "concept": concept_name,
            "found": True,
            "description": concept.get("description", ""),
            "facts": [f for f in facts if f],
            "relationships": [r for r in rels if r],
        }

    def search(self, query: str) -> Dict:
        return {
            "query": query,
            "facts": self.facts.search_text(query, ["statement"]),
            "concepts": self.concepts.search_text(query, ["name", "description"]),
        }

    def stats(self) -> Dict:
        return {
            "facts": self.facts.count(),
            "concepts": self.concepts.count(),
            "sources": self.sources.count(),
            "relationships": self.relationships.count(),
        }
