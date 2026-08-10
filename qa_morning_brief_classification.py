import sys
from datetime import datetime, timezone
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

    ready_gate_item = {
        **confirmed_news[0],
        "ticker_association_basis": "explicit_title_entity",
        "is_important": True,
        "age_hours": 1.0,
        "event_type": "product_catalyst",
        "source_evidence": {
            **(confirmed_news[0].get("source_evidence") or {}),
            "quality": "tier_1",
            "link_verified": True,
            "source_agreement": "consistent_headline_signal",
        },
    }
    ready_decision = svc._attach_news_decision_readiness([ready_gate_item])[0].get("decision_readiness") or {}
    if ready_decision.get("status") != "ready_for_paper_review":
        failures.append(f"fully verified news was not paper-review ready: {ready_decision}")
    if ready_decision.get("real_money_ready") is not False:
        failures.append("news decision gate incorrectly authorized real-money execution")

    monitor_gate_item = {
        **ready_gate_item,
        "event_type": "earnings",
        "source_evidence": {
            **ready_gate_item["source_evidence"],
            "original_document_verified": False,
        },
    }
    monitor_decision = svc._attach_news_decision_readiness([monitor_gate_item])[0].get("decision_readiness") or {}
    if monitor_decision.get("status") != "monitor" or "earnings_primary_document_missing" not in monitor_decision.get("verification_gap_codes", []):
        failures.append("earnings without a verified primary document was not held for monitoring")

    reject_gate_item = {
        **ready_gate_item,
        "source_evidence": {
            **ready_gate_item["source_evidence"],
            "source_agreement": "mixed_headline_signal",
        },
    }
    reject_decision = svc._attach_news_decision_readiness([reject_gate_item])[0].get("decision_readiness") or {}
    if reject_decision.get("status") != "reject" or "source_signal_conflict" not in reject_decision.get("hard_blocker_codes", []):
        failures.append("mixed source direction was not rejected by the news decision gate")
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

    sec_payload = {
        "filings": {
            "recent": {
                "accessionNumber": ["0000789019-26-000099", "0000789019-26-000100"],
                "form": ["8-K", "8-K"],
                "filingDate": ["2026-07-30", "2026-07-30"],
                "reportDate": ["2026-07-30", "2026-07-30"],
                "acceptanceDateTime": ["2026-07-30T12:00:00.000Z", "2026-07-30T13:00:00.000Z"],
                "primaryDocument": ["unrelated.htm", "earnings.htm"],
                "items": ["5.02,9.01", "2.02,9.01"],
            }
        }
    }

    class SecResponse:
        def __init__(self, status_code: int, payload=None):
            self.status_code = status_code
            self.payload = payload or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return self.payload

        def close(self):
            return None

    sec_calls = []

    def sec_get(url: str, headers=None, timeout=None, stream=False):
        sec_calls.append({"url": url, "headers": headers or {}, "stream": stream})
        if "data.sec.gov/submissions/" in url:
            return SecResponse(200, sec_payload)
        return SecResponse(200)

    svc._sec_filing_cache.clear()
    with patch.dict("os.environ", {"SEC_CONTACT_EMAIL": "qa@example.com"}), patch(
        "src.morning_brief_service.requests.get",
        sec_get,
    ):
        sec_filing = svc._find_sec_earnings_filing(
            "MSFT",
            "2026-07-30T12:30:00+00:00",
        )
    if sec_filing.get("status") != "verified" or sec_filing.get("form") != "8-K":
        failures.append("matching SEC earnings 8-K was not verified")
    if "2.02" not in str(sec_filing.get("items") or ""):
        failures.append("unrelated SEC 8-K was accepted as earnings evidence")
    if not str(sec_filing.get("url") or "").endswith("/earnings.htm"):
        failures.append("SEC primary document URL is incorrect")
    if not sec_calls or not str((sec_calls[0].get("headers") or {}).get("User-Agent") or "").strip():
        failures.append("SEC request did not declare a User-Agent")

    earnings_news = svc._enrich_news_item(
        {
            "ticker": "MSFT",
            "related_tickers": ["MSFT"],
            "ticker_association_basis": "explicit_title_entity",
            "title": "Microsoft reports quarterly earnings",
            "publisher": "Reuters",
            "link": "https://www.reuters.com/technology/microsoft-quarterly-earnings/",
            "source_url": "https://www.reuters.com/technology/microsoft-quarterly-earnings/",
            "source_domain": "reuters.com",
            "source_quality": "tier_1",
            "is_trusted_source": True,
            "published_at": "2026-07-30T12:30:00+00:00",
            "age_hours": 1.0,
            "event_type": "earnings",
            "impact": "high",
            "severity": "elevated",
        }
    )
    with patch.object(svc, "_find_sec_earnings_filing", return_value=sec_filing):
        primary_attached = svc._attach_news_primary_sources([earnings_news])
    primary_evidence = primary_attached[0].get("source_evidence") or {}
    if primary_evidence.get("original_document_verified") is not True:
        failures.append("verified SEC filing was not attached as original evidence")
    if len(primary_attached[0].get("primary_sources") or []) != 1:
        failures.append("verified SEC filing link is missing from news")
    if "nicht automatisch abgeglichen" not in str(
        (primary_attached[0].get("news_intelligence") or {}).get("precision_note") or ""
    ):
        failures.append("SEC evidence overclaim disclosure is missing")

    official_url = "https://www.bea.gov/news/2026/gdp-advance-estimate-2nd-quarter-2026"
    official_meta = svc._source_meta("U.S. Bureau of Economic Analysis", official_url)
    if official_meta.get("source_type") != "official_primary" or official_meta.get("quality") != "tier_1":
        failures.append("allowlisted government source was not classified as official primary")
    official_classification = svc._classify_news_signal(
        "GDP (Advance Estimate), 2nd Quarter 2026 " + official_url
    )
    official_news = svc._enrich_news_item(
        {
            "title": "GDP (Advance Estimate), 2nd Quarter 2026",
            "publisher": "U.S. Bureau of Economic Analysis",
            "link": official_url,
            "source_url": official_url,
            "source_summary": "Real gross domestic product increased in the second quarter.",
            "source_domain": official_meta.get("domain"),
            "source_type": official_meta.get("source_type"),
            "source_quality": official_meta.get("quality"),
            "is_trusted_source": official_meta.get("trusted"),
            "published_at": "2026-07-30T12:30:00+00:00",
            "age_hours": 1.0,
            **official_classification,
        }
    )
    official_evidence = official_news.get("source_evidence") or {}
    official_intelligence = official_news.get("news_intelligence") or {}
    if official_news.get("event_type") != "macro_data":
        failures.append("official GDP release was not classified as macro data")
    if official_evidence.get("original_document_verified") is not True:
        failures.append("official BEA release was not marked as primary evidence")
    if official_evidence.get("primary_source_verification") != "official_rss_and_allowlisted_domain":
        failures.append("official source verification method is missing")
    if official_intelligence.get("fact_basis") != "official_release_summary":
        failures.append("official release fact basis was not disclosed")
    if len(official_news.get("primary_sources") or []) != 1:
        failures.append("official primary-source link is missing")

    telegram = EmailAlertService.__new__(EmailAlertService)
    fresh_at = datetime.now(timezone.utc).isoformat()
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
            "top_news": [
                {
                    **clustered[0],
                    "published_at": fresh_at,
                    "market_confirmation": market_confirmation,
                    "primary_sources": primary_attached[0].get("primary_sources"),
                    "source_evidence": {
                        **(clustered[0].get("source_evidence") or {}),
                        "original_document_verified": True,
                        "published_at": fresh_at,
                    },
                    "decision_readiness": ready_decision,
                }
            ],
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
    for marker in ["Primärquelle:", "SEC 8-K", "Publisher-Kennzahlen nicht automatisch"]:
        if marker not in important_message:
            failures.append(f"important Telegram news missing {marker}")
    for marker in ["Fakt (Publisher-Zusammenfassung)", "Bedeutung:", "Einschätzung:", "Bestätigung:", "Invalidierung:"]:
        if marker not in important_message:
            failures.append(f"important Telegram news missing {marker}")
    for marker in ["Decision Gate:", "PAPER-REVIEW BEREIT", "Richtung:", "Echtgeld gesperrt", "Aktion:"]:
        if marker not in important_message:
            failures.append(f"important Telegram decision gate missing {marker}")

    telegram_messages.clear()
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
            "top_news": [{
                **official_news,
                "published_at": fresh_at,
                "source_evidence": {
                    **(official_news.get("source_evidence") or {}),
                    "published_at": fresh_at,
                },
            }],
        },
        "global",
    )
    official_message = next(
        (message for message in telegram_messages if "WICHTIG" in message),
        "",
    )
    for marker in [
        "Primärquelle:",
        "U.S. Bureau of Economic Analysis",
        "Offizielle Herkunft verifiziert",
        "Fakt (offizielle Behörden-Zusammenfassung)",
    ]:
        if marker not in official_message:
            failures.append(f"official Telegram news missing {marker}")

    if failures:
        print("\nClassification failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nMorning brief classification smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
