"""
Humor engine
=============
Extension of the "bhai" personality that finally gives core/
personality.py's "humor" trait (0.0-1.0, defined in DEFAULT_TRAITS but
never actually read by anything before this) something to drive.

maybe_joke() is the main entry point: it rolls against the CURRENT
humor trait value (get_personality().traits["humor"]) so a light aside
fires roughly as often as the slowly-drifting personality profile
says it should - a user who has been reacting well to jokes (whatever
signal elsewhere calls get_personality().adjust("humor", +0.05, ...))
gradually gets more of them, one who hasn't gets fewer, without this
module hardcoding its own independent rate.

Never fires during an urgent/warning delivery (checked via the same
Tone the caller already has, if passed in) - a joke has no business
showing up next to "your battery is at 3%".

Joke bank is small, curated, workplace-safe (no politics, no groups,
no edgy material) and bilingual (English + Hinglish, matching the
existing "bhai" voice) - categorized so a joke can be somewhat
on-topic (tech/general/motivational) rather than always random.
"""

import random
from typing import Dict, List, Optional

_JOKES: Dict[str, List[str]] = {
    "tech": [
        "Bhai, 99 little bugs in the code, 99 little bugs... take one down, patch it around, 127 little bugs in the code.",
        "Why do programmers prefer dark mode? Kyunki light attracts bugs, bhai.",
        "Mera code kaam kyun kar raha hai? Koi idea nahi... but chalo, don't touch it.",
        "There are 10 types of people, bhai - those who understand binary and those who don't.",
    ],
    "general": [
        "Bhai, main assistant hoon, therapist nahi - lekin free advice: turn it off and on again.",
        "Zindagi mein do cheezein guaranteed hain, bhai - taxes, aur mera Wi-Fi disconnect hona bilkul galat time pe.",
        "Kal maine kaha kal se sudhrunga - aaj bhi wahi plan hai.",
    ],
    "motivational": [
        "Bhai, chhota step bhi step hota hai - move karte raho.",
        "Failure is just Ultron-style debugging, bhai - trial, error, aur ek chai break.",
    ],
}
_ALL_CATEGORIES = list(_JOKES.keys())


def get_joke(category: Optional[str] = None) -> Dict:
    """Returns {"joke": str, "category": str}. Unknown/omitted category
    picks randomly across all categories."""
    if category not in _JOKES:
        category = random.choice(_ALL_CATEGORIES)
    return {"joke": random.choice(_JOKES[category]), "category": category}


def maybe_joke(category: Optional[str] = None, tone: Optional[str] = None) -> Optional[Dict]:
    """Rolls against the live humor trait from core.personality -
    returns a joke dict (see get_joke()) if the roll succeeds, else
    None. `tone` (pass the string value of whatever Tone the caller is
    already using, e.g. "urgent"/"formal"/"casual") lets this hard-skip
    urgent deliveries; a formal tone doesn't block a joke outright but
    slightly lowers the odds, matching how a considerate person still
    occasionally jokes in a formal setting, just less than casually."""
    if tone == "urgent":
        return None

    try:
        from core.personality import get_personality

        humor_level = get_personality().traits.get("humor", 0.3)
    except Exception:
        humor_level = 0.3

    roll_chance = humor_level
    if tone == "formal":
        roll_chance *= 0.5

    if random.random() > roll_chance:
        return None

    return get_joke(category)
