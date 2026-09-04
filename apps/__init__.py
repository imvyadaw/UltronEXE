"""
Phase 6 - App automations
==========================
Per-application automation classes, one file per app, grouped into
categories (browsers, office, communication, media, design, development,
cloud, system, utilities, security, gaming). Every class subclasses
BaseApp (apps/base_app.py) and returns Dicts in the same
{"success": True, ...} / {"error": "..."} shape used everywhere else in
Ultron. Wired into the AI tool-calling loop via ai/apps_tools.py.
"""

from apps.base_app import BaseApp

__all__ = ["BaseApp"]
