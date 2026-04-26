#!/usr/bin/env python3
"""
One-shot migration script: agent_*.db → NoSQL (state.json + interactions.jsonl)

Migrates agent database from SQLite to NoJSON-based storage using AgentMemoryNoSQL.
Creates a backup of the original database before migration.
"""

import argparse
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

from agent_memory_nosql import AgentMemoryNoSQL
from agent_logging import get_logger

logger = get_logger("migrate_agent_to_nosql")


def migrate_interactions(db_path: Path, memory: AgentMemoryNoSQL):
    """Migrate interactions table to interactions.jsonl."""
    logger.info(f"[Migration] Migrating interactions from {db_path}")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT user_id, user_message, bot_response, channel_id, timestamp FROM interactions ORDER BY timestamp DESC LIMIT 250")
        for row in cursor.fetchall():
            memory.register_interaction(
                user_id=row[0],
                user_message=row[1],
                bot_response=row[2],
                channel_id=row[3],
                timestamp=row[4] if len(row) > 4 else None
            )
        logger.info(f"[Migration] ✅ Migrated interactions")
    except sqlite3.OperationalError:
        logger.warning(f"[Migration] No interactions table found")
    finally:
        conn.close()


def migrate_daily_memory(db_path: Path, memory: AgentMemoryNoSQL):
    """Migrate daily_memory table to state.json."""
    logger.info(f"[Migration] Migrating daily memory from {db_path}")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT summary, updated_at FROM daily_memory ORDER BY updated_at DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            memory.save_daily_memory(row[0])
            logger.info(f"[Migration] ✅ Migrated daily memory")
    except sqlite3.OperationalError:
        logger.warning(f"[Migration] No daily_memory table found")
    finally:
        conn.close()


def migrate_recent_memory(db_path: Path, memory: AgentMemoryNoSQL):
    """Migrate recent_memory table to state.json."""
    logger.info(f"[Migration] Migrating recent memory from {db_path}")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT summary, updated_at FROM recent_memory ORDER BY updated_at DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            memory.save_recent_memory(row[0])
            logger.info(f"[Migration] ✅ Migrated recent memory")
    except sqlite3.OperationalError:
        logger.warning(f"[Migration] No recent_memory table found")
    finally:
        conn.close()


def migrate_relationships(db_path: Path, memory: AgentMemoryNoSQL):
    """Migrate relationships table to state.json."""
    logger.info(f"[Migration] Migrating relationships from {db_path}")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT user_id, summary, updated_at FROM relationships")
        for row in cursor.fetchall():
            memory.save_relationship(row[0], row[1])
        logger.info(f"[Migration] ✅ Migrated relationships")
    except sqlite3.OperationalError:
        logger.warning(f"[Migration] No relationships table found")
    finally:
        conn.close()


def migrate_recollections(db_path: Path, memory: AgentMemoryNoSQL):
    """Migrate recollections table to state.json."""
    logger.info(f"[Migration] Migrating recollections from {db_path}")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT recollection, source, created_at, used FROM recollections")
        for row in cursor.fetchall():
            rec_id = memory.add_recollection(row[0], source=row[1] if len(row) > 1 else "user")
            if len(row) > 3 and row[3]:
                memory.mark_recollection_used(rec_id)
        logger.info(f"[Migration] ✅ Migrated recollections")
    except sqlite3.OperationalError:
        logger.warning(f"[Migration] No recollections table found")
    finally:
        conn.close()


def migrate_database(db_path: Path, server_id: str, backup: bool = True):
    """Migrate a single agent database to NoSQL."""
    if not db_path.exists():
        logger.error(f"[Migration] Database not found: {db_path}")
        return False

    logger.info(f"[Migration] Starting migration for {db_path}")

    # Create backup
    if backup:
        backup_path = db_path.with_suffix(".bak")
        logger.info(f"[Migration] Creating backup at {backup_path}")
        shutil.copy2(db_path, backup_path)
        logger.info(f"[Migration] ✅ Backup created")

    # Initialize NoSQL backend
    memory = AgentMemoryNoSQL(server_id)

    # Migrate each table
    migrate_interactions(db_path, memory)
    migrate_daily_memory(db_path, memory)
    migrate_recent_memory(db_path, memory)
    migrate_relationships(db_path, memory)
    migrate_recollections(db_path, memory)

    logger.info(f"[Migration] ✅ Migration completed for {db_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Migrate agent databases from SQLite to NoSQL")
    parser.add_argument("--db-path", type=Path, required=True, help="Path to agent_*.db file")
    parser.add_argument("--server-id", type=str, required=True, help="Server ID for the database")
    parser.add_argument("--no-backup", action="store_true", help="Skip creating backup")
    args = parser.parse_args()

    logger.info(f"[Migration] Starting migration for {args.db_path} (server: {args.server_id})")

    success = migrate_database(args.db_path, args.server_id, backup=not args.no_backup)

    if success:
        logger.info("[Migration] ✅ All migrations completed successfully")
        print(f"✅ Migration completed. Backup: {args.db_path.with_suffix('.bak') if not args.no_backup else 'none'}")
    else:
        logger.error("[Migration] ❌ Migration failed")
        print("❌ Migration failed. Check logs for details.")
        exit(1)


if __name__ == "__main__":
    main()
