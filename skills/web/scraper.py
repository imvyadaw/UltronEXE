"""
Web scraper skill
==================
Structured scraping on top of skills/internet/web_tools.py's raw text
extraction: pulls links, images, tables, and specific elements via CSS
selectors from any URL. Static HTML only (requests + BeautifulSoup) - for
JS-rendered pages, pair with skills/web/form_filler.py's Selenium driver.
"""

from typing import Dict
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}


class WebScraper:
    """Structured, selector-driven scraping of static HTML pages."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def _get_soup(self, url: str) -> BeautifulSoup:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        resp = requests.get(url, headers=HEADERS, timeout=self.timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.content, "html.parser"), url

    def scrape_links(self, url: str, same_domain_only: bool = False) -> Dict:
        try:
            soup, resolved_url = self._get_soup(url)
            domain = urlparse(resolved_url).netloc
            links = []
            for a in soup.find_all("a", href=True):
                href = urljoin(resolved_url, a["href"])
                if same_domain_only and urlparse(href).netloc != domain:
                    continue
                text = a.get_text(strip=True)
                if href.startswith("http"):
                    links.append({"text": text, "url": href})
            return {"success": True, "url": resolved_url, "count": len(links), "links": links}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def scrape_images(self, url: str) -> Dict:
        try:
            soup, resolved_url = self._get_soup(url)
            images = []
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src")
                if not src:
                    continue
                images.append(
                    {
                        "url": urljoin(resolved_url, src),
                        "alt": img.get("alt", ""),
                    }
                )
            return {"success": True, "url": resolved_url, "count": len(images), "images": images}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def scrape_tables(self, url: str) -> Dict:
        """Extract HTML <table> elements as lists of row dicts (header -> value)."""
        try:
            soup, resolved_url = self._get_soup(url)
            tables_out = []
            for table in soup.find_all("table"):
                headers = [th.get_text(strip=True) for th in table.find_all("th")]
                rows = []
                for tr in table.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                    if not cells:
                        continue
                    if headers and len(headers) == len(cells):
                        rows.append(dict(zip(headers, cells)))
                    else:
                        rows.append(cells)
                if rows:
                    tables_out.append({"headers": headers, "rows": rows})
            return {"success": True, "url": resolved_url, "count": len(tables_out), "tables": tables_out}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def scrape_selector(self, url: str, selector: str) -> Dict:
        """Extract text of every element matching a CSS selector, e.g. 'h2.title'."""
        try:
            soup, resolved_url = self._get_soup(url)
            elements = soup.select(selector)
            texts = [el.get_text(strip=True) for el in elements]
            return {"success": True, "url": resolved_url, "selector": selector, "count": len(texts), "results": texts}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def scrape_metadata(self, url: str) -> Dict:
        """Title, meta description, and Open Graph tags - handy for link previews."""
        try:
            soup, resolved_url = self._get_soup(url)
            meta = {"title": soup.title.string.strip() if soup.title and soup.title.string else ""}
            desc_tag = soup.find("meta", attrs={"name": "description"})
            meta["description"] = desc_tag.get("content", "") if desc_tag else ""
            for tag in soup.find_all("meta", attrs={"property": lambda p: p and p.startswith("og:")}):
                meta[tag["property"]] = tag.get("content", "")
            return {"success": True, "url": resolved_url, "metadata": meta}
        except Exception as e:
            return {"success": False, "error": str(e)}


# --- Phase 4: unified skill facade --------------------------------------
from skills.base_skill import BaseSkill  # noqa: E402


class WebScraperSkill(BaseSkill):
    """BaseSkill wrapper around WebScraper for the skill registry / AI tool layer."""

    name = "web_scraper"
    description = "Scrape links, images, tables, CSS selectors, and page metadata from a URL."
    category = "web"

    def __init__(self, timeout: int = 15):
        self._scraper = WebScraper(timeout=timeout)
        super().__init__()

    def register_actions(self) -> None:
        s = self._scraper
        self._actions = {
            "links": s.scrape_links,
            "images": s.scrape_images,
            "tables": s.scrape_tables,
            "selector": s.scrape_selector,
            "metadata": s.scrape_metadata,
        }
