"""ChromaDB client
===============
🆓 ChromaDB-backed vector store - an optional, higher-quality alternative
to memory/vector_db/vector_store.py's plain-SQLite similarity search.
Same public shape (add / similarity_search) so memory/vector_db/__init__.py
can swap this in transparently when chromadb is installed, and
ai/rag_engine.py doesn't need to know or care which backend is live.

Persists to storage/chroma/ (already an existing, git-ignored folder in
this project - see storage/__init__.py) so it survives restarts, using
Chroma's own on-disk PersistentClient rather than the ephemeral in-memory
client.

Falls back gracefully: if chromadb isn't installed, HAS_CHROMADB is False
and callers should use a different backend (see
memory/vector_db/__init__.py.get_vector_store()).
"""

from pathlib import Path
from typing import Dict

from ai.embeddings import embed

PERSIST_DIR = Path(__file__).resolve().parents[2] / "storage" / "chroma"

try:
    import chromadb

    HAS_CHROMADB = True
except Exception:
    chromadb = None
    HAS_CHROMADB = False


class ChromaVectorStore:
    """Store text + embedding in a persistent Chroma collection, and run
    similarity search over it. Raises RuntimeError at construction if
    chromadb isn't installed - callers should check HAS_CHROMADB first."""

    def __init__(self, collection_name: str = "ultron_memory"):
        if not HAS_CHROMADB:
            raise RuntimeError(
                "chromadb is not installed. Run `pip install chromadb` to use this backend, "
                "or use memory/vector_db/vector_store.py's SQLite fallback instead."
            )
        PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(PERSIST_DIR))
        self._collection = self._client.get_or_create_collection(name=collection_name)
        self._next_id = self._collection.count()

    def add(self, text: str, category: str = "general") -> Dict:
        """Embed and store a piece of text. We supply our own embedding
        (ai/embeddings.py) rather than Chroma's default embedding function,
        so this backend and vector_store.py's SQLite backend stay
        interchangeable - same vectors, same similarity results, just a
        different storage/search engine underneath."""
        try:
            vec = embed(text)
            doc_id = str(self._next_id)
            self._next_id += 1
            self._collection.add(
                ids=[doc_id],
                embeddings=[vec],
                documents=[text],
                metadatas=[{"category": category}],
            )
            return {"success": True, "id": doc_id, "text": text, "category": category}
        except Exception as e:
            return {"error": str(e)}

    def similarity_search(self, query: str, top_k: int = 5) -> Dict:
        """Find the top_k stored texts most similar to `query`."""
        try:
            if self._collection.count() == 0:
                return {"query": query, "results": []}
            vec = embed(query)
            n = min(top_k, self._collection.count())
            res = self._collection.query(query_embeddings=[vec], n_results=n)

            results = []
            ids = res.get("ids", [[]])[0]
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            dists = res.get("distances", [[]])[0]
            for doc_id, text, meta, dist in zip(ids, docs, metas, dists):
                # Chroma returns a distance (lower = closer); convert to a
                # similarity score in the same ~[0, 1] range vector_store.py
                # uses, so callers can treat both backends the same way.
                score = max(0.0, 1.0 - dist)
                results.append(
                    {
                        "id": doc_id,
                        "text": text,
                        "category": (meta or {}).get("category", "general"),
                        "score": round(score, 4),
                    }
                )
            return {"query": query, "results": results}
        except Exception as e:
            return {"error": str(e)}

    def count(self) -> int:
        return self._collection.count()
