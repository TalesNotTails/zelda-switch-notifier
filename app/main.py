import json
import logging
import os
import random
import time
from pathlib import Path

import yaml

from checker import StoreChecker, IN_STOCK, OUT_OF_STOCK, UNKNOWN, ERROR
from notifier import send_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
STATE_PATH = Path("/app/state/state.json")


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            logger.warning("State file corrupt, starting fresh")
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def main():
    config = load_config()
    state = load_state()  # { store_name: {"last_status": ..., "last_notified_at": ts} }

    interval = config.get("check_interval_seconds", 240)
    jitter = config.get("check_interval_jitter_seconds", 60)
    timeout_ms = config.get("request_timeout_ms", 20000)
    wait_ms = config.get("page_load_wait_ms", 2500)
    cooldown = int(os.environ.get("RENOTIFY_COOLDOWN_SECONDS", "1800"))

    stores = config.get("stores", [])
    logger.info("Starting monitor for %d store(s)", len(stores))

    while True:
        with StoreChecker(timeout_ms=timeout_ms, page_load_wait_ms=wait_ms) as checker:
            for store in stores:
                name = store["name"]
                result = checker.check(store)
                now = time.time()
                prev = state.get(name, {"last_status": None, "last_notified_at": 0})

                if result == IN_STOCK:
                    became_in_stock = prev["last_status"] != IN_STOCK
                    past_cooldown = (now - prev.get("last_notified_at", 0)) > cooldown
                    if became_in_stock or past_cooldown:
                        message = f"IN STOCK: {name} - Zelda 40th Anniversary Switch 2! {store['url']}"
                        logger.info("Notifying: %s", message)
                        send_notification(message)
                        prev["last_notified_at"] = now
                    prev["last_status"] = IN_STOCK

                elif result in (OUT_OF_STOCK, UNKNOWN, ERROR):
                    prev["last_status"] = result

                state[name] = prev
                # Small stagger between stores so requests don't all fire at once
                time.sleep(random.uniform(2, 5))

        save_state(state)
        sleep_for = interval + random.uniform(-jitter, jitter)
        sleep_for = max(30, sleep_for)
        logger.info("Sweep complete. Sleeping %.0fs", sleep_for)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
