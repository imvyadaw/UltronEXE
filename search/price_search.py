"""
Price Search
============
No free, reliable price-comparison API is bundled here, so this
module doesn't pretend to be one - it wraps google_search.py restricted
to a fixed list of shopping sites and regex-extracts a price-looking
substring from whatever snippet Google returns, the same "cheap
heuristic, honestly labeled" trade-off object_finder.py makes for
"where's a blob" instead of "what is this object". extracted_price is
None whenever the snippet didn't contain a confident match - callers
should treat every result's snippet as the source of truth and
extracted_price as a best-effort convenience, not a guaranteed current
price. Google's cached snippet text can lag the live page by hours or
days, so this is not suitable for anything price-sensitive (checkout
decisions, arbitrage) without the caller re-fetching the actual page.
"""

import re
from typing import Dict, List, Optional

SHOPPING_SITES = ["amazon.com", "amazon.in", "flipkart.com", "ebay.com", "walmart.com"]

# Matches currency-prefixed numbers like "$19.99", "Rs. 1,299", "₹499" -
# a plain heuristic, not a robust money parser (no multi-currency
# normalization, no handling of ranges like "$10-$20").
PRICE_PATTERN = re.compile(r"(?:\$|₹|Rs\.?\s?|USD\s?|INR\s?)\s?[\d,]+(?:\.\d{1,2})?")


class PriceSearch:
    """Shopping-site search with heuristic price extraction. Use get_price_search()."""

    def is_available(self) -> bool:
        try:
            from search.google_search import get_google_search

            return get_google_search().is_available()
        except Exception:
            return False

    def search(self, product: str, num_per_site: int = 3) -> List[Dict]:
        """Searches each site in SHOPPING_SITES for `product` and
        returns a flat list of
        {"title": str, "url": str, "snippet": str,
        "extracted_price": Optional[str], "site": str}. Empty list on
        no backend or no query; individual sites that error out are
        just skipped rather than failing the whole call."""
        if not product:
            return []
        try:
            from search.google_search import get_google_search

            engine = get_google_search()
        except Exception:
            return []
        if not engine.is_available():
            return []

        results: List[Dict] = []
        for site in SHOPPING_SITES:
            try:
                hits = engine.search(product, num=num_per_site, site=site)
            except Exception:
                hits = []
            for h in hits:
                results.append({**h, "extracted_price": self._extract_price(h.get("snippet", "")), "site": site})
        return results

    @staticmethod
    def _extract_price(snippet: str) -> Optional[str]:
        if not snippet:
            return None
        match = PRICE_PATTERN.search(snippet)
        return match.group(0).strip() if match else None


_price_search: Optional[PriceSearch] = None


def get_price_search() -> PriceSearch:
    global _price_search
    if _price_search is None:
        _price_search = PriceSearch()
    return _price_search
