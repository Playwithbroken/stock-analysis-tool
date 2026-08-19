import argparse
from contextlib import closing
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = PROJECT_ROOT / "rollback" / "last-known-good.json"


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None, stdout=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=stdout is None,
        check=True,
    )


def resolve_commit(reference: str) -> str:
    result = run(["git", "rev-parse", f"{reference}^{{commit}}"], cwd=PROJECT_ROOT)
    return result.stdout.strip()


def export_commit(commit: str, destination: Path) -> None:
    archive = destination.parent / "rollback-source.tar"
    with archive.open("wb") as output:
        run(["git", "archive", "--format=tar", commit], cwd=PROJECT_ROOT, stdout=output)
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()
    with tarfile.open(archive, "r") as bundle:
        for member in bundle.getmembers():
            resolved = (destination / member.name).resolve()
            if destination_root not in resolved.parents and resolved != destination_root:
                raise RuntimeError(f"Unsafe archive member: {member.name}")
        bundle.extractall(destination, filter="data")


def database_snapshot(path: Path) -> dict:
    with closing(sqlite3.connect(path)) as connection:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        counts = {table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]) for table in tables}
        identity_row = connection.execute(
            "SELECT value FROM app_settings WHERE key = 'database_identity'"
        ).fetchone()
    return {
        "quick_check": quick_check,
        "tables": tables,
        "counts": counts,
        "identity": str(identity_row[0]) if identity_row else None,
    }


def create_current_database(path: Path) -> None:
    env = os.environ.copy()
    env.update({
        "APP_DATA_DIR": str(path.parent),
        "PORTFOLIO_DB_PATH": str(path),
        "TELEGRAM_ALERTS_ENABLED": "false",
    })
    probe = """
from src.storage import PortfolioManager
m = PortfolioManager()
p = m.create_portfolio('Rollback Drill')
m.add_holding(p['id'], 'AAPL', 2, buy_price=100, purchase_date='2026-08-01')
m.set_app_setting('rollback_drill_marker', 'preserve-me')
m.mark_signal_events_sent([{'event_key': 'rollback:drill', 'category': 'test', 'title': 'Rollback Drill'}])
"""
    run([sys.executable, "-c", probe], cwd=PROJECT_ROOT, env=env)


def create_consistent_copy(source: Path, destination: Path) -> None:
    with closing(sqlite3.connect(source)) as source_connection, closing(sqlite3.connect(destination)) as target_connection:
        source_connection.backup(target_connection)


def start_rollback_storage(source_root: Path, database: Path) -> None:
    env = os.environ.copy()
    env.update({
        "APP_DATA_DIR": str(database.parent),
        "PORTFOLIO_DB_PATH": str(database),
        "TELEGRAM_ALERTS_ENABLED": "false",
    })
    run(
        [sys.executable, "-c", "from src.storage import PortfolioManager; PortfolioManager()"],
        cwd=source_root,
        env=env,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-destructive rollback compatibility and recovery-time drill")
    parser.add_argument("--target-file", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--last-good", help="Override the commit in the target file")
    parser.add_argument("--rto-seconds", type=float, help="Override the local drill RTO")
    parser.add_argument("--report", type=Path, help="Also write the JSON report to this path")
    args = parser.parse_args()

    started = time.monotonic()
    target = json.loads(args.target_file.read_text(encoding="utf-8"))
    requested_ref = args.last_good or str(target["commit"])
    commit = resolve_commit(requested_ref)
    head = resolve_commit("HEAD")
    rto_seconds = float(args.rto_seconds or target.get("local_drill_rto_seconds", 120))

    with tempfile.TemporaryDirectory(prefix="rollback-drill-") as temp_name:
        temp = Path(temp_name)
        current_db = temp / "current.db"
        rollback_db = temp / "rollback.db"
        source_root = temp / "source"
        create_current_database(current_db)
        create_consistent_copy(current_db, rollback_db)
        before = database_snapshot(rollback_db)
        export_commit(commit, source_root)
        start_rollback_storage(source_root, rollback_db)
        after = database_snapshot(rollback_db)

    elapsed = round(time.monotonic() - started, 3)
    compatible = (
        before["quick_check"] == "ok"
        and after["quick_check"] == "ok"
        and before["identity"] == after["identity"]
        and before["tables"] == after["tables"]
        and before["counts"] == after["counts"]
    )
    report = {
        "schema": "rollback-drill-report.v1",
        "status": "passed" if compatible and elapsed <= rto_seconds else "failed",
        "current_head": head,
        "last_known_good": commit,
        "database_compatible": compatible,
        "identity_preserved": before["identity"] == after["identity"],
        "tables_preserved": before["tables"] == after["tables"],
        "row_counts_preserved": before["counts"] == after["counts"],
        "quick_check_before": before["quick_check"],
        "quick_check_after": after["quick_check"],
        "table_count": len(after["tables"]),
        "elapsed_seconds": elapsed,
        "rto_seconds": rto_seconds,
        "within_rto": elapsed <= rto_seconds,
        "temporary_environment_removed": True,
        "production_mutated": False,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
