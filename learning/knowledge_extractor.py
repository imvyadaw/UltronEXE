"""Knowledge extractor
====================
Turns a chunk of raw text (a web page, an article, a pasted paragraph)
into structured knowledge_base/ records: atomic facts, the concepts
they touch, and typed relationships between concepts - each stamped
with a source and a confidence score.

Pipeline for extract():
    1. learning.source_validator.SourceValidator scores/records where
       this text came from.
    2. An LLM pass (ai/llm/model_factory.ModelFactory - the same free-
       provider convenience layer ai/planning.py and ai/rag_engine.py
       use) asks for facts, concepts and subject-predicate-object
       relationships as JSON. If no free LLM provider is configured,
       falls back to a much dumber heuristic (one fact per sentence, no
       relationships) so the pipeline still produces *something*
       offline, the same fallback philosophy as ai/embeddings.py.
    3. Each candidate fact is checked against existing facts (cosine
       similarity via ai/embeddings, the same trick memory/vector_db
       uses) - a near-duplicate of an existing fact is treated as
       corroboration (learning.confidence.corroborate) instead of a new
       row, so the knowledge base doesn't fill up with the same claim
       restated by ten different sources.
    4. Everything genuinely new is scored with learning.confidence.score()
       and written to knowledge_base/ via KnowledgeBase.
"""

import json
import re
from typing import Dict, List, Optional

from ai.llm.model_factory import ModelFactory
from ai.embeddings import embed, cosine_similarity
from core.logger import get_logger
from knowledge_base import KnowledgeBase
from learning.source_validator import SourceValidator
from learning import confidence as confidence_scoring

logger = get_logger("knowledge_extractor")

DUPLICATE_SIMILARITY_THRESHOLD = 0.92
HEURISTIC_FALLBACK_CONFIDENCE = 0.4
MIN_SENTENCE_LENGTH = 25

EXTRACTION_PROMPT = """Read the text below and extract structured knowledge from it.

Return ONLY valid JSON (no markdown fences, no commentary) matching this shape:
{{
  "facts": [{{"statement": "...", "concepts": ["...", "..."], "confidence": 0.0}}],
  "relationships": [{{"subject": "...", "predicate": "...", "object": "...", "confidence": 0.0}}]
}}

Rules:
- Only include facts actually stated or clearly implied by the text, not outside knowledge.
- "statement" must be a single, self-contained sentence that makes sense with no other context.
- "confidence" is YOUR certainty (0-1) that the text asserts this, not whether it's true.
- Keep "concepts" to short noun phrases (people, places, organizations, topics) - 1-4 per fact.
- If nothing extractable is in the text, return {{"facts": [], "relationships": []}}.

Text:
{text}
"""


class KnowledgeExtractor:
    """Extracts facts/concepts/relationships from text and files new ones
    into the KnowledgeBase, corroborating existing ones instead of
    duplicating them."""

    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb = kb or KnowledgeBase()
        self.validator = SourceValidator(self.kb)
        try:
            self.llm = ModelFactory()
        except Exception as e:
            logger.warning(f"No LLM provider available for extraction, using heuristic fallback: {e}")
            self.llm = None

    def extract(self, text: str, source_name: str, source_url: Optional[str] = None) -> Dict:
        """Extract facts/relationships from `text` and store the new ones.
        Returns a summary of what was added vs corroborated."""
        if not text or not text.strip():
            return {"error": "No text provided"}
        try:
            source = self.validator.validate(name=source_name, url=source_url)
            if "error" in source:
                return source

            candidates = self._extract_candidates(text)

            new_facts, corroborated_facts = [], []
            for candidate in candidates.get("facts", []):
                statement = (candidate.get("statement") or "").strip()
                if not statement:
                    continue
                result = self._ingest_fact(
                    statement=statement,
                    concepts=candidate.get("concepts") or [],
                    extraction_confidence=candidate.get("confidence", 0.6),
                    source=source,
                )
                bucket = corroborated_facts if result["corroborated"] else new_facts
                bucket.append(result["fact"])

            relationships = []
            for rel in candidates.get("relationships", []):
                if not (rel.get("subject") and rel.get("predicate") and rel.get("object")):
                    continue
                conf = confidence_scoring.score(rel.get("confidence", 0.5), source["trust_score"])
                relationships.append(
                    self.kb.add_relationship(rel["subject"], rel["predicate"], rel["object"], conf, source["id"])
                )

            return {
                "source": source,
                "facts_added": len(new_facts),
                "facts_corroborated": len(corroborated_facts),
                "relationships_added": len(relationships),
                "new_facts": new_facts,
                "corroborated_facts": corroborated_facts,
                "relationships": relationships,
            }
        except Exception as e:
            logger.error(f"extract() failed: {e}")
            return {"error": str(e)}

    # -- fact ingestion --------------------------------------------------
    def _ingest_fact(self, statement: str, concepts: List[str], extraction_confidence: float, source: Dict) -> Dict:
        """Store `statement` as a new fact, or - if it's a near-duplicate
        of an existing fact - corroborate that one instead."""
        duplicate = self._find_duplicate(statement)
        if duplicate:
            existing_sources = len(duplicate.get("corroborating_source_ids", []))
            new_confidence = confidence_scoring.corroborate(
                duplicate.get("confidence", 0.5), existing_sources, source["trust_score"]
            )
            updated = self.kb.corroborate_fact(duplicate["id"], source["id"], new_confidence)
            return {"fact": updated, "corroborated": True}

        conf = confidence_scoring.score(extraction_confidence, source["trust_score"], corroborating_sources=1)
        fact = self.kb.add_fact(statement, source["id"], conf, concepts=concepts)
        return {"fact": fact, "corroborated": False}

    def _find_duplicate(self, statement: str) -> Optional[Dict]:
        """Cosine-similarity check against existing facts. Fine at
        personal-assistant scale (hundreds to low thousands of facts) -
        the same brute-force-in-Python trade-off memory/vector_db makes
        at larger scale."""
        candidate_vec = embed(statement)
        best, best_score = None, 0.0
        for fact in self.kb.facts.list_all():
            similarity = cosine_similarity(candidate_vec, embed(fact["statement"]))
            if similarity > best_score:
                best, best_score = fact, similarity
        return best if best and best_score >= DUPLICATE_SIMILARITY_THRESHOLD else None

    # -- extraction backends ---------------------------------------------
    def _extract_candidates(self, text: str) -> Dict:
        if self.llm is not None:
            try:
                raw = self.llm.complete(EXTRACTION_PROMPT.format(text=text[:8000]), temperature=0.2, max_tokens=1200)
                parsed = self._parse_json(raw)
                if parsed is not None:
                    return parsed
                logger.warning("LLM extraction returned unparseable JSON, falling back to heuristic")
            except Exception as e:
                logger.warning(f"LLM extraction failed, falling back to heuristic: {e}")
        return self._heuristic_extract(text)

    @staticmethod
    def _parse_json(raw: str) -> Optional[Dict]:
        cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            data = json.loads(cleaned)
            if not isinstance(data, dict):
                return None
            data.setdefault("facts", [])
            data.setdefault("relationships", [])
            return data
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _heuristic_extract(text: str) -> Dict:
        """No-LLM fallback: one fact per reasonably substantial sentence,
        no concepts/relationships. Confidence is capped low since nothing
        has checked these are genuine standalone assertions."""
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        facts = [
            {"statement": s.strip(), "concepts": [], "confidence": HEURISTIC_FALLBACK_CONFIDENCE}
            for s in sentences
            if len(s.strip()) > MIN_SENTENCE_LENGTH
        ]
        return {"facts": facts, "relationships": []}
