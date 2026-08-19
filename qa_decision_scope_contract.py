from pathlib import Path

from src.decision_scope import (
    manual_review_scope,
    paper_scope,
    research_scope,
    scope_for_strategy_status,
    validate_scope,
)


ROOT = Path(__file__).resolve().parent


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    scopes = [research_scope(), paper_scope(), manual_review_scope()]
    for scope in scopes:
        try:
            validate_scope(scope)
        except ValueError as exc:
            failures.append(str(exc))
        require(scope["real_money_execution_allowed"] is False, failures, "real-money execution was enabled")
        require(scope["automatic_execution_allowed"] is False, failures, "automatic execution was enabled")
        require(bool(scope.get("required_user_action")), failures, "required user action is missing")
    require(paper_scope()["paper_execution_allowed"] is True, failures, "paper scope must allow simulation")
    require(research_scope()["paper_execution_allowed"] is False, failures, "research must not execute a paper trade")
    require(manual_review_scope()["paper_execution_allowed"] is False, failures, "manual review candidate must not execute")
    require(
        scope_for_strategy_status("manual_review_ready")["mode"] == "manual_real_money_review_candidate",
        failures,
        "strategy readiness is not mapped to manual review",
    )

    api_source = (ROOT / "api.py").read_text(encoding="utf-8")
    morning_source = (ROOT / "src" / "morning_brief_service.py").read_text(encoding="utf-8")
    paper_source = (ROOT / "src" / "paper_trading_service.py").read_text(encoding="utf-8")
    telegram_source = (ROOT / "src" / "email_alert_service.py").read_text(encoding="utf-8")
    require('"decision_scope": research_scope()' in api_source, failures, "analysis API lacks research scope")
    require("attach_scope(dashboard, paper_scope())" in api_source, failures, "paper dashboard lacks paper scope")
    require("paper_scope() if status == \"ready_for_paper_review\" else research_scope()" in morning_source, failures, "news decisions lack scope gate")
    require("sized_playbooks = [attach_scope(item, paper_scope())" in paper_source, failures, "paper playbooks lack item scope")
    require("Keine automatische Echtgeld-Ausführung" in telegram_source, failures, "Telegram lacks explicit execution boundary")

    ui_contracts = {
        "AnalysisResult.tsx": "decision-scope-research",
        "PaperTradingPanel.tsx": "decision-scope-paper",
        "MorningBriefPanel.tsx": "decision-scope-news",
    }
    for filename, marker in ui_contracts.items():
        source = (ROOT / "frontend" / "src" / "components" / filename).read_text(encoding="utf-8")
        require(marker in source, failures, f"{filename} lacks visible decision scope")

    if failures:
        print("Decision scope QA failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("decision scope QA ok (research, paper-only, manual review candidate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
