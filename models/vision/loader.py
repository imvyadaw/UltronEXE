"""
models/vision/loader.py - locally-run multimodal vision model, served
via Ollama (https://ollama.com), the same offline/local-model pattern
models/ollama/loader.py already uses for text: Ollama handles pulling
and running the actual model weights, this stays a thin HTTP client
(just `requests`, already a project dependency).

Backend: Ollama + LLaVA (`llava`, default tag `llava:7b`) - chosen as
the default model because it's the multimodal model most commonly
already pulled alongside a text model in an Ollama setup, and it needs
no extra project dependency beyond what models/ollama/loader.py
already requires. Any other Ollama-served vision model (bakllava,
llava-llama3, moondream, ...) works the same way - just pass a
different `model` to the constructor.

Requires Ollama installed and running locally (`ollama serve`, or the
Ollama desktop app) with a vision-capable model pulled, e.g.
`ollama pull llava`.

Still not wired into agents/vision_agent.py or anywhere else - today's
vision/ package (OCR, face, object detection, screen capture) covers
current needs with dedicated libraries, not a downloaded model. This
module exists so the next local-vision-model integration has a
ready-to-use client instead of a placeholder to fill in first.
"""

import base64
from typing import Optional

import requests

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llava:7b"


class VisionModelLoader:
    """Thin HTTP client for a local Ollama vision model, following
    models/ollama/loader.py's OllamaClient shape: construct with a
    host/model, check `is_available()`, then `describe_image(path)`."""

    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        self.host = (host or DEFAULT_HOST).rstrip("/")
        self.model = model or DEFAULT_MODEL

    def is_available(self) -> bool:
        """Whether an Ollama server is reachable at self.host AND has
        self.model actually pulled - a reachable server with the wrong
        model pulled can't describe anything either."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=2)
            if resp.status_code != 200:
                return False
            models = [m["name"] for m in resp.json().get("models", [])]
            target = self.model.split(":")[0]
            return any(m.split(":")[0] == target for m in models)
        except requests.exceptions.RequestException:
            return False
        except Exception:
            return False

    def describe_image(self, image_path: str, prompt: str = "Describe this image in detail.") -> str:
        """Send `image_path` to the local vision model with `prompt`
        and return its text description. Raises RuntimeError (not a
        bare exception) on any failure - unreachable server, model not
        pulled, unreadable image, or a malformed response - so a
        caller gets a clear reason instead of a raw stack trace from
        deep inside `requests`."""
        try:
            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
        except OSError as exc:
            raise RuntimeError(f"could not read image at {image_path}: {exc}") from exc

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
        }
        try:
            resp = requests.post(f"{self.host}/api/generate", json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(f"could not reach Ollama at {self.host} - is `ollama serve` running?") from exc
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Ollama vision request failed: {exc}") from exc

        response_text = data.get("response")
        if not response_text:
            raise RuntimeError(f"Ollama returned no description - raw response: {data}")
        return response_text.strip()

    def chat(self, messages, model: Optional[str] = None, timeout: float = 120) -> dict:
        """Multi-turn variant of describe_image() for a caller that
        wants the raw chat-style response instead of a single string -
        same {"role", "content", "images": [base64, ...]} message shape
        Ollama's /api/chat expects. Returns {"content": str} on
        success or {"error": str} on failure, mirroring
        models/ollama/loader.py's OllamaClient.chat() return shape."""
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
        }
        try:
            resp = requests.post(f"{self.host}/api/chat", json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            return {"content": content}
        except requests.exceptions.ConnectionError:
            return {"error": f"could not reach Ollama at {self.host} - is `ollama serve` running?"}
        except Exception as exc:
            return {"error": str(exc)}


_loader: Optional[VisionModelLoader] = None


def get_vision_model_loader() -> VisionModelLoader:
    """Process-wide VisionModelLoader singleton, matching this
    codebase's get_x() convention used throughout models/ and
    intelligence/."""
    global _loader
    if _loader is None:
        _loader = VisionModelLoader()
    return _loader
