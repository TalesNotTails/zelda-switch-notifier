"""
Fetches a store's product page with a real headless browser (so JS-rendered
stock widgets on sites like Target/Best Buy/Walmart actually load) and
classifies the page as IN_STOCK / OUT_OF_STOCK / UNKNOWN based on configured
phrases.
"""
import logging
import random

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger("checker")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36",
]

IN_STOCK = "IN_STOCK"
OUT_OF_STOCK = "OUT_OF_STOCK"
UNKNOWN = "UNKNOWN"
ERROR = "ERROR"


def classify_text(page_text: str, in_stock_phrases, out_of_stock_phrases) -> str:
    text = page_text.lower()

    # Out-of-stock phrases win ties: safer to under-notify than spam a dead link.
    for phrase in out_of_stock_phrases or []:
        if phrase.lower() in text:
            return OUT_OF_STOCK

    for phrase in in_stock_phrases or []:
        if phrase.lower() in text:
            return IN_STOCK

    return UNKNOWN


class StoreChecker:
    """Reuses one browser instance across many checks for efficiency."""

    def __init__(self, timeout_ms: int = 20000, page_load_wait_ms: int = 2500):
        self.timeout_ms = timeout_ms
        self.page_load_wait_ms = page_load_wait_ms
        self._playwright = None
        self._browser = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def check(self, store: dict) -> str:
        name = store["name"]
        url = store["url"]

        if not url or url.startswith("REPLACE_WITH"):
            logger.warning("Skipping %s: no real URL configured yet", name)
            return UNKNOWN

        context = self._browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        try:
            page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(self.page_load_wait_ms)
            body_text = page.inner_text("body")
            result = classify_text(
                body_text,
                store.get("in_stock_phrases"),
                store.get("out_of_stock_phrases"),
            )
            logger.info("%s -> %s", name, result)
            return result
        except PlaywrightTimeoutError:
            logger.warning("%s: page load timed out", name)
            return ERROR
        except Exception as exc:  # noqa: BLE001 - log and keep the loop alive
            logger.warning("%s: check failed (%s)", name, exc)
            return ERROR
        finally:
            context.close()
