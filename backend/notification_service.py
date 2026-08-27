"""
Notification delivery service for MediTrack.

Every notification is always written to the database (in-app). Email and SMS
delivery are OPTIONAL add-on channels that only activate when their provider
is configured via environment variables — nothing is hardcoded, and no
credentials ever live in source control.

Environment variables (all optional):
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL
        -> enables email delivery via smtplib (any standard SMTP provider:
           SendGrid, SES, Mailgun, Gmail SMTP relay, etc.)
    SMS_GATEWAY_URL, SMS_API_KEY, SMS_SENDER_ID
        -> enables SMS delivery via a generic HTTP POST to your SMS gateway
           (Twilio, MSG91, TextLocal, etc. all expose a compatible HTTP API —
           adjust `_send_sms`'s payload shape to match your provider's docs)

If a channel's env vars are not set, MediTrack simply skips that channel and
logs it, so the app runs correctly in a fresh/dev environment with in-app
notifications only.
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText

logger = logging.getLogger("meditrack.notifications")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER or "")

SMS_GATEWAY_URL = os.getenv("SMS_GATEWAY_URL")
SMS_API_KEY = os.getenv("SMS_API_KEY")
SMS_SENDER_ID = os.getenv("SMS_SENDER_ID", "MEDTRK")

EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)
SMS_ENABLED = bool(SMS_GATEWAY_URL and SMS_API_KEY)


def send_email(to_email: str, subject: str, body: str) -> bool:
    if not EMAIL_ENABLED:
        logger.info("[email:skipped - not configured] to=%s subject=%s", to_email, subject)
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM_EMAIL
        msg["To"] = to_email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_EMAIL, [to_email], msg.as_string())
        logger.info("[email:sent] to=%s subject=%s", to_email, subject)
        return True
    except Exception as exc:  # pragma: no cover - best-effort delivery
        logger.warning("[email:failed] to=%s error=%s", to_email, exc)
        return False


def send_sms(to_phone: str, message: str) -> bool:
    if not SMS_ENABLED:
        logger.info("[sms:skipped - not configured] to=%s message=%s", to_phone, message)
        return False
    try:
        import urllib.request
        import json
        payload = json.dumps({
            "to": to_phone, "message": message, "sender_id": SMS_SENDER_ID,
        }).encode()
        req = urllib.request.Request(
            SMS_GATEWAY_URL, data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {SMS_API_KEY}"},
        )
        urllib.request.urlopen(req, timeout=10)
        logger.info("[sms:sent] to=%s", to_phone)
        return True
    except Exception as exc:  # pragma: no cover - best-effort delivery
        logger.warning("[sms:failed] to=%s error=%s", to_phone, exc)
        return False


def dispatch(patient, message: str, subject: str = "MediTrack Notification",
             send_email_too: bool = False, send_sms_too: bool = False) -> str:
    """Sends optional email/SMS alongside the always-created in-app notification.
    Returns a channel label describing what was actually attempted."""
    channels = ["in_app"]
    if send_email_too and getattr(patient, "email", None):
        send_email(patient.email, subject, message)
        channels.append("email")
    if send_sms_too and getattr(patient, "phone", None):
        send_sms(patient.phone, message)
        channels.append("sms")
    return "+".join(channels)
