"""
Utility skill wiring
=====================
Verification-pass fix: skills/utilities/tools.py (UtilityTools) has 19
real, stdlib-only, fully-implemented actions (text transforms, unit
conversion, date/time math, hashing/encoding, random generation) that
were never connected to the AI tool-calling loop - the class existed,
BaseSkill.execute() worked, but no tools_schema.py entry and no
_DIRECT_HANDLERS entry meant the model could never actually call them.
Nothing here is new logic; it only exposes what already worked.

Pattern mirrors ai/new_skills_tools.py exactly: a lazy module-level
singleton, `_tool()` specs matching each method's real signature, and
handlers that go through BaseSkill.execute() (so the existing
success/error normalization and argument-error handling apply
unchanged) rather than calling the bound methods directly.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's `_tool()` - duplicated
    rather than imported for the same circular-import reason documented
    in ai/new_skills_tools.py."""
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


_utility_skill = None


def _get_utility_skill():
    global _utility_skill
    if _utility_skill is None:
        from skills.utilities.tools import UtilityTools

        _utility_skill = UtilityTools()
    return _utility_skill


def _call(action: str):
    return lambda args: _get_utility_skill().execute(action, **args)


UTILITY_TOOLS = [
    _tool(
        "text_stats",
        "Count characters, words, lines, and sentences in a block of text.",
        {"text": {"type": "string"}},
        ["text"],
    ),
    _tool(
        "slugify",
        "Turn text into a URL-safe slug (lowercase, hyphenated).",
        {"text": {"type": "string"}, "separator": {"type": "string", "description": "Default '-'"}},
        ["text"],
    ),
    _tool(
        "truncate",
        "Shorten text to a max length, adding a suffix if cut.",
        {"text": {"type": "string"}, "max_length": {"type": "integer"}, "suffix": {"type": "string"}},
        ["text"],
    ),
    _tool(
        "change_case",
        "Convert text case.",
        {"text": {"type": "string"}, "case": {"type": "string", "description": "upper|lower|title|capitalize|swap"}},
        ["text"],
    ),
    _tool(
        "similarity",
        "Rough 0-1 similarity ratio between two strings.",
        {"text_a": {"type": "string"}, "text_b": {"type": "string"}},
        ["text_a", "text_b"],
    ),
    _tool(
        "convert_length",
        "Convert a length value between units (mm, cm, m, km, in, ft, yd, mi).",
        {"value": {"type": "number"}, "from_unit": {"type": "string"}, "to_unit": {"type": "string"}},
        ["value", "from_unit", "to_unit"],
    ),
    _tool(
        "convert_weight",
        "Convert a weight value between units (mg, g, kg, oz, lb).",
        {"value": {"type": "number"}, "from_unit": {"type": "string"}, "to_unit": {"type": "string"}},
        ["value", "from_unit", "to_unit"],
    ),
    _tool(
        "convert_temperature",
        "Convert a temperature between Celsius, Fahrenheit, and Kelvin.",
        {
            "value": {"type": "number"},
            "from_unit": {"type": "string", "description": "c|f|k"},
            "to_unit": {"type": "string", "description": "c|f|k"},
        },
        ["value", "from_unit", "to_unit"],
    ),
    _tool(
        "current_time",
        "Get the current date/time, optionally in a custom strftime format.",
        {"fmt": {"type": "string", "description": "Optional strftime format string"}},
    ),
    _tool(
        "add_time",
        "Add days/hours/minutes to a date string and return the result.",
        {
            "date_str": {"type": "string", "description": "e.g. 2026-08-16 or 2026-08-16 10:00:00"},
            "days": {"type": "integer"},
            "hours": {"type": "integer"},
            "minutes": {"type": "integer"},
        },
        ["date_str"],
    ),
    _tool(
        "time_between",
        "Compute the duration between two date/time strings.",
        {"start": {"type": "string"}, "end": {"type": "string"}},
        ["start", "end"],
    ),
    _tool(
        "hash_text",
        "Hash text with a given algorithm (e.g. sha256, md5).",
        {"text": {"type": "string"}, "algorithm": {"type": "string", "description": "Default sha256"}},
        ["text"],
    ),
    _tool("encode_base64", "Base64-encode a string.", {"text": {"type": "string"}}, ["text"]),
    _tool("decode_base64", "Base64-decode a string.", {"encoded": {"type": "string"}}, ["encoded"]),
    _tool(
        "generate_password",
        "Generate a random password.",
        {
            "length": {"type": "integer", "description": "4-256, default 16"},
            "symbols": {"type": "boolean", "description": "Include punctuation, default true"},
        },
    ),
    _tool("generate_uuid", "Generate a random UUID4."),
    _tool(
        "roll_dice",
        "Roll one or more dice.",
        {
            "sides": {"type": "integer", "description": "Default 6"},
            "count": {"type": "integer", "description": "Default 1, max 100"},
        },
    ),
    _tool("flip_coin", "Flip one or more coins.", {"times": {"type": "integer", "description": "Default 1, max 1000"}}),
    _tool(
        "random_number",
        "Get a random integer in a range.",
        {"min_value": {"type": "integer"}, "max_value": {"type": "integer"}},
    ),
]

UTILITY_ACTION_NAMES = [
    "text_stats",
    "slugify",
    "truncate",
    "change_case",
    "similarity",
    "convert_length",
    "convert_weight",
    "convert_temperature",
    "current_time",
    "add_time",
    "time_between",
    "hash_text",
    "encode_base64",
    "decode_base64",
    "generate_password",
    "generate_uuid",
    "roll_dice",
    "flip_coin",
    "random_number",
]

UTILITY_DIRECT_HANDLERS: Dict = {name: _call(name) for name in UTILITY_ACTION_NAMES}
