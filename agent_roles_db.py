"""
Roles Database Module
Centralized database management for all roles and subroles configuration.
All data has been migrated to NoSQL (role_configs_nosql.py).
"""

import json
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
from agent_logging import get_logger

logger = get_logger('agent_roles_db')


class RolesDatabase:
    """Centralized database handler for all roles configuration.
    
    All data has been migrated to NoSQL (role_configs_nosql.py).
    This class is kept for backward compatibility and delegates to NoSQL.
    """
    
    def __init__(self, server_id: str = None):
        """Initialize NoSQL-backed roles database.
        
        Args:
            server_id: Server ID. Must be a valid server ID, not None or 'default'.
        
        Raises:
            ValueError: If server_id is None, 'default'.
        """
        if not server_id or server_id == "default":
            raise ValueError(f"RolesDatabase requires a valid server_id, got: {server_id}")
        
        self.server_id = server_id
        self.db_path = None  # No longer uses SQLite
        self._lock = threading.RLock()
        self._nosql_cache = None
        logger.info(f"RolesDatabase initialized (NoSQL-backed) for server {server_id}")

    @property
    def _nosql(self):
        """Lazy accessor for the NoSQL role-configs facade (per server)."""
        if self._nosql_cache is None:
            from roles.role_configs_nosql import get_role_configs_nosql
            self._nosql_cache = get_role_configs_nosql(self.server_id)
        return self._nosql_cache
    
    # ─────────────────────────────────────────────────────────────────────
    # Nordic runes migrated to NoSQL - legacy wrappers removed (2026-04-29)
    # Code now uses RoleConfigsNoSQL directly via nordic_runes_discord.py
    # ─────────────────────────────────────────────────────────────────────

    def save_ring_accusation(self, accuser_id: str, accused_id: str,
                             accusation: str, evidence: str = None) -> int:
        """Save a ring accusation (NoSQL-backed)."""
        try:
            self._nosql.save_ring_accusation(accuser_id, accused_id, accusation, evidence)
            return 0
        except Exception as e:
            logger.error(f"Failed to save ring accusation: {e}")
            raise

    def get_ring_accusations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent ring accusations (NoSQL-backed)."""
        return self._nosql.get_ring_accusations(limit)

    def save_dice_game_stats(self, user_id: str, total_plays: int = 0,
                             total_bet: int = 0, total_won: int = 0, pots_won: int = 0,
                             biggest_prize: int = 0, last_play: str = None) -> bool:
        """Save dice game stats (NoSQL-backed)."""
        return self._nosql.save_dice_game_stats(
            user_id, total_plays=total_plays, total_bet=total_bet,
            total_won=total_won, pots_won=pots_won,
            biggest_prize=biggest_prize, last_play=last_play,
        )

    def get_dice_game_stats(self, user_id: str) -> Dict[str, Any]:
        """Get dice game stats (NoSQL-backed). Returns zeroed dict if missing."""
        data = self._nosql.get_dice_game_stats(user_id)
        if data:
            return data
        return {
            'total_plays': 0, 'total_bet': 0, 'total_won': 0, 'pots_won': 0,
            'biggest_prize': 0, 'last_play': None, 'created_at': None, 'updated_at': None,
        }

    def save_dice_game_play(self, user_id: str, user_name: str, bet: int,
                            dice: str, combination: str, prize: int,
                            pot_before: int, pot_after: int) -> int:
        """Save a dice game play (NoSQL-backed)."""
        try:
            self._nosql.save_dice_game_play(
                user_id, user_name, bet, dice, combination, prize, pot_before, pot_after,
            )
            return 0
        except Exception as e:
            logger.error(f"Failed to save dice game play: {e}")
            raise

    def get_dice_game_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent dice game plays (NoSQL-backed)."""
        return self._nosql.get_dice_game_history(limit)

    def save_cubilete_stats(self, user_id: str, total_plays: int = 0,
                             total_bet: int = 0, total_won: int = 0, pots_won: int = 0,
                             biggest_prize: int = 0, last_play: str = None) -> bool:
        """Save cubilete stats (NoSQL-backed)."""
        return self._nosql.save_cubilete_stats(
            user_id, total_plays=total_plays, total_bet=total_bet,
            total_won=total_won, pots_won=pots_won,
            biggest_prize=biggest_prize, last_play=last_play,
        )

    def get_cubilete_stats(self, user_id: str) -> Dict[str, Any]:
        """Get cubilete stats (NoSQL-backed). Returns zeroed dict if missing."""
        data = self._nosql.get_cubilete_stats(user_id)
        if data:
            return data
        return {
            'total_plays': 0, 'total_bet': 0, 'total_won': 0, 'pots_won': 0,
            'biggest_prize': 0, 'last_play': None, 'created_at': None, 'updated_at': None,
        }

    def save_cubilete_play(self, user_id: str, user_name: str, bet: int,
                            dice: str, combination: str, prize: int,
                            pot_before: int, pot_after: int) -> int:
        """Save a cubilete play (NoSQL-backed)."""
        try:
            self._nosql.save_cubilete_play(
                user_id, user_name, bet, dice, combination, prize, pot_before, pot_after,
            )
            return 0
        except Exception as e:
            logger.error(f"Failed to save cubilete play: {e}")
            raise

    def get_cubilete_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent cubilete plays (NoSQL-backed)."""
        return self._nosql.get_cubilete_history(limit)

    def is_role_enabled(self, role_name: str, server_id: str) -> bool:
        """Check if a role is enabled for a server - DEPRECATED: Use server_config.is_role_enabled instead."""
        from discord_bot.canvas.server_config import is_role_enabled as server_is_role_enabled
        return server_is_role_enabled(server_id, role_name, default_enabled=True)
    
    def set_role_enabled(self, role_name: str, server_id: str, enabled: bool) -> bool:
        """Enable or disable a role for a server - DEPRECATED: Use server_config.set_role_config instead."""
        from discord_bot.canvas.server_config import set_role_config as server_set_role_config
        return server_set_role_config(server_id, role_name, enabled)

    def get_all_roles_with_subroles(self) -> Dict[str, Any]:
        """Get all roles with subroles from server_config.json.
        
        Returns:
            Dict containing roles configuration from server_config.json
        """
        try:
            import os
            import json
            _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
            server_config_path = os.path.join(_BASE_DIR, "databases", self.server_id, "server_config.json")
            with open(server_config_path, encoding="utf-8") as f:
                config = json.load(f)
            return config.get("roles", {})
        except Exception as e:
            logger.error(f"Failed to load roles from server_config.json for server {self.server_id}: {e}")
            return {}

    def save_poe2_subscription(self, user_id: str, server_id: str, league: str = "Standard",
                                tracked_items: Optional[List[str]] = None,
                                purchases: Optional[List[Dict]] = None) -> bool:
        """Create or update a POE2 subscription (NoSQL-backed)."""
        return self._nosql.save_poe2_subscription(
            user_id, server_id, league=league,
            tracked_items=tracked_items, purchases=purchases,
        )

    def get_poe2_subscription(self, user_id: str, server_id: str) -> Optional[Dict[str, Any]]:
        """Get a POE2 subscription (NoSQL-backed)."""
        return self._nosql.get_poe2_subscription(user_id, server_id)

    def get_poe2_server_subscriptions(self, server_id: str) -> List[Dict[str, Any]]:
        """Get all POE2 subscriptions for a server (NoSQL-backed)."""
        return self._nosql.get_poe2_server_subscriptions(server_id)

    def delete_poe2_subscription(self, user_id: str, server_id: str) -> bool:
        """Delete a POE2 subscription (NoSQL-backed)."""
        return self._nosql.delete_poe2_subscription(user_id, server_id)
    
    def migrate_legacy_beggar_data(self, server_id: str) -> bool:
        """Migrate beggar data from the dedicated beggar database into roles.db."""
        legacy_path = Path(get_database_path(server_id, 'beggar'))
        if not legacy_path.exists():
            return False
        
        try:
            migrated_any = False
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    with sqlite3.connect(legacy_path) as legacy_conn:
                        legacy_cursor = legacy_conn.cursor()
                        
                        legacy_cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                        legacy_tables = {row[0] for row in legacy_cursor.fetchall()}
                        
                        if 'beggar_requests' in legacy_tables:
                            legacy_cursor.execute("""
                                SELECT user_id, user_name, request_type, message, channel_id, server_id, metadata, created_at
                                FROM beggar_requests
                                WHERE server_id = ?
                            """, (server_id,))
                            for row in legacy_cursor.fetchall():
                                cursor.execute("""
                                    INSERT INTO beggar_request_history
                                    (server_id, user_id, user_name, request_type, message, channel_id, metadata, created_at)
                                    SELECT ?, ?, ?, ?, ?, ?, ?, ?
                                    WHERE NOT EXISTS (
                                        SELECT 1
                                        FROM beggar_request_history
                                        WHERE server_id = ?
                                          AND user_id = ?
                                          AND request_type = ?
                                          AND message = ?
                                          AND created_at = ?
                                    )
                                """, (
                                    row[5] or server_id,
                                    row[0],
                                    row[1],
                                    row[2],
                                    row[3],
                                    row[4],
                                    row[6],
                                    row[7],
                                    row[5] or server_id,
                                    row[0],
                                    row[2],
                                    row[3],
                                    row[7],
                                ))
                                migrated_any = migrated_any or cursor.rowcount > 0
                        
                        if 'beggar_config' in legacy_tables:
                            legacy_cursor.execute("""
                                SELECT frequency_hours, last_reason, target_gold
                                FROM beggar_config
                                WHERE server_id = ?
                            """, (server_id,))
                            config_row = legacy_cursor.fetchone()
                            if config_row:
                                role_config = self.get_role_config('beggar')
                                config_data_raw = role_config.get('config_data') or '{}'
                                try:
                                    config_data = json.loads(config_data_raw)
                                except Exception:
                                    config_data = {}
                                if 'frequency_hours' not in config_data:
                                    config_data['frequency_hours'] = config_row[0]
                                if not config_data.get('current_reason') and config_row[1]:
                                    config_data['current_reason'] = config_row[1]
                                if 'target_gold' not in config_data:
                                    config_data['target_gold'] = config_row[2] or 0
                                enabled = role_config.get('enabled', False)
                                if not enabled and 'beggar_subscriptions' in legacy_tables:
                                    legacy_cursor.execute("""
                                        SELECT COUNT(*)
                                        FROM beggar_subscriptions
                                        WHERE server_id = ?
                                    """, (server_id,))
                                    enabled = (legacy_cursor.fetchone() or [0])[0] > 0
                                self.save_role_config('beggar', enabled, json.dumps(config_data))
                                migrated_any = True
                    conn.commit()
            if migrated_any:
                logger.info(f"Migrated legacy beggar data into roles.db for server {server_id}")
            return migrated_any
        except Exception as e:
            logger.error(f"Failed to migrate legacy beggar data: {e}")
            return False
    
    # NOTE: Banker methods (save_banker_wallet, get_banker_wallet, update_banker_balance,
    # save_banker_transaction, get_banker_transactions, get_all_banker_wallets) have been
    # moved to roles/banker/db_banker_core.py (dedicated databases/{server_id}/roles/banker.db).
    # Use roles.banker.banker_db.get_banker_roles_db_instance(server_id) instead.

    # ─── Beggar subrole methods (NoSQL-backed) ───

    def update_beggar_donation(self, user_id: str, user_name: str, amount: int, reason: str = "") -> bool:
        """Update beggar donation record for a user (NoSQL-backed)."""
        try:
            existing = self._nosql.get_beggar_subrole(user_id) or {}
            now = datetime.now().isoformat()
            new_total = existing.get('total_donated', 0) + amount
            new_weekly_total = existing.get('weekly_donated', 0) + amount
            new_count = existing.get('donation_count', 0) + 1
            new_weekly_count = existing.get('weekly_donation_count', 0) + 1
            first_donation = existing.get('first_donation') or now
            ok = self._nosql.save_beggar_subrole(
                user_id=user_id,
                user_name=user_name,
                total_donated=new_total,
                weekly_donated=new_weekly_total,
                donation_count=new_count,
                weekly_donation_count=new_weekly_count,
                first_donation=first_donation,
                last_donation=now,
                last_donation_amount=amount,
                last_reason=reason,
            )
            if ok:
                logger.info(f"Beggar donation {user_name}: +{amount} (weekly: {new_weekly_total}, total: {new_total})")
            return ok
        except Exception as e:
            logger.error(f"Failed to update beggar donation: {e}")
            return False

    def save_beggar_request(self, user_id: str, user_name: str, request_type: str,
                            message: str, channel_id: Optional[str] = None,
                            metadata: Optional[str] = None) -> bool:
        """Save a beggar request event (NoSQL-backed)."""
        return self._nosql.save_beggar_request(user_id, user_name, request_type, message, channel_id, metadata)

    def count_beggar_requests_type_last_day(self, request_type: str, server_id: Optional[str] = None) -> int:
        """Count beggar request events in the last 24h (NoSQL-backed).

        Note: per-server filtering is intrinsic because each server has its own JSONL.
        """
        return self._nosql.count_beggar_requests_type_last_day(request_type)

    def get_beggar_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get beggar statistics for a specific user (NoSQL-backed)."""
        data = self._nosql.get_beggar_subrole(user_id)
        if data:
            return {
                'total_donated': data.get('total_donated', 0),
                'weekly_donated': data.get('weekly_donated', 0),
                'donation_count': data.get('donation_count', 0),
                'weekly_donation_count': data.get('weekly_donation_count', 0),
                'first_donation': data.get('first_donation'),
                'last_donation': data.get('last_donation'),
                'last_donation_amount': data.get('last_donation_amount', 0),
                'last_reason': data.get('last_reason', ''),
                'created_at': data.get('created_at'),
                'updated_at': data.get('updated_at'),
            }
        return {
            'total_donated': 0, 'weekly_donated': 0, 'donation_count': 0, 'weekly_donation_count': 0,
            'first_donation': None, 'last_donation': None, 'last_donation_amount': 0, 'last_reason': '',
            'created_at': None, 'updated_at': None,
        }

    def get_weekly_donations_summary(self) -> List[Dict[str, Any]]:
        """Summary of users who donated this week (NoSQL-backed)."""
        try:
            out = []
            for entry in self._nosql.get_all_beggar_subroles(limit=500):
                if entry.get('weekly_donated', 0) > 0:
                    out.append({
                        'user_id': entry.get('user_id'),
                        'donor_name': entry.get('user_name'),
                        'weekly_amount': entry.get('weekly_donated', 0),
                        'weekly_count': entry.get('weekly_donation_count', 0),
                        'last_donation': entry.get('last_donation'),
                    })
            out.sort(key=lambda x: (-x['weekly_amount'], x.get('last_donation') or ''), reverse=False)
            # secondary sort by last_donation desc – re-sort primarily by amount desc
            out.sort(key=lambda x: x['weekly_amount'], reverse=True)
            return out
        except Exception as e:
            logger.error(f"Failed to get weekly donations summary: {e}")
            return []

    def get_recent_beggar_donations(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Recent beggar donations (NoSQL-backed), sorted by last_donation desc."""
        try:
            candidates = []
            for e in self._nosql.get_all_beggar_subroles(limit=1000):
                if e.get('weekly_donated', 0) > 0 or e.get('total_donated', 0) > 0:
                    candidates.append(e)
            candidates.sort(key=lambda x: x.get('last_donation') or '', reverse=True)
            return [{
                'user_id': e.get('user_id'),
                'donor_name': e.get('user_name'),
                'amount': e.get('last_donation_amount', 0),
                'donation_count': e.get('donation_count', 0),
                'last_donation': e.get('last_donation'),
                'reason': e.get('last_reason', ''),
                'weekly_donated': e.get('weekly_donated', 0),
                'weekly_donation_count': e.get('weekly_donation_count', 0),
                'total_donated': e.get('total_donated', 0),
            } for e in candidates[:limit]]
        except Exception as e:
            logger.error(f"Failed to get recent beggar donations: {e}")
            return []

    def get_beggar_leaderboard(self, server_id: str, limit: int = 10, weekly_only: bool = False) -> List[Dict[str, Any]]:
        """Top beggar donors (NoSQL-backed)."""
        try:
            donated_field = 'weekly_donated' if weekly_only else 'total_donated'
            count_field = 'weekly_donation_count' if weekly_only else 'donation_count'
            rows = [e for e in self._nosql.get_all_beggar_subroles(limit=1000) if e.get(donated_field, 0) > 0]
            rows.sort(key=lambda x: x.get(donated_field, 0), reverse=True)
            return [{
                'user_id': e.get('user_id'),
                'user_name': e.get('user_name'),
                'total_donated': e.get(donated_field, 0),
                'donation_count': e.get(count_field, 0),
                'last_donation': e.get('last_donation'),
                'created_at': e.get('created_at'),
                'historical_total_donated': e.get('total_donated', 0),
                'weekly_donated': e.get('weekly_donated', 0),
                'last_reason': e.get('last_reason', ''),
            } for e in rows[:limit]]
        except Exception as e:
            logger.error(f"Failed to get beggar leaderboard: {e}")
            return []

    def get_beggar_server_stats(self, server_id: str, weekly_only: bool = False) -> Dict[str, Any]:
        """Overall beggar stats for the server (NoSQL-backed)."""
        try:
            donated_field = 'weekly_donated' if weekly_only else 'total_donated'
            count_field = 'weekly_donation_count' if weekly_only else 'donation_count'
            donors = 0
            total_gold = 0
            total_donations = 0
            historical_total_gold = 0
            for e in self._nosql.get_all_beggar_subroles(limit=1000):
                if e.get(donated_field, 0) > 0:
                    donors += 1
                    total_gold += e.get(donated_field, 0)
                    total_donations += e.get(count_field, 0)
                    historical_total_gold += e.get('total_donated', 0)
            return {
                'total_donors': donors,
                'total_gold': total_gold,
                'total_donations': total_donations,
                'historical_total_gold': historical_total_gold,
                'period': 'weekly' if weekly_only else 'historical',
            }
        except Exception as e:
            logger.error(f"Failed to get beggar server stats: {e}")
            return {
                'total_donors': 0, 'total_gold': 0, 'total_donations': 0,
                'historical_total_gold': 0, 'period': 'weekly' if weekly_only else 'historical',
            }

    def reset_beggar_weekly_cycle(self, server_id: str) -> bool:
        """Reset weekly counters for the server (NoSQL-backed)."""
        ok = self._nosql.reset_beggar_weekly_cycle()
        if ok:
            logger.info(f"Reset beggar weekly cycle for server {server_id}")
        return ok


# Global database instance cache
_roles_db_instances: Dict[str, RolesDatabase] = {}

def get_roles_db_instance(server_id: str = None) -> Optional[RolesDatabase]:
    """Get the roles database instance for a specific server.
    
    Args:
        server_id: Server ID. If None or "default", returns None instead of creating placeholder.
    
    Returns:
        RolesDatabase instance or None if server_id is not valid.
    """
    global _roles_db_instances
    
    # Don't create database during module import - require explicit valid server_id
    if not server_id or server_id == "default":
        logger.debug("get_roles_db_instance called without valid server_id - skipping database creation")
        return None
    
    # Use server_id as cache key (NoSQL-backed, no personality-specific paths)
    cache_key = server_id
    
    # Check if we have a cached instance for this server
    if cache_key not in _roles_db_instances:
        _roles_db_instances[cache_key] = RolesDatabase(server_id)
    
    return _roles_db_instances[cache_key]

def invalidate_roles_db_instance(server_id: str = None):
    """Invalidate cached roles database instance for a server or all servers.
    
    Call this after personality change to force NoSQL re-initialization.
    
    Args:
        server_id: Server ID to invalidate, or None to clear all.
    """
    global _roles_db_instances
    if server_id:
        # Invalidate instance for this server
        if server_id in _roles_db_instances:
            del _roles_db_instances[server_id]
            logger.info(f"🗄️ [ROLES] Invalidated cached db instance for server: {server_id}")
    else:
        _roles_db_instances.clear()
        logger.info("🗄️ [ROLES] Invalidated all cached db instances")
