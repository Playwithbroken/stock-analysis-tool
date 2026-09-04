import sqlite3
import os
import uuid
import json
import hashlib
import tempfile
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

from src.advisory_service import merge_workspace_profile

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
DATA_DIR = os.path.abspath(os.getenv('APP_DATA_DIR', DEFAULT_DATA_DIR))
DB_PATH = os.path.abspath(os.getenv('PORTFOLIO_DB_PATH', os.path.join(DATA_DIR, 'portfolios.db')))
try:
    SQLITE_BUSY_TIMEOUT_MS = max(250, int(os.getenv('SQLITE_BUSY_TIMEOUT_MS', '3000')))
except ValueError:
    SQLITE_BUSY_TIMEOUT_MS = 3000


def _connect_db(*, row_factory: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.execute(f'PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}')
    conn.execute('PRAGMA foreign_keys = ON')
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn


def get_persistence_status() -> Dict[str, Any]:
    railway_runtime = bool(os.getenv('RAILWAY_PROJECT_ID') or os.getenv('RAILWAY_ENVIRONMENT_ID'))
    volume_name = (os.getenv('RAILWAY_VOLUME_NAME') or '').strip()
    raw_mount_path = (os.getenv('RAILWAY_VOLUME_MOUNT_PATH') or '').strip()
    volume_mount_path = os.path.abspath(raw_mount_path) if raw_mount_path else ''
    volume_attached = bool(volume_name and volume_mount_path)
    try:
        database_on_volume = bool(volume_mount_path and os.path.commonpath([DB_PATH, volume_mount_path]) == volume_mount_path)
    except ValueError:
        database_on_volume = False
    return {
        "railway_runtime": railway_runtime,
        "volume_name": volume_name,
        "volume_mount_path": volume_mount_path,
        "volume_attached": volume_attached,
        "database_on_volume": database_on_volume,
        "persistence_ready": not railway_runtime or (volume_attached and database_on_volume),
    }


def get_database_status() -> Dict[str, Any]:
    db_dir = os.path.dirname(DB_PATH)
    persistence = get_persistence_status()
    exists = os.path.exists(DB_PATH)
    writable = False
    write_probe_error = None
    if os.path.isdir(db_dir):
        try:
            with tempfile.NamedTemporaryFile(prefix=".write-probe-", dir=db_dir, delete=True) as probe:
                probe.write(b"ok")
                probe.flush()
            writable = True
        except Exception as exc:
            write_probe_error = exc.__class__.__name__
    quick_check = None
    error = None
    identity = None
    initialized_at = None
    counts: Dict[str, int] = {}
    if exists:
        try:
            conn = _connect_db()
            cursor = conn.cursor()
            cursor.execute('PRAGMA quick_check')
            row = cursor.fetchone()
            quick_check = row[0] if row else None
            cursor.execute("SELECT key, value FROM app_settings WHERE key IN ('database_identity', 'database_initialized_at')")
            settings = {key: value for key, value in cursor.fetchall()}
            identity = settings.get('database_identity')
            initialized_at = settings.get('database_initialized_at')
            for label, table in {
                'portfolios': 'portfolios',
                'holdings': 'holdings',
                'paper_trades': 'paper_trades',
                'forecasts': 'signal_forecasts',
                'forecast_outcomes': 'signal_forecast_outcomes',
                'deliveries': 'sent_signal_events',
                'paper_learning_attributions': 'paper_learning_attributions',
                'paper_learning_hypotheses': 'paper_learning_hypotheses',
                'paper_learning_rules': 'paper_learning_rules',
                'paper_learning_rule_history': 'paper_learning_rule_history',
                'paper_learning_runs': 'paper_learning_runs',
                'market_events': 'market_events',
                'news_events': 'news_events',
                'broker_orders': 'broker_orders',
                'broker_order_events': 'broker_order_events',
                'latency_samples': 'latency_samples',
                'integration_incidents': 'integration_incidents',
            }.items():
                cursor.execute(f'SELECT COUNT(*) FROM {table}')
                counts[label] = int((cursor.fetchone() or [0])[0] or 0)
            conn.close()
        except Exception as exc:
            error = exc.__class__.__name__
    return {
        "path": DB_PATH,
        "directory": db_dir,
        "directory_exists": os.path.isdir(db_dir),
        "exists": exists,
        "size_bytes": os.path.getsize(DB_PATH) if exists else 0,
        "writable": writable,
        "write_probe_error": write_probe_error,
        "quick_check": quick_check,
        "error": error,
        "identity": identity,
        "initialized_at": initialized_at,
        "counts": counts,
        **persistence,
    }

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = _connect_db()
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA synchronous = NORMAL')
    cursor = conn.cursor()
    
    # Portfolios table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS portfolios (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    ''')
    
    # Holdings table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS holdings (
        id TEXT PRIMARY KEY,
        portfolio_id TEXT NOT NULL,
        ticker TEXT NOT NULL,
        shares REAL NOT NULL,
        buy_price REAL,
        purchase_date TEXT,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios (id) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS signal_watch_items (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        value TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(kind, value)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sent_signal_events (
        event_key TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS price_alerts (
        id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,
        target_price REAL NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        cooldown_minutes INTEGER NOT NULL DEFAULT 5,
        last_triggered_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS paper_trades (
        id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        asset_class TEXT NOT NULL,
        direction TEXT NOT NULL,
        setup_type TEXT NOT NULL,
        thesis TEXT,
        entry_price REAL NOT NULL,
        stop_price REAL,
        target_price REAL,
        quantity REAL NOT NULL,
        confidence_score REAL,
        leverage REAL DEFAULT 1,
        opened_at TEXT NOT NULL,
        closed_at TEXT,
        closed_price REAL,
        status TEXT NOT NULL,
        notes TEXT,
        exit_reason TEXT,
        lessons_learned TEXT,
        underlying_entry_price REAL,
        option_type TEXT,
        contract_multiplier REAL DEFAULT 1,
        max_holding_days INTEGER,
        error_tag TEXT,
        trade_ticket_json TEXT NOT NULL DEFAULT '{}'
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS paper_trade_outcomes (
        id TEXT PRIMARY KEY,
        trade_id TEXT NOT NULL,
        horizon_hours INTEGER NOT NULL,
        due_at TEXT NOT NULL,
        status TEXT NOT NULL,
        result TEXT,
        checked_at TEXT,
        check_price REAL,
        performance_pct REAL,
        benchmark_symbol TEXT,
        benchmark_entry_price REAL,
        benchmark_check_price REAL,
        benchmark_return_pct REAL,
        active_return_pct REAL,
        notes TEXT,
        error_tag TEXT,
        UNIQUE(trade_id, horizon_hours),
        FOREIGN KEY (trade_id) REFERENCES paper_trades (id) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS signal_forecasts (
        id TEXT PRIMARY KEY,
        signal_key TEXT UNIQUE NOT NULL,
        symbol TEXT NOT NULL,
        direction TEXT,
        setup_type TEXT,
        session_label TEXT,
        source_label TEXT,
        thesis TEXT,
        trigger TEXT,
        invalidation TEXT,
        confidence REAL,
        rank_score REAL,
        expected_move TEXT,
        entry_price REAL,
        forecast_time TEXT NOT NULL,
        metadata_json TEXT,
        created_at TEXT NOT NULL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS signal_forecast_outcomes (
        id TEXT PRIMARY KEY,
        forecast_id TEXT NOT NULL,
        horizon_hours INTEGER NOT NULL,
        due_at TEXT NOT NULL,
        status TEXT NOT NULL,
        result TEXT,
        checked_at TEXT,
        exit_price REAL,
        performance_pct REAL,
        notes TEXT,
        UNIQUE(forecast_id, horizon_hours),
        FOREIGN KEY (forecast_id) REFERENCES signal_forecasts (id) ON DELETE CASCADE
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS decision_audit_log (
        id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        subject TEXT NOT NULL,
        decision TEXT NOT NULL,
        data_as_of TEXT,
        source_status TEXT NOT NULL,
        sources_json TEXT NOT NULL DEFAULT '[]',
        model_version TEXT NOT NULL,
        rule_version TEXT NOT NULL,
        user_action TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        previous_hash TEXT NOT NULL,
        event_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_decision_audit_created ON decision_audit_log(created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_decision_audit_subject ON decision_audit_log(subject, created_at DESC)')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS paper_learning_attributions (
        trade_id TEXT PRIMARY KEY,
        schema_version TEXT NOT NULL,
        outcome_quality TEXT NOT NULL,
        process_quality TEXT NOT NULL,
        primary_error TEXT,
        secondary_errors_json TEXT NOT NULL DEFAULT '[]',
        metrics_json TEXT NOT NULL DEFAULT '{}',
        evidence_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (trade_id) REFERENCES paper_trades (id) ON DELETE CASCADE
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS paper_learning_hypotheses (
        id TEXT PRIMARY KEY,
        fingerprint TEXT NOT NULL UNIQUE,
        strategy_id TEXT,
        segment_json TEXT NOT NULL DEFAULT '{}',
        statement TEXT NOT NULL,
        evidence_json TEXT NOT NULL DEFAULT '{}',
        proposed_rule_json TEXT NOT NULL DEFAULT '{}',
        uncertainty TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS paper_learning_runs (
        run_id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        checked_at TEXT,
        duration_ms REAL,
        result_json TEXT NOT NULL DEFAULT '{}',
        error_type TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS paper_learning_rules (
        id TEXT PRIMARY KEY,
        hypothesis_id TEXT,
        version INTEGER NOT NULL,
        status TEXT NOT NULL,
        rule_json TEXT NOT NULL DEFAULT '{}',
        baseline_json TEXT NOT NULL DEFAULT '{}',
        evaluation_json TEXT NOT NULL DEFAULT '{}',
        started_at TEXT,
        ended_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(hypothesis_id, version),
        FOREIGN KEY (hypothesis_id) REFERENCES paper_learning_hypotheses (id) ON DELETE SET NULL
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS paper_learning_rule_history (
        id TEXT PRIMARY KEY,
        rule_id TEXT NOT NULL,
        action TEXT NOT NULL,
        from_status TEXT,
        to_status TEXT,
        before_json TEXT NOT NULL DEFAULT '{}',
        after_json TEXT NOT NULL DEFAULT '{}',
        reason TEXT NOT NULL,
        audit_event_id TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (rule_id) REFERENCES paper_learning_rules (id) ON DELETE CASCADE
    )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_paper_learning_hypothesis_status ON paper_learning_hypotheses(status, updated_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_paper_learning_rule_status ON paper_learning_rules(status, updated_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_paper_learning_rule_history_rule ON paper_learning_rule_history(rule_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_paper_learning_rule_history_created ON paper_learning_rule_history(created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_paper_learning_run_started ON paper_learning_runs(started_at DESC)')

    # Provider-neutral, append-only evidence for real-time market and broker integrations.
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS market_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        event_id TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        event_type TEXT NOT NULL,
        feed TEXT NOT NULL,
        asset_class TEXT NOT NULL,
        symbol TEXT NOT NULL,
        exchange TEXT,
        provider_timestamp TEXT NOT NULL,
        received_at TEXT NOT NULL,
        normalized_at TEXT NOT NULL,
        sequence INTEGER,
        bid REAL,
        ask REAL,
        last REAL,
        size REAL,
        quality_json TEXT NOT NULL DEFAULT '{}',
        source_payload_hash TEXT,
        source_payload_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(provider, event_id)
    )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_events_symbol_time ON market_events(symbol, received_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_events_provider_time ON market_events(provider, received_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_events_type_time ON market_events(event_type, received_at DESC)')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS news_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        event_id TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        publisher TEXT NOT NULL,
        headline TEXT NOT NULL,
        source_url TEXT NOT NULL,
        published_at TEXT NOT NULL,
        received_at TEXT NOT NULL,
        normalized_at TEXT NOT NULL,
        symbols_json TEXT NOT NULL DEFAULT '[]',
        version INTEGER NOT NULL DEFAULT 1,
        correction_status TEXT NOT NULL DEFAULT 'original',
        source_payload_hash TEXT,
        source_payload_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(provider, event_id, version)
    )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_events_published ON news_events(published_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_events_provider_time ON news_events(provider, received_at DESC)')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS signal_decisions (
        id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        decision TEXT NOT NULL,
        execution_mode TEXT NOT NULL,
        signal_version TEXT NOT NULL,
        rule_version TEXT NOT NULL,
        risk_snapshot_id TEXT,
        input_event_ids_json TEXT NOT NULL DEFAULT '[]',
        data_age_ms REAL,
        rejection_reasons_json TEXT NOT NULL DEFAULT '[]',
        decision_payload_json TEXT NOT NULL DEFAULT '{}',
        decision_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_signal_decisions_symbol_time ON signal_decisions(symbol, decision_at DESC)')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS broker_orders (
        client_order_id TEXT PRIMARY KEY,
        broker_order_id TEXT,
        provider TEXT NOT NULL,
        account_mode TEXT NOT NULL CHECK(account_mode = 'paper'),
        account_id_hash TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        order_type TEXT NOT NULL,
        time_in_force TEXT NOT NULL,
        requested_quantity REAL NOT NULL,
        limit_price REAL,
        stop_price REAL,
        status TEXT NOT NULL,
        request_hash TEXT NOT NULL UNIQUE,
        signal_decision_id TEXT,
        submitted_at TEXT,
        filled_quantity REAL NOT NULL DEFAULT 0,
        filled_avg_price REAL,
        last_event_at TEXT,
        request_id TEXT,
        raw_order_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (signal_decision_id) REFERENCES signal_decisions (id) ON DELETE SET NULL
    )
    ''')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_broker_orders_provider_id ON broker_orders(provider, broker_order_id) WHERE broker_order_id IS NOT NULL')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_broker_orders_status_time ON broker_orders(status, updated_at DESC)')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS broker_order_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        event_id TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        client_order_id TEXT NOT NULL,
        broker_order_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        account_mode TEXT NOT NULL CHECK(account_mode = 'paper'),
        symbol TEXT NOT NULL,
        provider_timestamp TEXT NOT NULL,
        received_at TEXT NOT NULL,
        filled_quantity REAL NOT NULL DEFAULT 0,
        fill_price REAL,
        reason TEXT,
        source_payload_hash TEXT,
        source_payload_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(provider, event_id),
        FOREIGN KEY (client_order_id) REFERENCES broker_orders (client_order_id) ON DELETE CASCADE
    )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_broker_order_events_order_time ON broker_order_events(client_order_id, received_at ASC)')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS broker_positions_snapshots (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        account_mode TEXT NOT NULL CHECK(account_mode = 'paper'),
        account_id_hash TEXT NOT NULL,
        positions_json TEXT NOT NULL DEFAULT '[]',
        cash REAL,
        equity REAL,
        local_state_hash TEXT,
        broker_state_hash TEXT NOT NULL,
        reconciliation_status TEXT NOT NULL,
        orders_json TEXT NOT NULL DEFAULT '[]',
        differences_json TEXT NOT NULL DEFAULT '[]',
        captured_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_broker_positions_time ON broker_positions_snapshots(provider, captured_at DESC)')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS latency_samples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        correlation_id TEXT,
        provider TEXT NOT NULL,
        service TEXT NOT NULL,
        segment TEXT NOT NULL,
        latency_ms REAL NOT NULL,
        status TEXT NOT NULL,
        symbol TEXT,
        observed_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_latency_samples_segment_time ON latency_samples(segment, observed_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_latency_samples_provider_time ON latency_samples(provider, observed_at DESC)')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS integration_incidents (
        id TEXT PRIMARY KEY,
        provider TEXT,
        component TEXT NOT NULL,
        incident_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        status TEXT NOT NULL,
        summary TEXT NOT NULL,
        details_json TEXT NOT NULL DEFAULT '{}',
        opened_at TEXT NOT NULL,
        resolved_at TEXT,
        updated_at TEXT NOT NULL
    )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_integration_incidents_status_time ON integration_incidents(status, opened_at DESC)')
    for broker_order_column, broker_order_type in (
        ("filled_quantity", "REAL NOT NULL DEFAULT 0"),
        ("filled_avg_price", "REAL"),
        ("last_event_at", "TEXT"),
        ("request_id", "TEXT"),
        ("raw_order_json", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        try:
            cursor.execute(f"ALTER TABLE broker_orders ADD COLUMN {broker_order_column} {broker_order_type}")
        except sqlite3.OperationalError:
            pass
    for snapshot_column, snapshot_type in (
        ("orders_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("differences_json", "TEXT NOT NULL DEFAULT '[]'"),
    ):
        try:
            cursor.execute(f"ALTER TABLE broker_positions_snapshots ADD COLUMN {snapshot_column} {snapshot_type}")
        except sqlite3.OperationalError:
            pass
    try:
        cursor.execute('ALTER TABLE holdings ADD COLUMN purchase_date TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE sent_signal_events ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE paper_trades ADD COLUMN exit_reason TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE paper_trades ADD COLUMN lessons_learned TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE paper_trades ADD COLUMN underlying_entry_price REAL')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE paper_trades ADD COLUMN option_type TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE paper_trades ADD COLUMN contract_multiplier REAL DEFAULT 1')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE paper_trades ADD COLUMN max_holding_days INTEGER')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE paper_trades ADD COLUMN error_tag TEXT')
    except sqlite3.OperationalError:
        pass
    for benchmark_column, benchmark_type in (
        ("benchmark_symbol", "TEXT"),
        ("benchmark_entry_price", "REAL"),
        ("benchmark_check_price", "REAL"),
        ("benchmark_return_pct", "REAL"),
        ("active_return_pct", "REAL"),
    ):
        try:
            cursor.execute(f"ALTER TABLE paper_trade_outcomes ADD COLUMN {benchmark_column} {benchmark_type}")
        except sqlite3.OperationalError:
            pass
    try:
        cursor.execute("ALTER TABLE paper_trades ADD COLUMN trade_ticket_json TEXT NOT NULL DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE price_alerts ADD COLUMN cooldown_minutes INTEGER NOT NULL DEFAULT 5')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE price_alerts ADD COLUMN last_triggered_at TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE price_alerts ADD COLUMN created_at TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE price_alerts ADD COLUMN updated_at TEXT')
    except sqlite3.OperationalError:
        pass

    initialized_at = datetime.now().isoformat()
    cursor.execute(
        'INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)',
        ('database_identity', str(uuid.uuid4()), initialized_at),
    )
    cursor.execute(
        'INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)',
        ('database_initialized_at', initialized_at, initialized_at),
    )
    
    conn.commit()
    conn.close()

class PortfolioManager:
    def __init__(self):
        init_db()

    def _normalize_purchase_date(self, value: Optional[str]) -> Optional[str]:
        raw = str(value or '').strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw[:10]).date().isoformat()
        except Exception:
            return None

    def _merge_purchase_date(
        self,
        existing_purchase_date: Optional[str],
        new_purchase_date: Optional[str],
        existing_shares: float,
        added_shares: float,
    ) -> Optional[str]:
        existing_norm = self._normalize_purchase_date(existing_purchase_date)
        new_norm = self._normalize_purchase_date(new_purchase_date)
        if existing_norm and new_norm and existing_shares > 0 and added_shares > 0:
            try:
                existing_dt = datetime.fromisoformat(existing_norm)
                new_dt = datetime.fromisoformat(new_norm)
                weighted_ts = (
                    existing_dt.timestamp() * existing_shares
                    + new_dt.timestamp() * added_shares
                ) / (existing_shares + added_shares)
                return datetime.fromtimestamp(weighted_ts).date().isoformat()
            except Exception:
                return existing_norm or new_norm
        return new_norm or existing_norm

    def _normalize_ticker(self, ticker: str) -> str:
        clean_ticker = (ticker or "").strip().upper().replace(" ", "")
        if clean_ticker in {"BRK.B", "BRKB"}:
            return "BRK-B"
        if clean_ticker == "BTC":
            return "BTC-USD"
        if clean_ticker == "ETH":
            return "ETH-USD"
        if clean_ticker == "SOL":
            return "SOL-USD"
        return clean_ticker

    def create_portfolio(self, name: str) -> Dict[str, Any]:
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("Portfolio name is required")

        portfolio_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        
        conn = _connect_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO portfolios (id, name, created_at) VALUES (?, ?, ?)',
                       (portfolio_id, clean_name, created_at))
        if cursor.rowcount != 1:
            conn.rollback()
            conn.close()
            raise RuntimeError("Portfolio could not be saved")
        conn.commit()
        conn.close()
        
        return {"id": portfolio_id, "name": clean_name, "createdAt": created_at, "holdings": []}

    def get_portfolios(self) -> List[Dict[str, Any]]:
        conn = _connect_db(row_factory=True)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM portfolios ORDER BY datetime(created_at) DESC')
        portfolios = [dict(row) for row in cursor.fetchall()]
        
        for p in portfolios:
            cursor.execute(
                'SELECT ticker, shares, buy_price as buyPrice, purchase_date as purchaseDate FROM holdings WHERE portfolio_id = ?',
                (p['id'],),
            )
            p['holdings'] = [dict(row) for row in cursor.fetchall()]
            # Rename for frontend compatibility
            p['createdAt'] = p.pop('created_at')
            
        conn.close()
        return portfolios

    def delete_portfolio(self, portfolio_id: str):
        conn = _connect_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM portfolios WHERE id = ?', (portfolio_id,))
        cursor.execute('DELETE FROM holdings WHERE portfolio_id = ?', (portfolio_id,))
        conn.commit()
        conn.close()

    def add_holding(
        self,
        portfolio_id: str,
        ticker: str,
        shares: float,
        buy_price: Optional[float] = None,
        purchase_date: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        clean_ticker = self._normalize_ticker(ticker)
        if not clean_ticker:
            raise ValueError("Ticker is required")
        if shares is None or float(shares) <= 0:
            raise ValueError("Shares must be greater than zero")

        holding_id = str(uuid.uuid4())
        conn = _connect_db()
        cursor = conn.cursor()
        normalized_purchase_date = self._normalize_purchase_date(purchase_date)

        cursor.execute('SELECT 1 FROM portfolios WHERE id = ?', (portfolio_id,))
        if cursor.fetchone() is None:
            conn.close()
            return None
        
        # Check if holding already exists for this ticker
        cursor.execute(
            'SELECT id, shares, buy_price, purchase_date FROM holdings WHERE portfolio_id = ? AND ticker = ?',
            (portfolio_id, clean_ticker),
        )
        existing = cursor.fetchone()
        
        if existing:
            existing_shares = float(existing[1] or 0)
            existing_buy_price = existing[2]
            existing_purchase_date = existing[3]
            new_shares = existing_shares + shares
            new_buy_price = existing_buy_price
            if new_shares > 0:
                if existing_buy_price is not None and buy_price is not None:
                    new_buy_price = (
                        (existing_shares * float(existing_buy_price)) + (shares * float(buy_price))
                    ) / new_shares
                elif buy_price is not None:
                    new_buy_price = buy_price
            merged_purchase_date = self._merge_purchase_date(
                existing_purchase_date,
                normalized_purchase_date,
                existing_shares,
                shares,
            )
            cursor.execute(
                'UPDATE holdings SET shares = ?, buy_price = ?, purchase_date = ? WHERE id = ?',
                (new_shares, new_buy_price, merged_purchase_date, existing[0]),
            )
        else:
            cursor.execute(
                'INSERT INTO holdings (id, portfolio_id, ticker, shares, buy_price, purchase_date) VALUES (?, ?, ?, ?, ?, ?)',
                (holding_id, portfolio_id, clean_ticker, shares, buy_price, normalized_purchase_date),
            )

        conn.commit()
        cursor.execute(
            'SELECT ticker, shares, buy_price as buyPrice, purchase_date as purchaseDate FROM holdings WHERE portfolio_id = ? AND ticker = ?',
            (portfolio_id, clean_ticker),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "ticker": row[0],
            "shares": row[1],
            "buyPrice": row[2],
            "purchaseDate": row[3],
        }

    def remove_holding(self, portfolio_id: str, ticker: str):
        conn = _connect_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM holdings WHERE portfolio_id = ? AND ticker = ?', (portfolio_id, self._normalize_ticker(ticker)))
        conn.commit()
        conn.close()

    def upsert_signal_forecast(
        self,
        forecast: Dict[str, Any],
        outcomes: List[Dict[str, Any]],
    ) -> bool:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT OR IGNORE INTO signal_forecasts (
                id, signal_key, symbol, direction, setup_type, session_label,
                source_label, thesis, trigger, invalidation, confidence,
                rank_score, expected_move, entry_price, forecast_time,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                forecast.get("id"),
                forecast.get("signal_key"),
                forecast.get("symbol"),
                forecast.get("direction"),
                forecast.get("setup_type"),
                forecast.get("session_label"),
                forecast.get("source_label"),
                forecast.get("thesis"),
                forecast.get("trigger"),
                forecast.get("invalidation"),
                forecast.get("confidence"),
                forecast.get("rank_score"),
                forecast.get("expected_move"),
                forecast.get("entry_price"),
                forecast.get("forecast_time"),
                forecast.get("metadata_json"),
                forecast.get("created_at"),
            ),
        )
        inserted = cursor.rowcount > 0
        for outcome in outcomes:
            cursor.execute(
                '''
                INSERT OR IGNORE INTO signal_forecast_outcomes (
                    id, forecast_id, horizon_hours, due_at, status,
                    result, checked_at, exit_price, performance_pct, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    outcome.get("id"),
                    outcome.get("forecast_id"),
                    outcome.get("horizon_hours"),
                    outcome.get("due_at"),
                    outcome.get("status"),
                    outcome.get("result"),
                    outcome.get("checked_at"),
                    outcome.get("exit_price"),
                    outcome.get("performance_pct"),
                    outcome.get("notes"),
                ),
            )
        conn.commit()
        conn.close()
        return inserted

    def list_due_signal_forecast_outcomes(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = _connect_db(row_factory=True)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT
                o.*,
                f.symbol,
                f.direction,
                f.setup_type,
                f.session_label,
                f.source_label,
                f.entry_price,
                f.confidence,
                f.forecast_time,
                f.thesis,
                f.trigger,
                f.invalidation
            FROM signal_forecast_outcomes o
            JOIN signal_forecasts f ON f.id = o.forecast_id
            WHERE o.status IN ('pending', 'pending_data') AND o.due_at <= ?
            ORDER BY o.due_at ASC
            LIMIT ?
            ''',
            (datetime.utcnow().isoformat(), int(limit)),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def update_signal_forecast_outcome(self, outcome_id: str, updates: Dict[str, Any]) -> None:
        allowed = {
            "status",
            "result",
            "checked_at",
            "exit_price",
            "performance_pct",
            "notes",
        }
        fields = [key for key in updates.keys() if key in allowed]
        if not fields:
            return
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        assignments = ", ".join(f"{field} = ?" for field in fields)
        values = [updates[field] for field in fields]
        values.append(outcome_id)
        cursor.execute(
            f"UPDATE signal_forecast_outcomes SET {assignments} WHERE id = ?",
            values,
        )
        conn.commit()
        conn.close()

    def list_signal_forecasts(self, limit: int = 200) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM signal_forecasts
            ORDER BY forecast_time DESC
            LIMIT ?
            ''',
            (int(limit),),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def list_signal_forecast_outcomes(self, limit: int = 800) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT
                o.*,
                f.symbol,
                f.direction,
                f.setup_type,
                f.session_label,
                f.source_label,
                f.confidence,
                f.forecast_time
            FROM signal_forecast_outcomes o
            JOIN signal_forecasts f ON f.id = o.forecast_id
            ORDER BY o.due_at DESC
            LIMIT ?
            ''',
            (int(limit),),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def update_holding(
        self,
        portfolio_id: str,
        ticker: str,
        shares: Optional[float] = None,
        buy_price: Optional[float] = None,
        purchase_date: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        conn = _connect_db(row_factory=True)
        cursor = conn.cursor()
        clean_ticker = self._normalize_ticker(ticker)
        cursor.execute(
            'SELECT id, ticker, shares, buy_price, purchase_date FROM holdings WHERE portfolio_id = ? AND ticker = ?',
            (portfolio_id, clean_ticker),
        )
        existing = cursor.fetchone()
        if not existing:
            conn.close()
            return None

        updated_shares = float(shares) if shares is not None else float(existing['shares'] or 0)
        updated_buy_price = buy_price if buy_price is not None else existing['buy_price']
        updated_purchase_date = (
            self._normalize_purchase_date(purchase_date)
            if purchase_date is not None
            else existing['purchase_date']
        )

        cursor.execute(
            'UPDATE holdings SET shares = ?, buy_price = ?, purchase_date = ? WHERE id = ?',
            (updated_shares, updated_buy_price, updated_purchase_date, existing['id']),
        )
        conn.commit()
        cursor.execute(
            'SELECT ticker, shares, buy_price as buyPrice, purchase_date as purchaseDate FROM holdings WHERE id = ?',
            (existing['id'],),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_signal_watch_items(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT id, kind, value, created_at FROM signal_watch_items ORDER BY kind, value')
        items = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for item in items:
            item['createdAt'] = item.pop('created_at')
        return items

    def add_signal_watch_item(self, kind: str, value: str) -> Dict[str, Any]:
        item_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        normalized_kind = (kind or '').strip().lower()
        normalized_value = (value or '').strip()
        if normalized_kind == 'ticker':
            normalized_value = normalized_value.upper()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR IGNORE INTO signal_watch_items (id, kind, value, created_at) VALUES (?, ?, ?, ?)',
            (item_id, normalized_kind, normalized_value, created_at)
        )
        conn.commit()
        conn.close()
        return {
            "id": item_id,
            "kind": normalized_kind,
            "value": normalized_value,
            "createdAt": created_at,
        }

    def remove_signal_watch_item(self, kind: str, value: str):
        normalized_kind = (kind or '').strip().lower()
        normalized_value = (value or '').strip()
        if normalized_kind == 'ticker':
            normalized_value = normalized_value.upper()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'DELETE FROM signal_watch_items WHERE kind = ? AND value = ?',
            (normalized_kind, normalized_value)
        )
        conn.commit()
        conn.close()

    def get_sent_signal_event_keys(self) -> set[str]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT event_key FROM sent_signal_events')
        rows = cursor.fetchall()
        conn.close()
        return {row[0] for row in rows}

    def claim_signal_event_delivery(
        self,
        event: Dict[str, Any],
        lease_seconds: int = 900,
    ) -> Optional[str]:
        """Atomically reserve an event key before an external notification is sent.

        A lease prevents parallel scheduler threads or replicas from delivering the
        same event. Expired claims can be recovered after a crashed worker.
        """
        event_key = str(event.get('event_key') or '').strip()
        if not event_key:
            raise ValueError('event_key is required')
        now = datetime.now()
        claim_id = str(uuid.uuid4())
        claim_metadata = {
            'delivery_state': 'sending',
            'delivery_claim_id': claim_id,
            'delivery_claimed_at': now.isoformat(),
            'delivery_claim_expires_at': (now + timedelta(seconds=max(60, int(lease_seconds)))).isoformat(),
        }
        conn = _connect_db()
        try:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(
                'SELECT metadata_json FROM sent_signal_events WHERE event_key = ?',
                (event_key,),
            ).fetchone()
            if row is not None:
                try:
                    metadata = json.loads(row[0] or '{}')
                except (TypeError, ValueError, json.JSONDecodeError):
                    metadata = {}
                expires_raw = str(metadata.get('delivery_claim_expires_at') or '')
                try:
                    expires_at = datetime.fromisoformat(expires_raw)
                except (TypeError, ValueError):
                    expires_at = None
                if metadata.get('delivery_state') != 'sending' or not expires_at or expires_at > now:
                    conn.rollback()
                    return None
                conn.execute(
                    '''UPDATE sent_signal_events
                       SET category = ?, title = ?, sent_at = ?, metadata_json = ?
                       WHERE event_key = ?''',
                    (
                        str(event.get('category') or 'notification_claim'),
                        str(event.get('title') or event.get('line') or event_key)[:500],
                        now.isoformat(),
                        json.dumps(claim_metadata, ensure_ascii=True),
                        event_key,
                    ),
                )
            else:
                conn.execute(
                    '''INSERT INTO sent_signal_events
                       (event_key, category, title, sent_at, metadata_json)
                       VALUES (?, ?, ?, ?, ?)''',
                    (
                        event_key,
                        str(event.get('category') or 'notification_claim'),
                        str(event.get('title') or event.get('line') or event_key)[:500],
                        now.isoformat(),
                        json.dumps(claim_metadata, ensure_ascii=True),
                    ),
                )
            conn.commit()
            return claim_id
        finally:
            conn.close()

    def complete_signal_event_delivery(
        self,
        event: Dict[str, Any],
        claim_id: str,
    ) -> bool:
        """Turn a matching in-flight claim into a permanent sent marker."""
        event_key = str(event.get('event_key') or '').strip()
        conn = _connect_db()
        try:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(
                'SELECT metadata_json FROM sent_signal_events WHERE event_key = ?',
                (event_key,),
            ).fetchone()
            if row is None:
                conn.rollback()
                return False
            try:
                current = json.loads(row[0] or '{}')
            except (TypeError, ValueError, json.JSONDecodeError):
                current = {}
            if current.get('delivery_state') != 'sending' or current.get('delivery_claim_id') != claim_id:
                conn.rollback()
                return False
            metadata = {
                'delivery_state': 'sent',
                'delivery_claim_id': claim_id,
                'delivery_completed_at': datetime.now().isoformat(),
                'period_ids': event.get('period_ids'),
                'snapshot_count': event.get('snapshot_count'),
            }
            conn.execute(
                '''UPDATE sent_signal_events
                   SET category = ?, title = ?, sent_at = ?, metadata_json = ?
                   WHERE event_key = ?''',
                (
                    str(event.get('category') or 'notification'),
                    str(event.get('title') or event.get('line') or event_key)[:500],
                    datetime.now().isoformat(),
                    json.dumps(metadata, ensure_ascii=True, default=str),
                    event_key,
                ),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def release_signal_event_delivery(self, event_key: str, claim_id: str) -> bool:
        """Release only the caller's in-flight claim after a failed delivery."""
        conn = _connect_db()
        try:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(
                'SELECT metadata_json FROM sent_signal_events WHERE event_key = ?',
                (str(event_key),),
            ).fetchone()
            if row is None:
                conn.rollback()
                return False
            try:
                current = json.loads(row[0] or '{}')
            except (TypeError, ValueError, json.JSONDecodeError):
                current = {}
            if current.get('delivery_state') != 'sending' or current.get('delivery_claim_id') != claim_id:
                conn.rollback()
                return False
            conn.execute('DELETE FROM sent_signal_events WHERE event_key = ?', (str(event_key),))
            conn.commit()
            return True
        finally:
            conn.close()

    def mark_signal_events_sent(self, events: List[Dict[str, Any]]):
        if not events:
            return
        import json
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        inserted_events = []
        for event in events:
            metadata = {
                key: event.get(key)
                for key in (
                    "event_type",
                    "severity",
                    "impact_score",
                    "country",
                    "region",
                    "affected_assets",
                    "source_quality",
                    "source_label",
                    "source_url",
                    "trigger",
                    "invalidation",
                )
                if event.get(key) not in (None, "", [], {})
            }
            cursor.execute(
                'INSERT OR IGNORE INTO sent_signal_events (event_key, category, title, sent_at, metadata_json) VALUES (?, ?, ?, ?, ?)',
                (
                    event['event_key'],
                    event['category'],
                    event['title'],
                    datetime.now().isoformat(),
                    json.dumps(metadata, ensure_ascii=True, default=str),
                )
            )
            if cursor.rowcount == 1:
                inserted_events.append((event, metadata))
        conn.commit()
        conn.close()
        for event, metadata in inserted_events:
            self.record_decision_audit(
                event_type="telegram_delivery",
                subject=str(event.get("event_key") or event.get("title") or "telegram-event"),
                decision=str(event.get("category") or "notify"),
                data_as_of=event.get("data_as_of") or event.get("published_at"),
                source_status=str(event.get("source_quality") or metadata.get("source_quality") or "not_provided"),
                sources=[
                    {
                        "label": event.get("source_label") or metadata.get("source_label"),
                        "url": event.get("source_url") or metadata.get("source_url"),
                    }
                ],
                model_version=str(event.get("model_version") or event.get("schema_version") or "telegram-event.v1"),
                rule_version=str(event.get("rule_version") or "telegram-delivery.v1"),
                user_action="telegram_sent",
                payload={"title": event.get("title"), "metadata": metadata},
            )

    def record_decision_audit(
        self,
        *,
        event_type: str,
        subject: str,
        decision: str,
        data_as_of: Optional[str],
        source_status: str,
        sources: List[Dict[str, Any]],
        model_version: str,
        rule_version: str,
        user_action: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        created_at = datetime.now().isoformat()
        audit_id = str(uuid.uuid4())
        normalized_sources = [item for item in (sources or []) if isinstance(item, dict)]
        sources_json = json.dumps(normalized_sources, ensure_ascii=True, sort_keys=True, default=str)
        payload_json = json.dumps(payload or {}, ensure_ascii=True, sort_keys=True, default=str)
        conn = _connect_db()
        try:
            conn.execute('BEGIN IMMEDIATE')
            previous_row = conn.execute(
                'SELECT event_hash FROM decision_audit_log ORDER BY rowid DESC LIMIT 1'
            ).fetchone()
            previous_hash = str(previous_row[0]) if previous_row else "GENESIS"
            hash_material = json.dumps(
                {
                    "id": audit_id,
                    "event_type": str(event_type),
                    "subject": str(subject),
                    "decision": str(decision),
                    "data_as_of": data_as_of,
                    "source_status": str(source_status),
                    "sources": normalized_sources,
                    "model_version": str(model_version),
                    "rule_version": str(rule_version),
                    "user_action": str(user_action),
                    "payload": payload or {},
                    "previous_hash": previous_hash,
                    "created_at": created_at,
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            event_hash = hashlib.sha256(hash_material.encode("utf-8")).hexdigest()
            conn.execute(
                '''
                INSERT INTO decision_audit_log (
                    id, event_type, subject, decision, data_as_of, source_status,
                    sources_json, model_version, rule_version, user_action,
                    payload_json, previous_hash, event_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    audit_id, str(event_type), str(subject), str(decision), data_as_of,
                    str(source_status), sources_json, str(model_version), str(rule_version),
                    str(user_action), payload_json, previous_hash, event_hash, created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "id": audit_id,
            "schema": "decision-audit.v1",
            "event_hash": event_hash,
            "previous_hash": previous_hash,
            "created_at": created_at,
        }

    def list_decision_audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = _connect_db(row_factory=True)
        rows = [
            dict(row)
            for row in conn.execute(
                'SELECT * FROM decision_audit_log ORDER BY rowid DESC LIMIT ?',
                (max(1, min(500, int(limit))),),
            ).fetchall()
        ]
        conn.close()
        for row in rows:
            row["sources"] = json.loads(row.pop("sources_json") or "[]")
            row["payload"] = json.loads(row.pop("payload_json") or "{}")
        return rows

    def verify_decision_audit_chain(self) -> Dict[str, Any]:
        conn = _connect_db(row_factory=True)
        rows = [dict(row) for row in conn.execute('SELECT * FROM decision_audit_log ORDER BY rowid ASC').fetchall()]
        conn.close()
        previous_hash = "GENESIS"
        for index, row in enumerate(rows):
            sources = json.loads(row["sources_json"] or "[]")
            payload = json.loads(row["payload_json"] or "{}")
            material = json.dumps(
                {
                    "id": row["id"], "event_type": row["event_type"], "subject": row["subject"],
                    "decision": row["decision"], "data_as_of": row["data_as_of"],
                    "source_status": row["source_status"], "sources": sources,
                    "model_version": row["model_version"], "rule_version": row["rule_version"],
                    "user_action": row["user_action"], "payload": payload,
                    "previous_hash": previous_hash, "created_at": row["created_at"],
                },
                ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str,
            )
            expected_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
            if row["previous_hash"] != previous_hash or row["event_hash"] != expected_hash:
                return {"status": "invalid", "valid": False, "entries": len(rows), "broken_index": index, "broken_id": row["id"]}
            previous_hash = row["event_hash"]
        return {"status": "ok", "valid": True, "entries": len(rows), "head_hash": previous_hash}

    def get_sent_signal_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            'SELECT event_key, category, title, sent_at, metadata_json FROM sent_signal_events ORDER BY sent_at DESC LIMIT ?',
            (limit,)
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for row in rows:
            try:
                row["metadata"] = json.loads(row.pop("metadata_json") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                row["metadata"] = {}
                row.pop("metadata_json", None)
        return rows

    def get_app_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        conn = _connect_db()
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM app_settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default

    def set_app_setting(self, key: str, value: str):
        conn = _connect_db()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            ''',
            (key, value, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    def get_workspace_profile(self) -> Dict[str, Any]:
        import json
        default = merge_workspace_profile(
            {
                "display_name": "Maurice",
                "email": "",
                "timezone": "Europe/Berlin",
                "browser_notifications": False,
                "theme": "premium-light",
                "onboarding_done": False,
            },
            {},
        )
        raw = self.get_app_setting("workspace_profile")
        if raw:
            try:
                return merge_workspace_profile(default, json.loads(raw))
            except json.JSONDecodeError:
                pass
        return default

    def save_workspace_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        import json
        current = self.get_workspace_profile()
        updated = merge_workspace_profile(current, profile)
        self.set_app_setting("workspace_profile", json.dumps(updated))
        return updated

    def get_signal_score_settings(self) -> Dict[str, Any]:
        import json
        raw = self.get_app_setting("signal_score_settings")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return {
            "weights": {
                "source": 0.35,
                "timing": 0.30,
                "conviction": 0.35,
            },
            "high_conviction_min_score": 75,
            "do_not_trade": {
                "max_political_delay_days": 45,
                "min_score_for_new_trade": 78,
                "min_score_for_leverage": 88,
                "block_crypto_leverage": True,
            },
        }

    def save_signal_score_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        import json
        current = self.get_signal_score_settings()
        current.update(settings or {})
        current["weights"] = {
            **self.get_signal_score_settings().get("weights", {}),
            **(settings or {}).get("weights", {}),
        }
        current["do_not_trade"] = {
            **self.get_signal_score_settings().get("do_not_trade", {}),
            **(settings or {}).get("do_not_trade", {}),
        }
        self.set_app_setting("signal_score_settings", json.dumps(current))
        return current

    def get_paper_autopilot_settings(self) -> Dict[str, Any]:
        import json
        default = {
            "mode": "aggressive_learning",
            "max_trades": 5,
            "strict_min_score": 88,
            "learning_min_score": 60,
            "aggressive_min_score": 52,
            "learning_risk_multiplier": 0.25,
            "aggressive_risk_multiplier": 0.60,
            "capital_deployment_profile": "full_learning_v2",
            "show_interesting_now": True,
        }
        raw = self.get_app_setting("paper_autopilot_settings")
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    if not parsed.get("capital_deployment_profile"):
                        parsed = {
                            **parsed,
                            "max_trades": max(5, int(float(parsed.get("max_trades") or 3))),
                            "learning_risk_multiplier": max(
                                0.25,
                                float(parsed.get("learning_risk_multiplier") or 0.10),
                            ),
                            "aggressive_risk_multiplier": max(
                                0.60,
                                float(parsed.get("aggressive_risk_multiplier") or 0.25),
                            ),
                            "capital_deployment_profile": "full_learning_v2",
                        }
                    return {**default, **parsed}
            except json.JSONDecodeError:
                pass
        return default

    def save_paper_autopilot_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        import json
        current = self.get_paper_autopilot_settings()
        current.update(settings or {})
        mode = str(current.get("mode") or "aggressive_learning")
        if mode not in {"strict", "learn", "aggressive_learning"}:
            mode = "aggressive_learning"
        current["mode"] = mode
        current["max_trades"] = max(1, min(8, int(float(current.get("max_trades") or 5))))
        current["strict_min_score"] = max(50, min(99, float(current.get("strict_min_score") or 88)))
        current["learning_min_score"] = max(40, min(95, float(current.get("learning_min_score") or 60)))
        current["aggressive_min_score"] = max(35, min(90, float(current.get("aggressive_min_score") or 52)))
        current["learning_risk_multiplier"] = max(0.03, min(0.35, float(current.get("learning_risk_multiplier") or 0.25)))
        current["aggressive_risk_multiplier"] = max(
            current["learning_risk_multiplier"],
            min(0.65, float(current.get("aggressive_risk_multiplier") or 0.60)),
        )
        current["show_interesting_now"] = bool(current.get("show_interesting_now", True))
        self.set_app_setting("paper_autopilot_settings", json.dumps(current))
        return current

    def get_login_guard_state(self) -> Dict[str, Any]:
        import json
        raw = self.get_app_setting("login_guard")
        if raw:
            try:
                state = json.loads(raw)
                return {
                    "failed_attempts": int(state.get("failed_attempts", 0)),
                    "locked_until": state.get("locked_until"),
                }
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return {"failed_attempts": 0, "locked_until": None}

    def record_failed_login(self, max_attempts: int, lockout_minutes: int) -> Dict[str, Any]:
        import json
        state = self.get_login_guard_state()
        failed_attempts = int(state.get("failed_attempts", 0)) + 1
        locked_until = None
        if failed_attempts >= max_attempts:
            locked_until = (datetime.now() + timedelta(minutes=lockout_minutes)).isoformat()
            failed_attempts = 0
        next_state = {
            "failed_attempts": failed_attempts,
            "locked_until": locked_until,
        }
        self.set_app_setting("login_guard", json.dumps(next_state))
        return next_state

    def reset_login_guard(self):
        import json
        state = self.get_login_guard_state()
        if int(state.get("failed_attempts", 0)) == 0 and not state.get("locked_until"):
            return
        self.set_app_setting(
            "login_guard",
            json.dumps({"failed_attempts": 0, "locked_until": None}),
        )

    def list_paper_trades(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if status:
            cursor.execute(
                '''
                SELECT * FROM paper_trades
                WHERE status = ?
                ORDER BY opened_at DESC
                LIMIT ?
                ''',
                (status, limit),
            )
        else:
            cursor.execute(
                '''
                SELECT * FROM paper_trades
                ORDER BY
                    CASE WHEN status = 'open' THEN 0 ELSE 1 END,
                    COALESCE(closed_at, opened_at) DESC
                LIMIT ?
                ''',
                (limit,),
            )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for row in rows:
            try:
                row["trade_ticket"] = json.loads(row.pop("trade_ticket_json", "{}") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                row["trade_ticket"] = {}
        return rows

    def create_paper_trade(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        trade_id = str(uuid.uuid4())
        opened_at = datetime.now().isoformat()
        row = {
            "id": trade_id,
            "ticker": (payload.get("ticker") or "").upper(),
            "asset_class": payload.get("asset_class") or "equity",
            "direction": payload.get("direction") or "long",
            "setup_type": payload.get("setup_type") or "signal_follow",
            "thesis": payload.get("thesis") or "",
            "entry_price": float(payload.get("entry_price") or 0),
            "stop_price": float(payload["stop_price"]) if payload.get("stop_price") not in (None, "") else None,
            "target_price": float(payload["target_price"]) if payload.get("target_price") not in (None, "") else None,
            "quantity": float(payload.get("quantity") or 0),
            "confidence_score": float(payload["confidence_score"]) if payload.get("confidence_score") not in (None, "") else None,
            "leverage": float(payload.get("leverage") or 1),
            "opened_at": opened_at,
            "closed_at": None,
            "closed_price": None,
            "status": "open",
            "notes": payload.get("notes") or "",
            "exit_reason": payload.get("exit_reason") or "",
            "lessons_learned": payload.get("lessons_learned") or "",
            "underlying_entry_price": float(payload["underlying_entry_price"]) if payload.get("underlying_entry_price") not in (None, "") else None,
            "option_type": payload.get("option_type") or None,
            "contract_multiplier": float(payload.get("contract_multiplier") or 1),
            "max_holding_days": int(payload["max_holding_days"]) if payload.get("max_holding_days") not in (None, "") else None,
            "error_tag": payload.get("error_tag") or "",
            "trade_ticket": payload.get("trade_ticket") if isinstance(payload.get("trade_ticket"), dict) else {},
        }
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO paper_trades (
                id, ticker, asset_class, direction, setup_type, thesis, entry_price,
                stop_price, target_price, quantity, confidence_score, leverage,
                opened_at, closed_at, closed_price, status, notes, exit_reason, lessons_learned,
                underlying_entry_price, option_type, contract_multiplier, max_holding_days, error_tag,
                trade_ticket_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                row["id"],
                row["ticker"],
                row["asset_class"],
                row["direction"],
                row["setup_type"],
                row["thesis"],
                row["entry_price"],
                row["stop_price"],
                row["target_price"],
                row["quantity"],
                row["confidence_score"],
                row["leverage"],
                row["opened_at"],
                row["closed_at"],
                row["closed_price"],
                row["status"],
                row["notes"],
                row["exit_reason"],
                row["lessons_learned"],
                row["underlying_entry_price"],
                row["option_type"],
                row["contract_multiplier"],
                row["max_holding_days"],
                row["error_tag"],
                json.dumps(row["trade_ticket"], ensure_ascii=True, default=str),
            ),
        )
        conn.commit()
        conn.close()
        return row

    def upsert_paper_trade_outcomes(self, trade_id: str, outcomes: List[Dict[str, Any]]) -> int:
        if not outcomes:
            return 0
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        inserted = 0
        for outcome in outcomes:
            cursor.execute(
                '''
                INSERT OR IGNORE INTO paper_trade_outcomes (
                    id, trade_id, horizon_hours, due_at, status, result,
                    checked_at, check_price, performance_pct, benchmark_symbol,
                    benchmark_entry_price, benchmark_check_price, benchmark_return_pct,
                    active_return_pct, notes, error_tag
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    outcome.get("id"),
                    trade_id,
                    int(outcome.get("horizon_hours") or 0),
                    outcome.get("due_at"),
                    outcome.get("status") or "pending",
                    outcome.get("result"),
                    outcome.get("checked_at"),
                    outcome.get("check_price"),
                    outcome.get("performance_pct"),
                    outcome.get("benchmark_symbol"),
                    outcome.get("benchmark_entry_price"),
                    outcome.get("benchmark_check_price"),
                    outcome.get("benchmark_return_pct"),
                    outcome.get("active_return_pct"),
                    outcome.get("notes"),
                    outcome.get("error_tag"),
                ),
            )
            inserted += max(0, cursor.rowcount)
        conn.commit()
        conn.close()
        return inserted

    def list_due_paper_trade_outcomes(self, limit: int = 80) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT
                o.*,
                t.ticker,
                t.asset_class,
                t.direction,
                t.setup_type,
                t.entry_price,
                t.stop_price,
                t.target_price,
                t.quantity,
                t.leverage,
                t.opened_at,
                t.status AS trade_status,
                t.underlying_entry_price,
                t.option_type,
                t.contract_multiplier,
                t.max_holding_days,
                t.trade_ticket_json
            FROM paper_trade_outcomes o
            JOIN paper_trades t ON t.id = o.trade_id
            WHERE o.status IN ('pending', 'pending_data')
              AND o.due_at <= ?
            ORDER BY o.due_at ASC
            LIMIT ?
            ''',
            (datetime.now().isoformat(), limit),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for row in rows:
            try:
                row["trade_ticket"] = json.loads(row.pop("trade_ticket_json", "{}") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                row["trade_ticket"] = {}
        return rows

    def update_paper_trade_outcome(self, outcome_id: str, updates: Dict[str, Any]) -> None:
        allowed = {
            "status", "result", "checked_at", "check_price", "performance_pct",
            "benchmark_symbol", "benchmark_entry_price", "benchmark_check_price",
            "benchmark_return_pct", "active_return_pct", "notes", "error_tag",
        }
        clean = {key: value for key, value in (updates or {}).items() if key in allowed}
        if not clean:
            return
        assignments = ", ".join([f"{key} = ?" for key in clean.keys()])
        values = list(clean.values()) + [outcome_id]
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE paper_trade_outcomes SET {assignments} WHERE id = ?", values)
        conn.commit()
        conn.close()

    def list_paper_trade_outcomes(self, limit: int = 500) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT
                o.*,
                t.ticker,
                t.asset_class,
                t.direction,
                t.setup_type,
                t.opened_at,
                t.trade_ticket_json
            FROM paper_trade_outcomes o
            JOIN paper_trades t ON t.id = o.trade_id
            ORDER BY o.due_at DESC
            LIMIT ?
            ''',
            (limit,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for row in rows:
            try:
                row["trade_ticket"] = json.loads(row.pop("trade_ticket_json", "{}") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                row["trade_ticket"] = {}
        return rows

    def close_paper_trade(
        self,
        trade_id: str,
        closed_price: float,
        notes: Optional[str] = None,
        exit_reason: Optional[str] = None,
        lessons_learned: Optional[str] = None,
        trade_ticket: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM paper_trades WHERE id = ?', (trade_id,))
        existing = cursor.fetchone()
        if not existing:
            conn.close()
            return None
        if str(existing["status"] or "").lower() != "open":
            conn.close()
            return None
        closed_at = datetime.now().isoformat()
        merged_notes = notes if notes is not None else existing["notes"]
        merged_exit_reason = exit_reason if exit_reason is not None else existing["exit_reason"]
        merged_lessons = lessons_learned if lessons_learned is not None else existing["lessons_learned"]
        if isinstance(trade_ticket, dict):
            merged_ticket = trade_ticket
        else:
            try:
                merged_ticket = json.loads(existing["trade_ticket_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                merged_ticket = {}
        try:
            existing_ticket = json.loads(existing["trade_ticket_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            existing_ticket = {}
        immutable_snapshot = existing_ticket.get("learning_feature_snapshot")
        if immutable_snapshot is not None and merged_ticket.get("learning_feature_snapshot") != immutable_snapshot:
            conn.close()
            raise ValueError("learning_feature_snapshot is immutable after paper entry")
        cursor.execute(
            '''
            UPDATE paper_trades
            SET status = 'closed',
                closed_at = ?,
                closed_price = ?,
                notes = ?,
                exit_reason = ?,
                lessons_learned = ?,
                trade_ticket_json = ?
            WHERE id = ? AND status = 'open'
            ''',
            (
                closed_at,
                closed_price,
                merged_notes,
                merged_exit_reason,
                merged_lessons,
                json.dumps(merged_ticket, ensure_ascii=True, default=str),
                trade_id,
            ),
        )
        changed = cursor.rowcount
        conn.commit()
        if changed <= 0:
            conn.close()
            return None
        cursor.execute('SELECT * FROM paper_trades WHERE id = ?', (trade_id,))
        updated = dict(cursor.fetchone())
        conn.close()
        try:
            updated["trade_ticket"] = json.loads(updated.pop("trade_ticket_json", "{}") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            updated["trade_ticket"] = {}
        return updated

    def update_paper_trade_ticket(
        self,
        trade_id: str,
        trade_ticket: Dict[str, Any],
        open_only: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Persist evidence/management metadata without changing the trade lifecycle."""
        if not isinstance(trade_ticket, dict):
            raise ValueError("trade_ticket must be a dictionary")
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        where = "id = ? AND status = 'open'" if open_only else "id = ?"
        existing_row = cursor.execute(
            "SELECT trade_ticket_json FROM paper_trades WHERE id = ?",
            (trade_id,),
        ).fetchone()
        if existing_row:
            try:
                existing_ticket = json.loads(existing_row[0] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                existing_ticket = {}
            immutable_snapshot = existing_ticket.get("learning_feature_snapshot")
            if immutable_snapshot is not None and trade_ticket.get("learning_feature_snapshot") != immutable_snapshot:
                conn.close()
                raise ValueError("learning_feature_snapshot is immutable after paper entry")
        cursor.execute(
            f"UPDATE paper_trades SET trade_ticket_json = ? WHERE {where}",
            (json.dumps(trade_ticket, ensure_ascii=True, default=str), trade_id),
        )
        changed = cursor.rowcount
        conn.commit()
        if changed <= 0:
            conn.close()
            return None
        cursor.execute("SELECT * FROM paper_trades WHERE id = ?", (trade_id,))
        row = cursor.fetchone()
        updated = dict(row) if row else None
        conn.close()
        if not updated:
            return None
        try:
            updated["trade_ticket"] = json.loads(updated.pop("trade_ticket_json", "{}") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            updated["trade_ticket"] = {}
        return updated

    def upsert_paper_learning_run(self, run: Dict[str, Any]) -> Dict[str, Any]:
        run_id = str(run.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("paper learning run_id is required")
        now = datetime.now().isoformat()
        conn = _connect_db()
        conn.execute(
            '''
            INSERT INTO paper_learning_runs (
                run_id, status, started_at, checked_at, duration_ms, result_json,
                error_type, error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status = excluded.status,
                checked_at = excluded.checked_at,
                duration_ms = excluded.duration_ms,
                result_json = excluded.result_json,
                error_type = excluded.error_type,
                error = excluded.error,
                updated_at = excluded.updated_at
            ''',
            (
                run_id,
                str(run.get("status") or "unknown"),
                str(run.get("started_at") or now),
                run.get("checked_at"),
                run.get("duration_ms"),
                json.dumps(run, ensure_ascii=True, default=str),
                run.get("error_type"),
                str(run.get("error") or "")[:1000] or None,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()
        return {**run, "updated_at": now}

    def list_paper_learning_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = _connect_db(row_factory=True)
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM paper_learning_runs ORDER BY started_at DESC LIMIT ?",
            (max(1, min(500, int(limit))),),
        ).fetchall()]
        conn.close()
        for row in rows:
            try:
                result = json.loads(row.pop("result_json") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                result = {}
            row["result"] = result
        return rows

    def upsert_paper_learning_attribution(self, attribution: Dict[str, Any]) -> Dict[str, Any]:
        trade_id = str(attribution.get("trade_id") or "").strip()
        if not trade_id:
            raise ValueError("trade_id is required for paper learning attribution")
        now = datetime.now().isoformat()
        conn = _connect_db()
        conn.execute(
            '''
            INSERT INTO paper_learning_attributions (
                trade_id, schema_version, outcome_quality, process_quality, primary_error,
                secondary_errors_json, metrics_json, evidence_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET
                schema_version = excluded.schema_version,
                outcome_quality = excluded.outcome_quality,
                process_quality = excluded.process_quality,
                primary_error = excluded.primary_error,
                secondary_errors_json = excluded.secondary_errors_json,
                metrics_json = excluded.metrics_json,
                evidence_json = excluded.evidence_json,
                updated_at = excluded.updated_at
            ''',
            (
                trade_id,
                str(attribution.get("schema_version") or "paper-learning-attribution.v2"),
                str(attribution.get("outcome_quality") or "insufficient_evidence"),
                str(attribution.get("process_quality") or "insufficient_evidence"),
                attribution.get("primary_error"),
                json.dumps(attribution.get("secondary_errors") or [], ensure_ascii=True, default=str),
                json.dumps(attribution.get("metrics") or {}, ensure_ascii=True, default=str),
                json.dumps(attribution.get("evidence") or {}, ensure_ascii=True, default=str),
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()
        return {**attribution, "created_at": attribution.get("created_at") or now, "updated_at": now}

    def list_paper_learning_attributions(self, limit: int = 500) -> List[Dict[str, Any]]:
        conn = _connect_db(row_factory=True)
        rows = [dict(row) for row in conn.execute(
            '''
            SELECT a.*, t.ticker, t.asset_class, t.direction, t.setup_type, t.opened_at, t.closed_at
            FROM paper_learning_attributions a
            JOIN paper_trades t ON t.id = a.trade_id
            ORDER BY a.updated_at DESC LIMIT ?
            ''',
            (max(1, min(2000, int(limit))),),
        ).fetchall()]
        conn.close()
        for row in rows:
            row["secondary_errors"] = json.loads(row.pop("secondary_errors_json") or "[]")
            row["metrics"] = json.loads(row.pop("metrics_json") or "{}")
            row["evidence"] = json.loads(row.pop("evidence_json") or "{}")
        return rows

    def upsert_paper_learning_hypothesis(self, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        fingerprint = str(hypothesis.get("fingerprint") or "").strip()
        if not fingerprint:
            raise ValueError("hypothesis fingerprint is required")
        now = datetime.now().isoformat()
        hypothesis_id = str(hypothesis.get("id") or f"plh_{fingerprint[:24]}")
        evidence_payload = {
            **(hypothesis.get("evidence") or {}),
            "hypothesis_metadata": {
                "expected_effect": hypothesis.get("expected_effect"),
                "alternative_explanation": hypothesis.get("alternative_explanation"),
                "possible_downside": hypothesis.get("possible_downside"),
                "minimum_future_test_trades": hypothesis.get("minimum_future_test_trades"),
                "expires_at": hypothesis.get("expires_at"),
            },
        }
        conn = _connect_db()
        conn.execute(
            '''
            INSERT INTO paper_learning_hypotheses (
                id, fingerprint, strategy_id, segment_json, statement, evidence_json,
                proposed_rule_json, uncertainty, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fingerprint) DO UPDATE SET
                strategy_id = excluded.strategy_id,
                segment_json = excluded.segment_json,
                statement = excluded.statement,
                evidence_json = excluded.evidence_json,
                proposed_rule_json = excluded.proposed_rule_json,
                uncertainty = excluded.uncertainty,
                updated_at = excluded.updated_at
            ''',
            (
                hypothesis_id, fingerprint, hypothesis.get("strategy_id"),
                json.dumps(hypothesis.get("segment") or {}, ensure_ascii=True, default=str),
                str(hypothesis.get("statement") or "Paper pattern requires review."),
                json.dumps(evidence_payload, ensure_ascii=True, default=str),
                json.dumps(hypothesis.get("proposed_rule") or {}, ensure_ascii=True, default=str),
                str(hypothesis.get("uncertainty") or "high"),
                str(hypothesis.get("status") or "proposed"), now, now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM paper_learning_hypotheses WHERE fingerprint = ?", (fingerprint,)).fetchone()
        conn.close()
        return {**hypothesis, "id": row[0] if row else hypothesis_id, "updated_at": now}

    def list_paper_learning_hypotheses(self, limit: int = 200) -> List[Dict[str, Any]]:
        conn = _connect_db(row_factory=True)
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM paper_learning_hypotheses ORDER BY updated_at DESC LIMIT ?",
            (max(1, min(1000, int(limit))),),
        ).fetchall()]
        conn.close()
        for row in rows:
            row["segment"] = json.loads(row.pop("segment_json") or "{}")
            row["evidence"] = json.loads(row.pop("evidence_json") or "{}")
            row["proposed_rule"] = json.loads(row.pop("proposed_rule_json") or "{}")
            metadata = row["evidence"].get("hypothesis_metadata")
            if isinstance(metadata, dict):
                for key in (
                    "expected_effect",
                    "alternative_explanation",
                    "possible_downside",
                    "minimum_future_test_trades",
                    "expires_at",
                ):
                    row[key] = metadata.get(key)
        return rows

    def ensure_paper_learning_shadow_rule(self, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        hypothesis_id = str(hypothesis.get("id") or "").strip()
        if not hypothesis_id:
            raise ValueError("hypothesis id is required")
        conn = _connect_db(row_factory=True)
        existing = conn.execute(
            "SELECT * FROM paper_learning_rules WHERE hypothesis_id = ? ORDER BY version DESC LIMIT 1",
            (hypothesis_id,),
        ).fetchone()
        if existing:
            conn.close()
            row = dict(existing)
            row["rule"] = json.loads(row.pop("rule_json") or "{}")
            row["baseline"] = json.loads(row.pop("baseline_json") or "{}")
            row["evaluation"] = json.loads(row.pop("evaluation_json") or "{}")
            return row
        now = datetime.now(timezone.utc).isoformat()
        rule_id = f"plr_{uuid.uuid4().hex[:24]}"
        conn.execute(
            '''
            INSERT INTO paper_learning_rules (
                id, hypothesis_id, version, status, rule_json, baseline_json,
                evaluation_json, started_at, ended_at, created_at, updated_at
            ) VALUES (?, ?, 1, 'shadow', ?, ?, '{}', ?, NULL, ?, ?)
            ''',
            (
                rule_id, hypothesis_id,
                json.dumps(hypothesis.get("proposed_rule") or {}, ensure_ascii=True, default=str),
                json.dumps(hypothesis.get("evidence") or {}, ensure_ascii=True, default=str),
                now, now, now,
            ),
        )
        conn.commit()
        conn.close()
        return {"id": rule_id, "hypothesis_id": hypothesis_id, "version": 1, "status": "shadow", "rule": hypothesis.get("proposed_rule") or {}, "started_at": now}

    def list_paper_learning_rules(self, limit: int = 200) -> List[Dict[str, Any]]:
        conn = _connect_db(row_factory=True)
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM paper_learning_rules ORDER BY updated_at DESC LIMIT ?",
            (max(1, min(1000, int(limit))),),
        ).fetchall()]
        conn.close()
        for row in rows:
            row["rule"] = json.loads(row.pop("rule_json") or "{}")
            row["baseline"] = json.loads(row.pop("baseline_json") or "{}")
            row["evaluation"] = json.loads(row.pop("evaluation_json") or "{}")
        return rows

    def create_paper_learning_rule_version(self, source_rule_id: str) -> Dict[str, Any]:
        conn = _connect_db(row_factory=True)
        source = conn.execute(
            "SELECT * FROM paper_learning_rules WHERE id = ?",
            (str(source_rule_id),),
        ).fetchone()
        if not source:
            conn.close()
            raise ValueError("source paper learning rule not found")
        source_row = dict(source)
        hypothesis_id = source_row.get("hypothesis_id")
        version_row = conn.execute(
            "SELECT MAX(version) FROM paper_learning_rules WHERE hypothesis_id = ?",
            (hypothesis_id,),
        ).fetchone()
        version = int((version_row or [0])[0] or 0) + 1
        now = datetime.now(timezone.utc).isoformat()
        rule_id = f"plr_{uuid.uuid4().hex[:24]}"
        conn.execute(
            '''
            INSERT INTO paper_learning_rules (
                id, hypothesis_id, version, status, rule_json, baseline_json,
                evaluation_json, started_at, ended_at, created_at, updated_at
            ) VALUES (?, ?, ?, 'shadow', ?, ?, '{}', ?, NULL, ?, ?)
            ''',
            (
                rule_id,
                hypothesis_id,
                version,
                source_row.get("rule_json") or "{}",
                source_row.get("baseline_json") or "{}",
                now,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()
        created = next((item for item in self.list_paper_learning_rules(limit=1000) if item.get("id") == rule_id), None)
        if not created:
            raise RuntimeError("new paper learning rule version could not be loaded")
        return created

    def update_paper_learning_rule_status(
        self,
        rule_id: str,
        status: str,
        evaluation: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        allowed = {"shadow", "eligible_for_paper_review", "active_paper", "paused", "rejected", "rolled_back"}
        if status not in allowed:
            raise ValueError("invalid paper learning rule status")
        now = datetime.now().isoformat()
        ended_at = now if status in {"paused", "rejected", "rolled_back"} else None
        conn = _connect_db()
        cursor = conn.execute(
            '''
            UPDATE paper_learning_rules
            SET status = ?, evaluation_json = ?, ended_at = ?, updated_at = ?
            WHERE id = ?
            ''',
            (status, json.dumps(evaluation or {}, ensure_ascii=True, default=str), ended_at, now, rule_id),
        )
        conn.commit()
        conn.close()
        if cursor.rowcount <= 0:
            return None
        return next((item for item in self.list_paper_learning_rules(limit=1000) if item.get("id") == rule_id), None)

    def record_paper_learning_rule_history(
        self,
        rule_id: str,
        action: str,
        before: Dict[str, Any],
        after: Dict[str, Any],
        reason: str,
        audit_event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        history_id = f"plrh_{uuid.uuid4().hex[:24]}"
        created_at = datetime.now(timezone.utc).isoformat()
        row = {
            "id": history_id,
            "rule_id": str(rule_id),
            "action": str(action),
            "from_status": before.get("status"),
            "to_status": after.get("status"),
            "before": before,
            "after": after,
            "reason": str(reason),
            "audit_event_id": audit_event_id,
            "created_at": created_at,
        }
        conn = _connect_db()
        conn.execute(
            '''
            INSERT INTO paper_learning_rule_history (
                id, rule_id, action, from_status, to_status, before_json,
                after_json, reason, audit_event_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                history_id,
                str(rule_id),
                str(action),
                before.get("status"),
                after.get("status"),
                json.dumps(before, ensure_ascii=True, default=str),
                json.dumps(after, ensure_ascii=True, default=str),
                str(reason),
                audit_event_id,
                created_at,
            ),
        )
        conn.commit()
        conn.close()
        return row

    def list_paper_learning_rule_history(
        self,
        rule_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        conn = _connect_db(row_factory=True)
        if rule_id:
            rows = conn.execute(
                "SELECT * FROM paper_learning_rule_history WHERE rule_id = ? ORDER BY created_at DESC LIMIT ?",
                (str(rule_id), max(1, min(1000, int(limit)))),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM paper_learning_rule_history ORDER BY created_at DESC LIMIT ?",
                (max(1, min(1000, int(limit))),),
            ).fetchall()
        conn.close()
        result = [dict(row) for row in rows]
        for row in result:
            row["before"] = json.loads(row.pop("before_json") or "{}")
            row["after"] = json.loads(row.pop("after_json") or "{}")
        return result

    def list_price_alerts(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if enabled_only:
            cursor.execute(
                '''
                SELECT * FROM price_alerts
                WHERE enabled = 1
                ORDER BY updated_at DESC, created_at DESC
                '''
            )
        else:
            cursor.execute(
                '''
                SELECT * FROM price_alerts
                ORDER BY updated_at DESC, created_at DESC
                '''
            )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for row in rows:
            row["enabled"] = bool(row.get("enabled", 0))
        return rows

    def create_price_alert(
        self,
        symbol: str,
        direction: str,
        target_price: float,
        enabled: bool = True,
        cooldown_minutes: int = 5,
    ) -> Dict[str, Any]:
        alert_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        normalized_symbol = (symbol or "").strip().upper()
        normalized_direction = (direction or "").strip().lower()
        if normalized_direction not in {"above", "below"}:
            raise ValueError("direction must be 'above' or 'below'")

        row = {
            "id": alert_id,
            "symbol": normalized_symbol,
            "direction": normalized_direction,
            "target_price": float(target_price),
            "enabled": bool(enabled),
            "cooldown_minutes": max(1, int(cooldown_minutes or 5)),
            "last_triggered_at": None,
            "created_at": now,
            "updated_at": now,
        }

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO price_alerts (
                id, symbol, direction, target_price, enabled, cooldown_minutes,
                last_triggered_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                row["id"],
                row["symbol"],
                row["direction"],
                row["target_price"],
                1 if row["enabled"] else 0,
                row["cooldown_minutes"],
                row["last_triggered_at"],
                row["created_at"],
                row["updated_at"],
            ),
        )
        conn.commit()
        conn.close()
        return row

    def update_price_alert(self, alert_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"symbol", "direction", "target_price", "enabled", "cooldown_minutes", "last_triggered_at"}
        updates: Dict[str, Any] = {}
        for key, value in (payload or {}).items():
            if key not in allowed:
                continue
            updates[key] = value
        if not updates:
            return self.get_price_alert(alert_id)

        if "symbol" in updates:
            updates["symbol"] = (updates["symbol"] or "").strip().upper()
        if "direction" in updates:
            updates["direction"] = (updates["direction"] or "").strip().lower()
            if updates["direction"] not in {"above", "below"}:
                raise ValueError("direction must be 'above' or 'below'")
        if "target_price" in updates:
            updates["target_price"] = float(updates["target_price"])
        if "enabled" in updates:
            updates["enabled"] = 1 if bool(updates["enabled"]) else 0
        if "cooldown_minutes" in updates:
            updates["cooldown_minutes"] = max(1, int(updates["cooldown_minutes"] or 5))

        updates["updated_at"] = datetime.now().isoformat()
        sets = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values()) + [alert_id]

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE price_alerts SET {sets} WHERE id = ?", values)
        conn.commit()
        conn.close()
        return self.get_price_alert(alert_id)

    def get_price_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM price_alerts WHERE id = ?", (alert_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        payload = dict(row)
        payload["enabled"] = bool(payload.get("enabled", 0))
        return payload

    def delete_price_alert(self, alert_id: str) -> bool:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM price_alerts WHERE id = ?", (alert_id,))
        changed = cursor.rowcount
        conn.commit()
        conn.close()
        return changed > 0

    def update_paper_trade_journal(
        self,
        trade_id: str,
        notes: Optional[str] = None,
        exit_reason: Optional[str] = None,
        lessons_learned: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM paper_trades WHERE id = ?', (trade_id,))
        existing = cursor.fetchone()
        if not existing:
            conn.close()
            return None
        cursor.execute(
            '''
            UPDATE paper_trades
            SET notes = ?, exit_reason = ?, lessons_learned = ?
            WHERE id = ?
            ''',
            (
                existing["notes"] if notes is None else notes,
                existing["exit_reason"] if exit_reason is None else exit_reason,
                existing["lessons_learned"] if lessons_learned is None else lessons_learned,
                trade_id,
            ),
        )
        conn.commit()
        cursor.execute('SELECT * FROM paper_trades WHERE id = ?', (trade_id,))
        updated = dict(cursor.fetchone())
        conn.close()
        return updated
