"""Ollama loader
==============
Offline/local-model backend, as an alternative to the Groq cloud client
in ai/cloud_models/. This talks to a locally running Ollama server
(https://ollama.com) over HTTP - Ollama itself handles downloading and
running the actual model weights, so this stays a thin, dependency-light
client (just `requests`, already a project dependency) rather than
bundling multi-gigabyte model files.

Requires Ollama installed and running locally (`ollama serve`, or the
Ollama desktop app) with at least one model pulled (e.g. `ollama pull
llama3`).
"""

from typing import Dict, List, Optional

import requests

DEFAULT_HOST = "http://localhost:11434"


class OllamaClient:
    """Thin HTTP client for a local Ollama server."""

    def __init__(self, host: str = DEFAULT_HOST, model: str = "llama3"):
        self.host = host.rstrip("/")
        self.model = model

    def is_available(self) -> bool:
        """Check whether an Ollama server is reachable at self.host."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=2)
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def list_models(self) -> Dict:
        """List models currently pulled/available on the local Ollama server."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            return {"models": models, "count": len(models)}
        except requests.exceptions.ConnectionError:
            return {"error": f"Could not reach Ollama at {self.host} - is `ollama serve` running?"}
        except Exception as e:
            return {"error": str(e)}

    def has_model(self, model: str = None) -> bool:
        """Whether `model` (or self.model) has actually been pulled locally.
        Ollama tags look like "llama3.1:8b"; match on the part before ':'."""
        target = (model or self.model).split(":")[0]
        listed = self.list_models()
        return any(m.split(":")[0] == target for m in listed.get("models", []))

    def chat(
        self,
        messages: List[Dict],
        model: str = None,
        temperature: float = 0.7,
        tools: Optional[List[Dict]] = None,
        max_tokens: Optional[int] = None,
        num_ctx: Optional[int] = None,
        timeout: float = 120,
    ) -> Dict:
        """Send a chat-style request (list of {"role", "content"} dicts) to
        the local model. When `tools` is given (OpenAI/Groq-shaped function
        schemas - same format as ai/tools_schema.TOOLS), Ollama models that
        support tool calling (llama3.1+, qwen2.5, mistral-nemo, ...) return
        message.tool_calls the same way the cloud API does.

        `num_ctx` caps the context window (and so the KV-cache RAM Ollama
        allocates for this request) - left as None, Ollama sizes it for
        the model's full supported context, which for something like
        llama3.2 (128K) needs ~14GB of RAM on its own and fails with an
        out-of-memory error on a normal laptop, even for a one-line
        message with no tools. Defaults to config.LOCAL_CONTEXT_LENGTH
        when the caller doesn't override it - see ai/local_models/manager.py.

        Returns {"model", "content", "tool_calls"} on success (tool_calls
        is always a list, empty if none), or {"error": "..."} on failure.
        """
        options = {"temperature": temperature}
        if max_tokens:
            options["num_predict"] = max_tokens
        if num_ctx:
            options["num_ctx"] = num_ctx

        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if tools:
            payload["tools"] = tools

        try:
            resp = requests.post(f"{self.host}/api/chat", json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            message = data.get("message", {}) or {}
            return {
                "model": model or self.model,
                "content": message.get("content", ""),
                "tool_calls": message.get("tool_calls", []) or [],
            }
        except requests.exceptions.ConnectionError:
            return {"error": f"Could not reach Ollama at {self.host} - is `ollama serve` running?"}
        except requests.exceptions.Timeout:
            return {"error": "Ollama request timed out - the model may still be loading"}
        except requests.exceptions.HTTPError as e:
            # A model that doesn't support the `tools` field errors out here;
            # ai/local_models/manager.py catches this and retries once
            # without tools rather than failing the whole turn.
            return {"error": f"Ollama HTTP error: {e}"}
        except Exception as e:
            return {"error": str(e)}

    def generate(self, prompt: str, model: str = None) -> Dict:
        """Simple single-prompt completion (no conversation history)."""
        return self.chat([{"role": "user", "content": prompt}], model=model)


def load(host: str = DEFAULT_HOST, model: str = "llama3") -> OllamaClient:
    """Return an OllamaClient. Does not raise if the server isn't running yet -
    call .is_available() to check before relying on it."""
    return OllamaClient(host=host, model=model)
