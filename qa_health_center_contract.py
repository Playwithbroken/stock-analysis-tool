import asyncio
import inspect
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
    def raise_for_status():
        return None

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
            "backup",
            "operational_alerts",
            "schedule",
            "learning",
            "paper_autopilot",
            "paper_outcomes",
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

        backup = payload.get("backup") or {}
        for key in ["enabled", "directory", "backup_count", "retention_count", "interval_hours", "restore_test_interval_days"]:
            require(key in backup, failures, f"backup missing {key!r}")

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
        require(
            isinstance((paper_autopilot.get("demo_account_after") or {}).get("performance"), dict),
            failures,
            "paper_autopilot.demo_account_after.performance must be an object",
        )

        paper_outcomes = payload.get("paper_outcomes") or {}
        for key in [
            "status",
            "age_minutes",
            "stale",
            "stale_after_minutes",
            "pending_warn_count",
            "summary",
            "top_errors",
            "recent",
            "last_run",
        ]:
            require(key in paper_outcomes, failures, f"paper_outcomes missing {key!r}")
        require(isinstance(paper_outcomes.get("stale"), bool), failures, "paper_outcomes.stale must be a bool")
        require(isinstance(paper_outcomes.get("stale_after_minutes"), int), failures, "paper_outcomes.stale_after_minutes must be an int")
        require(isinstance(paper_outcomes.get("pending_warn_count"), int), failures, "paper_outcomes.pending_warn_count must be an int")
        require(isinstance(paper_outcomes.get("summary"), dict), failures, "paper_outcomes.summary must be an object")
        require(isinstance(paper_outcomes.get("top_errors"), list), failures, "paper_outcomes.top_errors must be a list")
        require(isinstance(paper_outcomes.get("recent"), list), failures, "paper_outcomes.recent must be a list")
        require(isinstance(paper_outcomes.get("last_run"), dict), failures, "paper_outcomes.last_run must be an object")
        for key in ["total", "evaluated", "pending", "hit_rate", "misses"]:
            require(key in paper_outcomes.get("summary", {}), failures, f"paper_outcomes.summary missing {key!r}")

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

        scheduler_source = inspect.getsource(api._forecast_learning_loop)
        require(
            "_run_paper_outcome_cycle(force_alerts=False)" in scheduler_source,
            failures,
            "forecast scheduler does not use the persisted paper outcome cycle",
        )
        scheduled_outcome_payload = asyncio.run(
            api._run_paper_outcome_cycle(force_alerts=False)
        )
        scheduled_outcome_raw = api.get_portfolio_manager().get_app_setting(
            "paper_trade_outcomes_last_result",
            "{}",
        )
        scheduled_outcome = json.loads(scheduled_outcome_raw or "{}")
        require(
            scheduled_outcome.get("checked_at") == scheduled_outcome_payload.get("checked_at"),
            failures,
            "scheduled paper outcome cycle was not persisted",
        )

        paper_outcome_eval = client.post("/api/trading/paper-outcomes/evaluate")
        require(paper_outcome_eval.status_code == 200, failures, "paper outcome evaluation request failed")
        if paper_outcome_eval.status_code == 200:
            outcome_payload = paper_outcome_eval.json()
            for key in ["checked_at", "status", "due", "evaluated", "pending_data", "errors", "paper_learning_alerts"]:
                require(key in outcome_payload, failures, f"paper outcome evaluation missing {key!r}")
            require(isinstance(outcome_payload.get("errors"), list), failures, "paper outcome evaluation errors must be a list")
            require(
                isinstance(outcome_payload.get("paper_learning_alerts"), dict),
                failures,
                "paper outcome evaluation paper_learning_alerts must be an object",
            )
            persisted_outcome_raw = api.get_portfolio_manager().get_app_setting(
                "paper_trade_outcomes_last_result",
                "{}",
            )
            persisted_outcome = json.loads(persisted_outcome_raw or "{}")
            require(
                persisted_outcome.get("checked_at") == outcome_payload.get("checked_at"),
                failures,
                "paper outcome run was not persisted for health diagnostics",
            )
            outcome_health = client.get("/api/admin/health-center")
            require(outcome_health.status_code == 200, failures, "paper outcome health refresh failed")
            if outcome_health.status_code == 200:
                refreshed_payload = outcome_health.json()
                refreshed_outcomes = refreshed_payload.get("paper_outcomes") or {}
                require(
                    refreshed_outcomes.get("status") != "not_seen",
                    failures,
                    "persisted paper outcome run still appears as not_seen",
                )
                require(
                    (refreshed_outcomes.get("last_run") or {}).get("checked_at") == outcome_payload.get("checked_at"),
                    failures,
                    "health center does not expose the persisted paper outcome run",
                )

        telegram_calls = []

        def fake_telegram_post(url, **kwargs):
            telegram_calls.append((url, kwargs))
            return FakeTelegramResponse()

        api.requests.post = fake_telegram_post
        os.environ["TELEGRAM_ALERTS_ENABLED"] = "true"
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456789" + ":" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
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

        paper_account_status = client.post("/api/admin/send-paper-account-status")
        require(paper_account_status.status_code == 200, failures, "paper account status Telegram request failed")
        if paper_account_status.status_code == 200:
            account_payload = paper_account_status.json()
            for key in ["status", "sent", "message", "demo_account"]:
                require(key in account_payload, failures, f"paper account status missing {key!r}")
            require(account_payload.get("status") == "ok", failures, "paper account status should return ok")
            require(isinstance(account_payload.get("demo_account"), dict), failures, "paper account demo_account must be an object")
            for key in ["equity", "day_status", "day_action", "net_pnl_value", "net_pnl_pct", "open_trade_count", "performance"]:
                require(key in account_payload.get("demo_account", {}), failures, f"paper account demo_account missing {key!r}")
            require(
                isinstance(account_payload.get("demo_account", {}).get("performance"), dict),
                failures,
                "paper account demo_account.performance must be an object",
            )
        require(len(telegram_calls) >= 2, failures, "paper account status should send a Telegram request")

        if failures:
            print("Health center contract QA failures:")
            for failure in failures:
                print(f"- {failure}")
            return 1

    print("health center contract QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
