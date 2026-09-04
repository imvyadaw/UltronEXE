"""
Chain of thought
================
A more deliberate, multi-pass reasoning engine than ai/reasoning.py's
single-shot chain-of-thought: it explicitly decomposes a hard question
into sub-questions, answers each one as its own LLM call (so long
reasoning chains don't get compressed/truncated into one response),
then synthesizes a final answer from the sub-answers. Each step is
kept in the returned trace for transparency/debugging.

Use ai/reasoning.py for a quick "think for a second" pass; use this
for genuinely multi-part problems (planning-adjacent, but the output
is an *answer* built from sub-answers rather than a list of tool
calls - see ai/planning.py for that).
"""

import json
from typing import Dict, List

from ai.ai_router import get_router

DECOMPOSE_PROMPT = """Break the following question or problem into 2-5 smaller
sub-questions that, once answered, make the original easy to answer.
Respond with ONLY a JSON array of strings, nothing else.

Question: {question}"""

ANSWER_SUBQUESTION_PROMPT = """Answer this sub-question concisely (2-4 sentences), as
one step of reasoning toward a larger question.

Larger question: {question}
Sub-question: {subquestion}"""

SYNTHESIZE_PROMPT = """You reasoned through this question step by step. Combine the
findings below into one clear, direct final answer.

Question: {question}

Findings:
{findings}

Final answer:"""


class ChainOfThought:
    """Decompose -> answer each part -> synthesize, with a full trace."""

    def run(self, question: str, max_subquestions: int = 5) -> Dict:
        trace: List[Dict] = []
        try:
            subquestions = self._decompose(question, max_subquestions)
            trace.append({"step": "decompose", "subquestions": subquestions})

            findings = []
            for sq in subquestions:
                answer = get_router().complete(
                    ANSWER_SUBQUESTION_PROMPT.format(question=question, subquestion=sq),
                    temperature=0.3,
                    max_tokens=250,
                )
                findings.append({"subquestion": sq, "answer": answer})
                trace.append({"step": "answer_subquestion", "subquestion": sq, "answer": answer})

            findings_text = "\n".join(f"- {f['subquestion']}: {f['answer']}" for f in findings)
            final_answer = get_router().complete(
                SYNTHESIZE_PROMPT.format(question=question, findings=findings_text),
                temperature=0.4,
                max_tokens=500,
            )
            trace.append({"step": "synthesize", "final_answer": final_answer})

            return {"question": question, "final_answer": final_answer, "trace": trace}
        except Exception as e:
            return {"error": str(e), "trace": trace}

    def _decompose(self, question: str, max_subquestions: int) -> List[str]:
        text = get_router().complete(DECOMPOSE_PROMPT.format(question=question), temperature=0.2, max_tokens=300)
        text = text.strip().strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
        try:
            subquestions = json.loads(text)
            if isinstance(subquestions, list):
                return [str(s) for s in subquestions[:max_subquestions]]
        except json.JSONDecodeError:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ai.chain_of_thought._decompose")
        # Fallback: treat the whole question as a single sub-question if
        # the model didn't return clean JSON.
        return [question]
