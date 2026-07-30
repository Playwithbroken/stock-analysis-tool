import sys
from types import SimpleNamespace

from src.email_alert_service import EmailAlertService
from src.morning_brief_service import MorningBriefService


def main() -> int:
    svc = MorningBriefService()

    cases = [
        (
            "Trump says new China tariff plan is under review",
            "public_figure",
            "high",
        ),
        (
            "AI infrastructure startup files for IPO after revenue doubles",
            "ipo",
            "high",
        ),
        (
            "Red Sea oil shipping disruption lifts crude futures",
            "energy",
            "medium",
        ),
    ]

    failures: list[str] = []
    for title, expected_type, expected_impact in cases:
        result = svc._classify_news_signal(title.lower())
        got_type = result.get("event_type")
        got_impact = result.get("impact")
        print(f"{title!r} -> type={got_type!r}, impact={got_impact!r}, region={result.get('region')!r}")
        if got_type != expected_type or got_impact != expected_impact:
            failures.append(f"{title}: expected {expected_type}/{expected_impact}, got {got_type}/{got_impact}")

    if svc._news_relevance_score({"title": cases[0][0], "event_type": "public_figure", "publisher": "Reuters", "source_quality": "tier_1"}) < 8:
        failures.append("public figure relevance score too low")
    if svc._news_relevance_score({"title": cases[1][0], "event_type": "ipo", "publisher": "Bloomberg", "source_quality": "tier_1"}) < 8:
        failures.append("IPO relevance score too low")

    ai_trade_earnings = svc._classify_news_signal(
        "Meta falls while Microsoft rises as the AI trade splits Big Tech "
        "https://www.cnbc.com/example-stock-today-earnings.html"
    )
    if ai_trade_earnings.get("event_type") != "earnings":
        failures.append("AI trade wording was falsely classified as trade policy")
    if svc._classify_product_catalyst(
        "Rolls-Royce CEO says a hyperscaler nuclear deal is imminent"
    ):
        failures.append("Rolls-Royce Holdings news was falsely mapped to BMW")
    bmw_luxury = svc._classify_product_catalyst(
        "BMW updates plans for Rolls-Royce Motor Cars"
    )
    if not bmw_luxury or bmw_luxury.get("ticker") != "BMW.DE":
        failures.append("specific Rolls-Royce Motor Cars alias no longer maps to BMW")

    public_intel = svc._build_event_intelligence("public_figure", "high", "elevated", "tier_1", None)
    ipo_intel = svc._build_event_intelligence("ipo", "high", "elevated", "tier_1", None)
    for label, payload, expected_asset in [
        ("public figure", public_intel, "S&P 500 Futures"),
        ("IPO", ipo_intel, "IPO basket"),
    ]:
        if expected_asset not in payload.get("affected_assets", []):
            failures.append(f"{label} intelligence missing {expected_asset}")
        for field in ["why_now", "trigger", "invalidation", "execution_window"]:
            if not payload.get(field):
                failures.append(f"{label} intelligence missing {field}")

    verified_news = svc._enrich_news_item(
        {
            "title": cases[0][0],
            "publisher": "Reuters",
            "link": "https://www.reuters.com/world/us/example-market-policy-report-2026-07-30/",
            "source_url": "https://www.reuters.com/world/us/example-market-policy-report-2026-07-30/",
            "source_domain": "reuters.com",
            "source_quality": "tier_1",
            "is_trusted_source": True,
            "published_at": "2026-07-30T06:00:00+00:00",
            "age_hours": 1.0,
            "event_type": "public_figure",
            "impact": "high",
            "severity": "elevated",
            "source_summary": "<p>The policy plan remains under review and no final measure was announced.</p>",
        }
    )
    intelligence = verified_news.get("news_intelligence") or {}
    evidence = verified_news.get("source_evidence") or {}
    if not verified_news.get("is_important") or int(verified_news.get("importance_score") or 0) < 12:
        failures.append("verified Tier-1 market news was not marked important")
    if evidence.get("link_verified") is not True or evidence.get("reporting_basis") != "publisher_summary":
        failures.append("verified news source evidence is incomplete")
    if "<p>" in str(intelligence.get("fact_summary") or ""):
        failures.append("publisher summary HTML was not cleaned")
    for field in [
        "fact_summary",
        "meaning",
        "bull_case",
        "bear_case",
        "confirmation",
        "invalidation",
        "assessment",
        "confidence",
        "precision_note",
    ]:
        if not intelligence.get(field):
            failures.append(f"important news intelligence missing {field}")

    unlinked_news = svc._build_news_intelligence(
        {
            **verified_news,
            "link": "",
            "source_url": "",
            "source_summary": "",
        }
    )
    if unlinked_news.get("is_important"):
        failures.append("news without a real source URL was marked important")
    if unlinked_news.get("fact_basis") != "headline_only":
        failures.append("headline-only reporting basis was not disclosed")

    telegram = EmailAlertService.__new__(EmailAlertService)
    telegram_messages: list[str] = []
    telegram._tg_post = (  # type: ignore[method-assign]
        lambda token, chat_id, text, disable_preview=True: telegram_messages.append(text)
    )
    telegram._send_telegram_rich_brief(
        SimpleNamespace(
            telegram_enabled=True,
            telegram_bot_token="qa-token",
            telegram_chat_id="qa-chat",
        ),
        {
            "macro_regime": "mixed",
            "opening_bias": "QA",
            "regions": {},
            "macro_assets": [],
            "top_news": [verified_news],
        },
        "global",
    )
    important_message = next(
        (message for message in telegram_messages if "WICHTIG" in message),
        "",
    )
    for marker in ["Fakt (Publisher-Zusammenfassung)", "Bedeutung:", "Einschätzung:", "Bestätigung:", "Invalidierung:"]:
        if marker not in important_message:
            failures.append(f"important Telegram news missing {marker}")

    if failures:
        print("\nClassification failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nMorning brief classification smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
