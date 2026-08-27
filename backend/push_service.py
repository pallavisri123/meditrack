"""
Web Push delivery for MediTrack — this is what actually gets a notification onto a
patient's phone (Android Chrome, desktop Chrome/Firefox/Edge, and iOS 16.4+ Safari
once the site is "Added to Home Screen"), using the standard, free, no-SMS-carrier
Web Push protocol. It works even when MediTrack isn't open, as long as the patient
has granted notification permission once.

Setup (all via environment variables — nothing hardcoded):
    1. Generate a VAPID key pair once:
         pip install py-vapid
         vapid --gen
       This produces `private_key.pem` / an application server key pair.
    2. Set:
         VAPID_PUBLIC_KEY   (base64url, shared with the browser)
         VAPID_PRIVATE_KEY  (PEM contents or base64url private key)
         VAPID_CLAIM_EMAIL  (mailto:you@yourdomain.com — required by the spec)
    3. Add `pywebpush` to requirements.txt (already included).

If these variables are not set, push notifications are silently skipped — the app
still works fully with in-app notifications (and optional email/SMS).
"""
import os
import json
import logging

logger = logging.getLogger("meditrack.push")

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_CLAIM_EMAIL = os.getenv("VAPID_CLAIM_EMAIL", "mailto:admin@meditrack.local")

PUSH_ENABLED = bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)

try:
    from pywebpush import webpush, WebPushException
    _WEBPUSH_AVAILABLE = True
except ImportError:  # pywebpush not installed yet in this environment
    _WEBPUSH_AVAILABLE = False


def send_push_to_subscription(subscription: dict, title: str, body: str, url: str = "/dashboard.html") -> bool:
    """subscription = {"endpoint": ..., "keys": {"p256dh": ..., "auth": ...}}"""
    if not PUSH_ENABLED or not _WEBPUSH_AVAILABLE:
        logger.info("[push:skipped - not configured] title=%s", title)
        return False
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_CLAIM_EMAIL},
        )
        return True
    except Exception as exc:  # pragma: no cover - best-effort delivery, includes WebPushException
        logger.warning("[push:failed] error=%s", exc)
        return False


def send_push_to_patient(db, patient_id: int, title: str, body: str, url: str = "/dashboard.html") -> int:
    """Sends to every device the patient has subscribed on. Returns count delivered."""
    if not PUSH_ENABLED:
        return 0
    import models as M
    subs = db.query(M.PushSubscription).filter_by(patient_id=patient_id).all()
    sent = 0
    for s in subs:
        ok = send_push_to_subscription(
            {"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}}, title, body, url)
        if ok:
            sent += 1
        elif _WEBPUSH_AVAILABLE:
            # Endpoint likely expired/unsubscribed on the browser side — clean it up.
            try:
                db.delete(s)
            except Exception:
                pass
    return sent
