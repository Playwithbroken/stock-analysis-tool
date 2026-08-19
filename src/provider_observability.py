from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import math
import threading
from typing import Any, Deque, Dict, Iterable

import requests


PROVIDER_SERVICES = ("quote", "news", "options", "telegram")
VALID_STATUSES = {"ok", "degraded", "error", "disabled"}
_MAX_SAMPLES = 200
_LOCK = threading.Lock()
_SAMPLES: Dict[str, Deque[Dict[str, Any]]] = defaultdict(lambda: deque(maxlen=_MAX_SAMPLES))


def classify_provider_error(
    service: str,
    error: BaseException | None = None,
    http_status: int | None = None,
    detail: str | None = None,
) -> str:
    prefix = str(service or "provider").strip().upper().replace("-", "_")
    text = f"{detail or ''} {error or ''}".lower()
    if "not_configured" in text or "not configured" in text or "missing_config" in text:
        return f"{prefix}_NOT_CONFIGURED"
    if isinstance(error, requests.Timeout) or "timeout" in text or http_status in {408, 504}:
        return f"{prefix}_TIMEOUT"
    if http_status in {401, 403}:
        return f"{prefix}_AUTH"
    if http_status == 429:
        return f"{prefix}_RATE_LIMITED"
    if http_status == 400:
        return f"{prefix}_INVALID_REQUEST"
    if http_status is not None and http_status >= 500:
        return f"{prefix}_UPSTREAM"
    if isinstance(error, requests.ConnectionError) or "connection" in text or "network" in text:
        return f"{prefix}_NETWORK"
    if "missing" in text or "empty" in text or "not_object" in text or "invalid_response" in text:
        return f"{prefix}_INVALID_RESPONSE"
    return f"{prefix}_UNAVAILABLE"


def record_provider_result(
    service: str,
    provider: str,
    operation: str,
    status: str,
    latency_ms: float | int | None = None,
    error_code: str | None = None,
    http_status: int | None = None,
    error_type: str | None = None,
) -> Dict[str, Any]:
    normalized_service = str(service or "provider").strip().lower()
    normalized_status = str(status or "error").strip().lower()
    if normalized_status not in VALID_STATUSES:
        normalized_status = "error"
    safe_latency = None
    try:
        numeric_latency = float(latency_ms) if latency_ms is not None else None
        if numeric_latency is not None and math.isfinite(numeric_latency):
            safe_latency = max(0, round(numeric_latency, 1))
    except (TypeError, ValueError):
        safe_latency = None
    sample = {
        "service": normalized_service,
        "provider": str(provider or "unknown").strip().lower(),
        "operation": str(operation or "request").strip().lower(),
        "status": normalized_status,
        "error_code": str(error_code or "").strip().upper() or None,
        "http_status": int(http_status) if isinstance(http_status, int) else None,
        "error_type": str(error_type or "").strip() or None,
        "latency_ms": safe_latency,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        _SAMPLES[normalized_service].append(sample)
    return sample


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * percentile) - 1))
    return round(ordered[index], 1)


def provider_metrics_snapshot() -> Dict[str, Any]:
    with _LOCK:
        copied = {service: list(_SAMPLES.get(service, ())) for service in PROVIDER_SERVICES}
    services: Dict[str, Any] = {}
    for service in PROVIDER_SERVICES:
        rows = copied[service]
        successful = sum(1 for row in rows if row["status"] == "ok")
        degraded = sum(1 for row in rows if row["status"] == "degraded")
        failed = sum(1 for row in rows if row["status"] == "error")
        disabled = sum(1 for row in rows if row["status"] == "disabled")
        attempted = successful + degraded + failed
        latencies = [row["latency_ms"] for row in rows if row.get("latency_ms") is not None]
        last_error = next(
            (
                row
                for row in reversed(rows)
                if row["status"] in {"error", "degraded"}
                or (row["status"] == "disabled" and row.get("error_code"))
            ),
            None,
        )
        last_sample = rows[-1] if rows else None
        services[service] = {
            "service": service,
            "status": last_sample["status"] if last_sample else "not_observed",
            "sample_count": len(rows),
            "attempt_count": attempted,
            "success_count": successful,
            "degraded_count": degraded,
            "failure_count": failed,
            "disabled_count": disabled,
            "success_rate_pct": round((successful / attempted) * 100, 1) if attempted else None,
            "average_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
            "p95_latency_ms": _percentile(latencies, 0.95),
            "last_observed_at": last_sample.get("occurred_at") if last_sample else None,
            "last_provider": last_sample.get("provider") if last_sample else None,
            "last_operation": last_sample.get("operation") if last_sample else None,
            "last_error": last_error,
        }
    return {
        "schema_version": "provider-metrics.v1",
        "window_size_per_service": _MAX_SAMPLES,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "services": services,
    }


def reset_provider_metrics() -> None:
    """Test helper; production code should retain the rolling in-process window."""
    with _LOCK:
        _SAMPLES.clear()
