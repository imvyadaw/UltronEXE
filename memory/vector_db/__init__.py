"""memory/vector_db package
=========================
Three interchangeable vector-store backends, all exposing the same
add(text, category) / similarity_search(query, top_k) shape:

    - vector_store.VectorStore    - plain SQLite, zero extra dependencies,
                                     always available (Phase 2 original).
    - chroma_client.ChromaVectorStore - free ChromaDB, if installed.
    - faiss_client.FaissVectorStore   - free FAISS, if installed (backup).

get_vector_store() picks the best one actually available at runtime, per
config.VECTOR_DB_BACKEND ("auto" = chroma -> faiss -> sqlite, or force one
by name). ai/rag_engine.py and anything else that just wants "a vector
store" should call this instead of importing VectorStore directly, so it
automatically benefits from a better backend if one is installed - with
zero code changes if it isn't.
"""

from core.logger import get_logger

try:
    from config import VECTOR_DB_BACKEND
except Exception:
    VECTOR_DB_BACKEND = "auto"

logger = get_logger("vector_db")

_store = None


def get_vector_store():
    """Return a process-wide singleton vector store: the best backend
    available, chosen once and reused (switching backends mid-process
    would mean two out-of-sync stores, so this doesn't re-check every
    call - restart Ultron after installing chromadb/faiss to pick it up)."""
    global _store
    if _store is not None:
        return _store

    backend = (VECTOR_DB_BACKEND or "auto").strip().lower()

    def _try_chroma():
        from memory.vector_db.chroma_client import ChromaVectorStore, HAS_CHROMADB

        if not HAS_CHROMADB:
            return None
        return ChromaVectorStore()

    def _try_faiss():
        from memory.vector_db.faiss_client import FaissVectorStore, HAS_FAISS

        if not HAS_FAISS:
            return None
        return FaissVectorStore()

    def _sqlite():
        from memory.vector_db.vector_store import VectorStore

        return VectorStore()

    order = {
        "chroma": [_try_chroma, _sqlite],
        "faiss": [_try_faiss, _sqlite],
        "sqlite": [_sqlite],
        "auto": [_try_chroma, _try_faiss, _sqlite],
    }.get(backend, [_try_chroma, _try_faiss, _sqlite])

    for builder in order:
        try:
            store = builder()
        except Exception as e:
            logger.warning("Vector store backend %s failed to initialize: %s", builder.__name__, e)
            store = None
        if store is not None:
            logger.info("Vector store backend selected: %s", store.__class__.__name__)
            _store = store
            return _store

    # _sqlite() never returns None (no optional dependency), so this line
    # is unreachable in practice - kept as a defensive final fallback.
    from memory.vector_db.vector_store import VectorStore

    _store = VectorStore()
    return _store
