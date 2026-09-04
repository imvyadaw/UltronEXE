"""
PHASE 30 - NEW TOOLS
====================
Genuinely new capabilities Ultron didn't have before (checked against the
registry in ai/tools_schema.py / ai/tool_runtime.py before adding these,
to avoid duplicating anything that already exists - the registry stood at
656 tools at the time this phase was written; it has since grown well
past that, so treat "656" as this file's historical starting point, not
the current total):

  - currency_convert   : live exchange-rate conversion (frankfurter.app,
                          ECB-backed, free, no API key required)
  - translate_text      : translate text between languages
  - get_word_definition  : English dictionary lookup (definitions,
                          part of speech, example usage)

Wired the same way every other batch of tools in this project is wired
(ai/new_skills_tools.py, ai/apps_tools.py, ai/browser_tools.py,
ai/utility_tools_wire.py): a *_DIRECT_HANDLERS dict of name -> callable
merged into ai/tool_runtime.py's _DIRECT_HANDLERS, and a *_TOOLS list of
schema entries appended onto ai/tools_schema.py's TOOLS. Nothing existing
is modified or removed - this is purely additive, same pattern as every
prior phase in this codebase.

All three use the shared HTTP session from ai/http_session_pool.py for
connection reuse across repeated calls (especially translate_text if the
user asks multiple translations in one turn, or currency_convert if
checking multiple pairs).

All three are plain HTTP calls via `requests` (already a project
dependency - see requirements.txt) with a short timeout and defensive
error handling: no internet / API hiccup returns a clean
{"success": False, "error": "..."} instead of raising, exactly like
every other tool in ai/tool_runtime.py.
"""

from typing import Dict


from ai.http_session_pool import get_http_session

_HTTP_TIMEOUT = 8


def _currency_convert(args: Dict) -> Dict:
    amount = args.get("amount", 1)
    from_currency = str(args.get("from_currency", "USD")).upper().strip()
    to_currency = str(args.get("to_currency", "INR")).upper().strip()
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"success": False, "error": f"Invalid amount: {amount!r}"}

    try:
        resp = get_http_session().get(
            "https://api.frankfurter.app/latest",
            params={"amount": amount, "from": from_currency, "to": to_currency},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        rates = data.get("rates", {})
        if to_currency not in rates:
            return {
                "success": False,
                "error": f"Unsupported currency pair: {from_currency}->{to_currency}. "
                f"Frankfurter supports major ISO currency codes (USD, EUR, INR, GBP, JPY, ...).",
            }
        converted = rates[to_currency]
        return {
            "success": True,
            "amount": amount,
            "from": from_currency,
            "to": to_currency,
            "converted": converted,
            "rate": converted / amount if amount else None,
            "date": data.get("date"),
            "source": "frankfurter.app (ECB reference rates)",
        }
    except Exception as e:
        return {"success": False, "error": f"Currency lookup failed (no internet or API down): {e}"}


def _translate_text(args: Dict) -> Dict:
    text = args.get("text", "")
    target_lang = str(args.get("target_lang", "en")).strip()
    source_lang = str(args.get("source_lang", "auto")).strip()
    if not text:
        return {"success": False, "error": "No text provided to translate."}

    try:
        # Google's public translate endpoint (no API key) - widely used by
        # small open-source tools for exactly this. Falls back cleanly to
        # an error if it ever stops responding, same as every other tool
        # here that depends on a free third-party endpoint.
        resp = get_http_session().get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": source_lang,
                "tl": target_lang,
                "dt": "t",
                "q": text,
            },
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        translated = "".join(chunk[0] for chunk in payload[0] if chunk[0])
        detected_lang = payload[2] if len(payload) > 2 else source_lang
        return {
            "success": True,
            "original_text": text,
            "translated_text": translated,
            "source_lang": detected_lang,
            "target_lang": target_lang,
        }
    except Exception as e:
        return {"success": False, "error": f"Translation failed (no internet or endpoint unavailable): {e}"}


def _get_word_definition(args: Dict) -> Dict:
    word = str(args.get("word", "")).strip()
    if not word:
        return {"success": False, "error": "No word provided."}

    try:
        resp = get_http_session().get(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code == 404:
            return {"success": False, "error": f"No definition found for '{word}'."}
        resp.raise_for_status()
        entries = resp.json()
        meanings = []
        for entry in entries:
            for meaning in entry.get("meanings", []):
                pos = meaning.get("partOfSpeech", "")
                for definition in meaning.get("definitions", [])[:2]:
                    meanings.append(
                        {
                            "part_of_speech": pos,
                            "definition": definition.get("definition", ""),
                            "example": definition.get("example"),
                        }
                    )
        return {"success": True, "word": word, "meanings": meanings[:6]}
    except Exception as e:
        return {"success": False, "error": f"Dictionary lookup failed (no internet or API down): {e}"}


PHASE30_DIRECT_HANDLERS = {
    "currency_convert": _currency_convert,
    "translate_text": _translate_text,
    "get_word_definition": _get_word_definition,
}


def _tool(name: str, description: str, properties: dict, required: list) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


PHASE30_TOOLS = [
    _tool(
        "currency_convert",
        "Convert an amount from one currency to another using live exchange rates "
        "(e.g. 'convert 100 dollars to rupees', '50 EUR to JPY'). Use ISO currency codes.",
        {
            "amount": {"type": "number", "description": "Amount to convert."},
            "from_currency": {"type": "string", "description": "3-letter ISO code, e.g. USD, INR, EUR."},
            "to_currency": {"type": "string", "description": "3-letter ISO code, e.g. USD, INR, EUR."},
        },
        ["amount", "from_currency", "to_currency"],
    ),
    _tool(
        "translate_text",
        "Translate text from one language to another (e.g. Hindi to English, English to Hindi). "
        "Use for explicit translation requests like 'translate this to Hindi'.",
        {
            "text": {"type": "string", "description": "The text to translate."},
            "target_lang": {
                "type": "string",
                "description": "Target language code, e.g. 'hi', 'en', 'es'. Default 'en'.",
            },
            "source_lang": {
                "type": "string",
                "description": "Source language code, or 'auto' to detect. Default 'auto'.",
            },
        },
        ["text", "target_lang"],
    ),
    _tool(
        "get_word_definition",
        "Look up the dictionary definition, part of speech, and example usage of an English word.",
        {"word": {"type": "string", "description": "The word to define."}},
        ["word"],
    ),
]
