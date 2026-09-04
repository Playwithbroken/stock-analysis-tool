import json
import os
import tempfile


class FakeTelegramResponse:
    status_code = 200
    ok = True
    reason = "OK"
    text = ""
    headers = {"content-type": "application/json"}

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True}


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "operational-alerts.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64
        os.environ["TELEGRAM_ALERTS_ENABLED"] = "true"
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456789" + ":" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
        os.environ["TELEGRAM_CHAT_ID"] = "test-chat"

        import api

        failures: list[str] = []
        telegram_calls = []

        def fake_post(url, **kwargs):
            telegram_calls.append((url, kwargs))
            return FakeTelegramResponse()

        api.requests.post = fake_post
        api._telegram_health_check = lambda: {"status": "ok", "sendable": True}
        api._market_feed_health_check = lambda: {
            "yfinance": {"status": "error"},
            "realtime": {"status": "disconnected", "stale_seconds": {"AAPL": 3600}},
            "realtime_required": False,
        }
        api.get_database_status = lambda: {
            "writable": False,
            "path": os.environ["PORTFOLIO_DB_PATH"],
            "error": "PermissionError",
            "railway_runtime": False,
            "persistence_ready": True,
        }
        manager = api.get_portfolio_manager()
        manager.set_app_setting("brief_scheduler_last_step_error", "brief step failed")

        first = api._run_operational_alert_cycle()
        second = api._run_operational_alert_cycle()
        third = api._run_operational_alert_cycle()
        first_codes = {item.get("code") for item in first.get("issues", [])}
        third_codes = {item.get("code") for item in third.get("issues", [])}
        require("scheduler_error" in first_codes, failures, "scheduler error was not detected")
        require("market_quotes_stale" not in first_codes, failures, "single provider failure must not alert")
        require("market_quotes_stale" in third_codes, failures, "confirmed quote/provider error was not detected")
        require("database_not_writable" in first_codes, failures, "unwritable database/volume was not detected")
        require(len(telegram_calls) == 3, failures, "operational alerts were not deduplicated on the second cycle")
        require(all(item.get("status") == "deduplicated" for item in second.get("deliveries", [])), failures, "second cycle should be deduplicated")

        manager.set_app_setting("brief_scheduler_last_step_error", "")
        manager.set_app_setting("brief_scheduler_loop_error", "")
        api._market_feed_health_check = lambda: {
            "yfinance": {"status": "ok"},
            "realtime": {"status": "ok", "stale_seconds": {"AAPL": 0}},
            "realtime_required": False,
        }
        api.get_database_status = lambda: {
            "writable": True,
            "railway_runtime": False,
            "persistence_ready": True,
        }
        api._telegram_health_check = lambda: {
            "status": "error",
            "diagnosis": "invalid_bot_token",
            "next_step": "token pruefen",
        }
        telegram_failure = api._run_operational_alert_cycle()
        require(
            (telegram_failure.get("deliveries") or [{}])[0].get("status") == "unavailable_same_channel",
            failures,
            "Telegram outage should be recorded as unavailable on the same channel",
        )
        persisted = json.loads(manager.get_app_setting("operational_alerts_last_result", "{}") or "{}")
        require(persisted.get("status") == "degraded", failures, "operational alert state was not persisted")

        if failures:
            print("Operational alerts QA failures:")
            for failure in failures:
                print(f"- {failure}")
            return 1
    print("operational alerts QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
