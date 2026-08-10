from datetime import datetime, timezone

from src.email_alert_service import EmailAlertService
from src.paper_trading_service import PaperTradingService


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class MemoryPortfolioManager:
    def __init__(self, trade):
        self.trade = trade
        self.saved = None

    def list_paper_trades(self, status=None, limit=50):
        return [self.trade] if not status or self.trade.get("status") == status else []

    def update_paper_trade_ticket(self, trade_id, ticket, open_only=True):
        require(trade_id == self.trade["id"], "wrong trade persisted")
        self.saved = ticket
        self.trade["trade_ticket"] = ticket
        return self.trade


def sample_trade():
    return {
        "id": "news-trade-1",
        "ticker": "MSFT",
        "status": "open",
        "setup_type": "confirmed_news_event",
        "asset_class": "equity",
        "direction": "long",
        "entry_price": 100.0,
        "current_price": 101.0,
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "trade_ticket": {
            "news_evidence": {
                "schema_version": "2.0",
                "source_url": "https://news.example/story",
                "reporting_source": {"publisher": "Example News", "url": "https://news.example/story"},
                "primary_source": {"authority": "Issuer", "url": "https://issuer.example/release"},
                "correction_status": {"status": "not_detected_at_capture"},
            }
        },
    }


def test_correction_is_persisted_and_requires_exit_review():
    trade = sample_trade()
    manager = MemoryPortfolioManager(trade)
    service = PaperTradingService(manager)
    service._fetch_news_source_status = lambda url: {
        "url": url,
        "status": "correction_detected" if "news.example" in url else "unchanged",
        "signal": "correction" if "news.example" in url else None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "actionable": "news.example" in url,
    }
    result = service.revalidate_open_news_sources()
    require(result["checked"] == 1 and result["actionable"] == 1, "correction must be actionable")
    correction = manager.saved["news_evidence"]["correction_status"]
    require(correction["status"] == "correction_detected", "correction status must persist")
    management = service._build_trade_management_plan(trade)
    require(management["status"] == "news_source_invalidated", "open trade must be re-evaluated")
    require(management["decision_grade"] == "exit", "source invalidation must become exit review")
    require(management["causality_proven"] is False, "management must not invent causality")
    service._fetch_news_source_status = lambda url: {
        "url": url,
        "status": "check_failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "actionable": False,
    }
    service.revalidate_open_news_sources()
    latched = manager.saved["news_evidence"]["correction_status"]
    require(latched["status"] == "correction_detected", "a transient retry must not clear an invalidation")
    require(latched["latched_for_manual_review"] is True, "invalidation must stay latched for review")
    require(latched["ongoing_monitor_verified"] is False, "failed checks must not claim verified monitoring")


def test_missing_source_is_actionable_but_transient_error_is_not():
    for fetched_status, actionable, expected in (
        ("source_unavailable", True, "news_source_invalidated"),
        ("check_failed", False, "monitor"),
    ):
        trade = sample_trade()
        manager = MemoryPortfolioManager(trade)
        service = PaperTradingService(manager)
        service._fetch_news_source_status = lambda url, s=fetched_status, a=actionable: {
            "url": url,
            "status": s,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "actionable": a,
        }
        service.revalidate_open_news_sources()
        management = service._build_trade_management_plan(trade)
        require(management["status"] == expected, f"{fetched_status} produced wrong management state")


def test_telegram_calls_out_source_warning():
    alert = EmailAlertService.__new__(EmailAlertService)
    text = alert._render_telegram_paper_trade_management_alert(
        {
            "ticker": "MSFT",
            "direction": "long",
            "asset_class": "equity",
            "setup_type": "confirmed_news_event",
            "management_status": "news_source_invalidated",
            "management_action": "close_review",
            "decision_grade": "exit",
            "source_status": "retracted_or_withdrawn",
            "source_checked_at": datetime.now(timezone.utc).isoformat(),
            "affected_source_url": "https://news.example/story",
            "management_summary": "Source changed.",
            "next_check": "Compare sources.",
        }
    )
    require("QUELLENWARNUNG" in text, "Telegram management alert must highlight the source warning")
    require("betroffene Quelle" in text, "Telegram warning must link the affected source")
    require("keine automatische Echtgeld" in text, "Telegram must retain paper-only boundary")


def main():
    tests = [
        test_correction_is_persisted_and_requires_exit_review,
        test_missing_source_is_actionable_but_transient_error_is_not,
        test_telegram_calls_out_source_warning,
    ]
    for test in tests:
        test()
    print(f"news source revalidation QA passed ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
