"""
ui/web_ui/server.py - alias for ui/web_ui/app.py.

The real implementation lives in app.py (Flask's own convention);
this file exists only so the path `ui/web_ui/server.py` from the
originally requested project tree also works, without maintaining two
copies of the same code.

    from ui.web_ui.server import create_app
    python -m ui.web_ui.server   # same as python -m ui.web_ui.app
"""

from ui.web_ui.app import create_app, main

__all__ = ["create_app", "main"]

if __name__ == "__main__":
    main()
