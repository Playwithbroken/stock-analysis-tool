import os
import tempfile


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_COOKIE_SECURE"] = "false"
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "telegram-only-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64
        os.environ["SIGNAL_ALERTS_ENABLED"] = "true"
        os.environ["TELEGRAM_ALERTS_ENABLED"] = "true"
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        os.environ["TELEGRAM_CHAT_ID"] = "123456789"
        os.environ["BROWSER_PUSH_ENABLED"] = "false"
        os.environ["SMTP_HOST"] = "smtp.example.invalid"
        os.environ["SMTP_USER"] = "alerts@example.invalid"
        os.environ["SMTP_PASSWORD"] = "smtp-password-that-must-not-be-used"
        os.environ["SMTP_FROM"] = "alerts@example.invalid"
        os.environ["ALERT_EMAIL_TO"] = "owner@example.invalid"

        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app)
        login = client.post("/api/auth/login", json={"password": "test-pass"})
        if login.status_code != 200:
            print(f"FAIL: login failed: {login.status_code} {login.text}")
            return 1

        status = client.get("/api/notifications/status")
        if status.status_code != 200:
            print(f"FAIL: notification status failed: {status.status_code} {status.text}")
            return 1
        payload = status.json()
        email = payload.get("email") or {}
        telegram = payload.get("telegram") or {}
        browser_push = payload.get("browser_push") or {}

        if email.get("configured") is not False or email.get("disabled") is not True:
            print(f"FAIL: email channel is not explicitly disabled: {email}")
            return 1
        if "Telegram" not in str(email.get("message") or ""):
            print(f"FAIL: email disabled message should point to Telegram: {email}")
            return 1
        if telegram.get("enabled") is not True or telegram.get("configured") is not True:
            print(f"FAIL: telegram channel should be enabled and configured: {telegram}")
            return 1
        if browser_push.get("enabled") is not False or browser_push.get("channel") != "telegram_only":
            print(f"FAIL: browser push should be disabled for telegram-only beta: {browser_push}")
            return 1

        service = api.get_email_alert_service()

        def fail_email(*args, **kwargs):
            raise AssertionError("Email delivery must not be used in telegram-only mode")

        sent = {}

        def fake_telegram(config, events, subject):
            sent["subject"] = subject
            sent["events"] = events
            return True

        service._send_email = fail_email
        service._send_telegram = fake_telegram

        test_alert = client.post("/api/signals/alerts/test")
        if test_alert.status_code != 200:
            print(f"FAIL: telegram test alert failed: {test_alert.status_code} {test_alert.text}")
            return 1
        result = test_alert.json()
        if result.get("status") != "ok" or "Telegram" not in str(result.get("message") or ""):
            print(f"FAIL: test alert should report Telegram delivery: {result}")
            return 1
        if not sent.get("events") or "Telegram" not in str(sent.get("subject") or ""):
            print(f"FAIL: telegram stub did not receive test alert: {sent}")
            return 1

        vapid = client.get("/api/push/vapid-key")
        if vapid.status_code != 410:
            print(f"FAIL: disabled browser push VAPID endpoint returned {vapid.status_code}")
            return 1
        push_test = client.post("/api/push/test")
        if push_test.status_code != 410:
            print(f"FAIL: disabled browser push test returned {push_test.status_code}")
            return 1

    print("telegram-only notification QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
