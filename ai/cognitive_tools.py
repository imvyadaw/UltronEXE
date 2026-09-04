"""Cognitive layer tool registry
=================================
Wires intelligence/decision_engine.py, goal_planner.py, intent_analyzer.py,
reasoning_engine.py, self_critique.py, verification_engine.py, model_trainer.py
into the AI tool-calling loop. These 7 modules were never imported anywhere
in the codebase before this - see core/assistant.py's ULTRON_COGNITIVE_LAYER_ENABLED
block for the always-on (non-tool-call) wiring; this module gives the model
direct callable access regardless of that flag, same split as
ai/system_config_tools.py.

Pattern mirrors ai/system_config_tools.py exactly: lazy singletons + a flat
COGNITIVE_TOOLS / COGNITIVE_DIRECT_HANDLERS pair, merged at the bottom of
ai/tools_schema.py and ai/tool_runtime.py respectively.

Naming: every tool is prefixed `cog_` to avoid colliding with any existing
decision/reasoning tools elsewhere in the schema.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


COGNITIVE_TOOLS = [
    _tool(
        "cog_decide_step",
        "Weigh a single proposed action/step before taking it - logs a structured "
        "decision record (risk level, reasoning) so it can be reviewed later with "
        "cog_record_outcome. Use before an ambiguous or risky action, not for routine tool calls.",
        {
            "step": {"type": "string", "description": "The action/step being considered"},
            "risk": {"type": "string", "enum": ["low", "medium", "high"], "description": "Risk level of this step"},
        },
        ["step"],
    ),
    _tool(
        "cog_record_outcome",
        "Record whether a previously-logged decision (from cog_decide_step) succeeded or failed.",
        {
            "decision_id": {"type": "integer", "description": "ID returned by cog_decide_step"},
            "success": {"type": "boolean", "description": "Whether the decision's outcome was successful"},
        },
        ["decision_id", "success"],
    ),
    _tool(
        "cog_plan_goal",
        "Break a multi-step user goal into a structured plan of sub-steps before executing it. "
        "Use for goals that need more than 1-2 tool calls to complete.",
        {
            "goal": {"type": "string", "description": "The goal to plan for"},
            "description": {"type": "string", "description": "Extra context/detail about the goal"},
            "register": {"type": "boolean", "description": "Whether to save this plan for later retrieval"},
        },
        ["goal"],
    ),
    _tool(
        "cog_recent_plans",
        "List recently registered goal plans.",
        {"limit": {"type": "integer", "description": "Max plans to return (default 20)"}},
        [],
    ),
    _tool(
        "cog_analyze_intent",
        "Analyze a piece of user text for underlying intent beyond its literal wording "
        "(useful for ambiguous or emotionally-loaded requests).",
        {
            "text": {"type": "string", "description": "Text to analyze"},
        },
        ["text"],
    ),
    _tool(
        "cog_reason",
        "Run a structured multi-step reasoning pass over a goal before answering - use for "
        "genuinely complex questions, not simple factual lookups.",
        {
            "goal": {"type": "string", "description": "The question or goal to reason through"},
            "complexity_hint": {"type": "string", "description": "Optional hint about how complex this is"},
        },
        ["goal"],
    ),
    _tool(
        "cog_self_critique",
        "Critique a drafted answer/output against the original goal before sending it to the "
        "user - flags gaps, unsupported claims, or missed requirements. Use for long or high-stakes answers.",
        {
            "goal": {"type": "string", "description": "The original goal/question"},
            "output": {"type": "string", "description": "The drafted answer/output to critique"},
        },
        ["goal", "output"],
    ),
    _tool(
        "cog_verify_claim",
        "Check a specific factual claim for internal consistency/support before stating it " "confidently to the user.",
        {
            "claim": {"type": "string", "description": "The claim to verify"},
        },
        ["claim"],
    ),
    _tool(
        "cog_train_weights",
        "Retrain the cognitive layer's lightweight context-weighting model from logged history.",
        {"context_type": {"type": "string", "description": "Optional context type to restrict training to"}},
        [],
    ),
]


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------
_instances: Dict[str, object] = {}


def _get(key: str):
    if key in _instances:
        return _instances[key]

    if key == "decision_engine":
        from intelligence.decision_engine import DecisionEngine

        obj = DecisionEngine()
    elif key == "goal_planner":
        from intelligence.goal_planner import GoalPlanner

        obj = GoalPlanner()
    elif key == "intent_analyzer":
        from intelligence.intent_analyzer import IntentAnalyzer

        obj = IntentAnalyzer()
    elif key == "reasoning_engine":
        from intelligence.reasoning_engine import CognitiveReasoningEngine

        obj = CognitiveReasoningEngine()
    elif key == "self_critique":
        from intelligence.self_critique import SelfCritique

        obj = SelfCritique()
    elif key == "verification_engine":
        from intelligence.verification_engine import ReasoningVerificationEngine

        obj = ReasoningVerificationEngine()
    elif key == "model_trainer":
        from intelligence.model_trainer import ModelTrainer

        obj = ModelTrainer()
    else:
        raise KeyError(f"Unknown cognitive tool key: {key}")

    _instances[key] = obj
    return obj


def _pick(d: dict, keys: list) -> dict:
    return {k: d[k] for k in keys if k in d and d[k] is not None}


def _h_decide_step(args: dict) -> Dict:
    return _get("decision_engine").decide_step(**_pick(args, ["step", "risk"]))


def _h_record_outcome(args: dict) -> Dict:
    return _get("decision_engine").record_outcome(**_pick(args, ["decision_id", "success"]))


def _h_plan_goal(args: dict) -> Dict:
    return _get("goal_planner").plan(**_pick(args, ["goal", "description", "register"]))


def _h_recent_plans(args: dict) -> Dict:
    return {"plans": _get("goal_planner").recent_plans(**_pick(args, ["limit"]))}


def _h_analyze_intent(args: dict) -> Dict:
    return _get("intent_analyzer").analyze(**_pick(args, ["text", "context"]))


def _h_reason(args: dict) -> Dict:
    return _get("reasoning_engine").reason(**_pick(args, ["goal", "complexity_hint"]))


def _h_self_critique(args: dict) -> Dict:
    return _get("self_critique").critique(**_pick(args, ["goal", "output"]))


def _h_verify_claim(args: dict) -> Dict:
    return _get("verification_engine").verify(**_pick(args, ["claim"]))


def _h_train_weights(args: dict) -> Dict:
    return _get("model_trainer").train(**_pick(args, ["context_type"]))


COGNITIVE_DIRECT_HANDLERS = {
    "cog_decide_step": _h_decide_step,
    "cog_record_outcome": _h_record_outcome,
    "cog_plan_goal": _h_plan_goal,
    "cog_recent_plans": _h_recent_plans,
    "cog_analyze_intent": _h_analyze_intent,
    "cog_reason": _h_reason,
    "cog_self_critique": _h_self_critique,
    "cog_verify_claim": _h_verify_claim,
    "cog_train_weights": _h_train_weights,
}
