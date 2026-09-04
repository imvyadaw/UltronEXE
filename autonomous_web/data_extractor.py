"""
data_extractor.py
==================
Pulls structured data out of a page: tables into rows of dicts, lists
of links, or arbitrary fields via a CSS-selector map. Meant for
public, non-authenticated scraping tasks the user asks for directly
(e.g. "grab the price list from this page") - always check the
target site's terms of service / robots.txt for what's allowed before
scraping it at scale.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from playwright.sync_api import Page

logger = logging.getLogger("ultron.data_extractor")


class DataExtractor:
    def __init__(self, page: Page):
        self.page = page

    def extract_table(self, table_selector: str = "table") -> List[Dict[str, str]]:
        """Extracts the first matching <table> into a list of row dicts,
        using the header row as keys."""
        table = self.page.query_selector(table_selector)
        if not table:
            logger.warning("No table found for selector: %s", table_selector)
            return []

        headers = [th.inner_text().strip() for th in table.query_selector_all("thead th")]
        if not headers:
            first_row_cells = table.query_selector_all("tr:first-child th, tr:first-child td")
            headers = [c.inner_text().strip() for c in first_row_cells]

        rows = table.query_selector_all("tbody tr") or table.query_selector_all("tr")
        results = []
        for row in rows:
            cells = row.query_selector_all("td")
            if not cells:
                continue
            values = [c.inner_text().strip() for c in cells]
            if headers and len(headers) == len(values):
                results.append(dict(zip(headers, values)))
            else:
                results.append({f"col_{i}": v for i, v in enumerate(values)})
        return results

    def extract_links(self, container_selector: str = "body") -> List[Dict[str, str]]:
        container = self.page.query_selector(container_selector)
        if not container:
            return []
        anchors = container.query_selector_all("a[href]")
        return [
            {"text": a.inner_text().strip(), "href": a.get_attribute("href")} for a in anchors if a.inner_text().strip()
        ]

    def extract_by_map(self, field_selectors: Dict[str, str]) -> Dict[str, Optional[str]]:
        """field_selectors: {"price": ".price", "title": "h1.product-title"}"""
        result = {}
        for field, selector in field_selectors.items():
            el = self.page.query_selector(selector)
            result[field] = el.inner_text().strip() if el else None
        return result

    def extract_all_matching(self, selector: str) -> List[str]:
        return [el.inner_text().strip() for el in self.page.query_selector_all(selector)]

    # -------------------------------------------------------------- export
    def save_json(self, data, path: str):
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Saved extracted data to %s", path)

    def save_csv(self, rows: List[Dict[str, str]], path: str):
        if not rows:
            logger.warning("save_csv called with no rows")
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        logger.info("Saved %d rows to %s", len(rows), path)
