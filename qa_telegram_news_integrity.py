from datetime import datetime, timedelta, timezone

from src.email_alert_service import EmailAlertService


class MemoryManager:
    def __init__(self):
        self.settings = {}

    def get_app_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_app_setting(self, key, value):
        self.settings[key] = value


def service() -> EmailAlertService:
    instance = EmailAlertService.__new__(EmailAlertService)
    instance.portfolio_manager = MemoryManager()
    return instance


def verified_story(title, url, **extra):
    published_at = extra.pop("published_at", datetime.now(timezone.utc).isoformat())
    return {
        "title": title,
        "ticker": "AAPL",
        "event_type": "policy",
        "source_url": url,
        "publisher": "Reuters",
        "published_at": published_at,
        "source_quality": "tier_1",
        "source_evidence": {
            "url": url,
            "published_at": published_at,
            "link_verified": True,
            "quality": "tier_1",
        },
        **extra,
    }


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main() -> int:
    svc = service()
    base = verified_story(
        "Apple faces confirmed European policy review on App Store rules",
        "https://www.reuters.com/technology/apple-policy-review?utm_source=test",
    )
    require(svc._telegram_news_source_contract(base)["valid"], "fresh verified Tier-1 story was rejected")

    for field, value in (
        ("source_url", ""),
        ("published_at", ""),
        ("source_quality", "tier_2"),
    ):
        broken = {**base, field: value}
        if field == "source_url":
            broken["source_evidence"] = {**base["source_evidence"], "url": ""}
        if field == "published_at":
            broken["source_evidence"] = {**base["source_evidence"], "published_at": ""}
        require(not svc._telegram_news_source_contract(broken)["valid"], f"missing/weak {field} passed")

    unverified = {**base, "source_evidence": {**base["source_evidence"], "link_verified": False}}
    require(not svc._telegram_news_source_contract(unverified)["valid"], "unverified link passed")
    stale = verified_story(
        base["title"],
        "https://www.reuters.com/technology/apple-policy-review-stale",
        published_at=(datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(),
    )
    require(not svc._telegram_news_source_contract(stale)["valid"], "stale news passed")

    selected = svc._select_new_verified_news([base], limit=7)
    require(len(selected) == 1, "verified story was not selected")
    svc._record_news_story_deliveries(selected, "rich_brief:global")
    require(not svc._select_new_verified_news([base], limit=7), "same URL was delivered twice")

    variant = verified_story(
        "European App Store policy review confirmed for Apple rules",
        "https://www.bloomberg.com/news/apple-europe-policy-review",
    )
    require(not svc._select_new_verified_news([variant], limit=7), "semantic headline variant was delivered twice")

    distinct = verified_story(
        "Apple launches new enterprise security hardware subscription",
        "https://www.reuters.com/technology/apple-security-launch",
    )
    require(len(svc._select_new_verified_news([distinct], limit=7)) == 1, "different story was over-deduplicated")

    macro = {
        **base,
        "title": "Official Apple policy review confirmed under European App Store rules",
        "summary": "The confirmed European policy review may affect App Store economics, services margins and large-cap technology risk.",
        "country": "Europe",
        "source_status": "Reuters confirmed wire",
        "impact_score": 93,
        "symbols": ["AAPL", "QQQ", "SPY"],
        "trigger": "Apple and QQQ underperform after the next liquid open with elevated volume.",
        "invalidation": "Official follow-up withdraws the review and the relative move fully reverses.",
    }
    normalized = svc._normalize_macro_alert_event(macro, 82)
    require(normalized is not None, "valid macro story failed normalization")
    require(not svc._news_story_can_send(normalized), "rich-brief story repeated as macro alert")

    print("Telegram news integrity QA passed (source, freshness, semantic and cross-channel dedupe).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
