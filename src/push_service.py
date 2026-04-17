"""
Browser Push Notification Service.

Manages VAPID keys, push subscriptions, and sending notifications
via the Web Push protocol. Subscriptions are stored in a local JSON file.
"""

import json
import os
import threading
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from py_vapid import Vapid

_HAS_WEBPUSH = True
try:
    from pywebpush import webpush, WebPushException
except ImportError:
    _HAS_WEBPUSH = False


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VAPID_KEY_FILE = DATA_DIR / "vapid_keys.json"
SUBSCRIPTIONS_FILE = DATA_DIR / "push_subscriptions.json"


class PushService:
    """Singleton-style push notification service."""

    _lock = threading.Lock()

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._vapid_private: str = ""
        self._vapid_public: str = ""
        self._subscriptions: List[Dict[str, Any]] = []
        self._load_vapid_keys()
        self._load_subscriptions()

    # ── VAPID Keys ────────────────────────────────────────────────────

    def _load_vapid_keys(self) -> None:
        if VAPID_KEY_FILE.exists():
            try:
                data = json.loads(VAPID_KEY_FILE.read_text())
                self._vapid_private = data["private_key"]
                self._vapid_public = data["public_key"]
                return
            except Exception:
                pass
        self._generate_vapid_keys()

    def _generate_vapid_keys(self) -> None:
        vapid = Vapid()
        vapid.generate_keys()
        self._vapid_private = vapid.private_pem().decode("utf-8")
        # applicationServerKey needs the raw uncompressed public key in
        # urlsafe base64. Older py_vapid exposed public_key_urlsafe_base64(),
        # newer Vapid02 does not, so support both paths.
        if hasattr(vapid, "public_key_urlsafe_base64"):
            self._vapid_public = vapid.public_key_urlsafe_base64()
        else:
            public_bytes = vapid.public_key.public_bytes(
                Encoding.X962,
                PublicFormat.UncompressedPoint,
            )
            self._vapid_public = (
                base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode("ascii")
            )
        VAPID_KEY_FILE.write_text(json.dumps({
            "private_key": self._vapid_private,
            "public_key": self._vapid_public,
        }, indent=2))
        print(f"[PushService] Generated new VAPID keys -> {VAPID_KEY_FILE}")

    @property
    def public_key(self) -> str:
        return self._vapid_public

    # ── Subscriptions ─────────────────────────────────────────────────

    def _load_subscriptions(self) -> None:
        if SUBSCRIPTIONS_FILE.exists():
            try:
                self._subscriptions = json.loads(SUBSCRIPTIONS_FILE.read_text())
            except Exception:
                self._subscriptions = []

    def _save_subscriptions(self) -> None:
        with self._lock:
            SUBSCRIPTIONS_FILE.write_text(json.dumps(self._subscriptions, indent=2))

    def subscribe(self, subscription: Dict[str, Any]) -> bool:
        """Register a new push subscription. Returns True if new."""
        endpoint = subscription.get("endpoint", "")
        if not endpoint:
            return False
        # Deduplicate by endpoint
        for existing in self._subscriptions:
            if existing.get("endpoint") == endpoint:
                # Update keys if changed
                existing.update(subscription)
                self._save_subscriptions()
                return False
        self._subscriptions.append(subscription)
        self._save_subscriptions()
        print(f"[PushService] New subscription registered (total: {len(self._subscriptions)})")
        return True

    def unsubscribe(self, endpoint: str) -> bool:
        """Remove a subscription by endpoint."""
        before = len(self._subscriptions)
        self._subscriptions = [s for s in self._subscriptions if s.get("endpoint") != endpoint]
        if len(self._subscriptions) < before:
            self._save_subscriptions()
            return True
        return False

    @property
    def subscription_count(self) -> int:
        return len(self._subscriptions)

    # ── Sending ───────────────────────────────────────────────────────

    def send_notification(
        self,
        title: str,
        body: str,
        icon: str = "/vite.svg",
        tag: str = "broker-freund",
        url: str = "/",
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a push notification to all registered subscriptions."""
        if not _HAS_WEBPUSH:
            return {"sent": 0, "failed": 0, "error": "pywebpush not installed"}

        if not self._subscriptions:
            return {"sent": 0, "failed": 0, "error": "no subscriptions"}

        payload = json.dumps({
            "title": title,
            "body": body,
            "icon": icon,
            "tag": tag,
            "url": url,
            "data": data or {},
        })

        claims = {
            "sub": "mailto:brokerfreund@localhost",
        }

        sent = 0
        failed = 0
        stale_endpoints: List[str] = []

        for sub in self._subscriptions:
            try:
                webpush(
                    subscription_info=sub,
                    data=payload,
                    vapid_private_key=self._vapid_private,
                    vapid_claims=claims,
                )
                sent += 1
            except WebPushException as e:
                failed += 1
                # 410 Gone or 404 = subscription expired
                if hasattr(e, "response") and e.response is not None:
                    status = getattr(e.response, "status_code", 0)
                    if status in (404, 410):
                        stale_endpoints.append(sub.get("endpoint", ""))
                print(f"[PushService] Push failed: {e}")
            except Exception as e:
                failed += 1
                print(f"[PushService] Push error: {e}")

        # Clean up stale subscriptions
        if stale_endpoints:
            self._subscriptions = [
                s for s in self._subscriptions
                if s.get("endpoint") not in stale_endpoints
            ]
            self._save_subscriptions()
            print(f"[PushService] Cleaned {len(stale_endpoints)} stale subscriptions")

        return {"sent": sent, "failed": failed}

    # ── Convenience methods for common notifications ──────────────────

    def notify_brief(self, session: str, headline: str) -> Dict[str, Any]:
        """Send a morning/session brief notification."""
        return self.send_notification(
            title=f"Broker Freund — {session}",
            body=headline[:200],
            tag=f"brief-{session}",
            url="/",
        )

    def notify_signal(self, ticker: str, signal_type: str, message: str) -> Dict[str, Any]:
        """Send a trading signal notification (squeeze, insider, etc.)."""
        return self.send_notification(
            title=f"{ticker} — {signal_type}",
            body=message[:200],
            tag=f"signal-{ticker}",
            url="/",
            data={"ticker": ticker, "type": signal_type},
        )

    def notify_price_alert(self, ticker: str, price: float, condition: str) -> Dict[str, Any]:
        """Send a price alert notification."""
        return self.send_notification(
            title=f"Price Alert: {ticker}",
            body=f"{ticker} is now ${price:.2f} ({condition})",
            tag=f"price-{ticker}",
            url="/",
            data={"ticker": ticker, "price": price},
        )
