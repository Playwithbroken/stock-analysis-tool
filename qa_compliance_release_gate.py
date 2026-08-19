import os
from datetime import datetime, timezone
from pathlib import Path

from src.compliance_gate import get_compliance_status


ROOT = Path(__file__).resolve().parent


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def approved_environment() -> dict[str, str]:
    return {
        "APP_DISTRIBUTION_MODE": "third_party",
        "EXTERNAL_COMPLIANCE_APPROVED": "true",
        "EXTERNAL_COMPLIANCE_REVIEWER": "External Counsel",
        "EXTERNAL_COMPLIANCE_REVIEWED_AT": datetime.now(timezone.utc).isoformat(),
        "EXTERNAL_COMPLIANCE_REVIEW_SCOPE": "0.9.0-beta.1 third-party pilot",
        "EXTERNAL_COMPLIANCE_REFERENCE": "LEGAL-2026-001",
        "DATA_CONTROLLER_NAME": "Example Controller",
        "PRIVACY_NOTICE_URL": "https://example.test/privacy",
        "DATA_RETENTION_POLICY_VERSION": "retention-v1",
    }


def main() -> int:
    failures: list[str] = []
    private = get_compliance_status({"APP_DISTRIBUTION_MODE": "personal"})
    require(private.get("request_allowed") is True, failures, "private single-user mode was blocked")
    require(private.get("external_release_allowed") is False, failures, "private mode must not claim external approval")

    blocked = get_compliance_status({"APP_DISTRIBUTION_MODE": "public"})
    require(blocked.get("request_allowed") is False, failures, "public mode bypassed external approval")
    require("external_compliance_not_approved" in (blocked.get("blockers") or []), failures, "approval blocker missing")
    require("missing_privacy_notice_url" in (blocked.get("blockers") or []), failures, "privacy blocker missing")

    approved_env = approved_environment()
    approved = get_compliance_status(approved_env)
    require(approved.get("external_release_allowed") is True, failures, "complete external approval was rejected")
    require(not approved.get("blockers"), failures, "approved external mode still has blockers")

    expired_env = {**approved_env, "EXTERNAL_COMPLIANCE_REVIEWED_AT": "2024-01-01T00:00:00+00:00"}
    expired = get_compliance_status(expired_env)
    require(expired.get("request_allowed") is False, failures, "expired external review was accepted")
    require("external_compliance_review_expired" in (expired.get("blockers") or []), failures, "review expiry blocker missing")

    os.environ.update({
        "APP_DISTRIBUTION_MODE": "personal",
        "APP_ACCESS_PASSWORD": "test-pass",
        "APP_SESSION_SECRET": "c" * 64,
        "APP_COOKIE_SECURE": "false",
        "TELEGRAM_ALERTS_ENABLED": "false",
    })
    from fastapi.testclient import TestClient
    import api

    client = TestClient(api.app)
    try:
        require(client.get("/api/compliance/status").status_code == 200, failures, "public compliance status endpoint failed")
        os.environ["APP_DISTRIBUTION_MODE"] = "public"
        os.environ["EXTERNAL_COMPLIANCE_APPROVED"] = "false"
        require(client.get("/api/auth/status").status_code == 503, failures, "middleware did not block unapproved public mode")
        health = client.get("/api/health")
        require(health.status_code == 200, failures, "health must remain reachable while blocked")
        require(health.json().get("status") == "degraded", failures, "blocked external mode was not degraded")
        os.environ.update(approved_env)
        require(client.get("/api/auth/status").status_code == 200, failures, "approved mode remained blocked")
    finally:
        client.close()

    packet = (ROOT / "COMPLIANCE_REVIEW_PACKET.md").read_text(encoding="utf-8")
    for marker in [
        "externe Prüfung ausstehend",
        "Anlageberatung / Erlaubnis",
        "MAR / öffentliche Empfehlungen",
        "Datenschutz / Profiling",
        "Interessenkonflikt-Erklärung",
        "Sign-off",
        "https://eur-lex.europa.eu/eli/dir/2014/65/oj/eng",
        "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32014R0596",
    ]:
        require(marker in packet, failures, f"review packet lacks {marker}")
    plan = (ROOT / "APP_COMPLETION_PLAN.md").read_text(encoding="utf-8")
    require("- [ ] Nutzungszweck, Datenrisiken" in plan, failures, "external expert review was falsely marked complete")
    require("- [ ] Vor Nutzung für Dritte" in plan, failures, "external legal review was falsely marked complete")

    if failures:
        print("Compliance release gate QA failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("compliance release gate QA ok (private allowed, external blocked, approval expiry enforced)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
