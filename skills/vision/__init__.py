"""
Camera + vision skill package
==============================
Physical-webcam vision, as opposed to vision/'s screen-capture-based
OCR/face/object detection. Narrow single-concern engine modules, each
paired with its own thin BaseSkill facade:

    camera_manager.py         - frame/snapshot source. Delegates the
                                 actual device handling entirely to
                                 eyes/live_camera.py's LiveCamera - does
                                 NOT open cv2.VideoCapture itself, so
                                 there's still only one place in the
                                 whole project that does.
    vision_provider.py        - "local" vision backend: describes an
                                 image via models/vision/model_manager.py's
                                 VisionModelManager (Ollama + LLaVA).
    remote_vision_provider.py - "remote" vision backend: describes an
                                 image via Gemini's multimodal API, for
                                 when the local model isn't set up.
    vision_engine.py          - orchestrates the above: capture a frame,
                                 then describe it (local first, remote
                                 fallback), in one call. Facade:
                                 camera_skill.py (skill name "vision").
    object_detector.py        - camera-input adapter over the existing
                                 vision/object_detection/yolo_detector.py
                                 (YOLOv8n, 80 COCO classes) - no detection
                                 logic duplicated here. Facade:
                                 object_detection_skill.py (skill name
                                 "camera_object_detection").
    ocr_engine.py              - camera-input adapter over the existing
                                 vision/ocr/tesseract_ocr.py. Facade:
                                 ocr_skill.py (skill name "camera_ocr").
    scene_analyzer.py         - one capture, fanned out to description +
                                 object_detector.py + ocr_engine.py
                                 together, so all three describe the same
                                 moment. Facade: scene_skill.py (skill
                                 name "camera_scene").

Each facade is registered in skills/__init__.py, and ai/vision_skill_tools.py
adds the matching AI tool-calling entries (camera_see/camera_snapshot/
camera_status/camera_detect_objects/camera_read_text/camera_analyze_scene) -
see that module's docstring for the full tool list and reachability story.

Note: nesting any of the *_skill.py facades under an extra
skills/vision/skills/ subfolder was considered (twice) and rejected both
times. Every facade lives flat in skills/vision/, matching every other
category here (skills/app_control/controller.py, skills/email/handler.py,
...) - none of them nest a second skills/ folder inside their own.
"""
