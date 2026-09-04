"""
Persona agent tool wiring
===========================
PHASE_18_6_AI_AGENTS/AGENTS' analyst/researcher/teacher/writer/guard
agents are real, fully-implemented, and already have matching entries
in ai/tools_schema.py's TOOLS list (analyze_text_with_data_lens,
analyze_numbers, research_topic, verify_claim_with_sources,
explain_topic_for_learning, quiz_me_on_topic, draft_text, rewrite_text,
guard_review_content - 9 tools total), but none of them had a
ai/tool_runtime.py dispatch entry, so the model got "Unknown tool" for
every one of them despite the backend working fine.

NOTE: AGENTS/coder.py's generate/review/explain (write_code/review_code/
explain_code/fix_code) are NOT part of this file - those tool names
were already reachable before this fix (see ai/tools_schema.py's
"Keep this in sync..." note), so only the 9 analyst/researcher/teacher/
writer/guard tools listed above were actually missing. Same merge
pattern as ai/utility_tools_wire.py/ai/new_skills_tools.py.
"""

from typing import Dict

_analyst = None
_researcher = None
_teacher = None
_writer = None
_guard = None


def _get_analyst():
    global _analyst
    if _analyst is None:
        from agents.analyst import get_analyst

        _analyst = get_analyst()
    return _analyst


def _get_researcher():
    global _researcher
    if _researcher is None:
        from agents.researcher import get_researcher

        _researcher = get_researcher()
    return _researcher


def _get_teacher():
    global _teacher
    if _teacher is None:
        from agents.teacher import get_teacher

        _teacher = get_teacher()
    return _teacher


def _get_writer():
    global _writer
    if _writer is None:
        from agents.writer import get_writer

        _writer = get_writer()
    return _writer


def _get_guard():
    global _guard
    if _guard is None:
        from agents.guard import get_guard

        _guard = get_guard()
    return _guard


AGENTS_DIRECT_HANDLERS: Dict = {
    "analyze_text_with_data_lens": lambda a: _get_analyst().analyze_text(a.get("text", ""), a.get("question")),
    "analyze_numbers": lambda a: _get_analyst().analyze_numbers(a.get("data", []), a.get("interpret", True)),
    "research_topic": lambda a: _get_researcher().research(a.get("topic", ""), a.get("num_sources", 5)),
    "verify_claim_with_sources": lambda a: _get_researcher().verify_claim(a.get("claim", "")),
    "explain_topic_for_learning": lambda a: _get_teacher().explain(a.get("topic", ""), a.get("level", "beginner")),
    "quiz_me_on_topic": lambda a: _get_teacher().quiz(a.get("topic", ""), a.get("num_questions", 3)),
    "draft_text": lambda a: _get_writer().draft(a.get("task", ""), a.get("tone", "neutral"), a.get("length", "medium")),
    "rewrite_text": lambda a: _get_writer().rewrite(a.get("text", ""), a.get("instruction", "")),
    "guard_review_content": lambda a: _get_guard().review(a.get("content", ""), a.get("kind", "code")),
}
