import json
import os
import tempfile


class FakeDataFetcher:
    calls = 0

    def __init__(self, ticker: str):
        self.ticker = ticker

    def get_price_data(self):
        type(self).calls += 1
        return {"current_price": 123.45, "ticker": self.ticker}


class FakeRealtimeMarketService:
    calls = 0

    def build_snapshot(self, tickers):
        type(self).calls += 1
        return {
            "connection_state": "ok",
            "quotes": [{"ticker": ticker, "price": 123.45} for ticker in tickers],
            "stale_seconds": {},
        }


class FakeTelegramResponse:
    ok = True
    status_code = 200
    reason = "OK"
    text = ""
    headers = {"content-type": "application/json"}

    @staticmethod
    def json():
        return {"ok": True}


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    access_password = "test-pass"
    session_secret = "x" * 64

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_COOKIE_SECURE"] = "false"
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "health-center-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = access_password
        os.environ["APP_SESSION_SECRET"] = session_secret
        os.environ["TELEGRAM_ALERTS_ENABLED"] = "false"
        os.environ["TELEGRAM_BOT_TOKEN"] = ""
        os.environ["TELEGRAM_CHAT_ID"] = ""
        os.environ["BROWSER_PUSH_ENABLED"] = "false"

        from fastapi.testclient import TestClient
        import api

        api.DataFetcher = FakeDataFetcher
        api.get_realtime_market_service = lambda: FakeRealtimeMarketService()

        client = TestClient(api.app)
        unauthenticated = client.get("/api/admin/health-center")
        if unauthenticated.status_code != 401:
            print(f"FAIL: unauthenticated health center returned {unauthenticated.status_code}")
            return 1

        login = client.post("/api/auth/login", json={"password": access_password})
        if login.status_code != 200:
            print(f"FAIL: login failed: {login.status_code} {login.text}")
            return 1

        response = client.get("/api/admin/health-center")
        if response.status_code != 200:
            print(f"FAIL: health center returned {response.status_code}: {response.text}")
            return 1

        payload = response.json()
        failures: list[str] = []
        for key in [
            "status",
            "generated_at",
            "timezone",
            "telegram",
            "notifications",
            "app",
            "database",
            "schedule",
            "learning",
            "paper_autopilot",
            "data_feeds",
            "recent_deliveries",
            "problems",
        ]:
            require(key in payload, failures, f"missing top-level key {key!r}")

        require(payload.get("status") in {"ok", "degraded"}, failures, "invalid health status")
        require(isinstance(payload.get("problems"), list), failures, "problems must be a list")

        app = payload.get("app") or {}
        require(app.get("version") == api.APP_VERSION, failures, "app.version mismatch")
        require(app.get("environment") == "production", failures, "app.environment mismatch")
        require(app.get("auth_configured") is True, failures, "app.auth_configured should be true")

        database = payload.get("database") or {}
        for key in ["path", "exists", "writable", "quick_check"]:
            require(key in database, failures, f"database missing {key!r}")
        require(database.get("exists") is True, failures, "database.exists should be true")
        require(database.get("writable") is True, failures, "database.writable should be true")

        schedule = payload.get("schedule") or {}
        require(isinstance(schedule.get("jobs"), list), failures, "schedule.jobs must be a list")
        require(len(schedule.get("jobs") or []) >= 1, failures, "schedule.jobs should not be empty")
        require(isinstance(schedule.get("summary"), dict), failures, "schedule.summary must be an object")
        if schedule.get("jobs"):
            job = schedule["jobs"][0]
            for key in ["job_key", "label", "time", "next_due_at", "sent_today"]:
                require(key in job, failures, f"schedule job missing {key!r}")

        paper_autopilot = payload.get("paper_autopilot") or {}
        for key in [
            "enabled",
            "loop_enabled",
            "status",
            "checked_at",
            "next_check_at",
            "opened_count",
            "selected_count",
            "last_selected",
            "last_opened",
            "demo_account_after",
            "block_reasons",
        ]:
            require(key in paper_autopilot, failures, f"paper_autopilot missing {key!r}")
        require(isinstance(paper_autopilot.get("block_reasons"), list), failures, "paper_autopilot.block_reasons must be a list")
        require(isinstance(paper_autopilot.get("last_selected"), list), failures, "paper_autopilot.last_selected must be a list")
        require(isinstance(paper_autopilot.get("last_opened"), list), failures, "paper_autopilot.last_opened must be a list")
        require(
            isinstance(paper_autopilot.get("demo_account_after"), dict),
            failures,
            "paper_autopilot.demo_account_after must be an object",
        )

        feeds = payload.get("data_feeds") or {}
        for key in ["morning_brief", "yfinance", "realtime", "forecast_learning"]:
            require(key in feeds, failures, f"data_feeds missing {key!r}")
            require(isinstance(feeds.get(key), dict), failures, f"data_feeds.{key} must be an object")

        rendered = json.dumps(payload, sort_keys=True)
        require(access_password not in rendered, failures, "health center leaked access password")
        require(session_secret not in rendered, failures, "health center leaked session secret")

        repeated = client.get("/api/admin/health-center")
        require(repeated.status_code == 200, failures, "repeated health center request failed")
        require(FakeDataFetcher.calls == 1, failures, "yfinance health probe was not cached")
        require(FakeRealtimeMarketService.calls == 1, failures, "realtime health probe was not cached")

        for preview_mode in ["strict", "learn"]:
            paper_preview = client.post(
                "/api/trading/paper-autopilot",
                json={"execute": False, "max_trades": 3, "mode": preview_mode},
            )
            require(paper_preview.status_code == 200, failures, f"paper {preview_mode} preview request failed")
            if paper_preview.status_code == 200:
                preview_payload = paper_preview.json()
                require(preview_payload.get("status") == "preview", failures, f"paper {preview_mode} preview status mismatch")
                require(preview_payload.get("mode") == preview_mode, failures, f"paper {preview_mode} preview mode mismatch")
                require(preview_payload.get("execute") is False, failures, f"paper {preview_mode} preview must not execute")
                require(isinstance(preview_payload.get("opened"), list), failures, f"paper {preview_mode} preview opened must be a list")
                require(len(preview_payload.get("opened") or []) == 0, failures, f"paper {preview_mode} preview must not open trades")

        telegram_calls = []

        def fake_telegram_post(url, **kwargs):
            telegram_calls.append((url, kwargs))
            return FakeTelegramResponse()

        api.requests.post = fake_telegram_post
        os.environ["TELEGRAM_ALERTS_ENABLED"] = "true"
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-token"
        os.environ["TELEGRAM_CHAT_ID"] = "test-chat"
        telegram_first = client.get("/api/admin/health-center")
        telegram_second = client.get("/api/admin/health-center")
        require(telegram_first.status_code == 200, failures, "enabled Telegram health request failed")
        require(telegram_second.status_code == 200, failures, "cached Telegram health request failed")
        require(len(telegram_calls) == 1, failures, "Telegram health probe was not cached")
        require(
            (telegram_second.json().get("telegram") or {}).get("status") == "ok",
            failures,
            "cached Telegram status should remain ok",
        )

        if failures:
            print("Health center contract QA failures:")
            for failure in failures:
                print(f"- {failure}")
            return 1

    print("health center contract QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
