"""
AUTONOMOUS_WEB
===============
A browser-automation agent ULTRON can use for user-directed web
tasks: opening pages, filling forms, pulling structured data,
keeping a logged-in session alive, and posting content the user
authored to their own social accounts.

captcha_solver.py was intentionally not built - see README_PHASE_17_6.md
in the parent folder for why. Everything below assumes a human is
either present to clear the occasional captcha, or that the sites
being automated don't present one for the actions in question.
"""

from .web_agent_core import WebAgentCore
from .site_navigator import SiteNavigator
from .data_extractor import DataExtractor
from .session_manager import SessionManager
from .form_filler import FormFiller
from .social_media_agent import SocialMediaAgent

__all__ = [
    "WebAgentCore",
    "SiteNavigator",
    "DataExtractor",
    "SessionManager",
    "FormFiller",
    "SocialMediaAgent",
]
