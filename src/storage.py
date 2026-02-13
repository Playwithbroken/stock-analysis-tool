import sqlite3
import os
import uuid
from datetime import datetime
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
