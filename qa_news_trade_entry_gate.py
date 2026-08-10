from copy import deepcopy
from datetime import datetime, timedelta, timezone

from qa_paper_demo_account import FakePortfolioManager, build_service, sample_scoreboard, sample_settings


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def valid_news_playbook():
    now = datetime.now(timezone.utc)
    published = now - timedelta(hours=2)
    return {
        "id": "news-MSFT-long",
        "ticker": "MSFT",
        "asset_class": "equity",
        "direction": "long",
        "setup_type": "confirmed_news_event",
        "score": 92,
        "news_evidence": {
            "schema_version": "2.0",
            "source_quality": "tier_1",
            "source_url": "https://www.reuters.com/markets/msft-qa",
            "published_at": published.isoformat(),
            "reporting_source": {
                "publisher": "Reuters",
                "url": "https://www.reuters.com/markets/msft-qa",
                "quality": "tier_1",
                "link_verified": True,
                "published_at": published.isoformat(),
            },
            "primary_source": None,
            "original_document_verified": False,
            "correction_status": {"status": "not_detected_at_capture"},
            "market_confirmation": {
                "status": "confirmed",
                "expected_headline_direction": "positive",
                "ticker": "MSFT",
                "benchmark": "QQQ",
                "relative_move_since_publication": 1.4,
                "baseline_at": (published - timedelta(minutes=15)).isoformat(),
                "observed_at": (published + timedelta(hours=1)).isoformat(),
                "event_window_aligned": True,
                "causality_proven": False,
            },
        },
    }


def test_complete_tier_1_chain_passes_without_claiming_causality():
    service = build_service(FakePortfolioManager())
    playbook = valid_news_playbook()
    require(service._confirmed_news_entry_errors(playbook) == [], "complete Tier-1 evidence should pass")
    require(
        playbook["news_evidence"]["market_confirmation"]["causality_proven"] is False,
        "time alignment must not be presented as proof of causality",
    )


def test_primary_source_can_substitute_for_tier_1_reporting():
    service = build_service(FakePortfolioManager())
    playbook = valid_news_playbook()
    evidence = playbook["news_evidence"]
    evidence["source_quality"] = "official_primary"
    evidence["reporting_source"]["quality"] = "official_primary"
    evidence["primary_source"] = {
        "authority": "Microsoft Investor Relations",
        "url": "https://www.microsoft.com/en-us/Investor/earnings/qa",
    }
    evidence["original_document_verified"] = True
    require(service._confirmed_news_entry_errors(playbook) == [], "verified primary source should satisfy source gate")


def test_timestamp_spoof_and_incomplete_window_are_blocked():
    service = build_service(FakePortfolioManager())
    stale = valid_news_playbook()
    old = datetime.now(timezone.utc) - timedelta(hours=30)
    stale["news_evidence"]["published_at"] = old.isoformat()
    stale["news_evidence"]["reporting_source"]["published_at"] = old.isoformat()
    errors = service._confirmed_news_entry_errors(stale)
    require("publication_outside_24h_entry_window" in errors, "actual timestamp must override a claimed fresh age")

    missing_window = valid_news_playbook()
    missing_window["news_evidence"]["market_confirmation"].pop("baseline_at")
    errors = service._confirmed_news_entry_errors(missing_window)
    require("market_reaction_timestamps_missing" in errors, "missing reaction baseline must block entry")

    wrong_order = valid_news_playbook()
    published = datetime.fromisoformat(wrong_order["news_evidence"]["published_at"])
    wrong_order["news_evidence"]["market_confirmation"]["observed_at"] = (published - timedelta(minutes=1)).isoformat()
    errors = service._confirmed_news_entry_errors(wrong_order)
    require("market_reaction_timestamp_order_invalid" in errors, "observation before publication must block entry")


def test_final_create_path_rechecks_tampered_internal_playbook():
    service = build_service(FakePortfolioManager())
    tampered = valid_news_playbook()
    tampered["news_evidence"]["reporting_source"]["url"] = ""
    tampered["news_evidence"]["source_url"] = ""
    service._build_playbooks = lambda *args, **kwargs: [deepcopy(tampered)]
    service._apply_news_evidence_learning = lambda *args, **kwargs: None
    service._apply_news_shadow_learning = lambda *args, **kwargs: None
    service._refresh_playbook_decision_state = lambda *args, **kwargs: None
    service._attach_demo_sizing = lambda playbooks, *args, **kwargs: playbooks
    try:
        service.create_trade_from_playbook(
            {"playbook_id": "news-MSFT-long", "direction": "long"},
            sample_scoreboard(),
            sample_settings(),
            {},
        )
    except ValueError as exc:
        require("entry evidence gate" in str(exc), "final entry path must name the evidence gate")
        require("primary_or_verified_tier_1_source_required" in str(exc), "tampered source must be explicit")
    else:
        raise AssertionError("final create path accepted a tampered news playbook")


def test_raw_candidate_age_is_derived_from_publication_timestamp():
    service = build_service(FakePortfolioManager())
    now = datetime.now(timezone.utc)
    item = {
        "ticker": "MSFT",
        "ticker_association_basis": "explicit_title_entity",
        "source_quality": "tier_1",
        "source_url": "https://www.reuters.com/markets/msft-qa",
        "published_at": (now - timedelta(hours=30)).isoformat(),
        "age_hours": 1.0,
        "event_type": "policy",
        "source_evidence": {"quality": "tier_1", "link_verified": True},
        "news_intelligence": {"is_important": True},
        "market_confirmation": {
            "status": "confirmed",
            "expected_headline_direction": "positive",
            "relative_move_since_publication": 1.0,
            "baseline_at": (now - timedelta(hours=30, minutes=15)).isoformat(),
            "observed_at": (now - timedelta(hours=29)).isoformat(),
            "event_window_aligned": True,
        },
    }
    reasons = service._news_gate_reasons(item)
    require("news_older_than_24h" in reasons, "claimed age_hours must not override publication timestamp")


def main():
    tests = [
        test_complete_tier_1_chain_passes_without_claiming_causality,
        test_primary_source_can_substitute_for_tier_1_reporting,
        test_timestamp_spoof_and_incomplete_window_are_blocked,
        test_final_create_path_rechecks_tampered_internal_playbook,
        test_raw_candidate_age_is_derived_from_publication_timestamp,
    ]
    for test in tests:
        test()
    print(f"news trade entry gate QA passed ({len(tests)} contracts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
