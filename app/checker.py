"""
Fetches a store's product page with a real headless browser (so JS-rendered
stock widgets on sites like Target/Best Buy/Walmart actually load) and
classifies the page as IN_STOCK / OUT_OF_STOCK / UNKNOWN based on configured
phrases.
"""
import logging
import random
import time

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

# Errors worth retrying a couple times before giving up on this sweep - these
# are typically a bot-protection WAF (Akamai/PerimeterX/etc.) abruptly
# resetting the connection against a headless browser, not a real outage.
# The page loading fine in a normal browser but failing here is the classic
# symptom.
TRANSIENT_ERROR_SNIPPETS = [
    "err_http2_protocol_error",
    "err_connection_reset",
    "err_connection_closed",
    "err_empty_response",
]

# Hides the most common automation fingerprint (navigator.webdriver === true)
# that bot-detection scripts check for.
STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
"""


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
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                # Falling back to HTTP/1.1 avoids a class of WAFs that reset
                # the connection when they fingerprint a headless client's
                # HTTP/2 handshake, which surfaces as ERR_HTTP2_PROTOCOL_ERROR.
                "--disable-http2",
            ],
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def check(self, store: dict, max_retries: int = 2) -> str:
        name = store["name"]
        url = store["url"]

        if not url or url.startswith("REPLACE_WITH"):
            logger.warning("Skipping %s: no real URL configured yet", name)
            return UNKNOWN

        last_exc = None
        for attempt in range(1, max_retries + 2):  # e.g. max_retries=2 -> 3 tries total
            context = self._browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            context.add_init_script(STEALTH_INIT_SCRIPT)
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
                logger.warning("%s: page load timed out (attempt %d)", name, attempt)
                last_exc = "timeout"
            except Exception as exc:  # noqa: BLE001 - log and keep the loop alive
                last_exc = str(exc)
                is_transient = any(s in last_exc.lower() for s in TRANSIENT_ERROR_SNIPPETS)
                if is_transient and attempt <= max_retries:
                    backoff = 3 * attempt
                    logger.warning(
                        "%s: transient error on attempt %d (%s) - retrying in %ds",
                        name, attempt, last_exc, backoff,
                    )
                    time.sleep(backoff)
                    continue
                logger.warning("%s: check failed (%s)", name, last_exc)
                return ERROR
            finally:
                context.close()

        logger.warning("%s: giving up after %d attempts (%s)", name, max_retries + 1, last_exc)
        return ERROR
