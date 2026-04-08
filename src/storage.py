import sqlite3
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'portfolios.db')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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
        sent_at TEXT NOT NULL
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
        lessons_learned TEXT
    )
    ''')
    try:
        cursor.execute('ALTER TABLE paper_trades ADD COLUMN exit_reason TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE paper_trades ADD COLUMN lessons_learned TEXT')
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()

class PortfolioManager:
    def __init__(self):
        init_db()

    def create_portfolio(self, name: str) -> Dict[str, Any]:
        portfolio_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO portfolios (id, name, created_at) VALUES (?, ?, ?)',
                       (portfolio_id, name, created_at))
        conn.commit()
        conn.close()
        
        return {"id": portfolio_id, "name": name, "createdAt": created_at, "holdings": []}

    def get_portfolios(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM portfolios')
        portfolios = [dict(row) for row in cursor.fetchall()]
        
        for p in portfolios:
            cursor.execute('SELECT ticker, shares, buy_price as buyPrice FROM holdings WHERE portfolio_id = ?', (p['id'],))
            p['holdings'] = [dict(row) for row in cursor.fetchall()]
            # Rename for frontend compatibility
            p['createdAt'] = p.pop('created_at')
            
        conn.close()
        return portfolios

    def delete_portfolio(self, portfolio_id: str):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM portfolios WHERE id = ?', (portfolio_id,))
        cursor.execute('DELETE FROM holdings WHERE portfolio_id = ?', (portfolio_id,))
        conn.commit()
        conn.close()

    def add_holding(self, portfolio_id: str, ticker: str, shares: float, buy_price: Optional[float] = None):
        holding_id = str(uuid.uuid4())
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if holding already exists for this ticker
        cursor.execute('SELECT id, shares FROM holdings WHERE portfolio_id = ? AND ticker = ?', (portfolio_id, ticker.upper()))
        existing = cursor.fetchone()
        
        if existing:
            new_shares = existing[1] + shares
            cursor.execute('UPDATE holdings SET shares = ? WHERE id = ?', (new_shares, existing[0]))
        else:
            cursor.execute('INSERT INTO holdings (id, portfolio_id, ticker, shares, buy_price) VALUES (?, ?, ?, ?, ?)',
                           (holding_id, portfolio_id, ticker.upper(), shares, buy_price))
                           
        conn.commit()
        conn.close()

    def remove_holding(self, portfolio_id: str, ticker: str):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM holdings WHERE portfolio_id = ? AND ticker = ?', (portfolio_id, ticker.upper()))
        conn.commit()
        conn.close()

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

    def mark_signal_events_sent(self, events: List[Dict[str, Any]]):
        if not events:
            return
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        for event in events:
            cursor.execute(
                'INSERT OR IGNORE INTO sent_signal_events (event_key, category, title, sent_at) VALUES (?, ?, ?, ?)',
                (
                    event['event_key'],
                    event['category'],
                    event['title'],
                    datetime.now().isoformat(),
                )
            )
        conn.commit()
        conn.close()

    def get_sent_signal_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            'SELECT event_key, category, title, sent_at FROM sent_signal_events ORDER BY sent_at DESC LIMIT ?',
            (limit,)
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_app_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM app_settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default

    def set_app_setting(self, key: str, value: str):
        conn = sqlite3.connect(DB_PATH)
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
        raw = self.get_app_setting("workspace_profile")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return {
            "display_name": "Maurice",
            "email": "",
            "timezone": "Europe/Berlin",
            "browser_notifications": False,
            "theme": "premium-light",
        }

    def save_workspace_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        import json
        current = self.get_workspace_profile()
        current.update(profile or {})
        self.set_app_setting("workspace_profile", json.dumps(current))
        return current

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
        }
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO paper_trades (
                id, ticker, asset_class, direction, setup_type, thesis, entry_price,
                stop_price, target_price, quantity, confidence_score, leverage,
                opened_at, closed_at, closed_price, status, notes, exit_reason, lessons_learned
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        conn.commit()
        conn.close()
        return row

    def close_paper_trade(
        self,
        trade_id: str,
        closed_price: float,
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
        closed_at = datetime.now().isoformat()
        merged_notes = notes if notes is not None else existing["notes"]
        merged_exit_reason = exit_reason if exit_reason is not None else existing["exit_reason"]
        merged_lessons = lessons_learned if lessons_learned is not None else existing["lessons_learned"]
        cursor.execute(
            '''
            UPDATE paper_trades
            SET status = 'closed',
                closed_at = ?,
                closed_price = ?,
                notes = ?,
                exit_reason = ?,
                lessons_learned = ?
            WHERE id = ?
            ''',
            (closed_at, closed_price, merged_notes, merged_exit_reason, merged_lessons, trade_id),
        )
        conn.commit()
        cursor.execute('SELECT * FROM paper_trades WHERE id = ?', (trade_id,))
        updated = dict(cursor.fetchone())
        conn.close()
        return updated

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
