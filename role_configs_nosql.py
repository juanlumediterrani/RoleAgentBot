"""NoSQL-based role configs using JsonStore and JsonlRingBuffer.

Replaces SQLite tables for role configuration and history with JSON/JSONL storage:
- databases/{server_id}/roles/poe2_subscriptions.json
- databases/{server_id}/roles/watcher_subscriptions.json
- databases/{server_id}/roles/dice_game_stats.json
- databases/{server_id}/roles/nordic_runes.jsonl (history)
- databases/{server_id}/roles/ring_accusations.jsonl (history)
- databases/{server_id}/roles/dice_game_history.jsonl (history)
- databases/{server_id}/roles/beggar_subrole.json

NOTE: Banker role remains on SQLite (critical data).
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from persistence.json_store import JsonStore
from persistence.jsonl_store import JsonlRingBuffer
from agent_logging import get_logger

logger = get_logger("role_configs_nosql")


class RoleConfigsNoSQL:
    """NoSQL-based role configuration and history storage.

    File structure:
    - databases/{server_id}/roles/
      - poe2_subscriptions.json: {user_id: {server_id: {...subscription...}}}
      - watcher_subscriptions.json: {user_id: {channel_id: {category: {...subscription...}}}}
      - dice_game_stats.json: {user_id: {...stats...}}
      - beggar_subrole.json: {user_id: {...subrole_data...}}
      - nordic_runes.jsonl: JSON lines of rune readings (history, max 100)
      - ring_accusations.jsonl: JSON lines of accusations (history, max 100)
      - dice_game_history.jsonl: JSON lines of game plays (history, max 200)
    """

    def __init__(self, server_id: str, db_dir: Optional[Path] = None):
        self.server_id = str(server_id)
        if db_dir is None:
            db_dir = Path(__file__).parent / "databases" / self.server_id / "roles"
            db_dir.mkdir(parents=True, exist_ok=True)
        else:
            db_dir = Path(db_dir)

        # Initialize stores
        self._poe2_subscriptions = JsonStore(
            db_dir / "poe2_subscriptions.json",
            default_factory=lambda: {},
            keep_backup=False,
        )

        self._watcher_subscriptions = JsonStore(
            db_dir / "watcher_subscriptions.json",
            default_factory=lambda: {},
            keep_backup=False,
        )

        self._dice_game_stats = JsonStore(
            db_dir / "dice_game_stats.json",
            default_factory=lambda: {},
            keep_backup=False,
        )

        self._beggar_subrole = JsonStore(
            db_dir / "beggar_subrole.json",
            default_factory=lambda: {},
            keep_backup=False,
        )

        self._nordic_runes = JsonlRingBuffer(
            db_dir / "nordic_runes.jsonl",
            max_lines=100,
            max_bytes=200 * 1024,
            keep_lines=80,
        )

        self._ring_accusations = JsonlRingBuffer(
            db_dir / "ring_accusations.jsonl",
            max_lines=100,
            max_bytes=200 * 1024,
            keep_lines=80,
        )

        self._dice_game_history = JsonlRingBuffer(
            db_dir / "dice_game_history.jsonl",
            max_lines=200,
            max_bytes=500 * 1024,
            keep_lines=150,
        )

        self._beggar_request_history = JsonlRingBuffer(
            db_dir / "beggar_request_history.jsonl",
            max_lines=500,
            max_bytes=500 * 1024,
            keep_lines=400,
        )

        logger.info(f"🗄️ [NoSQL Role Configs] Initialized for server {server_id} at {db_dir}")

    # --- POE2 Subscriptions ---

    def save_poe2_subscription(
        self,
        user_id: str,
        server_id: str,
        league: str = "Standard",
        tracked_items: Optional[List[str]] = None,
        purchases: Optional[List[Dict]] = None,
    ) -> bool:
        """Create or update a POE2 subscription for a user on a server."""
        try:
            now = datetime.now().isoformat()

            def updater(state: Dict) -> Dict:
                user_subs = state.get(str(user_id), {})
                user_subs[str(server_id)] = {
                    "league": league,
                    "tracked_items": tracked_items or [],
                    "purchases": purchases or [],
                    "created_at": user_subs.get(str(server_id), {}).get("created_at", now),
                    "updated_at": now,
                }
                state[str(user_id)] = user_subs
                return state

            self._poe2_subscriptions.update(updater)
            logger.debug(f"Saved POE2 subscription for user {user_id} in server {server_id}")
            return True
        except Exception as e:
            logger.exception(f"Failed to save POE2 subscription: {e}")
            return False

    def get_poe2_subscription(self, user_id: str, server_id: str) -> Optional[Dict[str, Any]]:
        """Get a POE2 subscription for a user on a server."""
        try:
            state = self._poe2_subscriptions.load()
            user_subs = state.get(str(user_id), {})
            return user_subs.get(str(server_id))
        except Exception as e:
            logger.exception(f"Failed to get POE2 subscription: {e}")
            return None

    def get_poe2_server_subscriptions(self, server_id: str) -> List[Dict[str, Any]]:
        """Get all POE2 subscriptions for a server."""
        try:
            state = self._poe2_subscriptions.load()
            subscriptions = []
            for uid, user_subs in state.items():
                if str(server_id) in user_subs:
                    sub = user_subs[str(server_id)].copy()
                    sub["user_id"] = uid
                    sub["server_id"] = server_id
                    subscriptions.append(sub)
            # Sort by updated_at descending
            subscriptions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return subscriptions
        except Exception as e:
            logger.exception(f"Failed to get POE2 server subscriptions: {e}")
            return []

    def delete_poe2_subscription(self, user_id: str, server_id: str) -> bool:
        """Delete a POE2 subscription for a user on a server."""
        try:
            def updater(state: Dict) -> Dict:
                user_subs = state.get(str(user_id), {})
                if str(server_id) in user_subs:
                    del user_subs[str(server_id)]
                state[str(user_id)] = user_subs
                return state

            self._poe2_subscriptions.update(updater)
            logger.debug(f"Deleted POE2 subscription for user {user_id} in server {server_id}")
            return True
        except Exception as e:
            logger.exception(f"Failed to delete POE2 subscription: {e}")
            return False

    # --- Watcher Subscriptions ---

    def save_watcher_subscription(
        self,
        user_id: str,
        channel_id: str,
        category: str,
        feed_id: Optional[int] = None,
        premises: Optional[str] = None,
        keywords: Optional[str] = None,
        method: str = "general",
        is_active: bool = True,
        created_by: Optional[str] = None,
    ) -> bool:
        """Save a news watcher subscription."""
        try:
            now = datetime.now().isoformat()

            def updater(state: Dict) -> Dict:
                if str(user_id) not in state:
                    state[str(user_id)] = {}
                if str(channel_id) not in state[str(user_id)]:
                    state[str(user_id)][str(channel_id)] = {}

                state[str(user_id)][str(channel_id)][category] = {
                    "feed_id": feed_id,
                    "premises": premises,
                    "keywords": keywords,
                    "method": method,
                    "is_active": is_active,
                    "subscribed_at": state[str(user_id)][str(channel_id)].get(category, {}).get("subscribed_at", now),
                    "created_by": created_by,
                }
                return state

            self._watcher_subscriptions.update(updater)
            logger.debug(f"Saved watcher subscription for user {user_id} channel {channel_id} category {category}")
            return True
        except Exception as e:
            logger.exception(f"Failed to save watcher subscription: {e}")
            return False

    def get_watcher_subscriptions(
        self,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get watcher subscriptions with optional filters."""
        try:
            state = self._watcher_subscriptions.load()
            subscriptions = []

            for uid, channels in state.items():
                if user_id and str(uid) != str(user_id):
                    continue
                for ch_id, cats in channels.items():
                    if channel_id and str(ch_id) != str(channel_id):
                        continue
                    for cat, data in cats.items():
                        if category and cat != category:
                            continue
                        subscriptions.append({
                            "user_id": uid,
                            "channel_id": ch_id,
                            "category": cat,
                            **data,
                        })
            return subscriptions
        except Exception as e:
            logger.exception(f"Failed to get watcher subscriptions: {e}")
            return []

    def delete_watcher_subscription(self, user_id: str, channel_id: str, category: str) -> bool:
        """Delete a watcher subscription."""
        try:
            def updater(state: Dict) -> Dict:
                if str(user_id) in state and str(channel_id) in state[str(user_id)]:
                    if category in state[str(user_id)][str(channel_id)]:
                        del state[str(user_id)][str(channel_id)][category]
                return state

            self._watcher_subscriptions.update(updater)
            logger.debug(f"Deleted watcher subscription for user {user_id} channel {channel_id} category {category}")
            return True
        except Exception as e:
            logger.exception(f"Failed to delete watcher subscription: {e}")
            return False

    def soft_delete_watcher_subscription(self, user_id: str, channel_id: str, category: str) -> bool:
        """Soft delete a watcher subscription (set is_active=False)."""
        try:
            def updater(state: Dict) -> Dict:
                if str(user_id) in state and str(channel_id) in state[str(user_id)]:
                    if category in state[str(user_id)][str(channel_id)]:
                        state[str(user_id)][str(channel_id)][category]["is_active"] = False
                return state

            self._watcher_subscriptions.update(updater)
            logger.debug(f"Soft deleted watcher subscription for user {user_id} channel {channel_id} category {category}")
            return True
        except Exception as e:
            logger.exception(f"Failed to soft delete watcher subscription: {e}")
            return False

    def get_watcher_users_with_active_subscriptions(self) -> List[str]:
        """Get all user_ids who have active personal subscriptions (user_id only, no channel_id)."""
        try:
            state = self._watcher_subscriptions.load()
            users = set()
            for uid, channels in state.items():
                for ch_id, cats in channels.items():
                    # Personal subscriptions have channel_id = None (stored as empty string or None)
                    if ch_id is None or ch_id == "" or ch_id == "None":
                        for cat, data in cats.items():
                            if data.get("is_active", True):
                                users.add(uid)
                                break
            return list(users)
        except Exception as e:
            logger.exception(f"Failed to get users with active subscriptions: {e}")
            return []

    # --- Dice Game Stats ---

    def save_dice_game_stats(
        self,
        user_id: str,
        total_plays: int = 0,
        total_bet: int = 0,
        total_won: int = 0,
        pots_won: int = 0,
        biggest_prize: int = 0,
        last_play: Optional[str] = None,
    ) -> bool:
        """Save or update dice game statistics for a user."""
        try:
            now = datetime.now().isoformat()

            def updater(state: Dict) -> Dict:
                existing = state.get(str(user_id), {})
                state[str(user_id)] = {
                    "total_plays": total_plays,
                    "total_bet": total_bet,
                    "total_won": total_won,
                    "pots_won": pots_won,
                    "biggest_prize": biggest_prize,
                    "last_play": last_play,
                    "created_at": existing.get("created_at", now),
                    "updated_at": now,
                }
                return state

            self._dice_game_stats.update(updater)
            logger.debug(f"Saved dice game stats for user {user_id}")
            return True
        except Exception as e:
            logger.exception(f"Failed to save dice game stats: {e}")
            return False

    def get_dice_game_stats(self, user_id: str) -> Dict[str, Any]:
        """Get dice game statistics for a user."""
        try:
            state = self._dice_game_stats.load()
            stats = state.get(str(user_id))
            if stats:
                return stats
            return {
                "total_plays": 0,
                "total_bet": 0,
                "total_won": 0,
                "pots_won": 0,
                "biggest_prize": 0,
                "last_play": None,
                "created_at": None,
                "updated_at": None,
            }
        except Exception as e:
            logger.exception(f"Failed to get dice game stats: {e}")
            return {}

    # --- Dice Game History ---

    def save_dice_game_play(
        self,
        user_id: str,
        user_name: str,
        bet: int,
        dice: str,
        combination: str,
        prize: int,
        pot_before: int,
        pot_after: int,
    ) -> bool:
        """Save a dice game play to history."""
        try:
            record = {
                "user_id": str(user_id),
                "user_name": user_name,
                "bet": bet,
                "dice": dice,
                "combination": combination,
                "prize": prize,
                "pot_before": pot_before,
                "pot_after": pot_after,
                "created_at": datetime.now().isoformat(),
            }
            self._dice_game_history.append(record)
            logger.debug(f"Saved dice game play for user {user_id}")
            return True
        except Exception as e:
            logger.exception(f"Failed to save dice game play: {e}")
            return False

    def get_dice_game_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent dice game plays."""
        try:
            records = list(self._dice_game_history.tail(limit))
            return records
        except Exception as e:
            logger.exception(f"Failed to get dice game history: {e}")
            return []

    # --- Nordic Runes History ---

    def save_nordic_runes_reading(
        self,
        user_id: str,
        question: str,
        runes_drawn: List[str],
        interpretation: str,
        reading_type: str,
    ) -> bool:
        """Save a rune reading to history."""
        try:
            record = {
                "user_id": str(user_id),
                "question": question,
                "runes_drawn": runes_drawn,
                "interpretation": interpretation,
                "reading_type": reading_type,
                "created_at": datetime.now().isoformat(),
            }
            self._nordic_runes.append(record)
            logger.debug(f"Saved nordic runes reading for user {user_id}")
            return True
        except Exception as e:
            logger.exception(f"Failed to save nordic runes reading: {e}")
            return False

    def get_nordic_runes_readings(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent rune readings for a user."""
        try:
            records = list(
                self._nordic_runes.filter_tail(
                    lambda r: r.get("user_id") == str(user_id),
                    limit=limit,
                )
            )
            return records
        except Exception as e:
            logger.exception(f"Failed to get nordic runes readings: {e}")
            return []

    # --- Ring Accusations History ---

    def save_ring_accusation(
        self,
        accuser_id: str,
        accused_id: str,
        accusation: str,
        evidence: Optional[str] = None,
    ) -> bool:
        """Save a ring accusation to history."""
        try:
            record = {
                "accuser_id": str(accuser_id),
                "accused_id": str(accused_id),
                "accusation": accusation,
                "evidence": evidence,
                "created_at": datetime.now().isoformat(),
            }
            self._ring_accusations.append(record)
            logger.debug(f"Saved ring accusation for accuser {accuser_id}")
            return True
        except Exception as e:
            logger.exception(f"Failed to save ring accusation: {e}")
            return False

    def get_ring_accusations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent ring accusations."""
        try:
            records = list(self._ring_accusations.tail(limit))
            return records
        except Exception as e:
            logger.exception(f"Failed to get ring accusations: {e}")
            return []

    # --- Beggar Subrole ---

    def save_beggar_subrole(
        self,
        user_id: str,
        user_name: str,
        total_donated: int = 0,
        weekly_donated: int = 0,
        donation_count: int = 0,
        weekly_donation_count: int = 0,
        first_donation: Optional[str] = None,
        last_donation: Optional[str] = None,
        last_donation_amount: int = 0,
        last_reason: str = "",
    ) -> bool:
        """Save or update beggar subrole data for a user."""
        try:
            now = datetime.now().isoformat()

            def updater(state: Dict) -> Dict:
                existing = state.get(str(user_id), {})
                state[str(user_id)] = {
                    "user_name": user_name,
                    "total_donated": total_donated,
                    "weekly_donated": weekly_donated,
                    "donation_count": donation_count,
                    "weekly_donation_count": weekly_donation_count,
                    "first_donation": first_donation or existing.get("first_donation"),
                    "last_donation": last_donation,
                    "last_donation_amount": last_donation_amount,
                    "last_reason": last_reason,
                    "created_at": existing.get("created_at", now),
                    "updated_at": now,
                }
                return state

            self._beggar_subrole.update(updater)
            logger.debug(f"Saved beggar subrole for user {user_id}")
            return True
        except Exception as e:
            logger.exception(f"Failed to save beggar subrole: {e}")
            return False

    def get_beggar_subrole(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get beggar subrole data for a user."""
        try:
            state = self._beggar_subrole.load()
            return state.get(str(user_id))
        except Exception as e:
            logger.exception(f"Failed to get beggar subrole: {e}")
            return None

    def get_all_beggar_subroles(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all beggar subrole data sorted by total donated."""
        try:
            state = self._beggar_subrole.load()
            subroles = []
            for uid, data in state.items():
                subroles.append({"user_id": uid, **data})
            subroles.sort(key=lambda x: x.get("total_donated", 0), reverse=True)
            return subroles[:limit]
        except Exception as e:
            logger.exception(f"Failed to get all beggar subroles: {e}")
            return []

    # --- Beggar Request History ---

    def save_beggar_request(
        self,
        user_id: str,
        user_name: str,
        request_type: str,
        message: str,
        channel_id: Optional[str] = None,
        metadata: Optional[str] = None,
    ) -> bool:
        """Append a beggar request event to the history JSONL."""
        try:
            entry = {
                "user_id": str(user_id),
                "user_name": user_name,
                "request_type": request_type,
                "message": message,
                "channel_id": channel_id,
                "metadata": metadata,
                "created_at": datetime.now().isoformat(),
            }
            self._beggar_request_history.append(entry)
            return True
        except Exception as e:
            logger.exception(f"Failed to save beggar request: {e}")
            return False

    def count_beggar_requests_type_last_day(self, request_type: str) -> int:
        """Count beggar requests of a given type in the last 24h."""
        try:
            from datetime import timedelta
            cutoff = datetime.now() - timedelta(days=1)
            count = 0
            for entry in self._beggar_request_history.tail(500):
                if entry.get("request_type") != request_type:
                    continue
                ts = entry.get("created_at")
                if not ts:
                    continue
                try:
                    if datetime.fromisoformat(ts) >= cutoff:
                        count += 1
                except Exception:
                    continue
            return count
        except Exception as e:
            logger.exception(f"Failed to count beggar requests: {e}")
            return 0

    def reset_beggar_weekly_cycle(self) -> bool:
        """Reset weekly_donated/weekly_donation_count for all users."""
        try:
            def updater(state: Dict) -> Dict:
                for uid, data in state.items():
                    data["weekly_donated"] = 0
                    data["weekly_donation_count"] = 0
                return state
            self._beggar_subrole.update(updater)
            return True
        except Exception as e:
            logger.exception(f"Failed to reset beggar weekly cycle: {e}")
            return False


# ---------------------------------------------------------------------------
# Module-level factory (one instance per server_id)
# ---------------------------------------------------------------------------

_instances: Dict[str, "RoleConfigsNoSQL"] = {}


def get_role_configs_nosql(server_id: str) -> "RoleConfigsNoSQL":
    """Return (creating if necessary) the RoleConfigsNoSQL for a server."""
    key = str(server_id)
    if key not in _instances:
        _instances[key] = RoleConfigsNoSQL(server_id=key)
    return _instances[key]
