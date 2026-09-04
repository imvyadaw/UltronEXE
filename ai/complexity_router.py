"""
Complexity Router (low-latency pipeline)
=========================================
    Voice -> Fast local STT -> Instant Intent Router -> Simple/Normal/Complex
           -> Direct Tool / Fast LLM / Strong LLM -> Streaming -> Streaming TTS

"Simple" already exists and is unchanged: ai/local_router.route_system_command()
answers unambiguous system commands (time, volume, open app, ...) with zero
LLM calls at all - core.assistant.Assistant.handle_command() tries that
before this module ever runs.

This module draws the *remaining* line: of whatever local_router didn't
already answer, which turns are quick, tool-free conversation ("Normal" -
routed to a small fast-streamed model, ai.cloud_models.groq_client.
chat_fast_stream) versus which ones plausibly need real reasoning, a tool
(including search_internet), or up-to-date information the fast model
doesn't have access to at all ("Complex" - the existing full
chat_with_tools() pipeline, unchanged).

ALLOWLIST DESIGN (changed from a blocklist): the fast/no-search tier is
opt-IN, not opt-out. Rather than trying to enumerate every way a factual
question can be phrased (impossible to keep complete across English +
Hinglish + however anyone types), classify() now only sends something to
the fast tier when it positively matches a known-safe casual-chat pattern
(greeting, thanks, small talk, "what can you do", opinion/joke request).
Anything that doesn't clearly match one of those - including a phrasing
nobody thought to list - defaults to "complex", so it always has
search_internet/fact_check_claim available rather than risk answering a
factual question from stale training data. This trades a little latency
on some borderline chit-chat for never silently guessing on something
that needed a real lookup.

Classification is pure regex/keyword matching over the raw text - no model
call, no network - so it's genuinely instant and adds no latency of its own.
"""

import re
from typing import Literal

Tier = Literal["normal", "complex"]

# Longer utterances are more likely to be multi-step or need real reasoning
# depth - past this length, always "complex" even if it superficially
# matches a casual pattern (e.g. "hi, so btw quick question...").
NORMAL_MAX_WORDS = 12

_URL_OR_PATH_RE = re.compile(r"(https?://|www\.|[a-zA-Z]:\\\\|/[\w.-]+/)")

# Optional leading wake-word/address phrase ("hi ultron", "hey ultron",
# "ultron,", ...). Voice mode's wake-word detector already strips this
# before handle_command() ever runs (see core.assistant.Assistant.
# run_listen), but typed input has no equivalent step - and a leading
# "hi" is exactly the kind of thing that could otherwise get mistaken
# for the whole message being casual chat (see _CASUAL_ALLOW_RE below).
# Stripped here too as defense in depth even though core.assistant now
# also strips it once up front before any router sees the text.
_WAKE_PREFIX_RE = re.compile(r"^\s*(?:hi|hey|hello|yo|ok|okay)?[\s,]*ultron\s*[,:]?\s*", re.IGNORECASE)

# Anything containing one of these anywhere is unconditionally "complex" -
# checked before the casual allowlist below, so a casual-sounding opener
# that then asks something factual ("hey, quick one - CM kaun hai") still
# gets search_internet attached. Same list purpose as before, just now a
# hard override rather than the only signal.
_FORCE_COMPLEX_WORDS = (
    "who is",
    "who was",
    "who are",
    "what is the capital",
    "capital of",
    "population of",
    "prime minister",
    "president of",
    "ceo of",
    "founder of",
    "how many ",
    "how much does",
    "how much is",
    "how old is",
    "when did",
    "when was",
    "when is",
    "where is",
    "what year",
    "latest",
    "right now",
    "weather",
    "temperature",
    "news",
    "stock price",
    "current price",
    "score of",
    "live score",
    "mausam",
    "kaun hai",
    "kaun tha",
    "kaun hain",
    "kab hua",
    "kab bana",
    "kab bani",
    "kab hai",
    "kitne ",
    "kitni ",
    "kitna hai",
    "kitna hoga",
    "kaha hai",
    "abhi kya",
    "kya hai",
    "kya hain",
    "kya tha",
    "kya price",
    "price kya",
    "rate kya",
    "kya rate",
    "sahi hai kya",
    "true hai kya",
    "fact check",
    "confirm karo",
    "pata hai kya",
    "naam kya hai",
    "kya ye sach",
)


def _boundary_pattern(words):
    """Wrap each phrase with \\b on both ends (after trimming any
    trailing/leading space some entries use as a separator) so short
    tokens like "hi" or "ho" only match as whole words - not as a
    substring inside "nahi", "hoga", etc."""
    return "|".join(r"\b" + re.escape(w.strip()) + r"\b" for w in words)


_FORCE_COMPLEX_RE = re.compile(_boundary_pattern(_FORCE_COMPLEX_WORDS), re.IGNORECASE)

# The ONLY thing allowed into the tool-free fast tier: recognizably casual
# conversation with no factual content to get wrong. Deliberately narrow -
# growing this list is safe (worst case something casual goes through the
# slower complex path instead), shrinking coverage of _FORCE_COMPLEX_WORDS
# above is not.
#
# NOT included: "kya chal raha (hai)" ("what's going on / what's
# running") - looks casual but is genuinely ambiguous with a real system
# query (a tool - list_running_apps - actually answers "what's running"),
# so it defaults to "complex" like any other non-allowlisted phrasing
# rather than risk guessing.
_CASUAL_ALLOW_WORDS = (
    # greetings / smalltalk
    "hi",
    "hii",
    "hiii",
    "hello",
    "hey",
    "yo",
    "namaste",
    "namaskar",
    "good morning",
    "good night",
    "good evening",
    "good afternoon",
    "how are you",
    "kaise ho",
    "kaisi ho",
    "kaise hain",
    "kya haal",
    "what's up",
    "whats up",
    "sup",
    # thanks / acknowledgement / farewell
    "thank",
    "thanks",
    "thank you",
    "thankyou",
    "shukriya",
    "dhanyavad",
    "bye",
    "goodbye",
    "good bye",
    "see you",
    "ttyl",
    "ok bye",
    "theek hai",
    "achha",
    "acha",
    "cool",
    "nice",
    "great",
    "awesome",
    "wow",
    "haha",
    "lol",
    "lmao",
    # about the assistant itself / its opinions - not external facts
    "what can you do",
    "who made you",
    "who created you",
    "your name",
    "tell me a joke",
    "joke sunao",
    "tumhara naam",
    "tum kaun ho",
    "what do you think",
    "your opinion",
    "tumhe kaisa laga",
    "i love you",
    "good job",
    "well done",
    "shabash",
)

# A short "address"/filler word that may trail (or lead, for "ultron"
# alone) a casual phrase without turning it into something else - e.g.
# "thanks yaar", "hi sir", "ok ultron". Anything beyond these words after
# the casual phrase means real content followed the greeting, which must
# not be swallowed - see the fullmatch requirement below.
_CASUAL_FILLER_WORDS = ("yaar", "bhai", "sir", "dude", "boss", "ultron", "hai")

_CASUAL_ALLOW_RE = re.compile(
    r"^(?:" + "|".join(_CASUAL_FILLER_WORDS) + r")?[\s,]*"
    r"(?:" + "|".join(re.escape(w.strip()) for w in _CASUAL_ALLOW_WORDS) + r")"
    r"[\s,.!]*(?:" + "|".join(_CASUAL_FILLER_WORDS) + r")?[\s,.!]*$",
    re.IGNORECASE,
)


def classify(text: str) -> Tier:
    """Classify already-not-"simple" text as "normal" (fast, tool-free
    model - casual chat ONLY) or "complex" (full tool-calling model,
    with search_internet/fact_check_claim available). Never raises,
    never touches the network - pure string matching.

    Default is "complex". "normal" requires the ENTIRE message (after
    stripping a leading wake-word address like "hi ultron") to consist of
    nothing but a recognized casual-chat phrase plus optional filler -
    not merely to *contain* one. This matters specifically for messages
    like "hi ultron, cpu kitna use ho raha hai": a plain substring check
    on "hi" would wrongly call the whole thing casual just because it
    opens with a greeting/address; requiring a full match means anything
    with real content after the greeting falls through to "complex" as
    it should."""
    if not text or not text.strip():
        return "normal"

    cleaned = _WAKE_PREFIX_RE.sub("", text.strip(), count=1).strip() or text.strip()

    if _FORCE_COMPLEX_RE.search(cleaned):
        return "complex"

    if _URL_OR_PATH_RE.search(cleaned):
        return "complex"

    if len(cleaned.split()) > NORMAL_MAX_WORDS:
        return "complex"

    # A "?" almost always means the user wants a specific answer, not
    # smalltalk - even something that opens casually.
    if "?" in cleaned:
        return "complex"

    if _CASUAL_ALLOW_RE.match(cleaned):
        return "normal"

    # Anything else - unrecognized phrasing, ambiguous, or simply not on
    # the casual allowlist - defaults to "complex" so it always has real
    # tools available rather than risk a guessed answer.
    return "complex"
