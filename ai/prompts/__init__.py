"""ai/prompts package
===================
Was a single file (ai/prompts.py) through Phase 1/2; split into a package
in Phase 3 so system prompts, task-specific templates, and the generic
PromptTemplate helper each have their own module instead of one growing
file. This __init__ re-exports SYSTEM_PROMPT (and the two new variants)
so every existing `from ai.prompts import SYSTEM_PROMPT` elsewhere in the
codebase (ai/cloud_models/groq_client.py, ai/local_models/manager.py)
keeps working unchanged.

Layout:
    ai/prompts/system_prompts.py - SYSTEM_PROMPT and situational variants
    ai/prompts/task_prompts.py   - per-task templates (planning, RAG, ...)
    ai/prompts/templates.py      - PromptTemplate / TemplateRegistry helper
"""

from ai.prompts.system_prompts import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_CONCISE,
    SYSTEM_PROMPT_GROUNDED,
)
from ai.prompts.task_prompts import TASK_PROMPTS
from ai.prompts.ultron_proactive import PROACTIVE_SYSTEM_PROMPT, build_proactive_prompt

__all__ = [
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_CONCISE",
    "SYSTEM_PROMPT_GROUNDED",
    "TASK_PROMPTS",
    "PROACTIVE_SYSTEM_PROMPT",
    "build_proactive_prompt",
]
