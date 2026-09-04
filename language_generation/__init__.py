"""
Language generation
=====================
style_emulation.py: analyze a writing sample into a small style
profile, then use that profile to condition ai.ai_router.complete()
(single-shot, no tools, no shared history - same guarantee
ai/reasoning.py already relies on) so generated text sounds like the
sample instead of Ultron's own default voice.
"""

from language_generation.style_emulation import analyze_style, generate_in_style

__all__ = ["analyze_style", "generate_in_style"]
