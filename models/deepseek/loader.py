"""
DeepSeek loader
=============
Same offline/local backend as models/ollama/loader.py underneath - Ollama
handles downloading and running the actual DeepSeek weights, this module
just pins the family-appropriate default model tag so callers don't need
to remember it. See models/ollama/loader.py's docstring for why this
project talks to Ollama over HTTP instead of bundling weights directly.

Requires Ollama installed and running locally with a DeepSeek model pulled,
e.g. `ollama pull deepseek-coder`.
"""

from models.ollama.loader import OllamaClient, DEFAULT_HOST


def load(host: str = DEFAULT_HOST, model: str = "deepseek-coder") -> OllamaClient:
    """Return an OllamaClient defaulted to the deepseek-coder tag. Does not raise
    if the server isn't running yet - call .is_available() to check, or
    .list_models() to confirm deepseek-coder (or your chosen model) is actually
    pulled before relying on it."""
    return OllamaClient(host=host, model=model)
