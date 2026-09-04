"""
models/llm/ - category namespace for the local text-generation model
loaders. The loaders themselves still live at their original paths
(models/llama/, models/ollama/, models/gemma/, models/deepseek/) so
every existing `from models.ollama.loader import ...` keeps working
unchanged - this package just re-exports them under one name for new
code that wants "give me an LLM loader" without caring which family.

    from models.llm import ollama, llama, gemma, deepseek
    client = ollama.load()

or, for the shared client class directly:

    from models.llm import OllamaClient
"""

from models.ollama import loader as ollama
from models.llama import loader as llama
from models.gemma import loader as gemma
from models.deepseek import loader as deepseek
from models.ollama.loader import OllamaClient, DEFAULT_HOST

__all__ = ["ollama", "llama", "gemma", "deepseek", "OllamaClient", "DEFAULT_HOST"]
