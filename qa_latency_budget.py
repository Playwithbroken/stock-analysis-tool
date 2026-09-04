from __future__ import annotations

from datetime import datetime, timezone
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.latency_monitor_service import LatencyMonitorService
import src.storage as storage


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_persistent_latency_percentiles_and_budgets() -> None:
    original_db_path = storage.DB_PATH
    with tempfile.TemporaryDirectory(prefix="latency-qa-") as temp_dir:
        storage.DB_PATH = str(Path(temp_dir) / "latency.db")
        env_patch = patch.dict("os.environ", {"LATENCY_BUDGET_RISK_MS": "50"})
        env_patch.start()
        try:
            storage.init_db()
            monitor = LatencyMonitorService()
            now = datetime.now(timezone.utc).isoformat()
            for value in (10, 20, 30, 40, 100):
                monitor.record(
                    provider="internal",
                    service="market_quality",
                    segment="risk",
                    latency_ms=value,
                    observed_at=now,
                )
            snapshot = monitor.snapshot(window_minutes=60)
            risk = snapshot["segments"]["risk"]
            require(risk["samples"] == 5, "latency samples were not persisted")
            require(risk["p50_ms"] == 30 and risk["p95_ms"] == 100 and risk["p99_ms"] == 100, "percentiles wrong")
            require(risk["violations"] == 1 and risk["status"] == "degraded", "budget violation missing")
            require(snapshot["segments"]["fill"]["status"] == "not_observed", "empty segment must be honest")

            for invalid in (-1, float("nan"), float("inf")):
                try:
                    monitor.record(provider="x", service="x", segment="risk", latency_ms=invalid)
                except ValueError:
                    continue
                raise AssertionError(f"invalid latency accepted: {invalid}")
        finally:
            env_patch.stop()
            storage.DB_PATH = original_db_path


if __name__ == "__main__":
    test_persistent_latency_percentiles_and_budgets()
    print("persistent latency budget QA passed")
