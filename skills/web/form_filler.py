"""
Form filler skill
==================
Fills and submits web forms on JS-rendered pages using Selenium (needed
because skills/web/scraper.py's requests+BeautifulSoup approach can't
execute JS or interact with dynamic forms). Uses webdriver-manager so no
manual chromedriver install is needed.

Note: this drives a *separate* automated browser window via Selenium -
it does not control the user's already-open Chrome (for that, see
browser/chrome/chrome.py, which uses UI automation on the real window).
Use this skill for headless/background form submissions (newsletter
signups, contact forms, login flows, repetitive data entry, etc).
"""

from typing import Dict, List, Optional

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager

    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

BY_MAP = {
    "id": "ID",
    "name": "NAME",
    "css": "CSS_SELECTOR",
    "xpath": "XPATH",
    "class": "CLASS_NAME",
    "tag": "TAG_NAME",
    "link_text": "LINK_TEXT",
}


class FormFiller:
    """Selenium-backed automated form filling for web pages."""

    def __init__(self, headless: bool = True, timeout: int = 15):
        if not HAS_SELENIUM:
            raise RuntimeError("Form filling needs: pip install selenium webdriver-manager")
        self.headless = headless
        self.timeout = timeout
        self._driver = None

    def _get_driver(self):
        if self._driver is not None:
            return self._driver
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1280,900")
        service = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=service, options=options)
        return self._driver

    def _by(self, by: str):
        return getattr(By, BY_MAP.get(by, "CSS_SELECTOR"))

    def fill_form(
        self, url: str, fields: List[Dict], submit_selector: Optional[str] = None, submit_by: str = "css"
    ) -> Dict:
        """
        fields: list of {"selector": str, "value": str, "by": "id"|"name"|"css"|"xpath" (default css)}
        submit_selector: selector of the submit button (skipped if None - use for
        "fill but don't submit" flows like drafts/previews).
        """
        try:
            driver = self._get_driver()
            driver.get(url if url.startswith(("http://", "https://")) else "https://" + url)
            wait = WebDriverWait(driver, self.timeout)

            filled = []
            for field in fields:
                by = self._by(field.get("by", "css"))
                selector = field["selector"]
                el = wait.until(EC.presence_of_element_located((by, selector)))
                el.clear()
                el.send_keys(field["value"])
                filled.append(selector)

            submitted = False
            if submit_selector:
                by = self._by(submit_by)
                submit_el = wait.until(EC.element_to_be_clickable((by, submit_selector)))
                submit_el.click()
                submitted = True

            return {"success": True, "url": url, "fields_filled": filled, "submitted": submitted}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def click_element(self, url: str, selector: str, by: str = "css") -> Dict:
        try:
            driver = self._get_driver()
            driver.get(url if url.startswith(("http://", "https://")) else "https://" + url)
            wait = WebDriverWait(driver, self.timeout)
            el = wait.until(EC.element_to_be_clickable((self._by(by), selector)))
            el.click()
            return {"success": True, "url": url, "clicked": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def extract_after_render(self, url: str, wait_selector: Optional[str] = None) -> Dict:
        """Load a JS-heavy page, wait for a selector to appear, then return the
        fully rendered HTML (useful before handing off to scraper.py for parsing)."""
        try:
            driver = self._get_driver()
            driver.get(url if url.startswith(("http://", "https://")) else "https://" + url)
            if wait_selector:
                WebDriverWait(driver, self.timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
                )
            return {"success": True, "url": url, "html": driver.page_source}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close(self) -> Dict:
        if self._driver is not None:
            self._driver.quit()
            self._driver = None
        return {"success": True, "action": "browser closed"}

    def __del__(self):
        try:
            if self._driver is not None:
                self._driver.quit()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("skills.web.form_filler.__del__")
