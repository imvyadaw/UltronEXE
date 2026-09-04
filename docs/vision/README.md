# Vision (physical camera)

`skills/vision/` is Ultron's physical-webcam vision package - as
opposed to `vision/`'s screen-capture-based OCR/face/object detection,
which reads the user's own display instead of a camera pointed at the
room. Every module here is a narrow, single-concern engine paired with
its own thin `BaseSkill` facade, and every one of them shares the same
camera instead of opening a second capture path.

## Layout

```
skills/vision/
├── camera_manager.py          - frame/snapshot source
├── vision_provider.py         - "local" description backend (Ollama + LLaVA)
├── remote_vision_provider.py  - "remote" description backend (Gemini)
├── vision_engine.py           - orchestrates the two backends -> see()/snapshot()/status()
├── camera_skill.py            - facade for vision_engine.py (skill name "vision")
├── object_detector.py         - camera-input adapter over YOLOv8n (80 COCO classes)
├── object_detection_skill.py  - facade (skill name "camera_object_detection")
├── ocr_engine.py               - camera-input adapter over Tesseract
├── ocr_skill.py                 - facade (skill name "camera_ocr")
├── scene_analyzer.py           - one capture -> description + objects + text together
├── scene_skill.py                - facade (skill name "camera_scene")
├── change_detector.py          - baseline-vs-live-frame "did anything change" engine
├── change_detection_skill.py   - facade (skill name "camera_change_detection")
└── vision_memory.py             - disk-backed baseline + change-event history
```

## The one rule every module here follows

`camera_manager.py`'s `CameraManager` is the **only** thing any of these
modules talk to for pixels, and it in turn delegates the actual device
handling entirely to `eyes/live_camera.py`'s `LiveCamera` - it does not
open `cv2.VideoCapture` itself. So there is exactly one place in the
whole project that opens a camera device, and exactly one place
(`camera_manager.py`) that turns a frame into a saved JPEG. Every
higher-level module (`object_detector.py`, `ocr_engine.py`,
`scene_analyzer.py`, `change_detector.py`, `vision_engine.py`) is a
thin adapter that captures via `get_camera_manager()` and hands the
resulting snapshot path to an already-existing, already-tested engine
(YOLOv8n, Tesseract, the two description backends) - no detection/OCR/
description logic is duplicated anywhere in this package.

Two hardware-adjacent dependencies degrade the same way everywhere in
this package: if `opencv-python` isn't installed, or there's no camera
at device index 0, `is_available()` returns `False` and every capture
call returns `None`/an error dict - never an exception. A missing
webcam is an expected, not exceptional, state.

## What each engine does

- **`vision_engine.py` (`see`)** - capture a frame, then describe it:
  local model (Ollama + LLaVA) first, Gemini fallback if the local
  backend isn't available or its `describe()` call itself fails. If
  neither backend is available, the error names both, not just the
  first one tried.
- **`object_detector.py`** - capture a frame, run it through the same
  YOLOv8n model `vision/object_detection/yolo_detector.py` already uses
  for screenshots (80 COCO classes: person, car, dog, laptop, phone, ...).
- **`ocr_engine.py`** - capture a frame, run it through the same
  Tesseract wrapper `vision/ocr/tesseract_ocr.py` already uses for
  screenshots. Useful for text that only exists in the physical world -
  a label, a page, a sign.
- **`scene_analyzer.py`** - one capture, fanned out to description +
  object detection + OCR together, so all three results describe the
  same moment instead of three separate (and possibly different)
  captures. Each sub-result keeps its own `success`/`error`, so a
  caller can tell exactly which of the three failed.
- **`change_detector.py`** - `set_baseline()` remembers a frame;
  `check()` captures a new frame, diffs it against the baseline
  (grayscale + blur + threshold, the changed-pixel percentage compared
  against `CHANGE_DETECTION_THRESHOLD_PERCENT`), and rolls the baseline
  forward to the new frame either way - each `check()` answers "what
  changed since the *last* check", not "since the very first one".
  Changes are recorded to `vision_memory.py`'s disk-backed event
  history (`storage/cache/vision_memory.json` by default), capped at
  `CHANGE_DETECTION_MAX_EVENTS`.

## Running the tests

```bash
pip install -r testing/requirements-test.txt   # pytest, if not already installed
pytest tests/vision/
```

`tests/vision/` mirrors the package one file per concern:

| File | Covers |
|---|---|
| `test_camera.py` | `CameraManager` (minus `capture_snapshot`), `camera_skill.py`, `VisionEngine.status()` |
| `test_capture.py` | `CameraManager.capture_snapshot()`, `VisionEngine.snapshot()` |
| `test_objects.py` | `object_detector.py`, `object_detection_skill.py` |
| `test_ocr.py` | `ocr_engine.py`, `ocr_skill.py` |
| `test_scene.py` | `scene_analyzer.py`, `scene_skill.py` |
| `test_changes.py` | `change_detector.py`, `change_detection_skill.py`, `vision_memory.py` |
| `test_integration.py` | `VisionEngine.see()`'s full backend chain, `vision_provider.py`/`remote_vision_provider.py`, the shared-`CameraManager` contract, and a full-package smoke test |

None of the tests need a physical webcam, Tesseract, Ollama, or a
Gemini API key - `tests/vision/conftest.py` fakes the one hardware
boundary each module actually touches (`eyes.live_camera.LiveCamera`,
`YOLODetector`, `TesseractOCR`, the two description backends) and
resets every `get_x()` singleton in the package between tests. Where a
test benefits from exercising real pixel math (JPEG encode/decode, the
change-detection diff threshold), it uses real `opencv-python` +
`numpy` against throwaway files under `tmp_path` rather than mocking
`cv2` away entirely.

## Common gotchas when extending this package

- Don't reach for `cv2.VideoCapture`/`get_live_camera()` directly from
  a new module - go through `get_camera_manager()` so there's still
  only one capture path.
- `CAMERA_WARMUP_FRAMES`, `CAMERA_SNAPSHOT_DIR`, and
  `CHANGE_DETECTION_THRESHOLD_PERCENT` are read from `config.py` at
  *call* time inside each method, so they're safe to override in a
  test via `monkeypatch.setattr` on the module. `VisionMemory`'s
  `CHANGE_DETECTION_MEMORY_FILE` is different - it's a constructor
  default parameter bound at import time, so tests construct
  `VisionMemory(path=...)` explicitly instead of monkeypatching the
  config name.
- A new facade under `skills/vision/` should stay flat (`skills/vision/
  your_skill.py`), not nested under an extra `skills/vision/skills/`
  subfolder - this has been proposed and rejected twice already (see
  `skills/vision/__init__.py`), to stay consistent with every other
  skill category in this project.
