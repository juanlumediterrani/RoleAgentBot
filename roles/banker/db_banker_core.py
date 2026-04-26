"""
Banker Core Database — Dedicated SQLite per server.
Located at: databases/{server_id}/roles/banker.db

Server isolation is provided by the directory structure (each server has its
own directory), not by columns. The server_id is only used for path resolution.
"""

import sqlite3
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from agent_logging import get_logger
from agent_db import DB_DIR, _resolve_server_storage_id

logger = get_logger('banker_core_db')


def get_banker_db_path(server_id: str) -> Path:
    """Get banker.db path for a server: databases/{server_id}/roles/banker.db"""
    storage_id = _resolve_server_storage_id(server_id) or str(server_id)
    roles_dir = DB_DIR / storage_id / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)
    return roles_dir / "banker.db"


class BankerCoreDB:
    """Dedicated banker database per server."""

    def __init__(self, server_id: str):
        self.server_id = server_id
        self.db_path = get_banker_db_path(server_id)
        self._lock = threading.RLock()
        self._init_tables()

    def _init_tables(self):
        """Initialize banker tables — exact structure from original roles.db."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Wallets table — EXACT columns from original banker_wallets
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS wallets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        wallet_id TEXT NOT NULL UNIQUE,
                        user_name TEXT NOT NULL,
                        balance INTEGER DEFAULT 0,
                        wallet_type TEXT DEFAULT 'user',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Transactions table — EXACT columns from original banker_transactions
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        from_wallet TEXT NOT NULL,
                        to_wallet TEXT NOT NULL,
                        amount INTEGER NOT NULL,
                        transaction_type TEXT NOT NULL,
                        description TEXT,
                        created_by TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Indexes — exact match from original
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallets_wallet_id ON wallets(wallet_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_from_wallet ON transactions(from_wallet)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_to_wallet ON transactions(to_wallet)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at)")

                conn.commit()
                logger.info(f"Banker database initialized at: {self.db_path}")

    # === Wallets ===

    def save_wallet(self, wallet_id: str, user_name: str,
                    balance: int = 0, wallet_type: str = 'user') -> bool:
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    now = datetime.now().isoformat()
                    cursor.execute("""
                        INSERT OR REPLACE INTO wallets
                        (wallet_id, user_name, balance, wallet_type, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (wallet_id, user_name, balance, wallet_type, now, now))
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Failed to save wallet {wallet_id}: {e}")
            return False

    def get_wallet(self, wallet_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT wallet_id, user_name, balance, wallet_type, created_at, updated_at
                        FROM wallets WHERE wallet_id = ?
                    """, (wallet_id,))
                    row = cursor.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get wallet {wallet_id}: {e}")
            return None

    def update_balance(self, wallet_id: str, new_balance: int) -> bool:
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    now = datetime.now().isoformat()
                    cursor.execute("""
                        UPDATE wallets SET balance = ?, updated_at = ?
                        WHERE wallet_id = ?
                    """, (new_balance, now, wallet_id))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update balance {wallet_id}: {e}")
            return False

    def get_all_wallets(self) -> List[Dict[str, Any]]:
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT wallet_id, user_name, balance, wallet_type, created_at, updated_at
                        FROM wallets ORDER BY created_at DESC
                    """)
                    return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get wallets: {e}")
            return []

    # === Transactions ===

    def save_transaction(self, from_wallet: str, to_wallet: str, amount: int,
                         transaction_type: str, description: str = None,
                         created_by: str = None) -> int:
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    now = datetime.now().isoformat()
                    cursor.execute("""
                        INSERT INTO transactions
                        (from_wallet, to_wallet, amount, transaction_type, description, created_by, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (from_wallet, to_wallet, amount, transaction_type,
                          description, created_by, now))
                    conn.commit()
                    return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to save transaction: {e}")
            raise

    def get_transactions(self, wallet_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    if wallet_id:
                        cursor.execute("""
                            SELECT id, from_wallet, to_wallet, amount, transaction_type,
                                   description, created_by, created_at
                            FROM transactions
                            WHERE from_wallet = ? OR to_wallet = ?
                            ORDER BY created_at DESC LIMIT ?
                        """, (wallet_id, wallet_id, limit))
                    else:
                        cursor.execute("""
                            SELECT id, from_wallet, to_wallet, amount, transaction_type,
                                   description, created_by, created_at
                            FROM transactions
                            ORDER BY created_at DESC LIMIT ?
                        """, (limit,))
                    return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get transactions: {e}")
            return []


# Per-server instance cache
_banker_core_instances: Dict[str, BankerCoreDB] = {}
_banker_core_lock = threading.Lock()


def get_banker_core_db(server_id: str) -> BankerCoreDB:
    """Get the BankerCoreDB instance for a specific server."""
    global _banker_core_instances
    if server_id not in _banker_core_instances:
        with _banker_core_lock:
            if server_id not in _banker_core_instances:
                _banker_core_instances[server_id] = BankerCoreDB(server_id)
    return _banker_core_instances[server_id]
