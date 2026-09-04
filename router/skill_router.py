"""
router.skill_router
====================
Given a user message, ranks which skills/ domain (email, calendar,
file, web, ...) it most likely belongs to, by keyword overlap with each
domain's skills/<name>/MANIFEST.md - the same lightweight approach
ai.tool_selector.ToolSelector uses for individual tools, one level up
at the domain/folder level.

Deliberately reads MANIFEST.md files as plain text instead of importing
each skills/<domain> package: several of those packages have optional
third-party dependencies (google-api-python-client, msal, twilio, ...)
that shouldn't need to be installed just to answer "which skill area
does this message sound like" for a debug console or a routing hint in
a UI.
"""

import re
from pathlib import Path
from typing import Dict, List

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
_WORD_RE = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set:
    return set(_WORD_RE.findall(text.lower()))


def _load_manifest(domain_dir: Path) -> str:
    manifest = domain_dir / "MANIFEST.md"
    if not manifest.exists():
        return ""
    try:
        return manifest.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def list_skills() -> Dict[str, str]:
    """{domain_name: manifest_text} for every skills/<domain>/ that has
    a MANIFEST.md. Cheap - reads text files only, imports nothing from
    inside skills/."""
    skills: Dict[str, str] = {}
    if not SKILLS_DIR.exists():
        return skills
    for entry in sorted(SKILLS_DIR.iterdir()):
        if entry.is_dir() and not entry.name.startswith("_"):
            text = _load_manifest(entry)
            if text:
                skills[entry.name] = text
    return skills


def select_skill(message: str, top_k: int = 3) -> List[Dict]:
    """Rank skill domains by keyword overlap between `message` and each
    domain's name + MANIFEST.md content. Returns up to top_k
    [{domain, score, matched_words}], best first - an empty list means
    nothing overlapped confidently enough to be worth acting on."""
    message_words = _words(message)
    if not message_words:
        return []

    scored: List[Dict] = []
    for domain, manifest_text in list_skills().items():
        domain_words = _words(domain.replace("_", " ")) | _words(manifest_text)
        overlap = message_words & domain_words
        if not overlap:
            continue
        score = len(overlap) / max(len(domain_words), 1)
        scored.append(
            {
                "domain": domain,
                "score": round(score, 4),
                "matched_words": sorted(overlap),
            }
        )

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_k]
