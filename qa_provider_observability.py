from pathlib import Path
from unittest.mock import Mock, patch

import requests

from src.email_alert_service import EmailAlertService
from src.option_data_provider import TradierOptionDataProvider
from src.realtime_market_service import RealtimeMarketService
from src.provider_observability import (
    classify_provider_error,
    provider_metrics_snapshot,
    record_provider_result,
    reset_provider_metrics,
)


ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def test_stable_error_taxonomy():
    require(classify_provider_error("quote", http_status=401) == "QUOTE_AUTH", "401 must map to auth")
    require(classify_provider_error("news", http_status=429) == "NEWS_RATE_LIMITED", "429 must map to rate limit")
    require(
        classify_provider_error("options", error=requests.Timeout("slow")) == "OPTIONS_TIMEOUT",
        "timeout must be stable",
    )
    require(
        classify_provider_error("telegram", error=requests.ConnectionError("network")) == "TELEGRAM_NETWORK",
        "network errors must be stable",
    )
    require(
        classify_provider_error("options", detail="tradier_access_token_not_configured")
        == "OPTIONS_NOT_CONFIGURED",
        "missing config must be explicit",
    )


def test_rolling_metrics_contract():
    reset_provider_metrics()
    record_provider_result("quote", "yfinance", "quote", "ok", latency_ms=10)
    record_provider_result(
        "quote", "yfinance", "quote", "error", latency_ms=30, error_code="QUOTE_TIMEOUT"
    )
    snapshot = provider_metrics_snapshot()
    require(snapshot["schema_version"] == "provider-metrics.v1", "schema must be versioned")
    require(set(snapshot["services"]) == {"quote", "news", "options", "telegram"}, "all services required")
    quote = snapshot["services"]["quote"]
    require(quote["attempt_count"] == 2 and quote["failure_count"] == 1, "counts must agree")
    require(quote["success_rate_pct"] == 50.0, "success rate must be reproducible")
    require(quote["average_latency_ms"] == 20.0 and quote["p95_latency_ms"] == 30.0, "latency metrics wrong")
    require(quote["last_error"]["error_code"] == "QUOTE_TIMEOUT", "last error code must remain visible")
    require(snapshot["services"]["news"]["status"] == "not_observed", "empty services must be honest")


def test_tradier_transport_records_success_disabled_and_http_failure():
    reset_provider_metrics()
    response = Mock(status_code=200)
    response.raise_for_status.return_value = None
    response.json.return_value = {"expirations": {"date": ["2026-09-18"]}}
    provider = TradierOptionDataProvider("test-token")
    with patch("src.option_data_provider.requests.get", return_value=response):
        require(provider.get_expirations("AAPL") == ["2026-09-18"], "Tradier payload must still work")
    require(provider_metrics_snapshot()["services"]["options"]["status"] == "ok", "success not recorded")

    try:
        TradierOptionDataProvider("").get_expirations("AAPL")
    except RuntimeError:
        pass
    else:
        raise AssertionError("missing Tradier token must fail")
    disabled = provider_metrics_snapshot()["services"]["options"]
    require(disabled["status"] == "disabled", "missing provider config must be disabled")
    require(disabled["last_error"]["error_code"] == "OPTIONS_NOT_CONFIGURED", "missing config code wrong")

    failed_response = Mock(status_code=429)
    failed_response.raise_for_status.side_effect = requests.HTTPError(response=failed_response)
    with patch("src.option_data_provider.requests.get", return_value=failed_response):
        try:
            provider.get_chain("AAPL", "2026-09-18")
        except requests.HTTPError:
            pass
        else:
            raise AssertionError("Tradier 429 must propagate")
    failed = provider_metrics_snapshot()["services"]["options"]
    require(failed["last_error"]["error_code"] == "OPTIONS_RATE_LIMITED", "Tradier 429 code wrong")


def test_telegram_transport_records_delivery_and_permission_error():
    reset_provider_metrics()
    service = EmailAlertService.__new__(EmailAlertService)
    success = Mock(status_code=200)
    success.raise_for_status.return_value = None
    with patch("src.email_alert_service.requests.post", return_value=success):
        service._tg_post("token", "chat", "hello")
    require(provider_metrics_snapshot()["services"]["telegram"]["status"] == "ok", "delivery not recorded")

    forbidden = Mock(status_code=403)
    forbidden.raise_for_status.side_effect = requests.HTTPError(response=forbidden)
    with patch("src.email_alert_service.requests.post", return_value=forbidden):
        try:
            service._tg_post("token", "chat", "hello")
        except RuntimeError:
            pass
        else:
            raise AssertionError("Telegram 403 must remain actionable")
    metric = provider_metrics_snapshot()["services"]["telegram"]
    require(metric["last_error"]["error_code"] == "TELEGRAM_AUTH", "Telegram permission code wrong")


def test_realtime_quote_path_records_actual_snapshot():
    reset_provider_metrics()
    service = RealtimeMarketService()
    service._build_quote = lambda symbol: {
        "symbol": symbol,
        "price": 100.0,
        "updated_at": "2099-01-01T00:00:00+00:00",
        "source": "alpaca",
        "feed": "iex",
        "streaming": True,
    }
    snapshot = service.build_snapshot(["AAPL"])
    require(snapshot["connection_state"] == "live", "quote fixture should be live")
    quote = provider_metrics_snapshot()["services"]["quote"]
    require(quote["status"] == "ok", "actual realtime quote path must record success")
    require(quote["last_operation"] == "build_snapshot", "quote operation must be attributable")


def test_health_center_and_ui_expose_contract():
    api_source = (ROOT / "api.py").read_text(encoding="utf-8")
    ui_source = (ROOT / "frontend/src/components/AdminHealthPanel.tsx").read_text(encoding="utf-8")
    require('"provider_metrics": provider_metrics_snapshot()' in api_source, "health payload missing metrics")
    require("_news_feed_health_check" in api_source, "news health measurement missing")
    news_source = (ROOT / "src/morning_brief_service.py").read_text(encoding="utf-8")
    require('"NEWS_PARTIAL_PROVIDER_FAILURE"' in news_source, "live news collection code missing")
    for marker in ("Provider-Metriken", "success_rate_pct", "p95_latency_ms", "lastError.error_code"):
        require(marker in ui_source, f"health UI missing {marker}")


if __name__ == "__main__":
    test_stable_error_taxonomy()
    test_rolling_metrics_contract()
    test_tradier_transport_records_success_disabled_and_http_failure()
    test_telegram_transport_records_delivery_and_permission_error()
    test_realtime_quote_path_records_actual_snapshot()
    test_health_center_and_ui_expose_contract()
    print("provider observability QA passed (quotes, news, options, Telegram)")
