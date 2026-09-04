"""
site_navigator.py
==================
Higher-level navigation helpers built on top of WebAgentCore: go to a
URL, click a link by visible text, scroll, wait for network idle,
handle simple pagination. Task modules (form_filler, data_extractor,
social_media_agent) call into this rather than touching Playwright
directly.
"""

from __future__ import annotations

import logging
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PWTimeout

logger = logging.getLogger("ultron.site_navigator")


class SiteNavigator:
    def __init__(self, page: Page, default_timeout_ms: int = 15000):
        self.page = page
        self.default_timeout_ms = default_timeout_ms

    def goto(self, url: str, wait_until: str = "load") -> bool:
        try:
            self.page.goto(url, wait_until=wait_until, timeout=self.default_timeout_ms)
            logger.info("Navigated to %s", url)
            return True
        except PWTimeout:
            logger.warning("Navigation to %s timed out", url)
            return False

    def click_text(self, text: str, exact: bool = False) -> bool:
        try:
            locator = self.page.get_by_text(text, exact=exact).first
            locator.click(timeout=self.default_timeout_ms)
            logger.info("Clicked text: %s", text)
            return True
        except PWTimeout:
            logger.warning("Could not find/click text: %s", text)
            return False

    def click_selector(self, selector: str) -> bool:
        try:
            self.page.click(selector, timeout=self.default_timeout_ms)
            return True
        except PWTimeout:
            logger.warning("Could not click selector: %s", selector)
            return False

    def wait_for_navigation(self, timeout_ms: Optional[int] = None):
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout_ms or self.default_timeout_ms)
        except PWTimeout:
            from core.error_trace import log_swallowed as _lsw

            _lsw("autonomous_web.site_navigator.wait_for_navigation")

    def scroll_to_bottom(self, pause_ms: int = 400, max_scrolls: int = 20):
        last_height = self.page.evaluate("document.body.scrollHeight")
        for _ in range(max_scrolls):
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(pause_ms)
            new_height = self.page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    def go_back(self):
        self.page.go_back()

    def current_url(self) -> str:
        return self.page.url

    def title(self) -> str:
        return self.page.title()
