"""
Patch generator
================
Turns one identified improvement (from improvement_engine.py) into an
actual code change - a full corrected version of the affected file -
by asking this project's existing LLM brain (ai/cloud_models/groq_client.py,
the same client agents/coder.py already uses) to fix it. Deliberately
narrow: one file per patch, no multi-file refactors, no dependency
changes - Priority 10's "detect weakness -> generate patch -> sandbox
test -> benchmark -> security test -> human approval -> deploy" flow
needs a patch small enough to review, not a rewrite.

Never touches the real project. propose() only reads from and apply()
only writes to whatever sandbox root evolution_manager.py hands it (a
throwaway tempfile.mkdtemp() copy made by sandbox.py) - never the
original project_root. Promoting an accepted sandbox back to
production is a separate, human-approved step this module does not
perform.

Same optional-dependency contract as agents/coder.py: no groq_client
module, no configured model, or any call failure all collapse to a
clean {"status": "generation_failed", ...} result rather than raising,
so evolution_manager.py's evaluate() can keep going (skip that one
issue) instead of the whole run dying.
"""

import difflib
from pathlib import Path
from typing import Dict, Optional


class PatchGenerator:
    """LLM-backed single-file patch proposals."""

    def propose(self, issue: Dict, sandbox_root) -> Dict:
        """issue: {"file": <path relative to project root, or absolute
        inside sandbox_root>, "type": str, "description": str (optional)}.

        Returns:
            {"status": "generation_failed" | "no_change" | "proposed",
             "file": str, "diff": str, "new_content": str | None,
             "error": str | None}

        Reads the current file out of sandbox_root, asks the brain for
        a corrected full version, and returns a proposal - does not
        write anything itself, see apply() for that.
        """
        file_path = self._resolve(issue.get("file", ""), sandbox_root)
        if file_path is None or not file_path.exists():
            return self._failed(issue, "file not found in sandbox")

        try:
            original = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return self._failed(issue, f"could not read file: {e}")

        fixed = self._call_brain(self._build_instruction(issue, original))
        if fixed is None:
            return self._failed(issue, "brain unavailable or call failed")

        fixed = self._strip_fences(fixed)
        if not fixed.strip():
            return self._failed(issue, "brain returned an empty file")
        if fixed.strip() == original.strip():
            return {"status": "no_change", "file": str(file_path), "diff": "", "new_content": None, "error": None}

        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                fixed.splitlines(keepends=True),
                fromfile=f"a/{issue.get('file', file_path.name)}",
                tofile=f"b/{issue.get('file', file_path.name)}",
            )
        )
        return {"status": "proposed", "file": str(file_path), "diff": diff, "new_content": fixed, "error": None}

    def apply(self, proposal: Dict) -> Dict:
        """Writes proposal["new_content"] to the sandbox file it points
        at. Only ever meant to be called against evolution_manager.py's
        throwaway sandbox copy - never the real project; this module has
        no idea what "the real project" even is, it just writes to
        whatever path the proposal carries. Refuses anything that isn't
        a "proposed" result with real content, so a caller can't
        accidentally apply a failed/no-change proposal."""
        if proposal.get("status") != "proposed" or not proposal.get("new_content"):
            return {"success": False, "error": "nothing to apply"}
        try:
            Path(proposal["file"]).write_text(proposal["new_content"], encoding="utf-8")
            return {"success": True, "error": None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _resolve(rel_path: str, sandbox_root) -> Optional[Path]:
        if not rel_path:
            return None
        p = Path(rel_path)
        return p if p.is_absolute() else Path(sandbox_root) / rel_path

    @staticmethod
    def _build_instruction(issue: Dict, original: str) -> str:
        kind = issue.get("type", "improvement")
        desc = issue.get("description", "")
        header = {
            "syntax_fix": (
                f"Fix the Python syntax error in this file so it compiles cleanly. " f"Reported error: {desc}"
                if desc
                else "Fix the Python syntax error in this file so it compiles cleanly."
            ),
        }.get(kind, f"Apply this improvement to the file: {desc or kind}.")
        return (
            f"{header}\n"
            "Reply with the COMPLETE corrected file content only - no prose, "
            "no explanation, no markdown code fences before or after. Change "
            "as little as possible; preserve everything not directly related "
            "to the fix.\n\n"
            f"--- current file content ---\n{original}"
        )

    @staticmethod
    def _strip_fences(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return text

    @staticmethod
    def _failed(issue: Dict, error: str) -> Dict:
        return {
            "status": "generation_failed",
            "file": issue.get("file", ""),
            "diff": "",
            "new_content": None,
            "error": error,
        }

    @staticmethod
    def _call_brain(user_message: str) -> Optional[str]:
        """Lazily calls ai/cloud_models/groq_client.py's UltronGroqClient.
        chat_with_tools(user_message: str, tool_callback=None) -> str -
        its REAL signature. (Note for whoever touches agents/coder.py
        next: CoderAgent._call_brain() there calls this same method with
        messages=/tools= keyword arguments that don't exist on it, so
        every CoderAgent call raises TypeError, gets swallowed by its
        own try/except, and CoderAgent silently reports itself as
        permanently unavailable. Not fixed here to keep this patch
        scoped to self_evolution/, but it's the same bug class and
        should get the same fix: drop the messages=/tools= kwargs and
        just pass the prompt string.)
        Returns None on any missing module, missing client, or call
        failure, so propose() above can collapse cleanly to
        "generation_failed" instead of raising."""
        try:
            from ai.cloud_models.groq_client import get_ultron_client
        except Exception:
            return None
        try:
            client = get_ultron_client()
            response = client.chat_with_tools(user_message)
            return response if isinstance(response, str) and response.strip() else None
        except Exception:
            return None
