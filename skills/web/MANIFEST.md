# Web skills

| Tool | Module |
|---|---|
| scrape_links, scrape_images, scrape_tables, scrape_selector, scrape_metadata | skills/web/scraper.py (`WebScraper`) |
| gather_sources, research | skills/web/research.py (`WebResearch` - builds on skills/internet/web_tools.py) |
| fill_form, click_element, extract_after_render, close | skills/web/form_filler.py (`FormFiller` - Selenium, needs `pip install selenium webdriver-manager`) |

`scraper.py` is static-HTML only (requests + BeautifulSoup, no JS
execution). For JS-rendered pages, use `form_filler.py`'s
`extract_after_render()` to get fully-rendered HTML first, then hand
that to `scraper.py`'s selector methods, or parse it directly.

`research.py`'s `research()` method optionally takes an `ai_router` object
(anything with a `.chat(prompt) -> str` method, e.g. `ai.ai_router.AIRouter()`)
to synthesize a cited summary; without one it just returns raw sources.
