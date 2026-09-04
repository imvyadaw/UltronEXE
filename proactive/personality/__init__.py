"""
Personality
===========
How Ultron *says* a proactive alert, as opposed to whether it should
say anything at all (that's proactive/triggers/). ultron_phrases.py is
the line bank; tone_manager.py picks a tone + line to fit the moment
and hands back finished text ready for ui.notifications.notify() and
the TTS layer.
"""

from proactive.personality.tone_manager import ToneManager, get_tone_manager, Tone

__all__ = ["ToneManager", "get_tone_manager", "Tone"]
