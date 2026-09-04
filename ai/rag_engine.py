"""
RAG engine
==========
Retrieval-augmented generation over Ultron's own memory: pulls the most
relevant stored notes/facts/vectors for a query (memory/vector_db +
memory/long_term), stuffs them into a prompt as context, then asks
ai.ai_router for a grounded answer that cites which memories it used.

This is what makes "what did I tell you about my flight last week"
work well instead of relying on whatever happens to still be in the
chat window's history.
"""

from typing import Dict, List

from ai.ai_router import get_router
from ai.prompts.system_prompts import SYSTEM_PROMPT_GROUNDED
from memory.vector_db.vector_store import VectorStore
from memory.long_term.long_term import LongTermMemory

# get_router().complete() takes one plain-text prompt (no separate system
# message), so SYSTEM_PROMPT_GROUNDED's grounded/"say so plainly instead of
# guessing" instruction is folded straight into this prompt rather than
# duplicating that instruction here as its own free-floating string.
RAG_PROMPT = SYSTEM_PROMPT_GROUNDED + """

Answer the user's question using ONLY the context below if it's relevant.

Context:
{context}

Question: {question}

Answer:"""


class RAGEngine:
    """Retrieve relevant memories, then answer grounded in them."""

    def __init__(self):
        self.vectors = VectorStore()
        self.long_term = LongTermMemory()

    def retrieve(self, query: str, top_k: int = 5) -> Dict:
        """Just the retrieval step, exposed on its own for callers that
        want to inspect sources before generating an answer."""
        vector_hits = self.vectors.similarity_search(query, top_k)
        fact_hits = self.long_term.search(query)
        return {
            "query": query,
            "vector_matches": vector_hits.get("results", []),
            "fact_matches": fact_hits.get("results", []),
        }

    def answer(self, question: str, top_k: int = 5) -> Dict:
        """Retrieve relevant memories and generate an answer grounded in them."""
        try:
            retrieved = self.retrieve(question, top_k)
            context_lines: List[str] = []
            for hit in retrieved["vector_matches"]:
                context_lines.append(f"- (note, relevance {hit.get('score')}) {hit.get('text')}")
            for f in retrieved["fact_matches"]:
                context_lines.append(f"- (fact) {f.get('key')}: {f.get('value')}")

            context = "\n".join(context_lines) if context_lines else "(no relevant memories found)"
            answer_text = get_router().complete(
                RAG_PROMPT.format(context=context, question=question), temperature=0.3, max_tokens=500
            )
            return {
                "question": question,
                "answer": answer_text,
                "sources_used": len(context_lines),
                "context": context,
            }
        except Exception as e:
            return {"error": str(e)}
