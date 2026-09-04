"""HuggingFace client (ai/llm/)
=============================
🆓 HuggingFace Inference API free tier - broadest model choice of the
four providers, but the slowest/least reliable (models can be "cold" and
need to warm up, and free-tier rate limits are tight). Used as a
lower-priority fallback by ai/llm/model_factory.py, behind Groq and
Gemini.

Setup: set HUGGINGFACE_API_KEY in .env (a free token from
https://huggingface.co/settings/tokens). Optional HUGGINGFACE_MODEL
overrides the default model. See config.py.
"""

import requests

from config import HUGGINGFACE_API_KEY, HUGGINGFACE_MODEL
from ai.llm.base_client import BaseLLMClient

_BASE_URL = "https://api-inference.huggingface.co/models"
_TIMEOUT = 30
_COLD_START_RETRY_SECONDS = 2


class HuggingFaceLLMClient(BaseLLMClient):
    name = "huggingface"

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or HUGGINGFACE_API_KEY
        self.model = model or HUGGINGFACE_MODEL

    def is_available(self) -> bool:
        return bool(self.api_key)

    def complete(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> str:
        if not self.is_available():
            raise RuntimeError("HuggingFace is not configured (HUGGINGFACE_API_KEY missing).")

        url = f"{_BASE_URL}/{self.model}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": max(temperature, 0.01),  # HF rejects temperature=0
                "max_new_tokens": max_tokens,
                "return_full_text": False,
            },
            "options": {"wait_for_model": True},
        }

        import time

        last_error = None
        for attempt in range(2):  # one retry - free-tier models often need to "wake up"
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=_TIMEOUT)
            except requests.RequestException as e:
                last_error = e
                time.sleep(_COLD_START_RETRY_SECONDS)
                continue

            if resp.status_code == 503:
                # Model is loading (cold start) - wait and retry once.
                last_error = RuntimeError("Model is loading (cold start)")
                time.sleep(_COLD_START_RETRY_SECONDS)
                continue
            if resp.status_code == 429:
                raise RuntimeError("HuggingFace free-tier rate limit hit. Try again shortly.")
            if not resp.ok:
                raise RuntimeError(f"HuggingFace API error {resp.status_code}: {resp.text[:300]}")

            data = resp.json()
            if isinstance(data, list) and data and "generated_text" in data[0]:
                return data[0]["generated_text"].strip()
            if isinstance(data, dict) and "generated_text" in data:
                return data["generated_text"].strip()
            raise RuntimeError(f"Unexpected HuggingFace response shape: {str(data)[:300]}")

        raise RuntimeError(f"HuggingFace request failed after retry: {last_error}")
