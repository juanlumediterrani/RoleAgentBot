"""
Beggar subrole database utilities.
Provides per-server subscription, activity, and configuration storage.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from agent_logging import get_logger
from agent_db import get_database_path

logger = get_logger('beggar_db')


class DatabaseRoleBeggar:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS beggar_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    request_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    channel_id TEXT,
                    server_id TEXT,
                    metadata TEXT
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS beggar_subscriptions (
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, server_id)
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS beggar_config (
                    server_id TEXT PRIMARY KEY,
                    frequency_hours INTEGER NOT NULL DEFAULT 6,
                    last_reason TEXT DEFAULT '',
                    target_gold INTEGER NOT NULL DEFAULT 0,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )
            conn.commit()

    def add_subscription(self, user_id: str, user_name: str, server_id: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    '''
                    INSERT OR REPLACE INTO beggar_subscriptions (user_id, user_name, server_id, created_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ''',
                    (user_id, user_name, server_id),
                )
                conn.execute(
                    '''
                    INSERT OR IGNORE INTO beggar_config (server_id, frequency_hours, last_reason, target_gold)
                    VALUES (?, 6, '', 0)
                    ''',
                    (server_id,),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.exception(f"Error adding beggar subscription: {e}")
            return False

    def remove_subscription(self, user_id: str, server_id: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'DELETE FROM beggar_subscriptions WHERE user_id = ? AND server_id = ?',
                    (user_id, server_id),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error removing beggar subscription: {e}")
            return False

    def is_subscribed(self, user_id: str, server_id: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT COUNT(*) FROM beggar_subscriptions WHERE user_id = ? AND server_id = ?',
                    (user_id, server_id),
                )
                return (cursor.fetchone() or [0])[0] > 0
        except Exception as e:
            logger.exception(f"Error checking beggar subscription: {e}")
            return False

    def register_request(self, user_id: str, user_name: str, request_type: str, message: str, channel_id: str | None, server_id: str, metadata: str | None = None) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    '''
                    INSERT INTO beggar_requests (user_id, user_name, request_type, message, created_at, channel_id, server_id, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (user_id, user_name, request_type, message, datetime.now().isoformat(), channel_id, server_id, metadata),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.exception(f"Error registering beggar request: {e}")
            return False

    def count_requests_type_last_day(self, request_type: str, server_id: str | None = None) -> int:
        since = (datetime.now() - timedelta(days=1)).isoformat()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if server_id:
                    cursor.execute(
                        '''
                        SELECT COUNT(*) FROM beggar_requests
                        WHERE request_type = ? AND server_id = ? AND created_at > ?
                        ''',
                        (request_type, server_id, since),
                    )
                else:
                    cursor.execute(
                        'SELECT COUNT(*) FROM beggar_requests WHERE request_type = ? AND created_at > ?',
                        (request_type, since),
                    )
                return (cursor.fetchone() or [0])[0]
        except Exception as e:
            logger.exception(f"Error counting beggar requests: {e}")
            return 0

    def get_frequency_hours(self, server_id: str) -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT frequency_hours FROM beggar_config WHERE server_id = ?', (server_id,))
                result = cursor.fetchone()
                if result:
                    return int(result[0])
                self.set_frequency_hours(server_id, 6)
                return 6
        except Exception as e:
            logger.exception(f"Error getting beggar frequency: {e}")
            return 6

    def set_frequency_hours(self, server_id: str, hours: int) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    '''
                    INSERT INTO beggar_config (server_id, frequency_hours, last_reason, target_gold, updated_at)
                    VALUES (?, ?, '', 0, CURRENT_TIMESTAMP)
                    ON CONFLICT(server_id) DO UPDATE SET
                        frequency_hours = excluded.frequency_hours,
                        updated_at = CURRENT_TIMESTAMP
                    ''',
                    (server_id, hours),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.exception(f"Error setting beggar frequency: {e}")
            return False

    def get_last_reason(self, server_id: str) -> str:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT last_reason FROM beggar_config WHERE server_id = ?', (server_id,))
                result = cursor.fetchone()
                return str(result[0]).strip() if result and result[0] else ''
        except Exception as e:
            logger.exception(f"Error getting beggar last reason: {e}")
            return ''

    def set_last_reason(self, server_id: str, reason: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    '''
                    INSERT INTO beggar_config (server_id, frequency_hours, last_reason, target_gold, updated_at)
                    VALUES (?, 6, ?, 0, CURRENT_TIMESTAMP)
                    ON CONFLICT(server_id) DO UPDATE SET
                        last_reason = excluded.last_reason,
                        updated_at = CURRENT_TIMESTAMP
                    ''',
                    (server_id, reason),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.exception(f"Error setting beggar last reason: {e}")
            return False

    def get_target_gold(self, server_id: str) -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT target_gold FROM beggar_config WHERE server_id = ?', (server_id,))
                result = cursor.fetchone()
                return int(result[0]) if result else 0
        except Exception as e:
            logger.exception(f"Error getting beggar target gold: {e}")
            return 0

    def set_target_gold(self, server_id: str, amount: int) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    '''
                    INSERT INTO beggar_config (server_id, frequency_hours, last_reason, target_gold, updated_at)
                    VALUES (?, 6, '', ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(server_id) DO UPDATE SET
                        target_gold = excluded.target_gold,
                        updated_at = CURRENT_TIMESTAMP
                    ''',
                    (server_id, amount),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.exception(f"Error setting beggar target gold: {e}")
            return False


_db_instances: dict[str, DatabaseRoleBeggar] = {}


def get_beggar_db_instance(server_name: str) -> Optional[DatabaseRoleBeggar]:
    try:
        if server_name not in _db_instances:
            db_path = get_database_path(server_name, 'beggar')
            _db_instances[server_name] = DatabaseRoleBeggar(db_path)
        return _db_instances[server_name]
    except Exception as e:
        logger.exception(f"Error creating beggar DB instance: {e}")
        return None
