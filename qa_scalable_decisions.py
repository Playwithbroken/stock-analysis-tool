"""Contract checks for account-independent strict Scalable research ideas."""

from datetime import datetime, timezone

from src.scalable_decision_service import ScalableDecisionService


def playbook(ticker: str, *, score: float = 94, freshness: str = "fresh", blocked: bool = False, asset: str = "equity"):
    return {
        "ticker": ticker,
        "asset_class": asset,
        "direction": "long",
        "setup_type": "quality_momentum",
        "score": score,
        "tradeable": not blocked,
        "do_not_trade_reasons": ["hard signal block"] if blocked else [],
        "reference_price": 100,
        "data_as_of": "2026-08-30T13:00:00Z",
        "market_data": {"freshness": freshness},
        "thesis": "Fresh price and signal confirmation.",
        "decision_framework": {
            "entry_trigger": "Close above 101 with volume",
            "invalidation": "Close below 96",
        },
        "risk_bucket": ticker,
    }


def main() -> None:
    dashboard = {
        "auto_selection": {"min_score": 88, "selected": [], "exploration": [], "aggressive_exploration": []},
        "playbooks": [
            playbook("IDEA"),
            playbook("STALE", freshness="stale"),
            playbook("BLOCK", blocked=True),
            playbook("LOW", score=87),
            playbook("OPT", asset="option"),
        ],
    }
    empty_portfolio = {"summary": {"total_value": 500000, "currency": "EUR"}, "holdings": []}
    report = ScalableDecisionService().build(empty_portfolio, dashboard)
    assert [row["ticker"] for row in report["ideas"]] == ["IDEA"], report
    assert report["ideas"][0]["evidence_level"] == "research_strict", report
    assert report["ideas"][0]["actionable_now"] is False, report

    held = {
        "summary": {"total_value": 500000, "currency": "EUR"},
        "holdings": [{
            "ticker": "IDEA",
            "name": "Idea AG",
            "position_value": 10000,
            "gain_loss_pct": 1,
            "quote_timestamp_utc": "2026-08-30T13:00:00Z",
            "quote_is_outdated": False,
        }],
    }
    held_report = ScalableDecisionService().build(held, dashboard, now=datetime(2026, 8, 30, 13, 1, tzinfo=timezone.utc))
    assert held_report["decisions"][0]["action"] == "AUFSTOCKEN_PRUEFEN", held_report
    assert held_report["decisions"][0]["evidence_level"] == "research_strict", held_report
    assert held_report["ideas"] == [], held_report
    print("Scalable independent research decisions: OK")


if __name__ == "__main__":
    main()


