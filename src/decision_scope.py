from copy import deepcopy
from typing import Any, Dict


SCOPE_SCHEMA = "decision-scope.v1"


def research_scope(*, user_action: str = "Quellen, Datenstand und Risiko unabhängig prüfen.") -> Dict[str, Any]:
    return {
        "schema": SCOPE_SCHEMA,
        "mode": "research_only",
        "label": "Research",
        "description": "Analyse- und Beobachtungsinformation; keine Order und keine Kauf- oder Verkaufsempfehlung.",
        "paper_execution_allowed": False,
        "real_money_execution_allowed": False,
        "automatic_execution_allowed": False,
        "required_user_action": user_action,
    }


def paper_scope(*, user_action: str = "Nur im Demo-Konto prüfen und das Ergebnis dokumentieren.") -> Dict[str, Any]:
    return {
        "schema": SCOPE_SCHEMA,
        "mode": "paper_only",
        "label": "Paper-only",
        "description": "Simuliertes Lernen ohne Brokerorder oder Echtgeldwirkung.",
        "paper_execution_allowed": True,
        "real_money_execution_allowed": False,
        "automatic_execution_allowed": False,
        "required_user_action": user_action,
    }


def manual_review_scope(*, user_action: str = "Suitability, aktuelle Brokerquote, Risiko und Quellen manuell neu prüfen.") -> Dict[str, Any]:
    return {
        "schema": SCOPE_SCHEMA,
        "mode": "manual_real_money_review_candidate",
        "label": "Möglicher Echtgeld-Prüfkandidat",
        "description": "Nur Kandidat für eine unabhängige manuelle Prüfung; keine Orderfreigabe und kein Ausführungssignal.",
        "paper_execution_allowed": False,
        "real_money_execution_allowed": False,
        "automatic_execution_allowed": False,
        "required_user_action": user_action,
    }


def attach_scope(payload: Dict[str, Any], scope: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(payload)
    result["decision_scope"] = deepcopy(scope)
    return result


def scope_for_strategy_status(status: Any) -> Dict[str, Any]:
    if str(status or "").lower() == "manual_review_ready":
        return manual_review_scope()
    return paper_scope()


def validate_scope(scope: Dict[str, Any]) -> None:
    if scope.get("schema") != SCOPE_SCHEMA:
        raise ValueError("decision_scope schema is missing or invalid")
    mode = scope.get("mode")
    if mode not in {"research_only", "paper_only", "manual_real_money_review_candidate"}:
        raise ValueError("decision_scope mode is invalid")
    if scope.get("real_money_execution_allowed") is not False:
        raise ValueError("real-money execution must remain disabled")
    if scope.get("automatic_execution_allowed") is not False:
        raise ValueError("automatic execution must remain disabled")
    expected_paper = mode == "paper_only"
    if scope.get("paper_execution_allowed") is not expected_paper:
        raise ValueError("paper execution permission does not match scope mode")
