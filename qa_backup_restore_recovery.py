import json
import os
import tempfile


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "recovery-test.db")
        os.environ["APP_BACKUP_DIR"] = os.path.join(tmp, "managed-backups")
        os.environ["APP_BACKUP_RETENTION_COUNT"] = "2"
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64
        os.environ["APP_COOKIE_SECURE"] = "false"
        os.environ["TELEGRAM_ALERTS_ENABLED"] = "false"

        from fastapi.testclient import TestClient
        import api

        failures: list[str] = []
        manager = api.get_portfolio_manager()
        portfolio = manager.create_portfolio("Recovery QA")
        manager.add_holding(portfolio["id"], "AAPL", 2, buy_price=100, purchase_date="2026-08-01")
        manager.set_app_setting("recovery_contract_marker", "present")
        manager.mark_signal_events_sent([
            {"event_key": "recovery:event", "category": "test", "title": "Recovery history"}
        ])

        cycle = api._run_backup_cycle(force_backup=True, force_restore_test=True)
        require(cycle.get("status") == "ok", failures, "forced backup/restore cycle failed")
        backup = cycle.get("backup") or {}
        restore = cycle.get("restore_test") or {}
        require(backup.get("quick_check") == "ok", failures, "backup quick_check failed")
        require(restore.get("quick_check") == "ok", failures, "restored database quick_check failed")
        require(restore.get("temporary_restore_removed") is True, failures, "temporary restore was not removed")
        for table in ["portfolios", "holdings", "paper_trades", "signal_forecast_outcomes", "app_settings", "sent_signal_events"]:
            require(table in (restore.get("counts") or {}), failures, f"restore counts missing {table}")
        require((restore.get("counts") or {}).get("portfolios", 0) >= 1, failures, "portfolio was not restored")
        require((restore.get("counts") or {}).get("holdings", 0) >= 1, failures, "holdings were not restored")
        require((restore.get("counts") or {}).get("sent_signal_events", 0) >= 1, failures, "alert history was not restored")

        for _ in range(3):
            api.get_database_backup_service().create_backup()
        status = api.get_database_backup_service().status()
        require(status.get("backup_count") == 2, failures, "backup retention did not keep exactly two managed backups")

        stored_backup = json.loads(manager.get_app_setting("database_backup_last_result", "{}") or "{}")
        stored_restore = json.loads(manager.get_app_setting("database_restore_test_last_result", "{}") or "{}")
        require(stored_backup.get("status") == "ok", failures, "successful backup result was not persisted")
        require(stored_restore.get("status") == "ok", failures, "successful restore result was not persisted")

        client = TestClient(api.app)
        require(client.post("/api/admin/backup/verify-restore").status_code == 401, failures, "restore endpoint must require auth")
        login = client.post("/api/auth/login", json={"password": "test-pass"})
        require(login.status_code == 200, failures, "test login failed")
        verify_response = client.post("/api/admin/backup/verify-restore")
        require(verify_response.status_code == 200, failures, "authenticated restore verification endpoint failed")
        health_response = client.get("/api/admin/health-center")
        require(health_response.status_code == 200, failures, "health center failed after recovery drill")
        health = health_response.json() if health_response.status_code == 200 else {}
        require(isinstance(health.get("backup"), dict), failures, "health center does not expose backup status")
        require((health.get("backup") or {}).get("restore_test_last_success_at"), failures, "health center misses restore timestamp")

        if failures:
            print("Backup/restore recovery QA failures:")
            for failure in failures:
                print(f"- {failure}")
            return 1
    print("backup/restore recovery QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
