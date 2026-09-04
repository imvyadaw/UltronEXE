"""
Legacy / text-based tool-call extraction
=========================================
Every LLM client (ai/cloud_models/groq_client.py, nvidia_client.py,
deepseek_client.py, openrouter_client.py, ai/local_models/manager.py) is
supposed to get tool calls back as *structured* data (Groq/OpenAI's
`message.tool_calls`, or Ollama's `tool_calls` field). This module handles
the fallback case: a model that was given `tools=` still answers in plain
text instead of using the structured field.

Two text shapes are recognized:

1. A JSON blob, optionally fenced in ```json ... ``` or ``` ... ```, with a
   "tool" key - e.g. {"tool": "get_cpu_ram_usage"}. This is the shape a
   model imitating Ultron's own internal dict format produces.

2. Meta's Llama-3.1 built-in text tool-call template:
   <function=get_cpu_ram_usage>{"arg": "val"}</function>
   Smaller/quantized Llama models (llama-3.1-8b-instant on Groq is the
   common offender) frequently fall back to emitting this literal template
   as plain content instead of Groq's own tool_calls field - and, worse,
   often keep writing *past* the tag with a fabricated "answer" (e.g. a
   made-up RAM percentage) instead of waiting for the real tool result.
   extract() finds the tag, and split_at_tool_call() lets a caller discard
   everything from the tag onward so that fabricated trailing text never
   reaches the user or the conversation history.
"""

import json
import re
from typing import Dict, Optional, Tuple

_FUNCTION_TAG_RE = re.compile(
    r"<function\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*>\s*(\{.*?\})?\s*</function>",
    re.DOTALL,
)

_JSON_PATTERNS = [
    re.compile(r"```json\s*(.*?)\s*```", re.DOTALL),
    re.compile(r"```\s*(.*?)\s*```", re.DOTALL),
    re.compile(r'(\{[^{}]*"tool"[^{}]*\})', re.DOTALL),
]


def extract(response: str) -> Optional[Dict]:
    """Return {"tool": name, **args} if `response` contains a text-based
    tool call in either recognized shape, else None."""
    if not response:
        return None
    response = response.strip()

    func_match = _FUNCTION_TAG_RE.search(response)
    if func_match:
        name = func_match.group(1)
        args_raw = func_match.group(2)
        try:
            args = json.loads(args_raw) if args_raw else {}
        except json.JSONDecodeError:
            args = {}
        return {"tool": name, **args}

    for pattern in _JSON_PATTERNS:
        match = pattern.search(response)
        if match:
            try:
                data = json.loads(match.group(1).strip())
                if "tool" in data:
                    return data
            except json.JSONDecodeError:
                continue

    try:
        data = json.loads(response)
        if "tool" in data:
            return data
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("ai.legacy_tool_call.extract")

    return None


def split_at_tool_call(response: str) -> Tuple[str, bool]:
    """Return (visible_text, found) where visible_text is everything
    BEFORE a detected tool call - trimming any fabricated text a model
    wrote after the tag/JSON instead of waiting for the real result.
    found is False (and visible_text == response) if nothing matched."""
    if not response:
        return response, False

    func_match = _FUNCTION_TAG_RE.search(response)
    if func_match:
        return response[: func_match.start()].strip(), True

    for pattern in _JSON_PATTERNS:
        match = pattern.search(response)
        if match:
            try:
                data = json.loads(match.group(1).strip())
                if "tool" in data:
                    return response[: match.start()].strip(), True
            except json.JSONDecodeError:
                continue

    try:
        data = json.loads(response.strip())
        if "tool" in data:
            return "", True
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("ai.legacy_tool_call.split_at_tool_call")

    return response, False
