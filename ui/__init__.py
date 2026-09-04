"""
Ultron UI layer (Phase 7).

Three surfaces, each independent and independently runnable:

- ui.web_ui    - Flask app (templates + static) for browser access.
- ui.mobile.api - REST API blueprint consumed by a mobile client.
- ui.voice_ui.avatar - avatar state machine driven by the voice pipeline.

See docs/architecture/phase7_ui_layer.md for what is and isn't wired
into core/ yet.
"""
