from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


ADVISORY_ENUMS = {
    "investment_objective": {"income", "growth", "capital_preservation", "speculation", "mixed"},
    "time_horizon": {"short", "medium", "long"},
    "risk_tolerance": {"low", "medium", "high", "speculative"},
    "experience_level": {"beginner", "intermediate", "advanced", "professional"},
    "loss_capacity": {"low", "medium", "high"},
    "liquidity_need": {"low", "medium", "high"},
    "preferred_strategy": {"long_term", "dividend", "day_trading", "swing_trading", "mixed"},
}

ADVISORY_DEFAULTS: Dict[str, Any] = {
    "advisory_enabled": True,
    "advisory_profile_version": 1,
    "investment_objective": "mixed",
    "time_horizon": "medium",
    "risk_tolerance": "medium",
    "experience_level": "intermediate",
    "loss_capacity": "medium",
    "liquidity_need": "medium",
    "preferred_strategy": "mixed",
    "max_single_position_pct": 12.5,
    "max_portfolio_drawdown_pct": 20.0,
    "suitability_notes": "",
    "advisory_profile_updated_at": None,
    "advisory_profile_complete": False,
}

ADVISORY_FIELDS = set(ADVISORY_DEFAULTS.keys())
REQUIRED_ADVISORY_FIELDS = {
    "investment_objective",
    "time_horizon",
    "risk_tolerance",
    "experience_level",
    "loss_capacity",
    "liquidity_need",
    "preferred_strategy",
    "max_single_position_pct",
    "max_portfolio_drawdown_pct",
}


def _safe_float(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = fallback
    return round(max(minimum, min(maximum, number)), 2)


def _safe_string(value: Any) -> str:
    return str(value or "").strip()


def normalize_advisory_profile(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    source = payload or {}
    raw = {**ADVISORY_DEFAULTS, **source}
    normalized: Dict[str, Any] = {}

    normalized["advisory_enabled"] = bool(raw.get("advisory_enabled", True))
    normalized["advisory_profile_version"] = 1

    for field, allowed_values in ADVISORY_ENUMS.items():
        value = _safe_string(raw.get(field)).lower()
        normalized[field] = value if value in allowed_values else ADVISORY_DEFAULTS[field]

    normalized["max_single_position_pct"] = _safe_float(raw.get("max_single_position_pct"), 12.5, 1.0, 100.0)
    normalized["max_portfolio_drawdown_pct"] = _safe_float(raw.get("max_portfolio_drawdown_pct"), 20.0, 1.0, 100.0)
    normalized["suitability_notes"] = _safe_string(raw.get("suitability_notes"))[:1200]
    normalized["advisory_profile_updated_at"] = raw.get("advisory_profile_updated_at")

    normalized["advisory_profile_complete"] = bool(source.get("advisory_profile_complete")) and all(
        normalized.get(field) not in (None, "")
        for field in REQUIRED_ADVISORY_FIELDS
    )
    return normalized


def advisory_profile_subset(profile: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_advisory_profile(profile)
    return {field: normalized.get(field) for field in ADVISORY_DEFAULTS.keys()}


def merge_workspace_profile(current: Dict[str, Any], patch: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = {**(current or {}), **(patch or {})}
    advisory_patch = {key: merged.get(key) for key in ADVISORY_FIELDS if key in merged}
    advisory = normalize_advisory_profile(advisory_patch)
    advisory_was_updated = bool(patch and any(key in ADVISORY_FIELDS for key in patch.keys()))

    if advisory_was_updated:
        advisory["advisory_profile_updated_at"] = datetime.now(timezone.utc).isoformat()
        advisory["advisory_profile_complete"] = all(
            advisory.get(field) not in (None, "")
            for field in REQUIRED_ADVISORY_FIELDS
        )

    merged.update(advisory)
    return merged


def build_suitability_check(profile: Dict[str, Any], request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    advisory = normalize_advisory_profile(profile)
    req = request or {}
    reasons: List[str] = []
    required_next_steps: List[str] = []
    risk_flags: List[str] = []

    action = _safe_string(req.get("action") or "watch").lower()
    strategy = _safe_string(req.get("strategy") or advisory["preferred_strategy"]).lower()
    asset_class = _safe_string(req.get("asset_class") or "equity").lower()
    risk_level = _safe_string(req.get("risk_level") or "medium").lower()
    thesis = _safe_string(req.get("thesis"))
    position_pct = _safe_float(req.get("position_pct"), 0.0, 0.0, 100.0)

    score = 78
    decision = "information_only"

    if not advisory["advisory_enabled"]:
        return {
            "status": "review",
            "profile_complete": advisory["advisory_profile_complete"],
            "decision": "advisory_disabled",
            "suitability_score": 0,
            "reasons": ["Beratungsprofil ist deaktiviert; Signale bleiben reine Marktinformation."],
            "required_next_steps": ["Beratungsprofil aktivieren, bevor daraus Handlungsrahmen abgeleitet werden."],
            "risk_flags": ["advisory_disabled"],
            "disclaimer": "Informations- und Entscheidungsrahmen, keine automatische Kauf- oder Verkaufsempfehlung.",
        }

    if not advisory["advisory_profile_complete"] and action in {"setup", "action", "trade", "buy", "sell"}:
        score -= 35
        decision = "needs_profile"
        required_next_steps.append("Beratungsprofil vollstaendig ausfuellen, bevor ein aktiver Setup-Rahmen erlaubt ist.")

    if risk_level in {"high", "critical", "speculative"} and advisory["risk_tolerance"] in {"low", "medium"}:
        score -= 22
        risk_flags.append("risk_tolerance_mismatch")
        reasons.append("Signalrisiko liegt ueber der hinterlegten Risikotoleranz.")

    if risk_level in {"high", "critical", "speculative"} and advisory["loss_capacity"] == "low":
        score -= 28
        risk_flags.append("loss_capacity_mismatch")
        reasons.append("Verlusttragfaehigkeit ist fuer dieses Risikoniveau zu niedrig.")

    if asset_class in {"crypto", "option", "options", "leveraged_etf", "cfd"}:
        if advisory["experience_level"] in {"beginner", "intermediate"}:
            score -= 18
            risk_flags.append("complex_product_experience")
            reasons.append("Komplexes oder stark schwankendes Produkt passt nur eingeschraenkt zur Erfahrung.")
        if advisory["risk_tolerance"] == "low":
            score -= 18
            risk_flags.append("complex_product_low_risk_profile")

    if strategy == "day_trading":
        if advisory["experience_level"] in {"beginner", "intermediate"}:
            score -= 24
            risk_flags.append("day_trading_experience")
            reasons.append("Daytrading verlangt hoeheren Erfahrungsgrad und klare Risikoregeln.")
        if advisory["preferred_strategy"] in {"long_term", "dividend"}:
            score -= 16
            risk_flags.append("strategy_mismatch")
            reasons.append("Daytrading passt nicht zur bevorzugten Langfrist-/Dividendenstrategie.")

    max_position = float(advisory["max_single_position_pct"])
    if position_pct and position_pct > max_position:
        score -= 30
        risk_flags.append("position_size_too_large")
        reasons.append(f"Geplante Positionsgroesse {position_pct:.2f}% liegt ueber dem Limit von {max_position:.2f}%.")

    if action in {"setup", "action", "trade", "buy", "sell"} and not thesis:
        score -= 14
        required_next_steps.append("These, Trigger und Invalidierung dokumentieren, bevor gehandelt wird.")

    if advisory["liquidity_need"] == "high" and req.get("time_horizon") == "long":
        score -= 10
        risk_flags.append("liquidity_horizon_mismatch")

    score = max(0, min(100, score))

    if decision != "needs_profile":
        if score < 45 or "position_size_too_large" in risk_flags:
            decision = "blocked"
        elif score < 65 or risk_flags:
            decision = "action_requires_review"
        elif action in {"setup", "action", "trade", "buy", "sell"}:
            decision = "setup_allowed"
        else:
            decision = "watch"

    status = "ok"
    if decision in {"blocked", "needs_profile"}:
        status = decision
    elif decision == "action_requires_review":
        status = "review"

    if not reasons:
        reasons.append("Signal passt grundsaetzlich zum hinterlegten Beratungsrahmen.")
    if not required_next_steps:
        required_next_steps.append("Trigger, Positionsgroesse und Invalidierung vor Umsetzung nochmals pruefen.")

    return {
        "status": status,
        "profile_complete": advisory["advisory_profile_complete"],
        "decision": decision,
        "suitability_score": score,
        "symbol": req.get("symbol"),
        "asset_class": asset_class,
        "strategy": strategy,
        "risk_level": risk_level,
        "reasons": reasons,
        "required_next_steps": required_next_steps,
        "risk_flags": risk_flags,
        "profile_limits": {
            "risk_tolerance": advisory["risk_tolerance"],
            "loss_capacity": advisory["loss_capacity"],
            "experience_level": advisory["experience_level"],
            "max_single_position_pct": advisory["max_single_position_pct"],
            "max_portfolio_drawdown_pct": advisory["max_portfolio_drawdown_pct"],
        },
        "disclaimer": "Informations- und Entscheidungsrahmen, keine automatische Kauf- oder Verkaufsempfehlung.",
    }
