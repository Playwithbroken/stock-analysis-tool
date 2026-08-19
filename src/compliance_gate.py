import os
from datetime import datetime, timezone
from typing import Any, Dict, Mapping


EXTERNAL_MODES = {"third_party", "public", "commercial", "multi_user"}


def _enabled(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def get_compliance_status(environment: Mapping[str, str] | None = None) -> Dict[str, Any]:
    env = environment or os.environ
    mode = str(env.get("APP_DISTRIBUTION_MODE", "personal") or "personal").strip().lower()
    if mode not in {"personal", "private", *EXTERNAL_MODES}:
        mode = "invalid"
    external_use = mode in EXTERNAL_MODES or mode == "invalid"
    approved = _enabled(env.get("EXTERNAL_COMPLIANCE_APPROVED"))
    required = {
        "reviewer": str(env.get("EXTERNAL_COMPLIANCE_REVIEWER", "")).strip(),
        "reviewed_at": str(env.get("EXTERNAL_COMPLIANCE_REVIEWED_AT", "")).strip(),
        "review_scope": str(env.get("EXTERNAL_COMPLIANCE_REVIEW_SCOPE", "")).strip(),
        "legal_reference": str(env.get("EXTERNAL_COMPLIANCE_REFERENCE", "")).strip(),
        "data_controller": str(env.get("DATA_CONTROLLER_NAME", "")).strip(),
        "privacy_notice_url": str(env.get("PRIVACY_NOTICE_URL", "")).strip(),
        "retention_policy_version": str(env.get("DATA_RETENTION_POLICY_VERSION", "")).strip(),
    }
    blockers = []
    if mode == "invalid":
        blockers.append("invalid_distribution_mode")
    if external_use and not approved:
        blockers.append("external_compliance_not_approved")
    if external_use:
        blockers.extend(f"missing_{key}" for key, value in required.items() if not value)
    review_age_days = None
    if external_use and required["reviewed_at"]:
        try:
            reviewed = datetime.fromisoformat(required["reviewed_at"].replace("Z", "+00:00"))
            if reviewed.tzinfo is None:
                reviewed = reviewed.replace(tzinfo=timezone.utc)
            review_age_days = max(0, (datetime.now(timezone.utc) - reviewed.astimezone(timezone.utc)).days)
            if review_age_days > 365:
                blockers.append("external_compliance_review_expired")
        except ValueError:
            blockers.append("invalid_reviewed_at")
    external_release_allowed = external_use and approved and not blockers
    return {
        "schema": "compliance-gate.v1",
        "distribution_mode": mode,
        "external_use": external_use,
        "external_release_allowed": external_release_allowed,
        "request_allowed": not external_use or external_release_allowed,
        "approval_declared": approved,
        "reviewer": required["reviewer"] or None,
        "reviewed_at": required["reviewed_at"] or None,
        "review_age_days": review_age_days,
        "review_scope": required["review_scope"] or None,
        "legal_reference": required["legal_reference"] or None,
        "data_controller_configured": bool(required["data_controller"]),
        "privacy_notice_configured": bool(required["privacy_notice_url"]),
        "retention_policy_version": required["retention_policy_version"] or None,
        "blockers": list(dict.fromkeys(blockers)),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "policy": (
            "Private single-user research and paper-trading mode."
            if not external_use
            else "Third-party release requires documented external legal, compliance and privacy approval."
        ),
    }
