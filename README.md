# Zelda 40th Anniversary Switch 2 — Stock Monitor

Polls retailer product pages with a real headless browser and texts you the
moment one shows the item in stock.

## 1. Fill in the product URLs

Open `config.yaml` and replace every `REPLACE_WITH_...` URL with the real
product page from that retailer (find each by searching the retailer's site
for "Nintendo Switch 2 Legend of Zelda 40th Anniversary Edition"). GameStop's
is already filled in as a working example. Delete any store block you don't
want watched.

If a store keeps logging `UNKNOWN` in the console, open its page in a normal
browser, right-click → "View Page Source" (or Inspect) while it's known to be
out of stock, and add whatever phrase it actually displays (e.g. "Notify Me",
"Sold Out Online") to that store's `out_of_stock_phrases` list.

## 2. Set up text notifications

Copy the example env file:

```bash
cp .env.example .env
```

Then pick ONE approach in `.env`:

**Option A — Twilio (recommended, real SMS):**
1. Sign up free at twilio.com, get a trial phone number.
2. Set `NOTIFY_METHOD=twilio` and fill in `TWILIO_ACCOUNT_SID`,
   `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `TWILIO_TO_NUMBER` (your own
   phone, in `+1XXXXXXXXXX` format).
2. Trial accounts can only text a verified number — verify your own number
   in the Twilio console first.

**Option B — Free email-to-SMS gateway (no signup, uses your carrier):**
1. Set `NOTIFY_METHOD=email_sms`.
2. Fill in an SMTP account to send from (a Gmail address with an
   [App Password](https://myaccount.google.com/apppasswords) works well —
   don't use your real Gmail password).
3. Set `SMS_GATEWAY_TO` to `yournumber@carriergateway.com`:
   - Verizon: `@vtext.com`
   - AT&T: `@txt.att.net`
   - T-Mobile: `@tmomail.net`
   - Google Fi: `@msg.fi.google.com`
4. This is free but slightly less reliable/instant than Twilio, and some
   carriers throttle or block it occasionally.

You can also set `NOTIFY_METHOD=both` to try Twilio first and email-to-SMS as
backup.

## 3. Run it

```bash
docker compose up -d --build
```

Check logs any time:

```bash
docker compose logs -f
```

Stop it:

```bash
docker compose down
```

## How it works

- Every ~4 minutes (randomized a bit so it doesn't look like a bot), it opens
  each product page in a headless Chromium browser, waits for the page to
  render, and scans the text for phrases like "Add to Cart" vs. "Sold Out" /
  "Currently Unavailable".
- The moment a store flips to in-stock, it fires a text with the store name
  and a direct link. It won't spam you every cycle — once notified, it waits
  `RENOTIFY_COOLDOWN_SECONDS` (default 30 min) before texting again about the
  same store, in case it stays in stock.
- State (last known status per store) is saved to `./state/state.json` on
  your host, so restarting the container doesn't lose track and re-fire
  duplicate notifications.

## Notes and limits

- Retailers like Amazon, Best Buy, Walmart, and Target actively try to detect
  and block automated browsing. This tool checks infrequently and uses a real
  browser to look as normal as possible, but a site can still occasionally
  block or CAPTCHA it — check `docker compose logs` if a store isn't reporting
  correctly. Please keep the check interval reasonable (don't drop it below
  ~1-2 minutes) so you don't get your IP flagged.
- This is for personal use checking a page you'd otherwise be refreshing by
  hand — always follow the retailer's terms of use.
- Given this item's demand, expect quick sellouts even with instant alerts —
  consider signing up for GameStop PowerUp Rewards Pro / retailer stock alert
  emails as a backup, and having a payment method saved on each site for
  faster checkout.
