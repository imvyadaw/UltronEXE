"""
Backward-compat shim: the real implementation moved to
browser/automation/form_filler.py (Phase 7's reorganization). Kept here
so existing imports (windows/__init__.py: `from browser.form_filler
import FormFiller`) keep working unchanged.
"""

from browser.automation.form_filler import FormFiller

__all__ = ["FormFiller"]
