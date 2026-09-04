# models/

Local model loaders/clients - anything that talks to a *locally
running* model backend (as opposed to `ai/cloud_models/`, which talks
to hosted APIs like Groq/Gemini/HuggingFace).

## Layout

```
models/
├── README.md
├── llm/          category re-export: ollama, llama, gemma, deepseek
├── voice/        category re-export: whisper
├── vision/       new - placeholder for a future local vision model
├── ollama/       loader.py - HTTP client for a local Ollama server
├── llama/        loader.py - Ollama, pinned to a llama3 tag
├── gemma/        loader.py - Ollama, pinned to a gemma tag
├── deepseek/     loader.py - Ollama, pinned to a deepseek tag
└── whisper/      loader.py - cloud Whisper (Groq-hosted) transcription
```

`llm/`, `voice/`, and `vision/` are **category namespaces**, added
this phase to group the existing per-family loaders by what they're
for. They don't move or replace anything - `models/ollama/loader.py`
etc. are still there and still imported directly in a few places
(`ai/local_models/manager.py`, `models/llama/loader.py`,
`models/gemma/loader.py`, `models/deepseek/loader.py`). The category
packages just re-export the same objects under a shorter, purpose-first
import path for new code:

```python
from models.llm import ollama          # same module as models.ollama.loader
from models.voice import whisper       # same module as models.whisper.loader
from models.vision import VisionModelLoader  # new - not implemented yet
```

## Why `llama`/`gemma`/`deepseek` all import from `ollama`

All three are thin wrappers around `models/ollama/loader.py`'s
`OllamaClient` - Ollama is the actual runtime that downloads and runs
the model weights, so these modules just pin a family-appropriate
default tag (`llama3`, `gemma`, `deepseek-coder`, ...) rather than
duplicating an HTTP client three times. See each `loader.py`'s
docstring for specifics.

## Vision is the exception

There's no `models/vision/loader.py` backend yet - today's vision
needs (`vision/ocr/`, `vision/face/`, `vision/object_detection/`,
`vision/screen/`, ...) are covered by dedicated libraries (Tesseract,
YOLO, OpenCV) rather than a locally-served model. `models/vision/` is
a stub for when a local multimodal model (e.g. served via Ollama, the
same way text models are here) gets added - see its module docstring.
