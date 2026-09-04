Implemented. See ai/local_models/manager.py (LocalAIManager) for the
offline chat/tool-calling backend, backed by a local Ollama server
(models/ollama/loader.py). ai/ai_router.py automatically routes to this
when offline, or when the cloud (Groq) backend fails, and back to cloud
once it's reachable again. Configure via OLLAMA_HOST / OLLAMA_MODEL in
.env - see config.py.
