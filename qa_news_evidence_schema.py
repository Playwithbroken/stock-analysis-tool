from __future__ import annotations

from datetime import datetime, timezone

from src.email_alert_service import EmailAlertService
from src.morning_brief_service import MorningBriefService
from src.paper_trading_service import PaperTradingService


class DummyPortfolioManager:
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sample_news() -> dict:
    return {
        "title": "Microsoft raises guidance after cloud demand improves",
        "publisher": "Reuters",
        "source_domain": "reuters.com",
        "source_url": "https://www.reuters.com/markets/companies/msft-guidance-qa",
        "published_at": "2026-08-10T09:00:00+00:00",
        "age_hours": 1.0,
        "source_quality": "tier_1",
        "ticker": "MSFT",
        "ticker_association_basis": "explicit_title_entity",
        "event_type": "earnings",
        "impact": "high",
        "source_evidence": {
            "quality": "tier_1",
            "domain": "reuters.com",
            "link_verified": True,
            "reporting_basis": "publisher_summary",
            "original_document_verified": True,
            "corroboration": "corroborated",
            "publisher_count": 2,
            "source_agreement": "aligned_headline_signal",
            "correction_status": {
                "status": "not_detected_at_capture",
                "checked_at": "2026-08-10T10:00:00+00:00",
                "signals": [],
                "monitoring_scope": "headline_and_publisher_summary_at_capture",
                "ongoing_monitor_verified": False,
            },
        },
        "primary_sources": [
            {
                "authority": "Microsoft Investor Relations",
                "form": "Earnings Release",
                "url": "https://www.microsoft.com/en-us/Investor/earnings/qa",
                "published_at": "2026-08-10T08:45:00+00:00",
                "verification_status": "official_domain",
            }
        ],
        "news_intelligence": {
            "is_important": True,
            "importance_score": 18,
            "fact_basis": "publisher_summary",
            "fact_summary": "Microsoft raised guidance and cited stronger cloud demand.",
            "meaning": "Higher guidance can lift forward revenue and margin expectations.",
            "assessment": "Important, but the price reaction must hold.",
            "directional_bias": "positive if confirmed",
            "bull_case": "Guidance is supported by durable demand and margins.",
            "bear_case": "The initial reaction fades if expectations were already too high.",
            "confirmation": ["Relative strength versus QQQ", "Volume confirms"],
            "invalidation": "MSFT loses the post-release reaction low.",
            "execution_horizon": "1-5 trading days",
        },
        "market_confirmation": {
            "status": "confirmed",
            "expected_headline_direction": "positive",
            "ticker": "MSFT",
            "benchmark": "QQQ",
            "asset_move_since_publication": 2.1,
            "benchmark_move_since_publication": 0.4,
            "relative_move_since_publication": 1.7,
            "baseline_at": "2026-08-10T09:00:00+00:00",
            "observed_at": "2026-08-10T10:00:00+00:00",
            "event_window_aligned": True,
            "causality_proven": False,
        },
    }


def test_correction_detection_and_trade_gate() -> None:
    brief = MorningBriefService.__new__(MorningBriefService)
    normal = brief._news_correction_status({"title": "Company publishes quarterly results"})
    corrected = brief._news_correction_status({"title": "CORRECTION: Company changes reported revenue"})
    withdrawn = brief._news_correction_status({"title": "Story withdrawn after source review"})
    require(normal["status"] == "not_detected_at_capture", "normal headline should not invent a correction")
    require(corrected["status"] == "correction_detected", "correction marker must be detected")
    require(withdrawn["status"] == "retracted_or_withdrawn", "withdrawal marker must be detected")
    require(normal["ongoing_monitor_verified"] is False, "capture scan must not claim continuous monitoring")

    service = PaperTradingService(DummyPortfolioManager())
    corrected_news = sample_news()
    corrected_news["source_evidence"] = {
        **corrected_news["source_evidence"],
        "correction_status": corrected,
    }
    reasons = service._news_gate_reasons(corrected_news)
    require("source_corrected_or_retracted" in reasons, "corrected source must block a news trade")


def test_versioned_news_evidence_separates_sources_and_analysis() -> None:
    service = PaperTradingService(DummyPortfolioManager())
    service._market_reference_fields = lambda ticker: {
        "reference_price": 100.0,
        "data_as_of": "2026-08-10T10:00:00+00:00",
        "market_data": {
            "price": 100.0,
            "data_as_of": "2026-08-10T10:00:00+00:00",
            "source": "qa",
            "freshness": "fresh",
            "liquidity_status": "strong",
        },
    }
    playbooks = service._build_confirmed_news_playbooks(
        {"generated_at": "2026-08-10T10:00:00+00:00", "top_news": [sample_news()]}
    )
    require(len(playbooks) == 1, "eligible news should create one confirmed-news playbook")
    evidence = playbooks[0]["news_evidence"]
    require(evidence["schema_version"] == "2.0", "news evidence must be versioned")
    require(evidence["reporting_source"]["publisher"] == "Reuters", "reporting publisher must remain separate")
    require(
        evidence["primary_source"]["authority"] == "Microsoft Investor Relations",
        "primary authority must remain separate",
    )
    require(evidence["facts"]["verified_against_primary"] is True, "primary verification must be explicit")
    require(evidence["interpretation"]["is_reported_fact"] is False, "analysis must not be labeled as reported fact")
    require(evidence["source_comparison"]["publisher_count"] == 2, "publisher count must be retained")
    require(
        evidence["correction_status"]["status"] == "not_detected_at_capture",
        "capture correction status must be retained",
    )


def test_telegram_renders_source_fact_and_interpretation_layers() -> None:
    service = PaperTradingService(DummyPortfolioManager())
    service._market_reference_fields = lambda ticker: {
        "reference_price": 100.0,
        "data_as_of": datetime.now(timezone.utc).isoformat(),
        "market_data": {"price": 100.0, "data_as_of": datetime.now(timezone.utc).isoformat()},
    }
    evidence = service._build_confirmed_news_playbooks(
        {"generated_at": "2026-08-10T10:00:00+00:00", "top_news": [sample_news()]}
    )[0]["news_evidence"]
    alert = EmailAlertService.__new__(EmailAlertService)
    text = "\n".join(alert._paper_news_evidence_lines(evidence))
    for expected in (
        "Berichtende Quelle",
        "Reuters",
        "Primärquelle",
        "Microsoft Investor Relations",
        "Bestätigter Faktenstand",
        "Unsere Interpretation – kein Quellenfakt",
        "2 Publisher",
        "keine Korrektur erkannt",
        "Kausalität",
    ):
        require(expected in text, f"telegram evidence block missing {expected!r}")


def main() -> int:
    tests = [
        test_correction_detection_and_trade_gate,
        test_versioned_news_evidence_separates_sources_and_analysis,
        test_telegram_renders_source_fact_and_interpretation_layers,
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"news evidence schema QA ok: {len(tests)} contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
