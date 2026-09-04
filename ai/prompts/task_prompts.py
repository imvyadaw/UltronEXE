"""Task prompts
============
Reusable prompt templates for specific tasks, built on
ai/prompts/templates.PromptTemplate. Centralizing these (instead of each
module having its own inline prompt string, as ai/rag_engine.py's
RAG_PROMPT currently does) means ai/prompt_manager.py can track and
improve them in one place, and callers get consistent, tested phrasing.

Existing inline prompts (ai/rag_engine.py's RAG_PROMPT, etc.) are left as
they are - working code isn't moved just to move it - but any *new*
task prompt should be added here rather than inlined in the calling
module.
"""

from ai.prompts.templates import PromptTemplate, TemplateRegistry

PLANNING_PROMPT = PromptTemplate(
    name="planning",
    description="Break a user goal down into an ordered list of concrete steps/tool calls.",
    template=(
        "You are planning how to accomplish the following goal for the user:\n"
        "{goal}\n\n"
        "Available tools: {available_tools}\n\n"
        "Break this down into a short, ordered list of concrete steps. Each step should "
        "either be a tool call (name + arguments) or a reasoning step if no tool applies. "
        "Be concise - do not add steps that aren't necessary to reach the goal."
    ),
)

REASONING_PROMPT = PromptTemplate(
    name="chain_of_thought",
    description="Think step-by-step through a question before answering.",
    template=("Think through this step-by-step, then give a final answer.\n\n" "Question: {question}\n\n" "Reasoning:"),
)

SUMMARIZE_PROMPT = PromptTemplate(
    name="summarize",
    description="Summarize a block of text to a target length.",
    template="Summarize the following in {max_sentences} sentence(s), keeping only the key point(s):\n\n{text}",
)

TOOL_SELECTION_PROMPT = PromptTemplate(
    name="tool_selection",
    description="Pick the single best tool for a user request from a candidate list.",
    template=(
        "User request: {request}\n\n"
        "Candidate tools:\n{tool_descriptions}\n\n"
        "Which single tool (by exact name) best handles this request? If none apply, "
        'answer "none". Answer with just the tool name, nothing else.'
    ),
)

MULTI_AGENT_DELEGATION_PROMPT = PromptTemplate(
    name="multi_agent_delegation",
    description="Decide which specialized agent should handle a sub-task.",
    template=(
        "Sub-task: {subtask}\n\n"
        "Available agents: {agent_list}\n\n"
        "Which agent is best suited to this sub-task? Answer with just the agent name."
    ),
)

FEW_SHOT_PROMPT = PromptTemplate(
    name="few_shot",
    description="Answer a new case by pattern-matching against labeled examples.",
    template=("Here are some examples:\n{examples}\n\n" "Now handle this new case in the same style:\n{new_case}"),
)

RAG_ANSWER_PROMPT = PromptTemplate(
    name="rag_answer",
    description=(
        "Same phrasing as ai/rag_engine.py's inline RAG_PROMPT - registered here too so "
        "ai/prompt_manager.py can track/version it alongside the other task prompts."
    ),
    template=(
        "Answer the user's question using ONLY the context below if it's relevant. If the "
        "context doesn't contain the answer, say so plainly instead of guessing.\n\n"
        "Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    ),
)

# All task prompts registered together so callers can do
# `from ai.prompts.task_prompts import TASK_PROMPTS; TASK_PROMPTS.render("summarize", ...)`
# instead of importing each constant by name.
TASK_PROMPTS = TemplateRegistry()
for _tpl in (
    PLANNING_PROMPT,
    REASONING_PROMPT,
    SUMMARIZE_PROMPT,
    TOOL_SELECTION_PROMPT,
    MULTI_AGENT_DELEGATION_PROMPT,
    FEW_SHOT_PROMPT,
    RAG_ANSWER_PROMPT,
):
    TASK_PROMPTS.register(_tpl)
