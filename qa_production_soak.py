from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.production_soak_service import read_production_soak, record_production_soak


class FakeManager:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get_app_setting(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)

    def set_app_setting(self, key: str, value: str) -> None:
        self.values[key] = value


def inputs(deployment_id: str = "deploy-1") -> dict:
    return {
        "release": {"commit_sha": "a" * 40, "deployment_id": deployment_id},
        "database": {
            "exists": True,
            "writable": True,
            "quick_check": "ok",
            "railway_runtime": True,
            "persistence_ready": True,
            "identity": "database-1",
        },
        "notification_status": {"telegram": {"enabled": True, "configured": True}},
        "provider_metrics": {"services": {"telegram": {"service": "telegram", "status": "ok"}}},
        "sent_events": [
            {"event_key": "paper-open:trade-1"},
            {"event_key": "paper-close:trade-1"},
        ],
    }


def test_soak_requires_elapsed_time_and_daily_observations() -> None:
    manager = FakeManager()
    start = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    report = record_production_soak(manager, now=start, **inputs())
    assert report["status"] == "collecting"
    assert report["remaining_hours"] == 168
    assert report["observed_days"] == 1

    for day in range(1, 8):
        report = record_production_soak(manager, now=start + timedelta(days=day, minutes=1), **inputs())
    assert report["status"] == "passed"
    assert report["elapsed_hours"] >= 168
    assert report["observed_days"] >= 7
    assert report["incidents"] == []


def test_incident_is_not_erased_and_redeploy_restarts_clock() -> None:
    manager = FakeManager()
    start = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    record_production_soak(manager, now=start, **inputs())
    broken = inputs()
    broken["database"] = {**broken["database"], "identity": "database-2"}
    failed = record_production_soak(manager, now=start + timedelta(hours=1), **broken)
    assert failed["status"] == "failed"
    assert any(item["code"] == "database_identity_changed" for item in failed["incidents"])

    healthy_again = record_production_soak(manager, now=start + timedelta(hours=2), **inputs())
    assert healthy_again["status"] == "failed"

    restarted = record_production_soak(manager, now=start + timedelta(hours=3), **inputs("deploy-2"))
    assert restarted["status"] == "collecting"
    assert restarted["elapsed_hours"] == 0
    assert len(restarted["history"]) == 1
    assert restarted["history"][0]["status"] == "failed"


def test_duplicate_trade_delivery_fails_soak() -> None:
    manager = FakeManager()
    payload = inputs()
    payload["sent_events"] = [
        {"event_key": "paper-open:trade-1"},
        {"event_key": "paper-open:trade-1"},
    ]
    report = record_production_soak(
        manager,
        now=datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc),
        **payload,
    )
    assert report["status"] == "failed"
    assert report["latest_checks"]["trade_delivery_duplicates"] == 1


if __name__ == "__main__":
    test_soak_requires_elapsed_time_and_daily_observations()
    test_incident_is_not_erased_and_redeploy_restarts_clock()
    test_duplicate_trade_delivery_fails_soak()
    print("qa_production_soak: ok")
