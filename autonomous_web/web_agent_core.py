"""
web_agent_core.py
==================
Base browser-automation engine (Playwright) that the rest of
AUTONOMOUS_WEB builds on: launch/close a browser, open pages, click,
type, wait for elements, screenshot. Keep this file dumb-and-reliable;
put task-specific logic in the other modules.

Dependencies: pip install playwright && playwright install chromium
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, TimeoutError as PWTimeout

logger = logging.getLogger("ultron.web_agent_core")


@dataclass
class AgentConfig:
    headless: bool = False  # visible by default so a captcha or
    # login prompt is something the user
    # can see and handle themselves
    user_data_dir: Optional[str] = None  # persistent profile (keeps logins)
    default_timeout_ms: int = 15000
    viewport: tuple = (1366, 900)


class WebAgentCore:
    """
    Usage:
        agent = WebAgentCore()
        agent.start()
        page = agent.new_page()
        page.goto("https://example.com")
        agent.stop()

    Or as a context manager:
        with WebAgentCore() as agent:
            page = agent.new_page()
            ...
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    def start(self):
        self._playwright = sync_playwright().start()
        launch_args = {"headless": self.config.headless}

        if self.config.user_data_dir:
            Path(self.config.user_data_dir).mkdir(parents=True, exist_ok=True)
            self._context = self._playwright.chromium.launch_persistent_context(
                self.config.user_data_dir,
                headless=self.config.headless,
                viewport={"width": self.config.viewport[0], "height": self.config.viewport[1]},
            )
            self._browser = None  # persistent context owns its own browser internally
        else:
            self._browser = self._playwright.chromium.launch(**launch_args)
            self._context = self._browser.new_context(
                viewport={"width": self.config.viewport[0], "height": self.config.viewport[1]}
            )

        self._context.set_default_timeout(self.config.default_timeout_ms)
        logger.info(
            "WebAgentCore started (headless=%s, persistent=%s)", self.config.headless, bool(self.config.user_data_dir)
        )

    def new_page(self) -> Page:
        if self._context is None:
            raise RuntimeError("Call start() before new_page()")
        return self._context.new_page()

    def screenshot(self, page: Page, path: str, full_page: bool = True):
        page.screenshot(path=path, full_page=full_page)
        logger.info("Saved screenshot to %s", path)

    def wait_for_selector(self, page: Page, selector: str, timeout_ms: Optional[int] = None) -> bool:
        try:
            page.wait_for_selector(selector, timeout=timeout_ms or self.config.default_timeout_ms)
            return True
        except PWTimeout:
            logger.warning("Timed out waiting for selector: %s", selector)
            return False

    def looks_like_challenge_page(self, page: Page) -> bool:
        """
        Heuristic check for a captcha/anti-bot challenge page, so the
        calling code can pause and hand control to the user instead of
        trying to power through it. This module does not attempt to
        solve challenges - see README_PHASE_17_6.md.
        """
        markers = ["captcha", "verify you are human", "cloudflare", "are you a robot"]
        try:
            content = page.content().lower()
            return any(m in content for m in markers)
        except Exception:
            return False

    def stop(self):
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        logger.info("WebAgentCore stopped")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with WebAgentCore() as agent:
        page = agent.new_page()
        page.goto("https://example.com")
        print(page.title())
