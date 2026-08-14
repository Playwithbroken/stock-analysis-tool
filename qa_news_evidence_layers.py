from __future__ import annotations

from pathlib import Path

from src.morning_brief_service import MorningBriefService


PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_SOURCE = PROJECT_ROOT / "frontend" / "src" / "components" / "MorningBriefPanel.tsx"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_backend_exposes_versioned_evidence_layers() -> None:
    service = MorningBriefService.__new__(MorningBriefService)
    intelligence = service._build_news_intelligence(
        {
            "title": "Company raises guidance after stronger demand",
            "source_summary": "The company raised its full-year revenue guidance.",
            "publisher": "Example Wire",
            "source_domain": "example.com",
            "source_url": "https://example.com/company-guidance",
            "published_at": "2026-08-14T08:00:00+00:00",
            "age_hours": 1.0,
            "source_quality": "tier_1",
            "source_type": "publisher",
            "event_type": "earnings",
            "impact": "high",
        }
    )

    layers = intelligence.get("evidence_layers") or {}
    require(layers.get("schema_version") == "1.0", "evidence layers must have a stable schema version")
    require(layers.get("facts", {}).get("summary") == intelligence.get("fact_summary"), "facts must retain the disclosed source summary")
    require(layers.get("facts", {}).get("basis") == intelligence.get("fact_basis"), "fact basis must remain explicit")
    require(layers.get("interpretation", {}).get("meaning") == intelligence.get("meaning"), "interpretation must remain separate from facts")
    require(layers.get("uncertainty", {}).get("counterargument") == intelligence.get("bear_case"), "counterargument must be explicit")
    require(layers.get("uncertainty", {}).get("confirmation_needed") == intelligence.get("confirmation"), "confirmation checks must remain explicit")
    require(layers.get("uncertainty", {}).get("invalidation") == intelligence.get("invalidation"), "invalidation must remain explicit")


def test_frontend_renders_all_layers_without_hover_dependency() -> None:
    source = FRONTEND_SOURCE.read_text(encoding="utf-8")
    expected_contracts = (
        'data-testid="news-evidence-layers"',
        "1 · Bestätigte Fakten",
        "2 · Interpretation (Analyse)",
        "Analyse, nicht Quellenfakt",
        "3 · Offene Unsicherheit",
        "Veröffentlichungszeit fehlt",
        "evidence.link_verified",
        "evidence.original_document_verified",
        "decisionReadiness.hard_blockers",
        "decisionReadiness.verification_gaps",
        "uncertainty.counterargument",
        "uncertainty.confirmation_needed",
        "uncertainty.invalidation",
        "Restunsicherheit bleibt bestehen.",
    )
    for expected in expected_contracts:
        require(expected in source, f"news evidence UI contract missing {expected!r}")
    component = source[source.index("function NewsEvidenceLayers"):source.index("function formatBriefGenerated")]
    require("title=" not in component, "critical evidence must not rely on hover tooltips")


def main() -> int:
    tests = [
        test_backend_exposes_versioned_evidence_layers,
        test_frontend_renders_all_layers_without_hover_dependency,
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"news evidence layers QA ok: {len(tests)} contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
