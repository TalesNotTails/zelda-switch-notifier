"""
Sends a text notification via Twilio's REST API and/or a free
email-to-SMS carrier gateway. Reads all credentials from environment
variables so nothing sensitive lives in code or config.yaml.
"""
import logging
import os
import smtplib
from email.mime.text import MIMEText

import requests

logger = logging.getLogger("notifier")


def _send_twilio(message: str) -> bool:
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    to_number = os.environ.get("TWILIO_TO_NUMBER")

    if not all([sid, token, from_number, to_number]):
        logger.error("Twilio notify requested but credentials are incomplete in .env")
        return False

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    try:
        resp = requests.post(
            url,
            data={"From": from_number, "To": to_number, "Body": message},
            auth=(sid, token),
            timeout=15,
        )
        if resp.status_code >= 300:
            logger.error("Twilio API error %s: %s", resp.status_code, resp.text)
            return False
        logger.info("Twilio SMS sent")
        return True
    except requests.RequestException as exc:
        logger.error("Twilio request failed: %s", exc)
        return False


def _send_email_sms(message: str) -> bool:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    gateway_to = os.environ.get("SMS_GATEWAY_TO")

    if not all([host, username, password, gateway_to]):
        logger.error("email_sms notify requested but SMTP settings are incomplete in .env")
        return False

    msg = MIMEText(message)
    msg["From"] = username
    msg["To"] = gateway_to
    msg["Subject"] = ""  # most carrier gateways ignore/prepend subject; keep blank

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(username, [gateway_to], msg.as_string())
        logger.info("Email-to-SMS sent via %s", host)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Email-to-SMS failed: %s", exc)
        return False


def send_notification(message: str) -> bool:
    method = os.environ.get("NOTIFY_METHOD", "twilio").lower()
    ok = False
    if method in ("twilio", "both"):
        ok = _send_twilio(message) or ok
    if method in ("email_sms", "both"):
        ok = _send_email_sms(message) or ok
    if not ok:
        logger.error("All configured notification methods failed for message: %s", message)
    return ok
