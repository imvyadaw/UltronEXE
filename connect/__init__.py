"""
CONNECT (Phase 18.7)
======================
Real API/protocol integrations to specific services - headless HTTP
or SMTP/IMAP calls, no on-screen app required. Contrast with ACTIONS/
in this same phase (generic, on-screen automation) and with apps/*.py
(Phase 6, per-app UI automation of the installed desktop client):

    whatsapp.py   - WhatsApp Business Cloud API. Contrast:
                    apps/communication/whatsapp.py drives WhatsApp
                    Desktop instead.
    email.py       - SMTP send + IMAP unread read. Stdlib only.
    calendar.py    - Google Calendar REST API v3 (read + create).
    spotify.py     - Spotify Web API (search + playback control).
                    Contrast: apps/media/spotify.py drives the
                    desktop app instead.
    youtube.py     - YouTube Data API v3 (search + metadata).
                    Contrast: browser/chrome/chrome.py's
                    youtube_play() scrapes search-results HTML
                    instead, needing no API key.
    social.py       - deliberately narrow webhook fan-out poster, not
                      native OAuth posting - see that module's own
                      docstring for why.

Every module needs its own credential(s) in environment variable(s)
(never hardcoded, never logged) and is_available() before anything
returns real data - no credential, no `requests` (where used), or no
network all collapse to an empty list/dict or
{"success": False, ...} rather than an exception, same contract every
other module in this project already promises. Text/content sent
through whatsapp.py, email.py, or social.py can be drafted by
PHASE_18_6_AI_AGENTS/AGENTS/writer.py and reviewed by that phase's
guard.py first - these modules' own job is only the send.

Purely additive - nothing in Phase 1-18.6 imports from here.
"""

from connect.whatsapp import get_whatsapp
from connect.email import get_email
from connect.calendar import get_calendar
from connect.spotify import get_spotify
from connect.youtube import get_youtube
from connect.social import get_social

__all__ = [
    "get_whatsapp",
    "get_email",
    "get_calendar",
    "get_spotify",
    "get_youtube",
    "get_social",
]
