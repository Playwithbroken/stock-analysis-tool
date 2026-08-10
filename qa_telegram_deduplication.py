from datetime import datetime, timezone

from src.email_alert_service import EmailAlertConfig, EmailAlertService


class MemoryManager:
    def __init__(self):
        self.sent = set()
        self.settings = {}

    def get_sent_signal_event_keys(self):
        return set(self.sent)

    def mark_signal_events_sent(self, events):
        self.sent.update(str(item.get("event_key")) for item in events if item.get("event_key"))

    def get_app_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_app_setting(self, key, value):
        self.settings[key] = value

    def get_portfolios(self):
        return []

    def get_signal_watch_items(self):
        return []


class PublicSignals:
    def build_watchlist_snapshot(self, items):
        return {}


class Briefs:
    def __init__(self, brief):
        self.brief = brief

    def get_brief_fast(self, snapshot, include_heavy=False):
        return self.brief


def build_service():
    service = EmailAlertService.__new__(EmailAlertService)
    service.portfolio_manager = MemoryManager()
    service.public_signal_service = PublicSignals()
    service.morning_brief_service = Briefs({})
    service.get_config = lambda: EmailAlertConfig(
        enabled=True,
        smtp_host="",
        smtp_port=0,
        smtp_user="",
        smtp_password="",
        smtp_from="",
        smtp_to="",
        smtp_starttls=False,
        telegram_enabled=True,
        telegram_bot_token="test-token",
        telegram_chat_id="test-chat",
        scheduled_briefs_enabled=True,
    )
    service._validate_telegram_config = lambda config: None
    service._validate_config = lambda config: None
    service.deliveries = []
    service._send_notifications = lambda config, events, subject: service.deliveries.append(
        {"subject": subject, "keys": [event["event_key"] for event in events]}
    )
    return service


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def test_buy_and_sell_are_idempotent():
    service = build_service()
    opened = [{
        "id": "open-1",
        "ticker": "AAPL",
        "direction": "long",
        "asset_class": "equity",
        "setup_type": "etf_momentum",
        "entry_price": 100.0,
        "trade_ticket": {},
    }]
    first = service.send_paper_trade_opened_alerts(opened, [])
    duplicate = service.send_paper_trade_opened_alerts(opened, [])
    require(first["sent"] == 1 and duplicate["sent"] == 0, "buy alert must be idempotent by trade id")

    closed = [{**opened[0], "closed_price": 105.0, "realized_pnl_pct": 5.0}]
    first = service.send_paper_trade_closed_alerts(closed)
    duplicate = service.send_paper_trade_closed_alerts(closed)
    require(first["sent"] == 1 and duplicate["sent"] == 0, "sell alert must be idempotent by trade id")
    require(len(service.deliveries) == 2, "duplicates must never reach Telegram transport")


def test_management_and_account_use_stateful_cooldowns():
    service = build_service()
    trade = {
        "id": "managed-1",
        "ticker": "MSFT",
        "direction": "long",
        "asset_class": "equity",
        "setup_type": "confirmed_news_event",
        "unrealized_pnl_pct": -1.0,
        "management_plan": {"status": "near_stop", "decision_grade": "review", "action": "close_review"},
    }
    first = service.send_paper_trade_management_alerts([trade])
    duplicate = service.send_paper_trade_management_alerts([trade])
    require(first["sent"] == 1 and duplicate["sent"] == 0, "management cooldown must block duplicate state")

    account = {
        "day_status": "risk_review",
        "management_counts": {"review": 1},
        "risk_circuit": {"status": "ready", "reasons": []},
        "trade_action_queue": {"status": "review", "top_priority": {"ticker": "MSFT"}},
    }
    first = service.send_paper_account_status_alert(account, [trade])
    duplicate = service.send_paper_account_status_alert(account, [trade])
    require(first["sent"] == 1 and duplicate["status"] == "cooldown", "account summary cooldown must block duplicate state")


def test_important_news_is_deduplicated_and_failed_delivery_is_retryable():
    event = {
        "title": "Official escalation near Red Sea shipping corridor",
        "summary": "Confirmed escalation can affect oil, shipping, insurance and European risk appetite into the next liquid session.",
        "event_type": "conflict",
        "country": "Middle East",
        "source_status": "official confirmed wire",
        "source_url": "https://news.example/red-sea",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "source_quality": "tier_1",
        "source_evidence": {
            "url": "https://news.example/red-sea",
            "link_verified": True,
            "quality": "tier_1",
        },
        "impact_score": 93,
        "symbols": ["XLE", "USO", "GLD", "DAX"],
        "trigger": "Brent and energy equities hold the move for 30 minutes after the European open.",
        "invalidation": "Official follow-up denies supply risk and crude reverses below the pre-headline level.",
    }
    service = build_service()
    service.morning_brief_service = Briefs({"top_news": [event]})
    first = service.check_and_send_critical_market_alerts()
    duplicate = service.check_and_send_critical_market_alerts()
    require(first["sent"] == 1 and duplicate["sent"] == 0, "important news must dedupe by stable event identity")

    retry = build_service()
    retry.morning_brief_service = Briefs({"top_news": [event]})
    attempts = {"count": 0}

    def fail_once(config, events, subject):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("simulated Telegram outage")
        retry.deliveries.append({"subject": subject, "keys": [item["event_key"] for item in events]})

    retry._send_notifications = fail_once
    try:
        retry.check_and_send_critical_market_alerts()
    except RuntimeError:
        pass
    else:
        raise AssertionError("simulated provider failure must surface")
    require(not retry.portfolio_manager.sent, "failed delivery must not be marked as sent")
    second = retry.check_and_send_critical_market_alerts()
    require(second["sent"] == 1 and attempts["count"] == 2, "failed news delivery must remain retryable")


def main():
    tests = [
        test_buy_and_sell_are_idempotent,
        test_management_and_account_use_stateful_cooldowns,
        test_important_news_is_deduplicated_and_failed_delivery_is_retryable,
    ]
    for test in tests:
        test()
    print(f"telegram deduplication QA passed ({len(tests)} test groups)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
