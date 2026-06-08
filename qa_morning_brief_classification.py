import sys

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

    if failures:
        print("\nClassification failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nMorning brief classification smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
