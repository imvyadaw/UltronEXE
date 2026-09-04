"""
PHASE 30 - EXTENDED TOOLS (audit fix, item #4, safe batch)
=============================================================
The deep-connectivity audit found 20 top-level packages (~14,000 lines)
that were fully implemented but never imported anywhere - the model
couldn't use any of it. This file wires the packages whose capabilities
are safe to expose directly to the model: local-only, no new-network-
surface, no ability to act on the outside world beyond what a normal
tool call already does.

  - reasoning/           -> check_fact
  - advanced_memory/      -> recall_memory, remember_event
  - quantum_dashboard/    -> get_live_metrics
  - command/              -> get_ultron_status, get_activity_report
  - display/screen_popup  -> show_popup_alert (cross-platform fallback;
                              show_notification in ai/tools_schema.py is
                              the Windows-native toast - this covers
                              Linux/Mac and headless-log fallback)
  - mouth/natural_speak   -> speak_text (offline pyttsx3 path; separate
                              from whatever cloud/voice/tts.py already
                              drives normal spoken replies)
  - skill_creator/        -> draft_new_skill (generate + sandbox-test +
                              statically validate; deliberately does NOT
                              auto-deploy - see skill_creator/__init__.py's
                              own docstring on why every install stays a
                              human-confirmed action)

Packages with real-world reach (device control, web automation, remote
network access, OS-level hooks) are wired separately in
ai/phase30_gated_tools.py, gated behind env flags off by default - same
convention this project already uses for ULTRON_AUTONOMY_ENABLED /
ULTRON_ORCHESTRATOR_ENABLED.
"""

from typing import Dict


def _check_fact(args: Dict) -> Dict:
    try:
        from reasoning.fact_checker import get_fact_checker

        result = get_fact_checker().check(str(args.get("claim", "")), top_k=int(args.get("top_k", 5)))
        entry_id = None
        try:
            # P2 - Evidence Ledger: persist every check so confidence and
            # source reliability can be tracked over time and "why did you
            # believe X" can be answered later. Best-effort - a ledger
            # failure must never break the fact-check response itself.
            from intelligence.evidence_ledger import get_evidence_ledger

            entry = get_evidence_ledger().log_fact_check_result(result)
            entry_id = entry.get("id")
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ai.phase30_extended_tools._check_fact")
        return {
            "success": True,
            "claim": result.claim,
            "verdict": result.verdict,
            "confidence": result.confidence,
            "evidence_count": len(result.evidence),
            "ledger_entry_id": entry_id,
        }
    except Exception as e:
        return {"success": False, "error": f"Fact check failed: {e}"}


def _recall_memory(args: Dict) -> Dict:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"success": False, "error": "No query provided."}
    try:
        from advanced_memory.episodic_memory import AdvancedEpisodicMemory

        mem = AdvancedEpisodicMemory()
        result = mem.recall_similar(query, top_k=int(args.get("top_k", 5)))
        return {"success": True, **result} if isinstance(result, dict) else {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": f"Memory recall failed: {e}"}


def _remember_event(args: Dict) -> Dict:
    event = str(args.get("event", "")).strip()
    if not event:
        return {"success": False, "error": "No event text provided."}
    try:
        from advanced_memory.episodic_memory import AdvancedEpisodicMemory

        mem = AdvancedEpisodicMemory()
        result = mem.record_event(
            event,
            context=str(args.get("context", "")),
            tags=str(args.get("tags", "")),
            importance=float(args.get("importance", 0.5)),
        )
        return {"success": True, **result} if isinstance(result, dict) else {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": f"Recording event failed: {e}"}


def _get_live_metrics(args: Dict) -> Dict:
    try:
        from quantum_dashboard.real_time_metrics import RealTimeMetrics

        snap = RealTimeMetrics().snapshot()
        return {"success": True, **snap.to_dict()}
    except Exception as e:
        return {"success": False, "error": f"Metrics snapshot failed: {e}"}


def _get_ultron_status(args: Dict) -> Dict:
    try:
        from command.control_panel import ControlPanel

        return {"success": True, **ControlPanel().status()}
    except Exception as e:
        return {"success": False, "error": f"Status lookup failed: {e}"}


def _get_activity_report(args: Dict) -> Dict:
    try:
        from command.control_panel import ControlPanel

        report = ControlPanel().report(period=str(args.get("period", "daily")))
        return {"success": True, **report}
    except Exception as e:
        return {"success": False, "error": f"Report generation failed: {e}"}


def _show_popup_alert(args: Dict) -> Dict:
    message = str(args.get("message", "")).strip()
    if not message:
        return {"success": False, "error": "No message provided."}
    try:
        from display.screen_popup import ScreenPopup

        popup = ScreenPopup()
        shown = popup.show(
            message,
            title=str(args.get("title", "Ultron")),
            auto_close_seconds=int(args.get("auto_close_seconds", 8)),
        )
        return {"success": True, "shown_on_screen": shown, "available": popup.is_available()}
    except Exception as e:
        return {"success": False, "error": f"Popup failed: {e}"}


def _speak_text(args: Dict) -> Dict:
    text = str(args.get("text", "")).strip()
    if not text:
        return {"success": False, "error": "No text provided."}
    try:
        from mouth.natural_speak import NaturalSpeak

        speaker = NaturalSpeak()
        if not speaker.is_available():
            return {"success": False, "error": "Offline TTS engine (pyttsx3) not available on this system."}
        spoke = speaker.speak(text, rate=int(args.get("rate", 175)), volume=float(args.get("volume", 1.0)))
        return {"success": bool(spoke)}
    except Exception as e:
        return {"success": False, "error": f"Speech failed: {e}"}


def _draft_new_skill(args: Dict) -> Dict:
    """Generate + sandbox-test + statically validate a new skill from API
    docs already on disk. Deliberately does NOT deploy - returns the
    validation report and generated source so a human reviews it first,
    same as every other entry point into skill_creator/auto_deployer.py."""
    doc_path = str(args.get("api_doc_path", "")).strip()
    skill_name = str(args.get("skill_name", "")).strip()
    base_url = str(args.get("base_url", "")).strip()
    description = str(args.get("description", "")).strip()
    if not doc_path or not skill_name or not base_url:
        return {"success": False, "error": "api_doc_path, skill_name, and base_url are required."}

    try:
        from skill_creator.api_doc_reader import APIDocReader
        from skill_creator.skill_code_generator import SkillCodeGenerator, SkillSpec
        from skill_creator.sandbox_tester import SandboxTester
        from skill_creator.skill_validator import SkillValidator

        reader = APIDocReader()
        is_markdown = doc_path.lower().endswith((".md", ".markdown"))
        endpoints = reader.read_markdown(doc_path) if is_markdown else reader.read_openapi(doc_path)

        spec = SkillSpec(
            skill_name=skill_name,
            description=description,
            base_url=base_url,
            endpoints=endpoints,
        )
        source_code = SkillCodeGenerator().generate(spec)

        sandbox_result = SandboxTester().run(source_code)
        validation = SkillValidator().validate(source_code)

        return {
            "success": True,
            "skill_name": skill_name,
            "endpoints_found": len(endpoints),
            "generated_source": source_code,
            "sandbox_passed": getattr(sandbox_result, "ok", None),
            "validation_summary": validation.summary(),
            "has_critical_issues": validation.has_critical(),
            "note": "Not deployed. Review generated_source and validation_summary, "
            "then deploy explicitly via skill_creator.auto_deployer if it looks right.",
        }
    except Exception as e:
        return {"success": False, "error": f"Skill drafting failed: {e}"}


PHASE30_EXTENDED_DIRECT_HANDLERS = {
    "check_fact": _check_fact,
    "recall_memory": _recall_memory,
    "remember_event": _remember_event,
    "get_live_metrics": _get_live_metrics,
    "get_ultron_status": _get_ultron_status,
    "get_activity_report": _get_activity_report,
    "show_popup_alert": _show_popup_alert,
    "speak_text": _speak_text,
    "draft_new_skill": _draft_new_skill,
}


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
        },
    }


PHASE30_EXTENDED_TOOLS = [
    _tool(
        "check_fact",
        "Check how well-supported a factual claim is before stating it confidently. "
        "Returns a verdict (supported/weakly_supported/unverified/contradicted) with a confidence score.",
        {
            "claim": {"type": "string", "description": "The factual claim to check."},
            "top_k": {"type": "number", "description": "How much evidence to gather (default 5)."},
        },
        ["claim"],
    ),
    _tool(
        "recall_memory",
        "Search past recorded events/experiences for ones similar to a query (semantic recall).",
        {
            "query": {"type": "string", "description": "What to recall."},
            "top_k": {"type": "number", "description": "Max results (default 5)."},
        },
        ["query"],
    ),
    _tool(
        "remember_event",
        "Record a new event/experience into long-term episodic memory for later recall.",
        {
            "event": {"type": "string", "description": "What happened."},
            "context": {"type": "string", "description": "Extra context."},
            "tags": {"type": "string", "description": "Comma-separated tags."},
            "importance": {"type": "number", "description": "0.0-1.0, default 0.5."},
        },
        ["event"],
    ),
    _tool(
        "get_live_metrics",
        "Get a live system snapshot (CPU, memory, disk, network) for the dashboard.",
    ),
    _tool(
        "get_ultron_status",
        "Get Ultron's own current status summary (mode, personality, recent activity).",
    ),
    _tool(
        "get_activity_report",
        "Get a daily or weekly digest of what Ultron has been doing.",
        {"period": {"type": "string", "description": "'daily' or 'weekly'. Default 'daily'."}},
    ),
    _tool(
        "show_popup_alert",
        "Show an on-screen popup alert (cross-platform fallback for when native toast notifications aren't available).",
        {
            "message": {"type": "string", "description": "The alert message."},
            "title": {"type": "string", "description": "Popup title. Default 'Ultron'."},
            "auto_close_seconds": {"type": "number", "description": "Seconds before auto-close. Default 8."},
        },
        ["message"],
    ),
    _tool(
        "speak_text",
        "Speak text out loud using the offline TTS engine.",
        {
            "text": {"type": "string", "description": "Text to speak."},
            "rate": {"type": "number", "description": "Words per minute. Default 175."},
            "volume": {"type": "number", "description": "0.0-1.0. Default 1.0."},
        },
        ["text"],
    ),
    _tool(
        "draft_new_skill",
        "Generate a new skill from API docs already saved locally, sandbox-test it, and statically "
        "validate it for dangerous code. Does NOT auto-deploy - returns the draft + report for review.",
        {
            "api_doc_path": {
                "type": "string",
                "description": "Local path to the API doc (OpenAPI/Swagger JSON/YAML, or .md for markdown-style docs).",
            },
            "skill_name": {"type": "string", "description": "Name for the new skill."},
            "base_url": {"type": "string", "description": "Base URL of the API this skill calls."},
            "description": {"type": "string", "description": "What the skill should do."},
        },
        ["api_doc_path", "skill_name", "base_url"],
    ),
]
