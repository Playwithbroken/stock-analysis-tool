from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List


SOAK_STATE_KEY = "production_soak_state_v1"
SOAK_SCHEMA = "production-soak.v1"
SOAK_REQUIRED_HOURS = 24 * 7
SOAK_REQUIRED_OBSERVED_DAYS = 7


def _as_utc(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _load_state(manager: Any) -> Dict[str, Any]:
    try:
        payload = json.loads(manager.get_app_setting(SOAK_STATE_KEY, "{}") or "{}")
        return payload if isinstance(payload, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _save_state(manager: Any, state: Dict[str, Any]) -> None:
    manager.set_app_setting(SOAK_STATE_KEY, json.dumps(state, ensure_ascii=True, sort_keys=True, default=str))


def _telegram_metric(provider_metrics: Dict[str, Any]) -> Dict[str, Any]:
    services = provider_metrics.get("services") or {}
    rows = services.values() if isinstance(services, dict) else services if isinstance(services, list) else []
    for row in rows:
        if isinstance(row, dict) and str(row.get("service") or "").lower() == "telegram":
            return row
    return {}


def _duplicate_trade_deliveries(sent_events: List[Dict[str, Any]]) -> List[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for event in sent_events or []:
        key = str(event.get("event_key") or "")
        if not (key.startswith("paper-open:") or key.startswith("paper-close:")):
            continue
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return sorted(duplicates)


def _current_incidents(
    *,
    run: Dict[str, Any],
    database: Dict[str, Any],
    notification_status: Dict[str, Any],
    scheduler_error: Any,
    scheduler_step_error: Any,
    backup_error: Any,
    restore_error: Any,
    provider_metrics: Dict[str, Any],
    sent_events: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    incidents: List[Dict[str, str]] = []

    def add(code: str, detail: str) -> None:
        incidents.append({"code": code, "detail": detail})

    if database.get("exists") is not True:
        add("database_missing", "Produktionsdatenbank fehlt.")
    if database.get("writable") is not True:
        add("database_not_writable", "Produktionsdatenbank oder Volume ist nicht beschreibbar.")
    if database.get("quick_check") not in {"ok", None}:
        add("database_integrity", f"SQLite quick_check: {database.get('quick_check')}")
    if database.get("railway_runtime") and database.get("persistence_ready") is not True:
        add("database_volume_missing", "Railway-Datenbank liegt nicht auf dem persistenten Volume.")
    baseline_identity = str(run.get("database_identity") or "")
    current_identity = str(database.get("identity") or "")
    if baseline_identity and current_identity and baseline_identity != current_identity:
        add("database_identity_changed", f"Datenbank-ID wechselte von {baseline_identity[:12]} auf {current_identity[:12]}.")
    if scheduler_error:
        add("scheduler_loop_error", str(scheduler_error))
    if scheduler_step_error:
        add("scheduler_step_error", str(scheduler_step_error))
    if backup_error:
        add("backup_error", str(backup_error))
    if restore_error:
        add("restore_test_error", str(restore_error))
    telegram = notification_status.get("telegram") if isinstance(notification_status.get("telegram"), dict) else {}
    if telegram.get("enabled") is True and telegram.get("configured") is not True:
        add("telegram_not_configured", "Telegram ist aktiviert, aber Bot-Token oder Chat-ID fehlt.")
    telegram_metric = _telegram_metric(provider_metrics)
    last_error = telegram_metric.get("last_error") if isinstance(telegram_metric.get("last_error"), dict) else {}
    error_at = _as_utc(last_error.get("occurred_at"))
    started_at = _as_utc(run.get("started_at"))
    if telegram_metric.get("status") == "error" and error_at and started_at and error_at >= started_at:
        add("telegram_delivery_error", str(last_error.get("message") or last_error.get("error_code") or "Telegram-Zustellung fehlgeschlagen."))
    duplicates = _duplicate_trade_deliveries(sent_events)
    if duplicates:
        add("duplicate_trade_delivery", "Doppelte Kauf-/Verkaufs-Event-ID: " + ", ".join(duplicates[:5]))
    return incidents


def _report(run: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    if not run:
        return {
            "schema": SOAK_SCHEMA,
            "status": "not_observed",
            "required_hours": SOAK_REQUIRED_HOURS,
            "message": "Noch keine automatische Produktionsbeobachtung gespeichert.",
        }
    started_at = _as_utc(run.get("started_at")) or now
    elapsed_hours = max(0.0, (now - started_at).total_seconds() / 3600)
    incidents = run.get("incidents") if isinstance(run.get("incidents"), list) else []
    days = run.get("days") if isinstance(run.get("days"), list) else []
    passed = not incidents and elapsed_hours >= SOAK_REQUIRED_HOURS and len(days) >= SOAK_REQUIRED_OBSERVED_DAYS
    status = "failed" if incidents else "passed" if passed else "collecting"
    remaining_hours = 0 if passed else max(0, math.ceil(SOAK_REQUIRED_HOURS - elapsed_hours))
    return {
        "schema": SOAK_SCHEMA,
        "status": status,
        "release_commit": run.get("release_commit"),
        "deployment_id": run.get("deployment_id"),
        "database_identity": run.get("database_identity"),
        "started_at": run.get("started_at"),
        "last_observed_at": run.get("last_observed_at"),
        "eligible_at": (started_at + timedelta(hours=SOAK_REQUIRED_HOURS)).isoformat(),
        "required_hours": SOAK_REQUIRED_HOURS,
        "required_observed_days": SOAK_REQUIRED_OBSERVED_DAYS,
        "elapsed_hours": round(elapsed_hours, 2),
        "remaining_hours": remaining_hours,
        "observation_count": int(run.get("observation_count") or 0),
        "observed_days": len(days),
        "remaining_observed_days": max(0, SOAK_REQUIRED_OBSERVED_DAYS - len(days)),
        "healthy_observation_count": int(run.get("healthy_observation_count") or 0),
        "failed_observation_count": int(run.get("failed_observation_count") or 0),
        "incidents": incidents[-20:],
        "latest_checks": run.get("latest_checks") or {},
        "message": (
            "Sieben Tage ohne kritischen Befund nachgewiesen."
            if status == "passed"
            else "Der Soak ist fehlgeschlagen; nach Behebung und neuem Deployment beginnt die Frist erneut."
            if status == "failed"
            else f"Produktionsbeobachtung läuft; noch {remaining_hours} Stunden bis zur frühesten Abnahme."
        ),
    }


def read_production_soak(manager: Any, now: datetime | None = None) -> Dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    state = _load_state(manager)
    report = _report(state.get("active_run") if isinstance(state.get("active_run"), dict) else {}, current)
    report["history"] = state.get("history") if isinstance(state.get("history"), list) else []
    return report


def record_production_soak(
    manager: Any,
    *,
    release: Dict[str, Any],
    database: Dict[str, Any],
    notification_status: Dict[str, Any],
    scheduler_error: Any = None,
    scheduler_step_error: Any = None,
    backup_error: Any = None,
    restore_error: Any = None,
    provider_metrics: Dict[str, Any] | None = None,
    sent_events: List[Dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> Dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    commit = str(release.get("commit_sha") or release.get("commit_short") or "").strip()
    deployment_id = str(release.get("deployment_id") or "").strip()
    if not commit or not deployment_id:
        return read_production_soak(manager, current)

    state = _load_state(manager)
    history = state.get("history") if isinstance(state.get("history"), list) else []
    run = state.get("active_run") if isinstance(state.get("active_run"), dict) else {}
    run_identity = (str(run.get("release_commit") or ""), str(run.get("deployment_id") or ""))
    current_identity = (commit, deployment_id)
    if run and run_identity != current_identity:
        history.append({**_report(run, current), "archived_at": current.isoformat()})
        history = history[-5:]
        run = {}
    if not run:
        run = {
            "release_commit": commit,
            "deployment_id": deployment_id,
            "database_identity": database.get("identity"),
            "started_at": current.isoformat(),
            "observation_count": 0,
            "healthy_observation_count": 0,
            "failed_observation_count": 0,
            "incidents": [],
            "days": [],
        }

    current_incidents = _current_incidents(
        run=run,
        database=database,
        notification_status=notification_status,
        scheduler_error=scheduler_error,
        scheduler_step_error=scheduler_step_error,
        backup_error=backup_error,
        restore_error=restore_error,
        provider_metrics=provider_metrics or {},
        sent_events=sent_events or [],
    )
    run["last_observed_at"] = current.isoformat()
    run["observation_count"] = int(run.get("observation_count") or 0) + 1
    healthy = not current_incidents
    counter_key = "healthy_observation_count" if healthy else "failed_observation_count"
    run[counter_key] = int(run.get(counter_key) or 0) + 1
    run["latest_checks"] = {
        "database": "ok" if not any(item["code"].startswith("database_") for item in current_incidents) else "error",
        "scheduler": "ok" if not any(item["code"].startswith("scheduler_") for item in current_incidents) else "error",
        "telegram": "ok" if not any(item["code"].startswith("telegram_") for item in current_incidents) else "error",
        "trade_delivery_duplicates": 0 if not any(item["code"] == "duplicate_trade_delivery" for item in current_incidents) else 1,
        "backup_restore": "ok" if not any(item["code"] in {"backup_error", "restore_test_error"} for item in current_incidents) else "error",
    }
    incident_log = run.get("incidents") if isinstance(run.get("incidents"), list) else []
    existing = {(item.get("code"), str(item.get("observed_at") or "")[:10]) for item in incident_log if isinstance(item, dict)}
    for incident in current_incidents:
        identity = (incident["code"], current.date().isoformat())
        if identity not in existing:
            incident_log.append({**incident, "observed_at": current.isoformat()})
    run["incidents"] = incident_log[-50:]

    days = run.get("days") if isinstance(run.get("days"), list) else []
    day_key = current.date().isoformat()
    day = next((item for item in days if item.get("date") == day_key), None)
    if day is None:
        day = {"date": day_key, "first_observed_at": current.isoformat(), "observation_count": 0, "failed_observation_count": 0}
        days.append(day)
    day["last_observed_at"] = current.isoformat()
    day["observation_count"] = int(day.get("observation_count") or 0) + 1
    if not healthy:
        day["failed_observation_count"] = int(day.get("failed_observation_count") or 0) + 1
    run["days"] = days[-10:]

    state = {"schema": SOAK_SCHEMA, "active_run": run, "history": history}
    _save_state(manager, state)
    report = _report(run, current)
    report["history"] = history
    return report
