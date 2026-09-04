"""
People Search
=============
Deliberately scoped narrower than its name might suggest: this module
looks up a person's *public, professional/biographical* footprint
(their LinkedIn, a Wikipedia page, an official staff/about-us bio) -
not a general-purpose "find anyone" tool. It does not, and will not,
grow into:

  - reverse phone/address/email lookups
  - aggregation across data-broker sites (Spokeo, Whitepages,
    BeenVerified, Intelius, MyLife, TruthFinder, PeopleFinders, and
    similar)
  - anything framed as a background check

That's a scoping decision, not an oversight: the difference between
"here's this person's public professional bio" and "here's how to
find out where someone lives" is the difference between a contacts
tool and a surveillance tool, and this project's own MEMORY/face_memory.py
and MEMORY/forget.py already show a consistent instinct toward
minimal, auditable, non-cascading handling of information about
people - this module follows that same instinct at the search layer.

Two safeguards enforce the scope instead of just documenting it:
queries are restricted to BIO_SITES via google_search.py's `site`
param, and any result whose URL host matches BLOCKED_DOMAINS is
dropped even if it somehow appeared anyway (e.g. Google indexing a
blocked domain's page under a bio-adjacent site search). Nothing here
writes to MEMORY/ automatically - a match found here becoming a
long_term.py fact or a face_memory.py entry is a deliberate,
separate call the caller makes, same as every other write in this
project.
"""

from typing import Dict, List, Optional
from urllib.parse import urlparse

BIO_SITES = ["linkedin.com", "wikipedia.org"]

BLOCKED_DOMAINS = {
    "spokeo.com",
    "whitepages.com",
    "beenverified.com",
    "intelius.com",
    "mylife.com",
    "truthfinder.com",
    "peoplefinders.com",
    "radaris.com",
    "instantcheckmate.com",
    "peekyou.com",
    "fastpeoplesearch.com",
}


class PeopleSearch:
    """Public professional/bio-only person search. Use get_people_search()."""

    def is_available(self) -> bool:
        try:
            from search.google_search import get_google_search

            return get_google_search().is_available()
        except Exception:
            return False

    def search(self, name: str, context: str = "", num_per_site: int = 3) -> List[Dict]:
        """Looks up `name` across BIO_SITES only. `context` is an
        optional extra term (a company, a field) appended to narrow an
        ambiguous common name - it is not a way to broaden scope past
        BIO_SITES. Returns
        {"title": str, "url": str, "snippet": str, "site": str},
        with any BLOCKED_DOMAINS hit silently dropped rather than
        surfaced. Empty list on no backend or no name."""
        if not name:
            return []
        try:
            from search.google_search import get_google_search

            engine = get_google_search()
        except Exception:
            return []
        if not engine.is_available():
            return []

        query = f"{name} {context}".strip()
        results: List[Dict] = []
        for site in BIO_SITES:
            try:
                hits = engine.search(query, num=num_per_site, site=site)
            except Exception:
                hits = []
            for h in hits:
                if self._is_blocked(h.get("url", "")):
                    continue
                results.append({**h, "site": site})
        return results

    @staticmethod
    def _is_blocked(url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
            return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)
        except Exception:
            return True  # if the URL can't even be parsed, don't trust it


_people_search: Optional[PeopleSearch] = None


def get_people_search() -> PeopleSearch:
    global _people_search
    if _people_search is None:
        _people_search = PeopleSearch()
    return _people_search
