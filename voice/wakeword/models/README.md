# Custom wake word models

Drop a custom-trained openWakeWord model here (`.onnx` or `.tflite`,
exported from https://github.com/dscripka/openWakeWord's training
notebook) and add its filename (without extension) to `WAKE_WORD_MODELS`
in `.env`, e.g.:

    WAKE_WORD_MODELS=hey_ultron,my_custom_word

Pretrained models (like `hey_ultron`) don't need to go here - openWakeWord
downloads and caches those itself on first use. This folder is only for
models you trained yourself.
