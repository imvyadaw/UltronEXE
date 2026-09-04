"""AI Supercharger + upgrade-pack tool registry
=================================================
Wires all 10 new top-level packages from this batch into the AI
tool-calling loop:

  ai_supercharger/, translation_engine/, entertainment_engine/,
  predictive_mind/, decision_engine_2.0/, advanced_personality/,
  empathy_engine/, language_generation/, penetration_testing/,
  threat_hunting/

Same pattern as ai/security_control_tools.py and
ai/special_control_tools.py: lazy singletons where the underlying
module is a class, direct function calls where it's plain functions,
one flat SUPERCHARGER_TOOLS / SUPERCHARGER_DIRECT_HANDLERS pair,
merged at the bottom of ai/tools_schema.py and ai/tool_runtime.py.

Naming: every tool is prefixed `sc_` (supercharger).

TWO PACKAGES IN THIS BATCH HAVE A LITERAL "." IN THEIR FOLDER/FILE
NAME (decision_engine_2.0/ and entertainment_engine/movie_suggester_2.0.py)
as requested in the target tree - neither is reachable with a normal
Python `import` statement (see each package's own __init__.py for why).
This module loads decision_engine_2.0's two files directly via
importlib.util.spec_from_file_location; entertainment_engine's dotted
file is already re-exported as plain functions by
entertainment_engine/__init__.py (same importlib approach, done once
there), so this module just imports entertainment_engine normally.

penetration_testing's scan_target() and threat_hunting's file/URL
checks are read-only/defensive by design (see each package's own
docstring) but scan_target() still touches the network, so it stays
confirm-gated like every other network/state-touching tool in this
codebase, on top of its own mandatory authorized=True flag.
"""

import importlib.util as _ilu
import os as _os
from typing import Dict

_HERE = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # project root


def _load_by_path(alias: str, rel_path: str):
    spec = _ilu.spec_from_file_location(alias, _os.path.join(_HERE, rel_path))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's `_tool()` helper. Duplicated
    on purpose - avoids a circular import since tools_schema.py imports
    *from* this module."""
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


def _pick(d: dict, keys: list) -> dict:
    return {k: d[k] for k in keys if k in d and d[k] is not None}


# ---------------------------------------------------------------------------
# Lazy-loaded dotted-name modules (decision_engine_2.0/*)
# ---------------------------------------------------------------------------
_dotted_cache: Dict[str, object] = {}


def _mcda_module():
    if "mcda" not in _dotted_cache:
        _dotted_cache["mcda"] = _load_by_path(
            "decision_engine_2_0._mcda", "decision_engine_2.0/multi_criteria_decision.py"
        )
    return _dotted_cache["mcda"]


def _risk_reward_module():
    if "risk_reward" not in _dotted_cache:
        _dotted_cache["risk_reward"] = _load_by_path(
            "decision_engine_2_0._risk_reward", "decision_engine_2.0/risk_reward_calculator.py"
        )
    return _dotted_cache["risk_reward"]


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
SUPERCHARGER_TOOLS = [
    # -- ai_supercharger --
    _tool(
        "sc_ensemble_ask",
        "Ask multiple configured cloud AI backends the same question in parallel and combine/vote on the best answer. Use for factual questions worth double-checking, not routine chat.",
        {
            "prompt": {"type": "string"},
            "strategy": {"type": "string", "description": "'vote' (pick best) or 'merge' (synthesize)"},
        },
        ["prompt"],
    ),
    _tool(
        "sc_model_choose_backend",
        "Get the currently recommended cloud AI backend for a given message, based on live error/latency stats and complexity tiering.",
        {"user_message": {"type": "string"}},
    ),
    _tool(
        "sc_model_force_backend",
        "Pin the next N AI turns to a specific cloud backend (e.g. 'groq', 'gemini').",
        {"name": {"type": "string"}, "turns": {"type": "integer"}, "reason": {"type": "string"}},
        ["name"],
    ),
    # -- translation_engine --
    _tool(
        "sc_translate",
        "Translate text into a target language (e.g. 'english', 'hindi', 'hinglish', or any language name).",
        {"text": {"type": "string"}, "target_lang": {"type": "string"}, "source_lang": {"type": "string"}},
        ["text"],
    ),
    _tool(
        "sc_detect_language",
        "Detect whether text is English, Hindi (Devanagari), or Hinglish (romanized Hindi).",
        {"text": {"type": "string"}},
        ["text"],
    ),
    # -- entertainment_engine --
    _tool(
        "sc_mood_playlist",
        "Suggest a mood-based music playlist, either from an explicit mood or free text to detect the mood from.",
        {"mood": {"type": "string"}, "text": {"type": "string"}, "count": {"type": "integer"}},
    ),
    _tool(
        "sc_movie_suggest_v2",
        "Suggest movies for a mood/weather context, optionally personalized/filtered by a free-text preference string.",
        {
            "mood": {"type": "string"},
            "weather_context": {"type": "string"},
            "language": {"type": "string"},
            "count": {"type": "integer"},
            "preferences": {"type": "string"},
        },
    ),
    _tool(
        "sc_movie_night_bundle",
        "Get one combined 'movie night' answer: a top movie pick plus a matching mood playlist.",
        {
            "mood": {"type": "string"},
            "text": {"type": "string"},
            "weather_context": {"type": "string"},
            "preferences": {"type": "string"},
        },
    ),
    # -- predictive_mind --
    _tool(
        "sc_behavior_profile",
        "Get a summary of the user's observed usage patterns: top actions/categories, busiest hours, and current predicted routine.",
        {"top_n": {"type": "integer"}},
    ),
    _tool(
        "sc_predict_next_action",
        "Predict the most likely next action(s) the user is about to want, based on time-of-day and action-sequence patterns.",
        {"top_k": {"type": "integer"}},
    ),
    # -- decision_engine_2.0 --
    _tool(
        "sc_decision_mcda",
        "Weighted multi-criteria decision analysis: rank several options scored on several weighted criteria.",
        {
            "options": {"type": "array", "description": "[{name, scores: {criterion: value}}]"},
            "criteria": {"type": "object", "description": "{criterion: {weight, lower_is_better}}"},
        },
        ["options", "criteria"],
    ),
    _tool(
        "sc_decision_expected_value",
        "Compute the probability-weighted expected value across a set of outcome scenarios.",
        {"scenarios": {"type": "array", "description": "[{outcome, probability}]"}},
        ["scenarios"],
    ),
    _tool(
        "sc_decision_risk_reward",
        "Compute a simple risk/reward ratio given a potential loss and potential gain.",
        {"potential_loss": {"type": "number"}, "potential_gain": {"type": "number"}},
        ["potential_loss", "potential_gain"],
    ),
    _tool(
        "sc_decision_kelly",
        "Compute a capped Kelly-criterion bet-sizing fraction given a win probability and win/loss multiples.",
        {
            "win_probability": {"type": "number"},
            "win_multiple": {"type": "number"},
            "loss_multiple": {"type": "number"},
            "kelly_cap": {"type": "number"},
        },
        ["win_probability", "win_multiple"],
    ),
    # -- advanced_personality --
    _tool(
        "sc_detect_sarcasm",
        "Estimate whether a piece of text is likely sarcastic, with a confidence score and matched signals.",
        {"text": {"type": "string"}},
        ["text"],
    ),
    _tool(
        "sc_tell_joke",
        "Get a light joke, optionally from a specific category ('tech', 'general', 'motivational').",
        {"category": {"type": "string"}},
    ),
    # -- empathy_engine --
    _tool(
        "sc_empathy_state",
        "Map a detected emotion (or free text) into a valence/arousal state and a recommended response posture.",
        {"emotion": {"type": "string"}, "confidence": {"type": "number"}, "text": {"type": "string"}},
    ),
    _tool(
        "sc_empathy_reply",
        "Generate a short, warm supportive reply opener for a given posture or emotion/text.",
        {"posture": {"type": "string"}, "emotion": {"type": "string"}, "text": {"type": "string"}},
    ),
    # -- language_generation --
    _tool(
        "sc_style_analyze",
        "Analyze a writing sample into a measurable style profile (sentence length, vocabulary richness, punctuation habits, etc).",
        {"sample_text": {"type": "string"}},
        ["sample_text"],
    ),
    _tool(
        "sc_style_generate",
        "Generate new text for a prompt, written in the style of a given writing sample.",
        {"prompt": {"type": "string"}, "sample_text": {"type": "string"}, "max_tokens": {"type": "integer"}},
        ["prompt", "sample_text"],
    ),
    # -- penetration_testing (DEFENSIVE ONLY) --
    _tool(
        "sc_pentest_scan",
        "Run defensive/passive security checks (TLS cert, HTTP security headers, common-port reachability) against a host. "
        "ONLY for infrastructure you own or are explicitly authorized to test - requires authorized=true and confirm=true.",
        {
            "host": {"type": "string"},
            "authorized": {"type": "boolean"},
            "confirm": {"type": "boolean"},
            "include_ports": {"type": "boolean"},
            "check_url": {"type": "string"},
        },
        ["host", "authorized", "confirm"],
    ),
    # -- threat_hunting (DEFENSIVE ONLY) --
    _tool(
        "sc_hash_file",
        "Compute the SHA-256 and MD5 hash of a local file (read-only, never executes the file).",
        {"file_path": {"type": "string"}},
        ["file_path"],
    ),
    _tool(
        "sc_file_reputation",
        "Hash a local file and check that hash's reputation via VirusTotal if configured (never uploads the file itself).",
        {"file_path": {"type": "string"}},
        ["file_path"],
    ),
    _tool(
        "sc_url_reputation",
        "Run a structural heuristic risk check on a URL string (never fetches the URL's content).",
        {"url": {"type": "string"}},
        ["url"],
    ),
]


# ---------------------------------------------------------------------------
# Direct handlers
# ---------------------------------------------------------------------------
def _h_ensemble_ask(d):
    from ai_supercharger.multi_model_ensemble import get_ensemble_response

    return get_ensemble_response(**_pick(d, ["prompt", "strategy"]))


def _h_model_choose_backend(d):
    from ai_supercharger.dynamic_model_switcher import choose_backend

    return choose_backend(**_pick(d, ["user_message"]))


def _h_model_force_backend(d):
    from ai_supercharger.dynamic_model_switcher import force_backend

    force_backend(**_pick(d, ["name", "turns", "reason"]))
    return {"success": True, "forced_backend": d.get("name")}


def _h_translate(d):
    from translation_engine.realtime_translator import translate

    return translate(**_pick(d, ["text", "target_lang", "source_lang"]))


def _h_detect_language(d):
    from translation_engine.realtime_translator import detect_language

    return {"language": detect_language(d.get("text", ""))}


def _h_mood_playlist(d):
    from entertainment_engine.mood_playlist import suggest_playlist

    return suggest_playlist(**_pick(d, ["mood", "text", "count"]))


def _h_movie_suggest_v2(d):
    from entertainment_engine import suggest_movies_v2

    return suggest_movies_v2(**_pick(d, ["mood", "weather_context", "language", "count", "preferences"]))


def _h_movie_night_bundle(d):
    from entertainment_engine import movie_night_bundle

    return movie_night_bundle(**_pick(d, ["mood", "text", "weather_context", "preferences"]))


def _h_behavior_profile(d):
    from predictive_mind.user_behavior_predictor import get_behavior_profile

    return get_behavior_profile(**_pick(d, ["top_n"]))


def _h_predict_next_action(d):
    from predictive_mind.user_behavior_predictor import predict_next_action

    return {"predictions": predict_next_action(**_pick(d, ["top_k"]))}


def _h_decision_mcda(d):
    return _mcda_module().evaluate(**_pick(d, ["options", "criteria"]))


def _h_decision_expected_value(d):
    return _risk_reward_module().expected_value(**_pick(d, ["scenarios"]))


def _h_decision_risk_reward(d):
    return _risk_reward_module().risk_reward_ratio(**_pick(d, ["potential_loss", "potential_gain"]))


def _h_decision_kelly(d):
    return _risk_reward_module().kelly_fraction(
        **_pick(d, ["win_probability", "win_multiple", "loss_multiple", "kelly_cap"])
    )


def _h_detect_sarcasm(d):
    from advanced_personality.sarcasm_detector import detect_sarcasm

    return detect_sarcasm(d.get("text", ""))


def _h_tell_joke(d):
    from advanced_personality.humor_engine import get_joke

    return get_joke(**_pick(d, ["category"]))


def _h_empathy_state(d):
    from empathy_engine.emotion_simulator import simulate_emotional_state

    return simulate_emotional_state(**_pick(d, ["emotion", "confidence", "text"]))


def _h_empathy_reply(d):
    from empathy_engine.supportive_response import generate_supportive_reply

    return generate_supportive_reply(**_pick(d, ["posture", "emotion", "text"]))


def _h_style_analyze(d):
    from language_generation.style_emulation import analyze_style

    return analyze_style(d.get("sample_text", ""))


def _h_style_generate(d):
    from language_generation.style_emulation import generate_in_style

    return generate_in_style(**_pick(d, ["prompt", "sample_text", "max_tokens"]))


def _h_pentest_scan(d):
    if not d.get("confirm"):
        return {
            "success": False,
            "needs_confirmation": True,
            "preview": f"Would run defensive TLS/header/port checks against '{d.get('host')}'. "
            "Only proceed if you own or are explicitly authorized to test this host.",
        }
    from penetration_testing.vulnerability_scanner import scan_target

    return scan_target(**_pick(d, ["host", "authorized", "include_ports", "check_url"]))


def _h_hash_file(d):
    from threat_hunting.malware_analyzer import hash_file

    return hash_file(d.get("file_path"))


def _h_file_reputation(d):
    from threat_hunting.malware_analyzer import check_file_reputation

    return check_file_reputation(d.get("file_path"))


def _h_url_reputation(d):
    from threat_hunting.malware_analyzer import check_url_reputation

    return check_url_reputation(d.get("url"))


SUPERCHARGER_DIRECT_HANDLERS = {
    "sc_ensemble_ask": _h_ensemble_ask,
    "sc_model_choose_backend": _h_model_choose_backend,
    "sc_model_force_backend": _h_model_force_backend,
    "sc_translate": _h_translate,
    "sc_detect_language": _h_detect_language,
    "sc_mood_playlist": _h_mood_playlist,
    "sc_movie_suggest_v2": _h_movie_suggest_v2,
    "sc_movie_night_bundle": _h_movie_night_bundle,
    "sc_behavior_profile": _h_behavior_profile,
    "sc_predict_next_action": _h_predict_next_action,
    "sc_decision_mcda": _h_decision_mcda,
    "sc_decision_expected_value": _h_decision_expected_value,
    "sc_decision_risk_reward": _h_decision_risk_reward,
    "sc_decision_kelly": _h_decision_kelly,
    "sc_detect_sarcasm": _h_detect_sarcasm,
    "sc_tell_joke": _h_tell_joke,
    "sc_empathy_state": _h_empathy_state,
    "sc_empathy_reply": _h_empathy_reply,
    "sc_style_analyze": _h_style_analyze,
    "sc_style_generate": _h_style_generate,
    "sc_pentest_scan": _h_pentest_scan,
    "sc_hash_file": _h_hash_file,
    "sc_file_reputation": _h_file_reputation,
    "sc_url_reputation": _h_url_reputation,
}
