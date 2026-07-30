import sys
from types import SimpleNamespace
from unittest.mock import patch

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
    multi_company_tickers = svc._extract_related_news_tickers(
        "Microsoft rises while Meta Platforms falls after earnings"
    )
    if set(multi_company_tickers) != {"MSFT", "META"}:
        failures.append("explicit company names were not mapped to all related tickers")
    if "BMW.DE" in svc._extract_related_news_tickers(
        "Rolls-Royce Holdings announces a nuclear power agreement"
    ):
        failures.append("Rolls-Royce Holdings was falsely mapped to BMW news")

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

    second_report = svc._enrich_news_item(
        {
            **verified_news,
            "title": "China tariff plan remains under review after Trump remarks",
            "publisher": "Bloomberg",
            "link": "https://www.bloomberg.com/news/articles/2026-07-30/china-tariff-plan-review",
            "source_url": "https://www.bloomberg.com/news/articles/2026-07-30/china-tariff-plan-review",
            "source_domain": "bloomberg.com",
            "source_summary": "The China tariff plan remains under review after the latest Trump remarks.",
        }
    )
    clustered = svc._cluster_news_events([verified_news, second_report])
    if len(clustered) != 1:
        failures.append("similar reports were not merged into one news event")
    else:
        clustered_evidence = clustered[0].get("source_evidence") or {}
        clustered_intelligence = clustered[0].get("news_intelligence") or {}
        if clustered_evidence.get("corroboration") != "multi_publisher":
            failures.append("multi-publisher corroboration was not disclosed")
        if clustered_evidence.get("publisher_count") != 2:
            failures.append("distinct publisher count is incorrect")
        if clustered_evidence.get("editorial_independence_verified") is not False:
            failures.append("editorial independence was overclaimed")
        if len(clustered[0].get("corroborating_sources") or []) != 2:
            failures.append("corroborating source links are missing")
        if "redaktionelle Unabhängigkeit" not in str(clustered_intelligence.get("precision_note") or ""):
            failures.append("multi-publisher precision disclosure is missing")

    conflicting_reports = []
    for publisher, domain, title in [
        ("Reuters", "reuters.com", "Tesla stock rises as robotaxi launch is approved"),
        ("CNBC", "cnbc.com", "Tesla stock falls as robotaxi launch is delayed"),
    ]:
        conflicting_reports.append(
            svc._enrich_news_item(
                {
                    "ticker": "TSLA",
                    "related_tickers": ["TSLA"],
                    "title": title,
                    "publisher": publisher,
                    "link": f"https://www.{domain}/tesla-robotaxi-launch",
                    "source_url": f"https://www.{domain}/tesla-robotaxi-launch",
                    "source_domain": domain,
                    "source_quality": "tier_1",
                    "is_trusted_source": True,
                    "published_at": "2026-07-30T06:00:00+00:00",
                    "age_hours": 1.0,
                    "event_type": "product_catalyst",
                    "impact": "high",
                    "severity": "elevated",
                }
            )
        )
    conflicting_cluster = svc._cluster_news_events(conflicting_reports)
    if len(conflicting_cluster) != 1:
        failures.append("conflicting reports were not recognized as the same event")
    elif (conflicting_cluster[0].get("source_evidence") or {}).get("source_agreement") != "mixed_headline_signal":
        failures.append("conflicting headline direction was not flagged")

    class ReactionFetcher:
        def __init__(self, ticker: str):
            self.ticker = ticker

        def get_intraday_reaction(self, published_at: str):
            move = {"TSLA": 1.4, "QQQ": 0.2}.get(self.ticker)
            if move is None:
                return {"error": "QA ticker unavailable"}
            return {
                "change_since_publication": move,
                "baseline_at": "2026-07-30T05:45:00+00:00",
                "observed_at": "2026-07-30T07:00:00+00:00",
                "bar_interval": "15m",
                "measurement_basis": "last_bar_before_publication_to_latest_available_bar",
                "event_window_aligned": True,
            }

    with patch("src.morning_brief_service.DataFetcher", ReactionFetcher):
        confirmed_news = svc._attach_news_market_confirmation(
            [
                {
                    **conflicting_reports[0],
                    "title": "Tesla stock rises after robotaxi approval",
                    "ticker": "TSLA",
                    "related_tickers": ["TSLA"],
                }
            ]
        )
    market_confirmation = confirmed_news[0].get("market_confirmation") or {}
    if market_confirmation.get("status") != "confirmed":
        failures.append("positive headline was not confirmed by positive benchmark-relative reaction")
    if abs(float(market_confirmation.get("relative_move_since_publication") or 0) - 1.2) > 0.001:
        failures.append("benchmark-relative reaction was calculated incorrectly")
    if market_confirmation.get("causality_proven") is not False:
        failures.append("market reaction incorrectly claimed causality")
    if market_confirmation.get("event_window_aligned") is not True:
        failures.append("event-aligned reaction basis was not disclosed")
    with patch("src.morning_brief_service.DataFetcher", ReactionFetcher):
        provider_only_news = svc._attach_news_market_confirmation(
            [
                {
                    "title": "Equity futures mixed before the interest-rate announcement",
                    "ticker": "GLD",
                    "related_tickers": ["GLD"],
                    "ticker_association_basis": "provider_related_feed_only",
                    "published_at": "2026-07-30T06:00:00+00:00",
                    "event_type": "central_bank",
                }
            ]
        )
    if provider_only_news[0].get("market_confirmation"):
        failures.append("provider-feed-only ticker association received a misleading price confirmation")

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
            "top_news": [{**clustered[0], "market_confirmation": market_confirmation}],
        },
        "global",
    )
    important_message = next(
        (message for message in telegram_messages if "WICHTIG" in message),
        "",
    )
    for marker in ["Quellenabgleich:", "2 verschiedene Publisher", "Preisreaktion BESTÄTIGT:", "relativ +1.20%"]:
        if marker not in important_message:
            failures.append(f"important Telegram news missing {marker}")
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
