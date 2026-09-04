"""
SEARCH (Phase 18.5)
====================
Six narrow modules over external search APIs, same one-module-per-
concern shape as EYES/, EARS/, DISPLAY/, and MOUTH/:

    google_search.py - the base web-search backend (Google Custom
                        Search JSON API). image_search.py,
                        price_search.py, and people_search.py all
                        build on this module rather than each making
                        their own HTTP calls.
    image_search.py  - same API, searchType=image, its own result
                        shape.
    news_search.py    - NewsAPI.org, for real publish timestamps and
                        source attribution google_search.py doesn't
                        give.
    fact_check.py     - Google Fact Check Tools API - returns what
                        publishers have already rated a claim, never
                        this project's own verdict.
    price_search.py   - google_search.py restricted to a fixed
                        shopping-site list, with a regex price-pattern
                        extraction over the snippet - an honestly-
                        labeled heuristic, not a real price-comparison
                        API.
    people_search.py  - google_search.py restricted to public
                        professional/biographical sources (LinkedIn,
                        Wikipedia) only, with a second filter dropping
                        any data-broker domain that slips through.
                        Deliberately does not do reverse phone/address
                        lookups or broker aggregation - see that
                        module's own docstring for why.

Every module needs its own API key(s) in an environment variable
(never hardcoded, never logged) and is_available() before search()
returns anything - no key, no `requests` package, or no network all
collapse to an empty list rather than an exception, same contract
every other module in this project already promises. Cross-module
imports (price_search.py and people_search.py into google_search.py)
are lazy inside methods, consistent with the rest of the codebase.

Purely additive - nothing in Phase 1-18.4 imports from here.
"""

from search.google_search import get_google_search
from search.image_search import get_image_search
from search.news_search import get_news_search
from search.fact_check import get_fact_check
from search.price_search import get_price_search
from search.people_search import get_people_search
from search.wikipedia_search import get_wikipedia_search

__all__ = [
    "get_google_search",
    "get_image_search",
    "get_news_search",
    "get_fact_check",
    "get_price_search",
    "get_people_search",
    "get_wikipedia_search",
]
