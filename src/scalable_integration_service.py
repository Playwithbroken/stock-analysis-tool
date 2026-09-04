"""Read-only Scalable Capital CLI integration.

The adapter intentionally exposes a closed set of commands. It never accepts command
arguments from an HTTP request and never invokes a shell. Broker credentials and OAuth
tokens remain owned by the official Scalable CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import threading
from typing import Any, Callable, Dict, Iterable, List, Optional
import uuid

from src.storage import DB_PATH


SCALABLE_PORTFOLIO_ID = "scalable-capital-read-only"
SCALABLE_PORTFOLIO_NAME = "Scalable Capital (Read-only)"

_ALLOWED_COMMANDS = {
    "capabilities": ("capabilities", "--json"),
    "whoami": ("whoami", "--json"),
    "holdings": ("broker", "holdings", "--json"),
    "overview": ("broker", "overview", "--json"),
    "analytics": ("broker", "analytics", "--json"),
    "transactions": ("broker", "transactions", "--json"),
}
_SYNC_COMMANDS = ("holdings", "overview")
_TICKER_PATTERN = re.compile(r"^[A-Z0-9.^=\-]{1,32}$")
_ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_PUBLIC_CLI_ERRORS = {
    "no_session": "Keine aktive Scalable-CLI-Sitzung. Bitte persönlich read-only anmelden.",
    "refresh_relogin_required": "Die Scalable-Sitzung muss persönlich erneuert werden.",
    "device_locked": "Der Scalable-Zugang ist gesperrt; bitte direkt bei Scalable prüfen.",
    "local_read_only": "Die Scalable-Sitzung ist lokal schreibgeschützt.",
}


class ScalableIntegrationError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.details = details or {}


@dataclass(frozen=True)
class NormalizedPosition:
    isin: str
    ticker: str
    name: str
    security_type: str
    quantity: Decimal
    fifo_price: Optional[Decimal]
    valuation: Decimal
    valuation_currency: str
    quote_mid_price: Optional[Decimal]
    quote_currency: str
    quote_timestamp_utc: Optional[str]
    quote_is_outdated: Optional[bool]
    resolution_method: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(str(os.getenv(name, default)).strip()))
    except (TypeError, ValueError):
        return max(minimum, default)


def _decimal(value: Any, field: str, *, optional: bool = False) -> Optional[Decimal]:
    if value is None or value == "":
        if optional:
            return None
        raise ScalableIntegrationError("broker_payload_invalid", f"Scalable-Feld '{field}' fehlt.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ScalableIntegrationError("broker_payload_invalid", f"Scalable-Feld '{field}' ist ungültig.")
    if not result.is_finite():
        raise ScalableIntegrationError("broker_payload_invalid", f"Scalable-Feld '{field}' ist nicht endlich.")
    return result


def _safe_error_message(value: Any, fallback: str) -> str:
    text = str(value or fallback).replace("\r", " ").replace("\n", " ").strip()
    # Do not allow a provider response to put account data or arbitrarily large text in logs/UI.
    return text[:240]


class ScalableCliClient:
    """Narrow subprocess boundary around the official CLI."""

    def __init__(self, executable: Optional[str] = None, timeout_seconds: Optional[float] = None):
        self.executable_setting = str(executable or os.getenv("SCALABLE_CLI_PATH", "sc")).strip() or "sc"
        self.timeout_seconds = float(timeout_seconds or os.getenv("SCALABLE_CLI_TIMEOUT_SECONDS", "25"))
        self.max_output_bytes = int(os.getenv("SCALABLE_CLI_MAX_OUTPUT_BYTES", "2097152"))

    def resolved_executable(self) -> Optional[str]:
        configured = self.executable_setting
        if Path(configured).is_absolute():
            path = Path(configured).resolve()
            if not path.is_file():
                return None
            # On Windows, `sc.exe` is the Service Control Manager, not the
            # Scalable CLI. Never report that system binary as broker-ready.
            if os.name == "nt" and path.name.lower() == "sc.exe" and "system32" in {
                part.lower() for part in path.parts
            }:
                return None
            return str(path)
        found = shutil.which(configured)
        if not found:
            return None
        path = Path(found).resolve()
        if os.name == "nt" and path.name.lower() == "sc.exe" and "system32" in {
            part.lower() for part in path.parts
        }:
            return None
        return str(path)

    def verify_binary(self, executable: str) -> None:
        expected = str(os.getenv("SCALABLE_CLI_SHA256", "")).strip().lower()
        if not expected:
            return
        digest = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
        if not hmac.compare_digest(digest, expected):
            raise ScalableIntegrationError(
                "cli_integrity_failed",
                "Die Prüfsumme der Scalable CLI stimmt nicht mit SCALABLE_CLI_SHA256 überein.",
            )

    def run(self, command: str) -> Dict[str, Any]:
        if command not in _ALLOWED_COMMANDS:
            raise ScalableIntegrationError("command_blocked", "Dieser Scalable-Befehl ist nicht freigegeben.")
        return self._run_argv(_ALLOWED_COMMANDS[command])

    def quote(self, isin: str) -> Dict[str, Any]:
        normalized = str(isin or "").strip().upper()
        if not _ISIN_PATTERN.fullmatch(normalized):
            raise ScalableIntegrationError("argument_blocked", "Ungültige ISIN für Scalable-Quote.")
        return self._run_argv(("broker", "quote", "--isin", normalized, "--json"))

    def security_news(self, isin: str, locale: str = "de_DE") -> Dict[str, Any]:
        normalized = str(isin or "").strip().upper()
        normalized_locale = str(locale or "de_DE").strip()
        if not _ISIN_PATTERN.fullmatch(normalized):
            raise ScalableIntegrationError("argument_blocked", "Ungültige ISIN für Scalable-News.")
        if normalized_locale not in {"de_DE", "en_DE"}:
            raise ScalableIntegrationError("argument_blocked", "Nicht freigegebene Scalable-News-Sprache.")
        return self._run_argv(
            ("broker", "security-news", "--isin", normalized, "--locale", normalized_locale, "--json")
        )

    def _run_argv(self, argv: tuple[str, ...]) -> Dict[str, Any]:
        executable = self.resolved_executable()
        if not executable:
            raise ScalableIntegrationError("cli_not_installed", "Die offizielle Scalable CLI wurde nicht gefunden.")
        self.verify_binary(executable)
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        try:
            completed = subprocess.run(
                [executable, *argv],
                shell=False,
                check=False,
                capture_output=True,
                text=False,
                timeout=self.timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise ScalableIntegrationError("cli_timeout", "Die Scalable CLI hat nicht rechtzeitig geantwortet.") from exc
        except OSError as exc:
            raise ScalableIntegrationError("cli_unavailable", "Die Scalable CLI konnte nicht gestartet werden.") from exc

        stdout = completed.stdout or b""
        stderr = completed.stderr or b""
        if len(stdout) > self.max_output_bytes or len(stderr) > self.max_output_bytes:
            raise ScalableIntegrationError("cli_output_too_large", "Die Scalable-Antwort überschreitet das sichere Größenlimit.")
        try:
            envelope = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ScalableIntegrationError("cli_output_invalid", "Die Scalable CLI lieferte kein gültiges JSON.") from exc
        if not isinstance(envelope, dict):
            raise ScalableIntegrationError("cli_output_invalid", "Die Scalable CLI lieferte eine ungültige Antwort.")
        if completed.returncode != 0 or envelope.get("ok") is False:
            error = envelope.get("error") if isinstance(envelope.get("error"), dict) else {}
            raw_code = str(error.get("code") or "cli_request_failed").strip().lower()
            code = raw_code if re.fullmatch(r"[a-z0-9_]{1,80}", raw_code) else "cli_request_failed"
            # Provider error text can contain account context. Keep it inside the CLI boundary.
            message = _PUBLIC_CLI_ERRORS.get(code, f"Scalable-Anfrage fehlgeschlagen ({code}).")
            raise ScalableIntegrationError(code, message)
        data = envelope.get("data", envelope)
        if not isinstance(data, dict):
            raise ScalableIntegrationError("cli_output_invalid", "Die Scalable CLI lieferte keine strukturierten Daten.")
        return data


class ScalableIntegrationService:
    def __init__(
        self,
        db_path: str = DB_PATH,
        cli_client: Optional[ScalableCliClient] = None,
        ticker_resolver: Optional[Callable[[str, str], Optional[str]]] = None,
    ):
        self.db_path = db_path
        self.cli = cli_client or ScalableCliClient()
        self.ticker_resolver = ticker_resolver or self._resolve_ticker
        self._sync_lock = threading.Lock()
        self._market_context_lock = threading.Lock()
        self._init_tables()

    @property
    def enabled(self) -> bool:
        return _env_bool("SCALABLE_INTEGRATION_ENABLED", False)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_tables(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = self._connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scalable_sync_state (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                status TEXT NOT NULL,
                last_attempt_at TEXT,
                last_success_at TEXT,
                error_code TEXT,
                error_message TEXT,
                position_count INTEGER NOT NULL DEFAULT 0,
                total_value TEXT,
                currency TEXT,
                valuation_timestamp_utc TEXT,
                payload_sha256 TEXT,
                details_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS scalable_positions (
                isin TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                name TEXT NOT NULL,
                security_type TEXT,
                quantity TEXT NOT NULL,
                fifo_price TEXT,
                valuation TEXT NOT NULL,
                valuation_currency TEXT NOT NULL,
                quote_mid_price TEXT,
                quote_currency TEXT,
                quote_timestamp_utc TEXT,
                quote_is_outdated INTEGER,
                resolution_method TEXT NOT NULL,
                synced_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scalable_live_quotes (
                isin TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                bid_price TEXT,
                ask_price TEXT,
                mid_price TEXT NOT NULL,
                currency TEXT NOT NULL,
                quote_timestamp_utc TEXT NOT NULL,
                quote_is_outdated INTEGER NOT NULL,
                fetched_at TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scalable_security_news_cache (
                isin TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                locale TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scalable_transactions (
                transaction_hash TEXT PRIMARY KEY,
                isin TEXT,
                ticker TEXT,
                side TEXT,
                transaction_type TEXT,
                summary_type TEXT,
                quantity TEXT,
                amount TEXT,
                currency TEXT,
                status TEXT,
                event_datetime_utc TEXT,
                imported_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scalable_aux_sync_state (
                state_key TEXT PRIMARY KEY,
                last_attempt_at TEXT,
                last_success_at TEXT,
                status TEXT NOT NULL,
                item_count INTEGER NOT NULL DEFAULT 0,
                error_code TEXT
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO scalable_sync_state (singleton_id, status) VALUES (1, 'never_synced')"
        )
        conn.commit()
        conn.close()

    def is_managed_portfolio(self, portfolio_id: str) -> bool:
        return str(portfolio_id or "") == SCALABLE_PORTFOLIO_ID

    def status(self, *, check_session: bool = False) -> Dict[str, Any]:
        conn = self._connect()
        row = conn.execute("SELECT * FROM scalable_sync_state WHERE singleton_id = 1").fetchone()
        conn.close()
        result = dict(row) if row else {"status": "never_synced"}
        details_raw = result.pop("details_json", "{}")
        try:
            details = json.loads(details_raw or "{}")
        except json.JSONDecodeError:
            details = {}
        result.update(
            {
                "enabled": self.enabled,
                "auto_sync_enabled": self.enabled and _env_bool("SCALABLE_AUTO_SYNC_ENABLED", True),
                "auto_sync_interval_minutes": _env_int("SCALABLE_AUTO_SYNC_INTERVAL_MINUTES", 15, 5),
                "cli_installed": bool(self.cli.resolved_executable()),
                "read_only": True,
                "managed_portfolio_id": SCALABLE_PORTFOLIO_ID,
                "details": details if isinstance(details, dict) else {},
            }
        )
        result.pop("singleton_id", None)
        interval_minutes = int(result["auto_sync_interval_minutes"])
        last_success_raw = str(result.get("last_success_at") or "").strip()
        try:
            last_success = datetime.fromisoformat(last_success_raw.replace("Z", "+00:00"))
            if last_success.tzinfo is None:
                last_success = last_success.replace(tzinfo=timezone.utc)
            next_due = last_success.astimezone(timezone.utc) + timedelta(minutes=interval_minutes)
            result["next_sync_due_at"] = next_due.isoformat()
            result["snapshot_stale"] = datetime.now(timezone.utc) > next_due + timedelta(minutes=interval_minutes)
        except (TypeError, ValueError):
            result["next_sync_due_at"] = None
            result["snapshot_stale"] = result.get("status") == "ok"
        if check_session and result["enabled"] and result["cli_installed"]:
            try:
                self.cli.run("whoami")
                result["authenticated"] = True
            except ScalableIntegrationError as exc:
                result["authenticated"] = False
                result["session_error_code"] = exc.code
        return result

    def snapshot(self) -> Dict[str, Any]:
        conn = self._connect()
        rows = conn.execute(
            """SELECT isin, ticker, name, security_type, quantity, fifo_price, valuation,
                      valuation_currency, quote_mid_price, quote_currency, quote_timestamp_utc,
                      quote_is_outdated, resolution_method
               FROM scalable_positions ORDER BY valuation DESC, isin"""
        ).fetchall()
        conn.close()
        return {"status": self.status(), "positions": [dict(row) for row in rows]}

    def refresh_market_context(self) -> Dict[str, Any]:
        """Refresh validated quotes and a small rotating news batch for current holdings."""
        if not self.enabled:
            raise ScalableIntegrationError("integration_disabled", "Scalable-Integration ist deaktiviert.")
        if not self._market_context_lock.acquire(blocking=False):
            return {"status": "in_progress", "quotes_refreshed": 0, "news_refreshed": 0}
        attempted_at = _utc_now()
        try:
            snapshot = self.snapshot()
            positions = [row for row in snapshot.get("positions") or [] if isinstance(row, dict)]
            max_positions = min(50, _env_int("SCALABLE_MARKET_CONTEXT_MAX_POSITIONS", 50, 1))
            quote_ttl = _env_int("SCALABLE_QUOTE_CACHE_SECONDS", 240, 30)
            quote_rows = []
            errors: List[str] = []
            for row in positions[:max_positions]:
                if not self._quote_refresh_due(str(row.get("isin") or ""), quote_ttl):
                    continue
                try:
                    payload = self.cli.quote(str(row.get("isin") or ""))
                    self._validate_source_context([payload])
                    quote_rows.append(self._normalize_live_quote(payload, row))
                except ScalableIntegrationError as exc:
                    errors.append(exc.code)
            if quote_rows:
                self._commit_live_quotes(quote_rows, attempted_at)

            news_rows = []
            news_limit = min(10, _env_int("SCALABLE_NEWS_MAX_PER_SYNC", 3, 1))
            news_ttl_minutes = _env_int("SCALABLE_NEWS_CACHE_MINUTES", 30, 5)
            for row in self._news_refresh_candidates(positions, news_ttl_minutes, news_limit):
                try:
                    payload = self.cli.security_news(
                        str(row.get("isin") or ""),
                        os.getenv("SCALABLE_NEWS_LOCALE", "de_DE"),
                    )
                    news_rows.append(self._normalize_security_news(payload, row))
                except ScalableIntegrationError as exc:
                    errors.append(exc.code)
            if news_rows:
                self._commit_security_news(news_rows, attempted_at)
            self._record_aux_state(
                "market_context",
                attempted_at,
                "ok" if not errors else "partial",
                len(quote_rows) + len(news_rows),
                errors[0] if errors else None,
            )
            return {
                "status": "ok" if not errors else "partial",
                "quotes_refreshed": len(quote_rows),
                "news_refreshed": len(news_rows),
                "error_codes": sorted(set(errors)),
                "fetched_at": attempted_at,
            }
        finally:
            self._market_context_lock.release()

    def refresh_transactions(self) -> Dict[str, Any]:
        """Import the recent read-only transaction page using irreversible provider-id hashes."""
        if not self.enabled:
            raise ScalableIntegrationError("integration_disabled", "Scalable-Integration ist deaktiviert.")
        attempted_at = _utc_now()
        if not self._aux_refresh_due("transactions", _env_int("SCALABLE_TRANSACTIONS_CACHE_MINUTES", 15, 5)):
            return {"status": "cached", "imported": 0}
        try:
            payload = self.cli.run("transactions")
            self._validate_source_context([payload])
            result = self._result_payload(payload)
            items = result.get("items")
            if not isinstance(items, list):
                raise ScalableIntegrationError("broker_payload_invalid", "Scalable-Transaktionen enthalten keine Liste.")
            ticker_by_isin = {
                str(row.get("isin") or "").upper(): str(row.get("ticker") or "").upper()
                for row in self.snapshot().get("positions") or []
            }
            normalized = [
                self._normalize_transaction(item, ticker_by_isin, attempted_at)
                for item in items[:100]
                if isinstance(item, dict)
            ]
            conn = self._connect()
            try:
                for row in normalized:
                    conn.execute(
                        """INSERT OR IGNORE INTO scalable_transactions (
                               transaction_hash, isin, ticker, side, transaction_type, summary_type,
                               quantity, amount, currency, status, event_datetime_utc, imported_at
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        row,
                    )
                imported = conn.total_changes
                conn.commit()
            finally:
                conn.close()
            self._record_aux_state("transactions", attempted_at, "ok", len(normalized), None)
            return {"status": "ok", "received": len(normalized), "imported": imported, "fetched_at": attempted_at}
        except ScalableIntegrationError as exc:
            self._record_aux_state("transactions", attempted_at, "error", 0, exc.code)
            raise

    def market_context_snapshot(self) -> Dict[str, Any]:
        conn = self._connect()
        quotes = conn.execute(
            """SELECT isin, ticker, bid_price, ask_price, mid_price, currency,
                      quote_timestamp_utc, quote_is_outdated, fetched_at
               FROM scalable_live_quotes ORDER BY ticker"""
        ).fetchall()
        news = conn.execute(
            """SELECT isin, ticker, locale, summary_json, sources_json, fetched_at
               FROM scalable_security_news_cache ORDER BY ticker"""
        ).fetchall()
        transactions = conn.execute(
            """SELECT transaction_hash, isin, ticker, side, transaction_type, summary_type,
                      quantity, amount, currency, status, event_datetime_utc, imported_at
               FROM scalable_transactions ORDER BY event_datetime_utc DESC LIMIT 100"""
        ).fetchall()
        states = conn.execute("SELECT * FROM scalable_aux_sync_state ORDER BY state_key").fetchall()
        conn.close()
        return {
            "quotes": [dict(row) for row in quotes],
            "news": [
                {
                    **{key: row[key] for key in ("isin", "ticker", "locale", "fetched_at")},
                    "summary": json.loads(row["summary_json"] or "{}"),
                    "sources": json.loads(row["sources_json"] or "[]"),
                }
                for row in news
            ],
            "transactions": [dict(row) for row in transactions],
            "states": [dict(row) for row in states],
            "read_only": True,
        }

    def transaction_feedback(self) -> Dict[str, Any]:
        """Compare imported broker actions with the latest preceding Scalable decision audit."""
        conn = self._connect()
        try:
            transactions = [
                dict(row)
                for row in conn.execute(
                    """SELECT transaction_hash, ticker, side, transaction_type, event_datetime_utc
                       FROM scalable_transactions ORDER BY event_datetime_utc DESC LIMIT 200"""
                ).fetchall()
            ]
            audits = [
                dict(row)
                for row in conn.execute(
                    """SELECT created_at, payload_json FROM decision_audit_log
                       WHERE event_type='scalable_decision_report' ORDER BY created_at DESC LIMIT 500"""
                ).fetchall()
            ]
        except sqlite3.OperationalError:
            transactions, audits = [], []
        finally:
            conn.close()

        audit_rows: List[Dict[str, Any]] = []
        for audit in audits:
            try:
                payload = json.loads(audit.get("payload_json") or "{}")
                created = datetime.fromisoformat(str(audit.get("created_at") or "").replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            for decision in [*(payload.get("decisions") or []), *(payload.get("ideas") or [])]:
                if isinstance(decision, dict) and self._valid_feedback_ticker(decision.get("ticker")):
                    audit_rows.append({"created_at": created.astimezone(timezone.utc), **decision})

        max_age_days = _env_int("SCALABLE_FEEDBACK_MAX_SIGNAL_AGE_DAYS", 7, 1)
        samples: List[Dict[str, Any]] = []
        counts = {"aligned": 0, "contrary": 0, "no_prior_signal": 0, "unmapped": 0}
        for transaction in transactions:
            ticker = str(transaction.get("ticker") or "").upper()
            side = str(transaction.get("side") or "").lower()
            if not ticker or side not in {"buy", "sell"}:
                counts["unmapped"] += 1
                continue
            try:
                event_at = datetime.fromisoformat(str(transaction.get("event_datetime_utc") or "").replace("Z", "+00:00"))
                if event_at.tzinfo is None:
                    event_at = event_at.replace(tzinfo=timezone.utc)
                event_at = event_at.astimezone(timezone.utc)
            except (TypeError, ValueError):
                counts["unmapped"] += 1
                continue
            prior = next(
                (
                    item for item in audit_rows
                    if str(item.get("ticker") or "").upper() == ticker
                    and timedelta(0) <= event_at - item["created_at"] <= timedelta(days=max_age_days)
                ),
                None,
            )
            action = str((prior or {}).get("action") or "")
            if not prior or action == "HALTEN":
                result = "no_prior_signal"
            else:
                buy_actions = {"KAUF_PRUEFEN", "AUFSTOCKEN_PRUEFEN"}
                sell_actions = {"SHORT_PRUEFEN", "REDUZIEREN_PRUEFEN", "VERKAUFEN_PRUEFEN"}
                result = "aligned" if (side == "buy" and action in buy_actions) or (side == "sell" and action in sell_actions) else "contrary"
            counts[result] += 1
            samples.append(
                {
                    "transaction_hash": transaction.get("transaction_hash"),
                    "ticker": ticker,
                    "side": side,
                    "event_datetime_utc": transaction.get("event_datetime_utc"),
                    "prior_action": action or None,
                    "prior_score": (prior or {}).get("score"),
                    "prior_decision_at": prior["created_at"].isoformat() if prior else None,
                    "result": result,
                }
            )
        decisive = counts["aligned"] + counts["contrary"]
        return {
            "status": "ok",
            "counts": {**counts, "decisive": decisive, "total_transactions": len(transactions)},
            "alignment_rate_pct": round(counts["aligned"] / decisive * 100, 1) if decisive else None,
            "samples": samples[:50],
            "learning_eligible": decisive >= _env_int("SCALABLE_FEEDBACK_MIN_SAMPLES", 20, 5),
            "automatic_rule_changes": False,
            "policy": "Nur Messung. Keine automatische Strategie- oder Echtgeldregel wird aus Broker-Transaktionen geändert.",
        }

    @staticmethod
    def _valid_feedback_ticker(value: Any) -> bool:
        return bool(_TICKER_PATTERN.fullmatch(str(value or "").strip().upper()))

    def _quote_refresh_due(self, isin: str, ttl_seconds: int) -> bool:
        conn = self._connect()
        row = conn.execute("SELECT fetched_at FROM scalable_live_quotes WHERE isin = ?", (isin,)).fetchone()
        conn.close()
        if not row:
            return True
        try:
            fetched = datetime.fromisoformat(str(row["fetched_at"]).replace("Z", "+00:00"))
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - fetched.astimezone(timezone.utc)).total_seconds() >= ttl_seconds
        except (TypeError, ValueError):
            return True

    def _normalize_live_quote(self, payload: Dict[str, Any], position: Dict[str, Any]) -> Dict[str, Any]:
        result = self._result_payload(payload)
        expected_isin = str(position.get("isin") or "").upper()
        if str(result.get("isin") or "").upper() != expected_isin:
            raise ScalableIntegrationError("broker_context_mismatch", "Scalable-Quote gehört nicht zur angefragten ISIN.")
        mid = _decimal(result.get("quote_mid_price"), "quote_mid_price")
        bid = _decimal(result.get("quote_bid_price"), "quote_bid_price", optional=True)
        ask = _decimal(result.get("quote_ask_price"), "quote_ask_price", optional=True)
        if mid is None or mid <= 0 or (bid is not None and ask is not None and (bid > ask or not (bid <= mid <= ask))):
            raise ScalableIntegrationError("broker_payload_invalid", "Scalable-Quote enthält widersprüchliche Preise.")
        timestamp = str(result.get("quote_timestamp_utc") or "").strip()
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ScalableIntegrationError("broker_payload_invalid", "Scalable-Quote hat keinen gültigen Zeitstempel.") from exc
        outdated = result.get("quote_is_outdated")
        if not isinstance(outdated, bool):
            raise ScalableIntegrationError("broker_payload_invalid", "Scalable-Quote enthält keinen Frischestatus.")
        material = {
            "isin": expected_isin,
            "bid": str(bid) if bid is not None else None,
            "ask": str(ask) if ask is not None else None,
            "mid": str(mid),
            "currency": str(result.get("quote_currency") or "").upper(),
            "timestamp": timestamp,
            "outdated": outdated,
        }
        return {**material, "ticker": str(position.get("ticker") or "").upper(), "hash": hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()}

    def _commit_live_quotes(self, rows: List[Dict[str, Any]], fetched_at: str) -> None:
        conn = self._connect()
        try:
            for row in rows:
                conn.execute(
                    """INSERT INTO scalable_live_quotes (
                           isin, ticker, bid_price, ask_price, mid_price, currency,
                           quote_timestamp_utc, quote_is_outdated, fetched_at, payload_sha256
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(isin) DO UPDATE SET
                           ticker=excluded.ticker, bid_price=excluded.bid_price, ask_price=excluded.ask_price,
                           mid_price=excluded.mid_price, currency=excluded.currency,
                           quote_timestamp_utc=excluded.quote_timestamp_utc,
                           quote_is_outdated=excluded.quote_is_outdated, fetched_at=excluded.fetched_at,
                           payload_sha256=excluded.payload_sha256""",
                    (row["isin"], row["ticker"], row["bid"], row["ask"], row["mid"], row["currency"], row["timestamp"], int(row["outdated"]), fetched_at, row["hash"]),
                )
                conn.execute(
                    """UPDATE scalable_positions SET quote_mid_price=?, quote_currency=?,
                           quote_timestamp_utc=?, quote_is_outdated=? WHERE isin=?""",
                    (row["mid"], row["currency"], row["timestamp"], int(row["outdated"]), row["isin"]),
                )
            conn.commit()
        finally:
            conn.close()

    def _news_refresh_candidates(self, positions: List[Dict[str, Any]], ttl_minutes: int, limit: int) -> List[Dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
        conn = self._connect()
        cached = {str(row["isin"]): str(row["fetched_at"]) for row in conn.execute("SELECT isin, fetched_at FROM scalable_security_news_cache")}
        conn.close()
        due = []
        for row in positions:
            raw = cached.get(str(row.get("isin") or ""))
            try:
                fetched = datetime.fromisoformat(str(raw).replace("Z", "+00:00")) if raw else None
                if fetched and fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                fetched = None
            if fetched is None or fetched.astimezone(timezone.utc) <= cutoff:
                due.append(row)
        return due[:limit]

    def _normalize_security_news(self, payload: Dict[str, Any], position: Dict[str, Any]) -> Dict[str, Any]:
        expected_isin = str(position.get("isin") or "").upper()
        if str(payload.get("isin") or "").upper() != expected_isin:
            raise ScalableIntegrationError("broker_context_mismatch", "Scalable-News gehören nicht zur angefragten ISIN.")
        summary = payload.get("summary") if isinstance(payload.get("summary"), (dict, list)) else {}
        sources = payload.get("sources") if isinstance(payload.get("sources"), (dict, list)) else []
        summary_json = json.dumps(summary, ensure_ascii=False, default=str)
        sources_json = json.dumps(sources, ensure_ascii=False, default=str)
        if len(summary_json.encode("utf-8")) + len(sources_json.encode("utf-8")) > 262144:
            raise ScalableIntegrationError("broker_payload_invalid", "Scalable-News überschreiten das sichere Größenlimit.")
        material = f"{expected_isin}:{summary_json}:{sources_json}".encode("utf-8")
        return {"isin": expected_isin, "ticker": str(position.get("ticker") or "").upper(), "locale": str(payload.get("locale") or "de_DE"), "summary": summary_json, "sources": sources_json, "hash": hashlib.sha256(material).hexdigest()}

    def _commit_security_news(self, rows: List[Dict[str, Any]], fetched_at: str) -> None:
        conn = self._connect()
        try:
            for row in rows:
                conn.execute(
                    """INSERT INTO scalable_security_news_cache
                       (isin, ticker, locale, summary_json, sources_json, fetched_at, payload_sha256)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(isin) DO UPDATE SET ticker=excluded.ticker, locale=excluded.locale,
                           summary_json=excluded.summary_json, sources_json=excluded.sources_json,
                           fetched_at=excluded.fetched_at, payload_sha256=excluded.payload_sha256""",
                    (row["isin"], row["ticker"], row["locale"], row["summary"], row["sources"], fetched_at, row["hash"]),
                )
            conn.commit()
        finally:
            conn.close()

    def _normalize_transaction(self, item: Dict[str, Any], ticker_by_isin: Dict[str, str], imported_at: str) -> tuple[Any, ...]:
        provider_id = str(item.get("id") or "").strip()
        if not provider_id:
            raise ScalableIntegrationError("broker_payload_invalid", "Scalable-Transaktion hat keine ID.")
        isin = str(item.get("isin") or "").strip().upper() or None
        if isin and not _ISIN_PATTERN.fullmatch(isin):
            isin = None
        side = str(item.get("side") or "").strip().lower()[:24] or None
        quantity = _decimal(item.get("quantity"), "transaction.quantity", optional=True)
        amount = _decimal(item.get("amount"), "transaction.amount", optional=True)
        event_datetime = str(item.get("last_event_datetime") or "").strip() or None
        if event_datetime:
            try:
                parsed = datetime.fromisoformat(event_datetime.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise ScalableIntegrationError(
                    "broker_payload_invalid",
                    "Scalable-Transaktion hat keinen gültigen Zeitstempel.",
                ) from exc
        return (
            hashlib.sha256(provider_id.encode("utf-8")).hexdigest(),
            isin,
            ticker_by_isin.get(isin or "") or None,
            side,
            str(item.get("type") or item.get("security_transaction_type") or "")[:80] or None,
            str(item.get("summary_type") or "")[:80] or None,
            str(quantity) if quantity is not None else None,
            str(amount) if amount is not None else None,
            str(item.get("currency") or "")[:8].upper() or None,
            str(item.get("status") or "")[:40] or None,
            event_datetime[:64] if event_datetime else None,
            imported_at,
        )

    def _aux_refresh_due(self, key: str, ttl_minutes: int) -> bool:
        conn = self._connect()
        row = conn.execute("SELECT last_success_at FROM scalable_aux_sync_state WHERE state_key=?", (key,)).fetchone()
        conn.close()
        if not row or not row["last_success_at"]:
            return True
        try:
            value = datetime.fromisoformat(str(row["last_success_at"]).replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) - value.astimezone(timezone.utc) >= timedelta(minutes=ttl_minutes)
        except (TypeError, ValueError):
            return True

    def _record_aux_state(self, key: str, attempted_at: str, status: str, count: int, error_code: Optional[str]) -> None:
        conn = self._connect()
        conn.execute(
            """INSERT INTO scalable_aux_sync_state
               (state_key, last_attempt_at, last_success_at, status, item_count, error_code)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(state_key) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,
                   last_success_at=CASE WHEN excluded.status IN ('ok','partial') THEN excluded.last_attempt_at ELSE scalable_aux_sync_state.last_success_at END,
                   status=excluded.status, item_count=excluded.item_count, error_code=excluded.error_code""",
            (key, attempted_at, attempted_at if status in {"ok", "partial"} else None, status, int(count), error_code),
        )
        conn.commit()
        conn.close()

    def portfolio_analysis(self) -> Dict[str, Any]:
        """Build current-value metrics only from the reconciled broker snapshot."""
        snapshot = self.snapshot()
        if snapshot["status"].get("status") != "ok":
            raise ScalableIntegrationError(
                "snapshot_unavailable",
                "Es liegt noch kein gültiger Scalable-Snapshot vor.",
            )
        holdings: List[Dict[str, Any]] = []
        total_value = Decimal("0")
        total_cost = Decimal("0")
        cost_basis_complete = True
        for row in snapshot["positions"]:
            quantity = _decimal(row.get("quantity"), "quantity") or Decimal("0")
            valuation = _decimal(row.get("valuation"), "valuation") or Decimal("0")
            fifo_price = _decimal(row.get("fifo_price"), "fifo_price", optional=True)
            current_price = valuation / quantity if quantity > 0 else Decimal("0")
            if fifo_price is None:
                cost_basis_complete = False
                cost_basis = valuation
            else:
                cost_basis = fifo_price * quantity
            gain_loss = valuation - cost_basis
            gain_loss_pct = (valuation / cost_basis - Decimal("1")) * Decimal("100") if cost_basis > 0 else Decimal("0")
            total_value += valuation
            total_cost += cost_basis
            holdings.append(
                {
                    "ticker": row["ticker"],
                    "isin": row["isin"],
                    "name": row["name"],
                    "shares": float(quantity),
                    "current_price": float(current_price),
                    "buy_price": float(fifo_price) if fifo_price is not None else None,
                    "purchase_date": None,
                    "holding_days": None,
                    "position_value": float(valuation),
                    "cost_basis": float(cost_basis),
                    "gain_loss": float(gain_loss),
                    "gain_loss_pct": float(gain_loss_pct),
                    "return_since_buy": float(gain_loss),
                    "return_since_buy_pct": float(gain_loss_pct),
                    "change_1d": None,
                    "change_1y": None,
                    "sector": "Broker-Snapshot",
                    "score": 0,
                    "recommendation": "HOLD",
                    "valuation": "BROKER_SNAPSHOT",
                    "broker_currency": row["valuation_currency"],
                    "quote_timestamp_utc": row["quote_timestamp_utc"],
                    "quote_is_outdated": bool(row["quote_is_outdated"]) if row["quote_is_outdated"] is not None else None,
                }
            )
        gain = total_value - total_cost
        gain_pct = (total_value / total_cost - Decimal("1")) * Decimal("100") if total_cost > 0 else Decimal("0")
        return {
            "holdings": holdings,
            "summary": {
                "total_value": float(total_value),
                "total_cost": float(total_cost),
                "gain_loss": float(gain),
                "gain_loss_pct": float(gain_pct),
                "return_since_buy": float(gain),
                "return_since_buy_pct": float(gain_pct),
                "num_holdings": len(holdings),
                "avg_score": 0,
                "avg_holding_days": None,
                "sector_allocation": {"Broker-Snapshot": 100.0} if holdings else {},
                "cost_basis_complete": cost_basis_complete,
                "source": "scalable_cli_reconciled",
                "as_of": snapshot["status"].get("valuation_timestamp_utc"),
                "currency": snapshot["status"].get("currency"),
            },
        }

    def sync(self) -> Dict[str, Any]:
        if not self.enabled:
            raise ScalableIntegrationError(
                "integration_disabled",
                "Scalable-Integration ist deaktiviert. Setze SCALABLE_INTEGRATION_ENABLED=true.",
            )
        if not self._sync_lock.acquire(blocking=False):
            raise ScalableIntegrationError(
                "sync_in_progress",
                "Eine Scalable-Synchronisierung läuft bereits.",
            )
        attempted_at = _utc_now()
        try:
            payloads = {name: self.cli.run(name) for name in _SYNC_COMMANDS}
            self._validate_source_context(payloads.values())
            positions = self._normalize_positions(self._result_payload(payloads["holdings"]))
            overview = self._normalize_overview(self._result_payload(payloads["overview"]))
            self._reconcile(positions, overview)
            self._validate_tickers(positions)
            payload_hash = self._payload_hash(positions, overview)
            self._commit_snapshot(positions, overview, attempted_at, payload_hash)
            return self.snapshot()
        except ScalableIntegrationError as exc:
            self._record_failure(attempted_at, exc)
            raise
        finally:
            self._sync_lock.release()

    @staticmethod
    def _result_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Accept both direct fixtures and the CLI's account-context result wrapper."""
        result = payload.get("result")
        if result is None:
            return payload
        if not isinstance(result, dict):
            raise ScalableIntegrationError("broker_payload_invalid", "Scalable-Antwort enthält kein gültiges Ergebnis.")
        return result

    def _normalize_positions(self, payload: Dict[str, Any]) -> List[NormalizedPosition]:
        items = payload.get("items")
        if not isinstance(items, list):
            raise ScalableIntegrationError("broker_payload_invalid", "Scalable-Holdings enthalten keine Positionsliste.")
        if payload.get("count") is not None and int(payload["count"]) != len(items):
            raise ScalableIntegrationError("broker_count_mismatch", "Scalable-Positionsanzahl ist widersprüchlich.")
        overrides = self._ticker_overrides()
        existing_tickers = self._existing_ticker_map()
        normalized: List[NormalizedPosition] = []
        seen_isins: set[str] = set()
        unresolved: List[str] = []
        for item in items:
            if not isinstance(item, dict):
                raise ScalableIntegrationError("broker_payload_invalid", "Scalable-Position ist ungültig.")
            isin = str(item.get("isin") or "").strip().upper()
            if not _ISIN_PATTERN.fullmatch(isin) or isin in seen_isins:
                raise ScalableIntegrationError("broker_payload_invalid", "Scalable lieferte eine ungültige oder doppelte ISIN.")
            seen_isins.add(isin)
            name = str(item.get("name") or isin).strip()[:240]
            ticker = overrides.get(isin)
            method = "override" if ticker else "snapshot" if isin in existing_tickers else "resolver"
            if not ticker:
                ticker = existing_tickers.get(isin)
            if not ticker:
                ticker = self.ticker_resolver(isin, name)
            ticker = str(ticker or "").strip().upper()
            if not _TICKER_PATTERN.fullmatch(ticker):
                unresolved.append(isin)
                continue
            quantity = _decimal(item.get("quantity"), "quantity")
            valuation = _decimal(item.get("valuation"), "valuation")
            if quantity is None or quantity < 0 or valuation is None or valuation < 0:
                raise ScalableIntegrationError("broker_payload_invalid", "Scalable lieferte negative Positionswerte.")
            normalized.append(
                NormalizedPosition(
                    isin=isin,
                    ticker=ticker,
                    name=name,
                    security_type=str(item.get("security_type") or "")[:80],
                    quantity=quantity,
                    fifo_price=_decimal(item.get("fifo_price"), "fifo_price", optional=True),
                    valuation=valuation,
                    valuation_currency=str(item.get("valuation_currency") or "EUR").strip().upper()[:8],
                    quote_mid_price=_decimal(item.get("quote_mid_price"), "quote_mid_price", optional=True),
                    quote_currency=str(item.get("quote_currency") or "").strip().upper()[:8],
                    quote_timestamp_utc=str(item.get("quote_timestamp_utc") or "").strip() or None,
                    quote_is_outdated=item.get("quote_is_outdated") if isinstance(item.get("quote_is_outdated"), bool) else None,
                    resolution_method=method,
                )
            )
        if unresolved:
            raise ScalableIntegrationError(
                "ticker_resolution_failed",
                f"{len(unresolved)} Scalable-Position(en) konnten keinem Marktticker sicher zugeordnet werden.",
                details={"unresolved_isins": unresolved},
            )
        return normalized

    def _existing_ticker_map(self) -> Dict[str, str]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT isin, ticker FROM scalable_positions").fetchall()
        finally:
            conn.close()
        return {
            str(row["isin"]).strip().upper(): str(row["ticker"]).strip().upper()
            for row in rows
            if _ISIN_PATTERN.fullmatch(str(row["isin"]).strip().upper())
            and _TICKER_PATTERN.fullmatch(str(row["ticker"]).strip().upper())
        }

    def _normalize_overview(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        valuation = payload.get("valuation")
        timestamps = payload.get("timestamps")
        if not isinstance(valuation, dict) or not isinstance(timestamps, dict):
            raise ScalableIntegrationError("broker_payload_invalid", "Scalable-Übersicht ist unvollständig.")
        securities = _decimal(valuation.get("securities"), "valuation.securities", optional=True) or Decimal("0")
        crypto = _decimal(valuation.get("crypto"), "valuation.crypto", optional=True) or Decimal("0")
        total = _decimal(valuation.get("total"), "valuation.total", optional=True)
        return {
            # `broker holdings` currently enumerates securities only. Crypto is a
            # separate overview bucket and must not be reconciled as an unnamed holding.
            "invested_value": securities,
            "total_value": securities,
            "broker_total_value": total,
            "unrepresented_crypto_value": crypto,
            "valuation_timestamp_utc": str(timestamps.get("valuation_timestamp_utc") or "").strip() or None,
        }

    def _validate_source_context(self, payloads: Iterable[Dict[str, Any]]) -> None:
        fingerprints = set()
        for payload in payloads:
            account_id = str(payload.get("account_id") or "").strip()
            portfolio_id = str(payload.get("portfolio_id") or "").strip()
            if not account_id or not portfolio_id:
                raise ScalableIntegrationError("broker_context_missing", "Scalable-Konto- oder Portfolio-Kontext fehlt.")
            fingerprints.add(hashlib.sha256(f"{account_id}:{portfolio_id}".encode("utf-8")).hexdigest())
        if len(fingerprints) != 1:
            raise ScalableIntegrationError("broker_context_mismatch", "Scalable-Antworten stammen nicht aus demselben Portfolio.")

    def _reconcile(self, positions: List[NormalizedPosition], overview: Dict[str, Any]) -> None:
        position_total = sum((item.valuation for item in positions), Decimal("0"))
        expected = overview["invested_value"]
        absolute_tolerance = _decimal(os.getenv("SCALABLE_RECONCILIATION_TOLERANCE_EUR", "0.05"), "tolerance") or Decimal("0.05")
        relative_tolerance = abs(expected) * Decimal("0.00001")
        tolerance = max(absolute_tolerance, relative_tolerance)
        difference = abs(position_total - expected)
        if difference > tolerance:
            raise ScalableIntegrationError(
                "reconciliation_failed",
                "Positionssumme und Scalable-Brokerübersicht stimmen nicht überein; der alte Stand bleibt aktiv.",
                details={"difference": str(difference), "tolerance": str(tolerance)},
            )

    def _validate_tickers(self, positions: List[NormalizedPosition]) -> None:
        tickers = [item.ticker for item in positions]
        if len(set(tickers)) != len(tickers):
            raise ScalableIntegrationError(
                "ticker_collision",
                "Mehrere ISINs wurden demselben Ticker zugeordnet; der Import wurde gestoppt.",
            )

    def _commit_snapshot(
        self,
        positions: List[NormalizedPosition],
        overview: Dict[str, Any],
        synced_at: str,
        payload_hash: str,
    ) -> None:
        currencies = {item.valuation_currency for item in positions if item.valuation_currency}
        currency = next(iter(currencies)) if len(currencies) == 1 else "MIXED"
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR IGNORE INTO portfolios (id, name, created_at) VALUES (?, ?, ?)",
                (SCALABLE_PORTFOLIO_ID, SCALABLE_PORTFOLIO_NAME, synced_at),
            )
            conn.execute("UPDATE portfolios SET name = ? WHERE id = ?", (SCALABLE_PORTFOLIO_NAME, SCALABLE_PORTFOLIO_ID))
            conn.execute("DELETE FROM holdings WHERE portfolio_id = ?", (SCALABLE_PORTFOLIO_ID,))
            conn.execute("DELETE FROM scalable_positions")
            for item in positions:
                conn.execute(
                    """INSERT INTO holdings (id, portfolio_id, ticker, shares, buy_price, purchase_date)
                       VALUES (?, ?, ?, ?, ?, NULL)""",
                    (
                        str(uuid.uuid5(uuid.NAMESPACE_URL, f"scalable:{item.isin}")),
                        SCALABLE_PORTFOLIO_ID,
                        item.ticker,
                        float(item.quantity),
                        float(item.fifo_price) if item.fifo_price is not None else None,
                    ),
                )
                conn.execute(
                    """INSERT INTO scalable_positions (
                           isin, ticker, name, security_type, quantity, fifo_price, valuation,
                           valuation_currency, quote_mid_price, quote_currency, quote_timestamp_utc,
                           quote_is_outdated, resolution_method, synced_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item.isin,
                        item.ticker,
                        item.name,
                        item.security_type,
                        str(item.quantity),
                        str(item.fifo_price) if item.fifo_price is not None else None,
                        str(item.valuation),
                        item.valuation_currency,
                        str(item.quote_mid_price) if item.quote_mid_price is not None else None,
                        item.quote_currency,
                        item.quote_timestamp_utc,
                        int(item.quote_is_outdated) if item.quote_is_outdated is not None else None,
                        item.resolution_method,
                        synced_at,
                    ),
                )
            conn.execute(
                """UPDATE scalable_sync_state
                   SET status = 'ok', last_attempt_at = ?, last_success_at = ?, error_code = NULL,
                       error_message = NULL, position_count = ?, total_value = ?, currency = ?,
                       valuation_timestamp_utc = ?, payload_sha256 = ?, details_json = '{}'
                   WHERE singleton_id = 1""",
                (
                    synced_at,
                    synced_at,
                    len(positions),
                    str(overview.get("total_value")) if overview.get("total_value") is not None else None,
                    currency,
                    overview.get("valuation_timestamp_utc"),
                    payload_hash,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _record_failure(self, attempted_at: str, error: ScalableIntegrationError) -> None:
        conn = self._connect()
        conn.execute(
            """UPDATE scalable_sync_state
               SET status = 'error', last_attempt_at = ?, error_code = ?, error_message = ?, details_json = ?
               WHERE singleton_id = 1""",
            (
                attempted_at,
                error.code[:80],
                _safe_error_message(error.public_message, "Scalable-Synchronisierung fehlgeschlagen."),
                json.dumps(error.details, ensure_ascii=True, separators=(",", ":")),
            ),
        )
        conn.commit()
        conn.close()

    def _payload_hash(self, positions: List[NormalizedPosition], overview: Dict[str, Any]) -> str:
        payload = {
            "positions": [
                {
                    "isin": item.isin,
                    "ticker": item.ticker,
                    "quantity": str(item.quantity),
                    "fifo_price": str(item.fifo_price) if item.fifo_price is not None else None,
                    "valuation": str(item.valuation),
                    "currency": item.valuation_currency,
                    "quote_timestamp_utc": item.quote_timestamp_utc,
                }
                for item in sorted(positions, key=lambda value: value.isin)
            ],
            "overview": {
                "invested_value": str(overview["invested_value"]),
                "total_value": str(overview["total_value"]) if overview.get("total_value") is not None else None,
                "valuation_timestamp_utc": overview.get("valuation_timestamp_utc"),
            },
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _ticker_overrides(self) -> Dict[str, str]:
        raw = str(os.getenv("SCALABLE_ISIN_TICKER_MAP", "")).strip()
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ScalableIntegrationError("ticker_map_invalid", "SCALABLE_ISIN_TICKER_MAP ist kein gültiges JSON.") from exc
        if not isinstance(value, dict):
            raise ScalableIntegrationError("ticker_map_invalid", "SCALABLE_ISIN_TICKER_MAP muss ein JSON-Objekt sein.")
        result: Dict[str, str] = {}
        for isin, ticker in value.items():
            normalized_isin = str(isin).strip().upper()
            normalized_ticker = str(ticker).strip().upper()
            if not _ISIN_PATTERN.fullmatch(normalized_isin) or not _TICKER_PATTERN.fullmatch(normalized_ticker):
                raise ScalableIntegrationError("ticker_map_invalid", "SCALABLE_ISIN_TICKER_MAP enthält einen ungültigen Eintrag.")
            result[normalized_isin] = normalized_ticker
        return result

    @staticmethod
    def _resolve_ticker(isin: str, _name: str) -> Optional[str]:
        try:
            import yfinance as yf

            quotes = getattr(yf.Search(isin, max_results=8), "quotes", []) or []
            for quote in quotes:
                if not isinstance(quote, dict):
                    continue
                symbol = str(quote.get("symbol") or "").strip().upper()
                if _TICKER_PATTERN.fullmatch(symbol):
                    return symbol
        except Exception:
            return None
        return None


__all__ = [
    "SCALABLE_PORTFOLIO_ID",
    "ScalableCliClient",
    "ScalableIntegrationError",
    "ScalableIntegrationService",
]


