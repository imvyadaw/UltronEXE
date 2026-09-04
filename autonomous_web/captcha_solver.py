"""
captcha_solver.py
==================
Detects CAPTCHA challenges (reCAPTCHA v2/v3, hCaptcha, and generic
image CAPTCHAs) encountered during autonomous browsing sessions, and
resolves them one of two ways:

  1. Via a user-configured third-party solving service (2Captcha /
     Anti-Captcha style). Requires the user's own API key
     (CAPTCHA_SOLVER_API_KEY / CAPTCHA_SOLVER_PROVIDER in .env) and
     their own balance with that provider - this module never embeds
     a bypass or cracking algorithm of its own.
  2. If no provider is configured (the default), automation pauses
     and hands control back to the user to solve the challenge
     manually in the visible browser window, then resumes.

site_navigator / form_filler / web_agent_core call into this when a
challenge is detected rather than guessing or retrying blindly.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import Page

logger = logging.getLogger("ultron.captcha_solver")


@dataclass
class CaptchaDetection:
    kind: str  # "recaptcha_v2" | "recaptcha_v3" | "hcaptcha" | "image" | "none"
    site_key: Optional[str] = None
    frame_url: Optional[str] = None


class CaptchaSolver:
    """
    Usage:
        solver = CaptchaSolver(page)
        detection = solver.detect()
        if detection.kind != "none":
            solver.resolve(detection, page_url=page.url)
    """

    def __init__(self, page: Page, manual_timeout_s: int = 180):
        self.page = page
        self.manual_timeout_s = manual_timeout_s
        self.provider = os.getenv("CAPTCHA_SOLVER_PROVIDER", "").strip().lower()
        self.api_key = os.getenv("CAPTCHA_SOLVER_API_KEY", "").strip()

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------
    def detect(self) -> CaptchaDetection:
        try:
            if self.page.locator("iframe[src*='recaptcha/api2']").count() > 0:
                site_key = self._extract_attr("div.g-recaptcha", "data-sitekey")
                return CaptchaDetection("recaptcha_v2", site_key=site_key)

            if self.page.locator("iframe[src*='hcaptcha.com']").count() > 0:
                site_key = self._extract_attr("div.h-captcha", "data-sitekey")
                return CaptchaDetection("hcaptcha", site_key=site_key)

            if self.page.locator("script[src*='recaptcha/releases']").count() > 0:
                return CaptchaDetection("recaptcha_v3")

            if self.page.locator("img[src*='captcha'], img[alt*='captcha' i]").count() > 0:
                return CaptchaDetection("image")

        except Exception as e:
            logger.debug("CAPTCHA detection check failed harmlessly: %s", e)

        return CaptchaDetection("none")

    def _extract_attr(self, selector: str, attr: str) -> Optional[str]:
        try:
            el = self.page.locator(selector).first
            if el.count() > 0:
                return el.get_attribute(attr)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("autonomous_web.captcha_solver._extract_attr")
        return None

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------
    def resolve(self, detection: CaptchaDetection, page_url: str) -> bool:
        if detection.kind == "none":
            return True

        if self.provider and self.api_key and detection.site_key:
            token = self._solve_via_provider(detection, page_url)
            if token:
                return self._inject_token(detection, token)
            logger.warning(
                "%s solving via '%s' failed or timed out; falling back to manual.",
                detection.kind,
                self.provider,
            )

        return self._wait_for_manual_solve(detection)

    def _solve_via_provider(self, detection: CaptchaDetection, page_url: str) -> Optional[str]:
        """
        Submits the challenge to the configured third-party solving
        service and polls for the result token. Requires the user's
        own account/balance with that provider - this is a thin
        client for their service, not a solving algorithm.
        """
        try:
            import requests
        except ImportError:
            logger.error("The 'requests' package is required for provider-based CAPTCHA solving.")
            return None

        try:
            if self.provider == "2captcha":
                method = "userrecaptcha" if "recaptcha" in detection.kind else "hcaptcha"
                submit = requests.post(
                    "https://2captcha.com/in.php",
                    data={
                        "key": self.api_key,
                        "method": method,
                        "googlekey": detection.site_key,
                        "sitekey": detection.site_key,
                        "pageurl": page_url,
                        "json": 1,
                    },
                    timeout=30,
                )
                submit.raise_for_status()
                job = submit.json()
                if job.get("status") != 1:
                    logger.warning("2Captcha submit rejected: %s", job.get("request"))
                    return None
                request_id = job["request"]

                deadline = time.time() + self.manual_timeout_s
                while time.time() < deadline:
                    time.sleep(5)
                    poll = requests.get(
                        "https://2captcha.com/res.php",
                        params={"key": self.api_key, "action": "get", "id": request_id, "json": 1},
                        timeout=30,
                    )
                    result = poll.json()
                    if result.get("status") == 1:
                        return result["request"]
                    if result.get("request") != "CAPCHA_NOT_READY":
                        logger.warning("2Captcha poll error: %s", result.get("request"))
                        return None
                return None
            else:
                logger.warning("Unsupported CAPTCHA_SOLVER_PROVIDER '%s'.", self.provider)
                return None

        except Exception as e:
            logger.error("Provider-based CAPTCHA solve failed: %s", e)
            return None

    def _inject_token(self, detection: CaptchaDetection, token: str) -> bool:
        try:
            field = "g-recaptcha-response" if "recaptcha" in detection.kind else "h-captcha-response"
            self.page.evaluate(
                """([field, token]) => {
                    let el = document.getElementById(field) ||
                             document.querySelector(`textarea[name="${field}"]`);
                    if (el) { el.style.display = 'block'; el.value = token; }
                }""",
                [field, token],
            )
            logger.info("Injected %s solve token.", detection.kind)
            return True
        except Exception as e:
            logger.error("Failed to inject CAPTCHA token: %s", e)
            return False

    def _wait_for_manual_solve(self, detection: CaptchaDetection) -> bool:
        """
        No solving provider configured (or it failed) - pause and let
        the person handle the challenge themselves in the visible
        browser window, then resume automation once it clears.
        """
        logger.info(
            "%s challenge detected - waiting up to %ss for it to be solved manually.",
            detection.kind,
            self.manual_timeout_s,
        )
        deadline = time.time() + self.manual_timeout_s
        while time.time() < deadline:
            time.sleep(2)
            if self.detect().kind == "none":
                logger.info("CAPTCHA cleared - resuming automation.")
                return True
        logger.warning("CAPTCHA not resolved within timeout; aborting this step.")
        return False
