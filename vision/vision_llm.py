"""
Vision LLM
==========
Lets Ultron actually LOOK at the screen and understand it, instead of only
acting on the accessibility tree (windows/apps' `click_ui_element` /
`list_ui_elements`, driven by pywinauto UIA) or classical CV (OCR in
vision/ui_detection/element_locator.py, YOLO in
vision/object_detection/yolo_detector.py).

Those existing paths cover native Windows controls and plain text well,
but they're blind to anything that isn't an accessible control or clean
text: canvas-drawn web UI, images/diagrams/charts, video frames, games,
custom-rendered widgets. This module closes that gap by sending an actual
screenshot to a vision-capable LLM (Gemini, since GEMINI_API_KEY/
GEMINI_MODEL are already configured for ai/cloud_models/gemini_client.py
and gemini-2.0-flash accepts inline image parts) and asking it either to
describe/answer a question about the screen, or to return approximate
on-screen pixel coordinates for something described in plain English -
which callers can then feed straight into automation/mouse/mouse.py's
MouseControl.click(x, y).

Deliberately independent of ai_router.py: this always talks to Gemini
directly (needs a real multimodal model, so it can't silently fall back
to a text-only backend the way chat turns do). If GEMINI_API_KEY isn't
set, every method here returns a clear {"error": ...} dict - same
fail-soft convention as the rest of vision/ and automation/ - rather than
raising and crashing the tool-calling loop.
"""

import base64
import io
import json
from typing import Dict, Optional

import requests

from config import GEMINI_API_KEY, GEMINI_MODEL
from vision.screen.capture import ScreenCapture

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT = 60

DESCRIBE_PROMPT = (
    "You are looking at a screenshot of the user's computer screen. "
    "Answer the following question about what you see, concisely and "
    "concretely (mention specific text/labels/colors you can actually "
    "read, don't guess at anything off-screen).\n\nQuestion: {question}"
)

LOCATE_PROMPT = (
    "You are looking at a screenshot of the user's computer screen, which "
    'is {width}x{height} pixels. Find this on screen: "{target}".\n\n'
    "Reply with ONLY a JSON object, no other text, in exactly this shape:\n"
    '{{"found": true, "x": <int>, "y": <int>, "confidence": "high|medium|low"}}\n'
    "x/y must be the pixel coordinates of the CENTER of that element in "
    "the full {width}x{height} image. If you can't find it, reply "
    '{{"found": false, "reason": "<short reason>"}}.'
)


class VisionLLM:
    """Screenshot -> Gemini multimodal understanding, for anything the
    accessibility tree and classical CV can't see. Use get_vision_llm()."""

    def __init__(self):
        self._screen = ScreenCapture()

    @staticmethod
    def _classify_error(e: Exception) -> str:
        msg = str(e).lower()
        if "429" in msg or "rate limit" in msg or "quota" in msg:
            return "rate limit"
        if "401" in msg or "403" in msg or "api key" in msg:
            return "invalid API key"
        if "timeout" in msg or "timed out" in msg:
            return "timeout"
        if "connection" in msg or "network" in msg:
            return "network error"
        return "error"

    def _capture_b64(self, region: Optional[tuple] = None):
        """Returns (base64_str, width, height) on success, or a dict with
        an 'error' key on failure - same isinstance(..., dict) convention
        ScreenCapture itself uses."""
        image = self._screen.capture(region=region)
        if isinstance(image, dict):
            return image  # {"error": ...}
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return b64, image.width, image.height

    def _call_gemini_vision(self, prompt: str, image_b64: str, max_tokens: int = 500) -> str:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set - vision features need a Gemini key in .env.")

        url = f"{_BASE_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/png", "data": image_b64}},
                    ],
                }
            ],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens},
        }
        try:
            resp = requests.post(url, json=payload, timeout=_TIMEOUT)
        except requests.RequestException as e:
            raise RuntimeError(f"Gemini vision request failed: {e}") from e

        if resp.status_code == 429:
            raise RuntimeError("Gemini free-tier rate limit hit.")
        if not resp.ok:
            raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError):
            reason = (data.get("candidates") or [{}])[0].get("finishReason", "unknown")
            raise RuntimeError(f"Gemini returned no usable content (finishReason={reason})")

    # -- public API -----------------------------------------------------

    def describe_screen(self, question: str = "Describe what's currently on screen.") -> Dict:
        """Ask a free-form question about whatever is currently visible on
        screen - "what does this chart show", "is there an error dialog
        open", "summarize this webpage", etc."""
        captured = self._capture_b64()
        if isinstance(captured, dict):
            return captured
        image_b64, width, height = captured
        try:
            answer = self._call_gemini_vision(DESCRIBE_PROMPT.format(question=question), image_b64)
            return {"question": question, "answer": answer, "screen_size": [width, height]}
        except Exception as e:
            return {"error": f"{self._classify_error(e)}: {e}"}

    def locate_on_screen(self, target: str) -> Dict:
        """Ask Gemini to point at something on screen by description and
        return its approximate center pixel coordinates. Meant as a
        fallback for things click_ui_element (accessibility tree) can't
        see - canvas/web-rendered buttons, icons with no label, images."""
        captured = self._capture_b64()
        if isinstance(captured, dict):
            return captured
        image_b64, width, height = captured
        try:
            raw = self._call_gemini_vision(LOCATE_PROMPT.format(width=width, height=height, target=target), image_b64)
            # Models sometimes wrap JSON in ```json fences despite being told not to.
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            result = json.loads(cleaned)
            if result.get("found"):
                result["x"] = int(result["x"])
                result["y"] = int(result["y"])
            return result
        except json.JSONDecodeError:
            return {"error": f"Gemini didn't return valid JSON: {raw[:200]}"}
        except Exception as e:
            return {"error": f"{self._classify_error(e)}: {e}"}

    def click_on_screen(self, target: str, double_click: bool = False) -> Dict:
        """locate_on_screen() + an actual click, in one call. Vision-based
        fallback path - prefer click_ui_element (accessibility tree) when
        the target is a normal Windows control, since that's more precise
        and doesn't cost an API call. Use this when that fails or the
        target is something visual (an icon, an image, canvas content)."""
        located = self.locate_on_screen(target)
        if located.get("error") or not located.get("found"):
            return located

        from automation.mouse.mouse import MouseControl

        mouse = MouseControl()
        x, y = located["x"], located["y"]
        result = mouse.double_click(x, y) if double_click else mouse.click(x, y)
        if isinstance(result, dict) and result.get("error"):
            return result
        return {"clicked": target, "x": x, "y": y, "confidence": located.get("confidence", "unknown")}


_vision_llm: Optional[VisionLLM] = None


def get_vision_llm() -> VisionLLM:
    global _vision_llm
    if _vision_llm is None:
        _vision_llm = VisionLLM()
    return _vision_llm
