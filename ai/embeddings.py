"""Embeddings
==========
Generates a fixed-size numeric vector for a piece of text so
memory/vector_db/ can do similarity search.

Two backends:
- sentence-transformers (if installed) - real neural embeddings, best quality.
- Hashing-trick bag-of-words (always available, zero extra dependencies) -
  each word is hashed into one of N buckets and counted, then the vector
  is L2-normalized. This is a lightweight, fully offline fallback: it
  captures shared vocabulary between texts (good enough for "did I already
  save a note like this" / "find past notes about X"), but it is not a
  semantic embedding in the neural-network sense - synonyms won't match.
"""

import hashlib
import math
import re
from typing import List

# Must match all-MiniLM-L6-v2's real output width (384), not an arbitrary
# round number - the hash-trick fallback below has to produce vectors the
# same length as the real model's, or cosine_similarity() silently breaks
# (wrong result or ValueError) the moment a caller mixes a vector saved by
# one backend with a query embedded by the other (e.g. hash-fallback
# vectors saved before sentence-transformers was installed, queried again
# after). Was hardcoded to 256 before this fix.
VECTOR_SIZE = 384

try:
    from sentence_transformers import SentenceTransformer

    _model = SentenceTransformer("all-MiniLM-L6-v2")
    HAS_SENTENCE_TRANSFORMERS = True
except Exception:
    _model = None
    HAS_SENTENCE_TRANSFORMERS = False

_WORD_RE = re.compile(r"[a-z0-9]+")


def _hash_embed(text: str, size: int = VECTOR_SIZE) -> List[float]:
    """Deterministic hashing-trick bag-of-words vector. No dependencies."""
    vec = [0.0] * size
    words = _WORD_RE.findall(text.lower())
    for word in words:
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        vec[h % size] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def embed(text: str) -> List[float]:
    """Return an embedding vector for `text`. Uses sentence-transformers if
    available, otherwise the offline hashing-trick fallback above."""
    if not text:
        return [0.0] * VECTOR_SIZE
    if HAS_SENTENCE_TRANSFORMERS:
        try:
            return _model.encode(text).tolist()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ai.embeddings.embed")
    return _hash_embed(text)


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
