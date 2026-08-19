import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        database = Path(tmp) / "audit.db"
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = str(database)
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "a" * 64
        os.environ["APP_COOKIE_SECURE"] = "false"
        os.environ["TELEGRAM_ALERTS_ENABLED"] = "false"

        from fastapi.testclient import TestClient
        import api

        manager = api.get_portfolio_manager()
        first = manager.record_decision_audit(
            event_type="recommendation_snapshot",
            subject="AAPL",
            decision="HOLD",
            data_as_of="2026-08-19T12:00:00Z",
            source_status="verified",
            sources=[{"label": "SEC", "url": "https://www.sec.gov/example"}],
            model_version="stock-analyzer.v1",
            rule_version="analysis-recommendation.v1",
            user_action="analysis_requested",
            payload={"score": 64, "scope": "research_only"},
        )
        second = manager.record_decision_audit(
            event_type="rule_change",
            subject="paper-autopilot-settings",
            decision="settings_updated",
            data_as_of="2026-08-19T12:01:00Z",
            source_status="internal_configuration",
            sources=[],
            model_version="paper-autopilot.v2",
            rule_version="paper-autopilot-settings.v2",
            user_action="paper_autopilot_settings_saved",
            payload={"before": {"mode": "strict"}, "after": {"mode": "learn"}},
        )
        require(second["previous_hash"] == first["event_hash"], failures, "audit entries are not hash-linked")
        chain = manager.verify_decision_audit_chain()
        require(chain.get("valid") is True and chain.get("entries") == 2, failures, "valid audit chain was rejected")
        entries = manager.list_decision_audit(limit=10)
        require(entries[0].get("user_action") == "paper_autopilot_settings_saved", failures, "user action was not stored")
        require(entries[1].get("sources", [{}])[0].get("label") == "SEC", failures, "sources were not stored")
        for key in ["data_as_of", "source_status", "model_version", "rule_version", "event_hash"]:
            require(bool(entries[1].get(key)), failures, f"recommendation audit misses {key}")

        manager.mark_signal_events_sent([{
            "event_key": "audit:telegram:1",
            "category": "paper_trade",
            "title": "Paper trade opened",
            "source_quality": "tier_1",
            "source_label": "SEC",
            "source_url": "https://www.sec.gov/example",
            "data_as_of": "2026-08-19T12:02:00Z",
        }])
        telegram_entries = manager.list_decision_audit(limit=10)
        require(any(row.get("event_type") == "telegram_delivery" for row in telegram_entries), failures, "Telegram delivery was not audited")
        require(manager.verify_decision_audit_chain().get("valid") is True, failures, "Telegram audit broke the chain")

        with TestClient(api.app) as client:
            require(client.get("/api/admin/decision-audit").status_code == 401, failures, "audit endpoint must require authentication")
            require(client.post("/api/auth/login", json={"password": "test-pass"}).status_code == 200, failures, "test login failed")
            score_change = client.post(
                "/api/settings/signal-score",
                json={"do_not_trade": {"min_score_for_new_trade": 81}},
            )
            require(score_change.status_code == 200, failures, "signal-score rule change failed")
            require((score_change.json().get("audit") or {}).get("schema") == "decision-audit.v1", failures, "signal-score change lacks audit receipt")
            autopilot_change = client.post(
                "/api/trading/paper-autopilot/settings",
                json={"mode": "learn", "max_trades": 4},
            )
            require(autopilot_change.status_code == 200, failures, "paper-autopilot rule change failed")
            require((autopilot_change.json().get("audit") or {}).get("schema") == "decision-audit.v1", failures, "autopilot change lacks audit receipt")
            response = client.get("/api/admin/decision-audit?limit=2")
            require(response.status_code == 200, failures, "authenticated audit endpoint failed")
            if response.status_code == 200:
                body = response.json()
                require(body.get("schema") == "decision-audit.v1", failures, "audit API schema missing")
                require((body.get("chain") or {}).get("valid") is True, failures, "audit API did not verify chain")
                require(len(body.get("entries") or []) == 2, failures, "audit API limit was not applied")

        with closing(sqlite3.connect(database)) as connection:
            connection.execute(
                "UPDATE decision_audit_log SET decision = 'BUY' WHERE id = ?",
                (first["id"],),
            )
            connection.commit()
        broken = manager.verify_decision_audit_chain()
        require(broken.get("valid") is False and broken.get("broken_id") == first["id"], failures, "tampering was not detected")

    source_contracts = {
        ROOT / "api.py": ["analysis_requested", "brief_generated", "paper_dashboard_requested", "signal_score_settings_saved", "paper_autopilot_settings_saved"],
        ROOT / "src" / "storage.py": ["telegram_delivery", "previous_hash", "event_hash"],
        ROOT / "frontend" / "src" / "components" / "AdminHealthPanel.tsx": ["decision-audit-health"],
    }
    for path, markers in source_contracts.items():
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in source, failures, f"{path.name} lacks audit marker {marker}")

    if failures:
        print("Decision audit QA failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("decision audit QA ok (recommendations, rules, Telegram, auth, tamper detection)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
