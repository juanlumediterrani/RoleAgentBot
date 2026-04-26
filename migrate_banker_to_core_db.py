"""
Migration script: Move banker data from roles_<personality>.db to dedicated banker/banker.db.

Usage:
    python migrate_banker_to_core_db.py [--dry-run] [--server-id SERVER_ID]
"""

import argparse
import sqlite3
from pathlib import Path
from typing import List, Tuple, Optional

from agent_logging import get_logger
from agent_db import get_all_server_ids
from roles.banker.db_banker_core import get_banker_core_db

logger = get_logger('migrate_banker')


def discover_legacy_roles_db(server_id: str) -> Optional[Path]:
    """Find the roles_<personality>.db file for a server (if any)."""
    from agent_db import get_database_path, get_personality_name
    
    base_path = get_database_path(server_id)
    personality = get_personality_name(server_id)
    
    if not personality:
        # Try to discover any roles_*.db in the directory
        if base_path.exists():
            candidates = list(base_path.glob("roles_*.db"))
            if candidates:
                return candidates[0]  # Return first found
        return None
    
    legacy_path = base_path / f"roles_{personality}.db"
    if legacy_path.exists():
        return legacy_path
    
    # Try to find any roles_*.db as fallback
    candidates = list(base_path.glob("roles_*.db"))
    if candidates:
        return candidates[0]
    
    return None


def migrate_server(server_id: str, dry_run: bool = False) -> Tuple[int, int]:
    """
    Migrate banker data for a single server.
    
    Returns: (wallets_migrated, transactions_migrated)
    """
    legacy_path = discover_legacy_roles_db(server_id)
    
    if not legacy_path:
        logger.debug(f"No legacy roles.db found for server {server_id}")
        return (0, 0)
    
    if dry_run:
        logger.info(f"[DRY-RUN] Would migrate from {legacy_path}")
    
    core_db = get_banker_core_db(server_id)
    wallets_count = 0
    transactions_count = 0
    
    try:
        with sqlite3.connect(legacy_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Check if banker tables exist
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name IN ('banker_wallets', 'banker_transactions')
            """)
            existing = {row[0] for row in cursor.fetchall()}
            
            if 'banker_wallets' not in existing:
                logger.debug(f"No banker_wallets table in {legacy_path}")
                return (0, 0)
            
            # Migrate wallets
            cursor.execute("""
                SELECT wallet_id, user_name, balance, wallet_type, created_at, updated_at
                FROM banker_wallets
            """)
            wallets = cursor.fetchall()
            
            for row in wallets:
                if not dry_run:
                    # Check if wallet already exists (idempotent)
                    existing = core_db.get_wallet(row['wallet_id'])
                    if existing:
                        # Keep higher balance if conflict
                        if row['balance'] > existing['balance']:
                            core_db.update_balance(row['wallet_id'], row['balance'])
                    else:
                        core_db.save_wallet(
                            wallet_id=row['wallet_id'],
                            user_name=row['user_name'],
                            balance=row['balance'],
                            wallet_type=row['wallet_type']
                        )
                wallets_count += 1
            
            # Migrate transactions
            if 'banker_transactions' in existing:
                cursor.execute("""
                    SELECT from_wallet, to_wallet, amount, transaction_type,
                           description, created_by, created_at
                    FROM banker_transactions
                    ORDER BY created_at
                """)
                transactions = cursor.fetchall()
                
                for row in transactions:
                    if not dry_run:
                        core_db.save_transaction(
                            from_wallet=row['from_wallet'],
                            to_wallet=row['to_wallet'],
                            amount=row['amount'],
                            transaction_type=row['transaction_type'],
                            description=row['description'],
                            created_by=row['created_by']
                        )
                    transactions_count += 1
            
            if not dry_run:
                core_db.record_migration(
                    source_db=str(legacy_path),
                    wallets_count=wallets_count,
                    transactions_count=transactions_count
                )
            
            logger.info(
                f"{'[DRY-RUN] ' if dry_run else ''}Server {server_id}: "
                f"{wallets_count} wallets, {transactions_count} transactions "
                f"from {legacy_path.name}"
            )
            return (wallets_count, transactions_count)
            
    except Exception as e:
        logger.error(f"Failed to migrate server {server_id}: {e}")
        raise


def run_migration(dry_run: bool = False, server_id: Optional[str] = None):
    """Run migration for all servers or a specific server."""
    logger.info("=" * 60)
    logger.info(f"Banker Database Migration {'[DRY-RUN]' if dry_run else ''}")
    logger.info("Source: roles_<personality>.db")
    logger.info("Target:  databases/{server_id}/roles/banker.db")
    logger.info("=" * 60)
    
    if server_id:
        server_ids = [server_id]
    else:
        server_ids = get_all_server_ids()
    
    logger.info(f"Processing {len(server_ids)} server(s)")
    
    total_wallets = 0
    total_transactions = 0
    servers_migrated = 0
    servers_skipped = 0
    
    for sid in server_ids:
        try:
            wallets, transactions = migrate_server(sid, dry_run=dry_run)
            if wallets > 0 or transactions > 0:
                total_wallets += wallets
                total_transactions += transactions
                servers_migrated += 1
            else:
                servers_skipped += 1
        except Exception as e:
            logger.error(f"Skipping server {sid} due to error: {e}")
            continue
    
    logger.info("=" * 60)
    if dry_run:
        logger.info("DRY-RUN complete — no changes made")
    else:
        logger.info("Migration Complete")
    logger.info(f"Servers processed: {servers_migrated} migrated, {servers_skipped} skipped")
    logger.info(f"Total wallets: {total_wallets}")
    logger.info(f"Total transactions: {total_transactions}")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate banker data to dedicated database")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--server-id", type=str, help="Migrate only specific server")
    args = parser.parse_args()
    
    run_migration(dry_run=args.dry_run, server_id=args.server_id)
