"""
router.ai_router
=================
Public-facing alias for ai.ai_router.AIRouter, the module that actually
picks cloud (Groq) vs local (Ollama) per turn - online/offline
detection, fallback, and retry all happen there. Kept here too so code
that thinks in terms of "the routing layer" (router.intent_router,
router.command_router, router.skill_router, router.ai_router) doesn't
also need to know that this particular router historically lives under
ai/ instead of router/ or core/.
"""

