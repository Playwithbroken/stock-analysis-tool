"""Contract checks for the Scalable Capital read-only integration."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from unittest.mock import patch

from src.scalable_integration_service import (
    SCALABLE_PORTFOLIO_ID,
    ScalableCliClient,
    ScalableIntegrationError,
    ScalableIntegrationService,
)


class FakeCli:
    def __init__(self):
        self.commands = []
        self.quote_isins = []
        self.news_isins = []
        self.invested_value = "150.00"

    def resolved_executable(self):
        return "/verified/official/sc"

    def run(self, command):
        self.commands.append(command)
        if command == "holdings":
            return {
                "account_id": "secret-account-id",
                "portfolio_id": "secret-portfolio-id",
                "count": 2,
                "items": [
                    {
                        "isin": "US0378331005",
                        "name": "Apple Inc.",
                        "security_type": "STOCK",
                        "quantity": "1.5",
                        "pending_quantity": "0",
                        "blocked_quantity": "0",
                        "fifo_price": "80.00",
                        "valuation": "120.00",
                        "valuation_currency": "EUR",
                        "quote_mid_price": "80.00",
                        "quote_currency": "EUR",
                        "quote_timestamp_utc": "2026-08-26T08:00:00Z",
                        "quote_is_outdated": False,
                    },
                    {
                        "isin": "IE00B4L5Y983",
                        "name": "iShares Core MSCI World",
                        "security_type": "ETF",
                        "quantity": "0.25",
                        "fifo_price": "100.00",
                        "valuation": "30.00",
                        "valuation_currency": "EUR",
                        "quote_mid_price": "120.00",
                        "quote_currency": "EUR",
                        "quote_timestamp_utc": "2026-08-26T08:00:00Z",
                        "quote_is_outdated": False,
                    },
                ],
            }
        if command == "overview":
            return {
                "account_id": "secret-account-id",
                "portfolio_id": "secret-portfolio-id",
                "valuation": {"total": "175.00", "securities": self.invested_value, "crypto": "0"},
                "timestamps": {
                    "valuation_timestamp_utc": "2026-08-26T08:00:01Z",
                    "inventory_timestamp_utc": "2026-08-26T08:00:00Z",
                },
            }
        if command == "transactions":
            return {
                "account_id": "secret-account-id",
                "portfolio_id": "secret-portfolio-id",
                "items": [
                    {
                        "id": "raw-provider-transaction-id",
                        "isin": "US0378331005",
                        "side": "BUY",
                        "type": "SECURITY_TRANSACTION",
                        "summary_type": "BUY",
                        "quantity": "1.5",
                        "amount": "-120.00",
                        "currency": "EUR",
                        "status": "SETTLED",
                        "last_event_datetime": "2026-08-26T08:00:00Z",
                    }
                ],
            }
        raise AssertionError(f"unexpected command: {command}")

    def quote(self, isin):
        self.quote_isins.append(isin)
        mid = "80.00" if isin == "US0378331005" else "120.00"
        return {
            "account_id": "secret-account-id",
            "portfolio_id": "secret-portfolio-id",
            "result": {
                "isin": isin,
                "quote_bid_price": str(float(mid) - 0.1),
                "quote_ask_price": str(float(mid) + 0.1),
                "quote_mid_price": mid,
                "quote_currency": "EUR",
                "quote_timestamp_utc": "2026-08-26T08:00:00Z",
                "quote_is_outdated": False,
            },
        }

    def security_news(self, isin, locale="de_DE"):
        self.news_isins.append(isin)
        return {
            "isin": isin,
            "locale": locale,
            "summary": {"headline": f"News for {isin}"},
            "sources": [{"name": "provider"}],
        }


def init_portfolio_schema(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE portfolios (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE holdings (
            id TEXT PRIMARY KEY,
            portfolio_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            buy_price REAL,
            purchase_date TEXT
        );
        CREATE TABLE decision_audit_log (
            event_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def main() -> None:
    resolver_map = {"US0378331005": "AAPL", "IE00B4L5Y983": "EUNL.DE"}
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "portfolios.db")
        init_portfolio_schema(db_path)
        fake_cli = FakeCli()
        with patch.dict(os.environ, {"SCALABLE_INTEGRATION_ENABLED": "true"}, clear=False):
            service = ScalableIntegrationService(
                db_path,
                cli_client=fake_cli,
                ticker_resolver=lambda isin, _name: resolver_map.get(isin),
            )
            result = service.sync()

            assert fake_cli.commands == ["holdings", "overview"], fake_cli.commands
            assert result["status"]["status"] == "ok", result
            assert result["status"]["position_count"] == 2, result
            assert result["status"]["read_only"] is True, result
            assert result["status"]["auto_sync_enabled"] is True, result
            assert result["status"]["snapshot_stale"] is False, result
            serialized = json.dumps(result)
            assert "secret-account-id" not in serialized, serialized
            assert "secret-portfolio-id" not in serialized, serialized

            conn = sqlite3.connect(db_path)
            imported = conn.execute(
                "SELECT ticker, shares, buy_price FROM holdings WHERE portfolio_id = ? ORDER BY ticker",
                (SCALABLE_PORTFOLIO_ID,),
            ).fetchall()
            before_hash = conn.execute(
                "SELECT payload_sha256 FROM scalable_sync_state WHERE singleton_id = 1"
            ).fetchone()[0]
            conn.close()
            assert imported == [("AAPL", 1.5, 80.0), ("EUNL.DE", 0.25, 100.0)], imported
            analysis = service.portfolio_analysis()
            assert analysis["summary"]["total_value"] == 150.0, analysis
            assert analysis["summary"]["source"] == "scalable_cli_reconciled", analysis
            assert analysis["summary"]["currency"] == "EUR", analysis

            context_refresh = service.refresh_market_context()
            assert context_refresh["quotes_refreshed"] == 2, context_refresh
            assert context_refresh["news_refreshed"] == 2, context_refresh
            transaction_refresh = service.refresh_transactions()
            assert transaction_refresh["imported"] == 1, transaction_refresh
            context = service.market_context_snapshot()
            assert len(context["quotes"]) == 2, context
            assert len(context["news"]) == 2, context
            assert len(context["transactions"]) == 1, context
            serialized_context = json.dumps(context)
            assert "raw-provider-transaction-id" not in serialized_context, serialized_context
            assert len(context["transactions"][0]["transaction_hash"]) == 64, context
            assert service.refresh_transactions()["status"] == "cached"

            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO decision_audit_log (event_type, created_at, payload_json) VALUES (?, ?, ?)",
                (
                    "scalable_decision_report",
                    "2026-08-25T08:00:00+00:00",
                    json.dumps({"decisions": [{"ticker": "AAPL", "action": "AUFSTOCKEN_PRUEFEN", "score": 93}]}),
                ),
            )
            conn.commit()
            conn.close()
            feedback = service.transaction_feedback()
            assert feedback["counts"]["aligned"] == 1, feedback
            assert feedback["alignment_rate_pct"] == 100.0, feedback
            assert feedback["automatic_rule_changes"] is False, feedback

            def resolver_must_not_run(_isin, _name):
                raise AssertionError("verified ticker mappings must be reused on later syncs")

            service.ticker_resolver = resolver_must_not_run
            cached_result = service.sync()
            assert {item["resolution_method"] for item in cached_result["positions"]} == {"snapshot"}

            service._sync_lock.acquire()
            try:
                try:
                    service.sync()
                    raise AssertionError("overlapping sync must be blocked")
                except ScalableIntegrationError as exc:
                    assert exc.code == "sync_in_progress", exc.code
            finally:
                service._sync_lock.release()
            assert service.status()["status"] == "ok"

            fake_cli.invested_value = "999.00"
            try:
                service.sync()
                raise AssertionError("reconciliation mismatch must fail")
            except ScalableIntegrationError as exc:
                assert exc.code == "reconciliation_failed", exc.code

            conn = sqlite3.connect(db_path)
            after_hash = conn.execute(
                "SELECT payload_sha256 FROM scalable_sync_state WHERE singleton_id = 1"
            ).fetchone()[0]
            still_imported = conn.execute(
                "SELECT COUNT(*) FROM holdings WHERE portfolio_id = ?", (SCALABLE_PORTFOLIO_ID,)
            ).fetchone()[0]
            last_success = conn.execute(
                "SELECT last_success_at FROM scalable_sync_state WHERE singleton_id = 1"
            ).fetchone()[0]
            conn.close()
            assert before_hash == after_hash
            assert still_imported == 2
            assert last_success

    cli = ScalableCliClient(executable="definitely-not-used")
    try:
        cli.run("broker.trade.buy")
        raise AssertionError("trade command must be blocked")
    except ScalableIntegrationError as exc:
        assert exc.code == "command_blocked", exc.code

    with patch.object(cli, "_run_argv", return_value={}) as run_argv:
        cli.quote("US0378331005")
        run_argv.assert_called_once_with(("broker", "quote", "--isin", "US0378331005", "--json"))
    for invalid_isin in ("", "US0378331005;trade", "../../secret"):
        try:
            cli.quote(invalid_isin)
            raise AssertionError("invalid quote argument must be blocked")
        except ScalableIntegrationError as exc:
            assert exc.code == "argument_blocked", exc.code
    try:
        cli.security_news("US0378331005", "de_DE;whoami")
        raise AssertionError("invalid locale must be blocked")
    except ScalableIntegrationError as exc:
        assert exc.code == "argument_blocked", exc.code

    print("Scalable read-only contract: OK")


if __name__ == "__main__":
    main()


