"""
skills/vision/remote_vision_provider.py
=========================================
Second vision_provider.py backend - the one its docstring left a slot
for ("a second backend ... has a single place to plug in without
touching camera_manager.py or vision_engine.py at all"). Describes a
camera snapshot via Gemini's multimodal API instead of the local
Ollama+LLaVA model, for the case where the local model isn't
installed/running (VISION_MODEL_HOST unreachable, model not pulled) but
GEMINI_API_KEY is already configured for ai/cloud_models/gemini_client.py
and vision/vision_llm.py's screen-vision path.

Same request shape as vision/vision_llm.py's _call_gemini_vision(): not
importing that module directly since it's built around ScreenCapture's
in-memory PIL image (screenshots), while this reads a JPEG file already
saved to disk by camera_manager.py - different enough inputs that a
shared helper would need its own file-vs-buffer branching for one
call site. Kept independent, same as vision_llm.py is deliberately kept
independent of ai_router.py.

Never raises - describe()/is_available() return the same
{"success": True/False, ...} shape as vision_provider.py's
VisionProvider, so vision_engine.py can treat both backends
interchangeably.
"""

import base64
from typing import Optional

import requests

from config import GEMINI_API_KEY, GEMINI_MODEL, VISION_MODEL_TIMEOUT_S

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

DEFAULT_PROMPT = "Describe what the camera currently sees, in one or two plain sentences."


class RemoteVisionProvider:
    """Thin facade over Gemini's multimodal API - describe(image_path),
    matching VisionProvider's (local_vision_provider) public shape."""

    def is_available(self) -> bool:
        return bool(GEMINI_API_KEY)

    def describe(self, image_path: str, prompt: Optional[str] = None) -> dict:
        """Returns {"success": True, "description": str} or
        {"success": False, "error": str} - never raises."""
        if not GEMINI_API_KEY:
            return {
                "success": False,
                "error": "GEMINI_API_KEY not set - remote vision needs a Gemini key in .env.",
            }
        try:
            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("ascii")
        except OSError as exc:
            return {"success": False, "error": f"Could not read snapshot at {image_path}: {exc}"}

        url = f"{_BASE_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt or DEFAULT_PROMPT},
                        {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
                    ],
                }
            ],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 500},
        }
        try:
            resp = requests.post(url, json=payload, timeout=VISION_MODEL_TIMEOUT_S)
        except requests.RequestException as exc:
            return {"success": False, "error": f"Gemini vision request failed: {exc}"}

        if resp.status_code == 429:
            return {"success": False, "error": "Gemini free-tier rate limit hit."}
        if not resp.ok:
            return {"success": False, "error": f"Gemini API error {resp.status_code}: {resp.text[:300]}"}

        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError):
            reason = (data.get("candidates") or [{}])[0].get("finishReason", "unknown")
            return {"success": False, "error": f"Gemini returned no usable content (finishReason={reason})"}

        if not text:
            return {"success": False, "error": "Gemini returned an empty description."}
        return {"success": True, "description": text}


_provider: Optional[RemoteVisionProvider] = None


def get_remote_vision_provider() -> RemoteVisionProvider:
    """Process-wide RemoteVisionProvider singleton, matching this
    codebase's get_x() convention."""
    global _provider
    if _provider is None:
        _provider = RemoteVisionProvider()
    return _provider
