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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from persistence.json_store import JsonStore
from persistence.jsonl_store import JsonlRingBuffer
from agent_logging import get_logger

# Import validation schemas
try:
    from validation.role_schemas import (
        POE2Subscription,
        WatcherSubscription,
        DiceGameStats,
        BeggarSubrole,
        NordicRunesReading,
        RingAccusation,
        MCPlaylist,
        MCQueueEntry,
        MCPreferences,
    )
    from validation.news_watcher_schemas import UserPremises
    VALIDATION_AVAILABLE = True
except ImportError:
    VALIDATION_AVAILABLE = False
    POE2Subscription = None
    WatcherSubscription = None
    DiceGameStats = None
    BeggarSubrole = None
    NordicRunesReading = None
    RingAccusation = None
    MCPlaylist = None
    MCQueueEntry = None
    MCPreferences = None
    UserPremises = None

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
            # Use project root databases directory
            db_dir = Path(__file__).parent.parent / "databases" / self.server_id / "roles"
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

        self._watcher_premises = JsonStore(
            db_dir / "watcher_premises.json",
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
            schema=NordicRunesReading if VALIDATION_AVAILABLE else None,
            validate_on_append=True,
        )

        self._ring_accusations = JsonlRingBuffer(
            db_dir / "ring_accusations.jsonl",
            max_lines=100,
            max_bytes=200 * 1024,
            keep_lines=80,
            schema=RingAccusation if VALIDATION_AVAILABLE else None,
            validate_on_append=True,
        )

        self._dice_game_history = JsonlRingBuffer(
            db_dir / "dice_game_history.jsonl",
            max_lines=200,
            max_bytes=500 * 1024,
            keep_lines=150,
            # Dice game history entries vary, schema applied at method level
        )

        self._beggar_request_history = JsonlRingBuffer(
            db_dir / "beggar_request_history.jsonl",
            max_lines=500,
            max_bytes=500 * 1024,
            keep_lines=400,
            # Beggar request history entries vary, schema applied at method level
        )

        # --- MC (Master of Ceremonies) stores ---
        self._mc_playlists = JsonStore(
            db_dir / "mc_playlists.json",
            default_factory=lambda: {},
            keep_backup=False,
        )
        self._mc_queue = JsonStore(
            db_dir / "mc_queue.json",
            default_factory=lambda: {},
            keep_backup=False,
        )
        self._mc_preferences = JsonStore(
            db_dir / "mc_preferences.json",
            default_factory=lambda: {},
            keep_backup=False,
        )
        self._mc_history = JsonlRingBuffer(
            db_dir / "mc_history.jsonl",
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

            # Validate subscription data
            if VALIDATION_AVAILABLE and POE2Subscription:
                sub_to_validate = {
                    "league": league,
                    "tracked_items": tracked_items or [],
                    "purchases": purchases or [],
                    "created_at": now,
                    "updated_at": now,
                }
                try:
                    POE2Subscription(**sub_to_validate)
                except Exception as e:
                    logger.warning(f"⚠️ [NoSQL Role] POE2 subscription validation failed: {e}. Skipping save.")
                    return False

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
            logger.info(f"[save_watcher_subscription] Called with user_id={user_id}, channel_id={channel_id}, category={category}, method={method}, VALIDATION_AVAILABLE={VALIDATION_AVAILABLE}")

            # Validate subscription data
            if VALIDATION_AVAILABLE and WatcherSubscription:
                sub_to_validate = {
                    "feed_id": feed_id,
                    "premises": premises,
                    "keywords": keywords,
                    "method": method,
                    "is_active": is_active,
                    "subscribed_at": now,
                    "created_by": created_by,
                }
                try:
                    WatcherSubscription(**sub_to_validate)
                except Exception as e:
                    logger.warning(f"⚠️ [NoSQL Role] Watcher subscription validation failed: {e}. Data: {sub_to_validate}. Skipping save.")
                    return False

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
            logger.info(f"[save_watcher_subscription] Successfully saved for user {user_id} channel {channel_id} category {category}")
            return True
        except Exception as e:
            logger.exception(f"[save_watcher_subscription] Failed to save watcher subscription: {e}")
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

    # --- Watcher Premises ---

    def get_watcher_premises(self, user_id: str) -> tuple:
        """Get premises and context for a user/channel.

        Returns:
            Tuple of (premises_list, context_string)
        """
        try:
            state = self._watcher_premises.load()
            entry = state.get(str(user_id), {})
            premises = entry.get("premises", [])
            context = entry.get("context")
            return premises, context
        except Exception as e:
            logger.exception(f"Failed to get watcher premises: {e}")
            return [], None

    def save_watcher_premise(self, user_id: str, premises: list, context: str = None) -> bool:
        """Save full premises list and context for a user/channel."""
        try:
            # Validate premises data before saving
            if VALIDATION_AVAILABLE and UserPremises:
                try:
                    premises_to_validate = {
                        "user_id": str(user_id),
                        "premises": premises,
                        "context": context,
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat(),
                    }
                    UserPremises(**premises_to_validate)
                except Exception as e:
                    logger.warning(f"⚠️ [NoSQL Role] Watcher premises validation failed: {e}. Skipping save.")
                    return False
            
            def updater(state: Dict) -> Dict:
                state[str(user_id)] = {
                    "premises": premises,
                    "context": context,
                }
                return state

            self._watcher_premises.update(updater)
            return True
        except Exception as e:
            logger.exception(f"Failed to save watcher premises: {e}")
            return False

    def add_watcher_premise(self, user_id: str, premise: str, max_premises: int = 3) -> tuple:
        """Add a premise for a user. Returns (success, message)."""
        try:
            state = self._watcher_premises.load()
            entry = state.get(str(user_id), {"premises": [], "context": None})
            current = entry.get("premises", [])
            if len(current) >= max_premises:
                return False, f"Maximum premises limit ({max_premises}) reached."
            current.append(premise)
            self.save_watcher_premise(user_id, current, entry.get("context"))
            return True, f"Premise #{len(current)} added."
        except Exception as e:
            logger.exception(f"Failed to add watcher premise: {e}")
            return False, str(e)

    def modify_watcher_premise(self, user_id: str, index: int, new_premise: str) -> tuple:
        """Modify a premise by 1-based index. Returns (success, message)."""
        try:
            state = self._watcher_premises.load()
            entry = state.get(str(user_id), {"premises": [], "context": None})
            current = entry.get("premises", [])
            if index < 1 or index > len(current):
                return False, f"Invalid index {index}. You have {len(current)} premises."
            current[index - 1] = new_premise
            self.save_watcher_premise(user_id, current, entry.get("context"))
            return True, f"Premise #{index} updated."
        except Exception as e:
            logger.exception(f"Failed to modify watcher premise: {e}")
            return False, str(e)

    def delete_watcher_premise(self, user_id: str, index: int) -> tuple:
        """Delete a premise by 1-based index. Returns (success, message)."""
        try:
            state = self._watcher_premises.load()
            entry = state.get(str(user_id), {"premises": [], "context": None})
            current = entry.get("premises", [])
            if index < 1 or index > len(current):
                return False, f"Invalid index {index}. You have {len(current)} premises."
            removed = current.pop(index - 1)
            self.save_watcher_premise(user_id, current, entry.get("context"))
            return True, f"Premise #{index} deleted: {removed}"
        except Exception as e:
            logger.exception(f"Failed to delete watcher premise: {e}")
            return False, str(e)

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

            # Validate stats data
            if VALIDATION_AVAILABLE and DiceGameStats:
                stats_to_validate = {
                    "player_id": str(user_id),
                    "total_wins": pots_won,
                    "total_losses": total_plays - pots_won,
                    "total_rolls": total_plays,
                    "last_played_at": last_play or now,
                    "created_at": now,
                }
                try:
                    DiceGameStats(**stats_to_validate)
                except Exception as e:
                    logger.warning(f"⚠️ [NoSQL Role] Dice game stats validation failed: {e}. Skipping save.")
                    return False

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
            # Extract rune keys if runes_drawn contains dicts
            if runes_drawn and isinstance(runes_drawn[0], dict):
                runes_drawn = [r.get('key', r.get('name', str(r))) for r in runes_drawn]
            
            record = {
                "user_id": str(user_id),
                "reading_date": datetime.now().strftime('%Y-%m-%d'),
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

    def delete_nordic_runes_readings(self, user_id: str) -> int:
        """Delete all rune readings for a user (GDPR)."""
        try:
            before_count = len(list(self._nordic_runes.filter_tail(lambda r: r.get("user_id") == str(user_id), limit=10000)))
            self._nordic_runes.filter_in_place(lambda r: r.get("user_id") != str(user_id))
            after_count = len(list(self._nordic_runes.filter_tail(lambda r: r.get("user_id") == str(user_id), limit=10000)))
            deleted = before_count - after_count
            logger.info(f"Deleted {deleted} nordic runes readings for user {user_id}")
            return deleted
        except Exception as e:
            logger.exception(f"Failed to delete nordic runes readings: {e}")
            return 0

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
                "accusation_text": accusation,
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

            # Validate beggar subrole data
            if VALIDATION_AVAILABLE and BeggarSubrole:
                subrole_to_validate = {
                    "player_id": str(user_id),
                    "request_count": donation_count,
                    "last_request_at": last_donation or now,
                    "created_at": now,
                }
                try:
                    BeggarSubrole(**subrole_to_validate)
                except Exception as e:
                    logger.warning(f"⚠️ [NoSQL Role] Beggar subrole validation failed: {e}. Skipping save.")
                    return False

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

    # --- MC Playlists ---

    def mc_create_playlist(self, name: str, user_id: str, user_name: str,
                           server_id: str, server_name: str) -> bool:
        """Create a new playlist. Returns False if already exists."""
        try:
            state = self._mc_playlists.load()
            key = f"{user_id}:{name}"
            if key in state:
                return False
            state[key] = {
                "name": name,
                "user_id": user_id,
                "user_name": user_name,
                "server_id": server_id,
                "server_name": server_name,
                "created_at": datetime.now().isoformat(),
                "updated_at": None,
                "active": True,
            }
            self._mc_playlists.update(lambda _: state)
            return True
        except Exception as e:
            logger.exception(f"Failed to create MC playlist: {e}")
            return False

    def mc_get_user_playlists(self, user_id: str) -> list:
        """Get all active playlists for a user. Returns list of tuples (name, created_at, updated_at)."""
        try:
            state = self._mc_playlists.load()
            results = []
            for entry in state.values():
                if entry.get("user_id") == user_id and entry.get("active", True):
                    results.append((0, entry["name"], entry.get("created_at"), entry.get("updated_at")))
            results.sort(key=lambda x: x[2] or "", reverse=True)
            return results
        except Exception as e:
            logger.exception(f"Failed to get MC user playlists: {e}")
            return []

    # --- MC Queue ---

    def _queue_key(self, server_id: str, channel_id: str) -> str:
        return f"{server_id}:{channel_id}"

    def mc_add_song_to_queue(self, server_id: str, channel_id: str, user_id: str,
                             title: str, url: str, duration: str = None,
                             artist: str = None, position: int = None) -> bool:
        """Add a song to the playback queue."""
        try:
            state = self._mc_queue.load()
            qk = self._queue_key(server_id, channel_id)
            queue = [e for e in state.get(qk, []) if e.get("active", True)]

            entry = {
                "server_id": server_id,
                "channel_id": channel_id,
                "user_id": user_id,
                "title": title,
                "url": url,
                "duration": duration,
                "artist": artist,
                "added_at": datetime.now().isoformat(),
                "active": True,
            }

            if position is None or position == -1:
                queue.append(entry)
            elif position == 0:
                queue.insert(0, entry)
            else:
                # position is 1-indexed
                queue.insert(max(0, position - 1), entry)

            # Re-assign sequential positions
            for i, e in enumerate(queue, 1):
                e["position"] = i

            state[qk] = queue
            self._mc_queue.update(lambda _: state)
            return True
        except Exception as e:
            logger.exception(f"Failed to add song to MC queue: {e}")
            return False

    def mc_get_queue(self, server_id: str, channel_id: str) -> list:
        """Get current playback queue as list of tuples matching legacy format."""
        try:
            state = self._mc_queue.load()
            qk = self._queue_key(server_id, channel_id)
            queue = [e for e in state.get(qk, []) if e.get("active", True)]
            queue.sort(key=lambda e: e.get("position", 0))
            return [
                (e.get("position", i), e["title"], e["url"], e.get("duration"),
                 e.get("artist"), e.get("user_id"), e.get("added_at"))
                for i, e in enumerate(queue, 1)
            ]
        except Exception as e:
            logger.exception(f"Failed to get MC queue: {e}")
            return []

    def mc_get_queue_all_channels(self, server_id: str) -> list:
        """Get all queue entries for a server across all channels."""
        try:
            state = self._mc_queue.load()
            results = []
            for qk, queue in state.items():
                if not qk.startswith(f"{server_id}:"):
                    continue
                for e in queue:
                    if not e.get("active", True):
                        continue
                    results.append((
                        e.get("position", 0), e["title"], e["url"], e.get("duration"),
                        e.get("artist"), e.get("user_id"), e.get("added_at"), e.get("channel_id"),
                    ))
            results.sort(key=lambda x: x[6] or "", reverse=True)
            return results
        except Exception as e:
            logger.exception(f"Failed to get MC queue all channels: {e}")
            return []

    def mc_remove_song_from_queue(self, server_id: str, channel_id: str, position: int) -> bool:
        """Remove a specific song from queue by position (1-indexed)."""
        try:
            state = self._mc_queue.load()
            qk = self._queue_key(server_id, channel_id)
            queue = state.get(qk, [])
            active = [e for e in queue if e.get("active", True)]
            removed = False
            for e in active:
                if e.get("position") == position:
                    e["active"] = False
                    removed = True
                    break
            if removed:
                # Re-assign positions for remaining active entries
                remaining = [e for e in queue if e.get("active", True)]
                for i, e in enumerate(remaining, 1):
                    e["position"] = i
                state[qk] = queue
                self._mc_queue.update(lambda _: state)
            return removed
        except Exception as e:
            logger.exception(f"Failed to remove song from MC queue: {e}")
            return False

    def mc_clear_queue(self, server_id: str, channel_id: str) -> bool:
        """Clear entire playback queue for a channel."""
        try:
            state = self._mc_queue.load()
            qk = self._queue_key(server_id, channel_id)
            for e in state.get(qk, []):
                e["active"] = False
            self._mc_queue.update(lambda _: state)
            return True
        except Exception as e:
            logger.exception(f"Failed to clear MC queue: {e}")
            return False

    def mc_clean_old_queue(self, days: int = 7) -> int:
        """Clean old queue entries (older than X days)."""
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            state = self._mc_queue.load()
            cleaned = 0
            for qk, queue in state.items():
                for e in queue:
                    if e.get("active", True) and e.get("added_at", "") < cutoff:
                        e["active"] = False
                        cleaned += 1
            self._mc_queue.update(lambda _: state)
            if cleaned:
                logger.info(f"Cleaned {cleaned} old MC queue entries older than {days} days")
            return cleaned
        except Exception as e:
            logger.exception(f"Failed to clean old MC queue: {e}")
            return 0

    # --- MC History ---

    def mc_register_history(self, server_id: str, channel_id: str, user_id: str,
                            title: str, url: str, duration: str = None,
                            artist: str = None) -> bool:
        """Register a song in playback history."""
        try:
            self._mc_history.append({
                "server_id": server_id,
                "channel_id": channel_id,
                "user_id": user_id,
                "title": title,
                "url": url,
                "duration": duration,
                "artist": artist,
                "played_at": datetime.now().isoformat(),
            })
            return True
        except Exception as e:
            logger.exception(f"Failed to register MC history: {e}")
            return False

    def mc_get_history(self, server_id: str, channel_id: str, limit: int = 10) -> list:
        """Get recent playback history as legacy-format tuples."""
        try:
            all_entries = list(self._mc_history.iter_records())
            filtered = [
                e for e in all_entries
                if e.get("server_id") == server_id and e.get("channel_id") == channel_id
            ]
            filtered.sort(key=lambda e: e.get("played_at", ""), reverse=True)
            return [
                (e["title"], e["url"], e.get("duration"), e.get("artist"),
                 e.get("user_id"), e.get("played_at"))
                for e in filtered[:limit]
            ]
        except Exception as e:
            logger.exception(f"Failed to get MC history: {e}")
            return []

    def mc_get_statistics(self, server_id: str = None) -> dict:
        """Get basic MC statistics."""
        try:
            pl_state = self._mc_playlists.load()
            playlists_total = sum(1 for e in pl_state.values() if e.get("active", True))

            q_state = self._mc_queue.load()
            queue_total = sum(
                sum(1 for e in q if e.get("active", True))
                for q in q_state.values()
            )

            all_history = list(self._mc_history.iter_records())
            historial_total = len(all_history)

            queue_server = 0
            history_server = 0
            if server_id:
                for qk, q in q_state.items():
                    if qk.startswith(f"{server_id}:"):
                        queue_server += sum(1 for e in q if e.get("active", True))
                history_server = sum(1 for e in all_history if e.get("server_id") == server_id)

            return {
                "playlists_total": playlists_total,
                "queue_total": queue_total,
                "historial_total": historial_total,
                "queue_servidor": queue_server,
                "historial_servidor": history_server,
            }
        except Exception as e:
            logger.exception(f"Failed to get MC statistics: {e}")
            return {}

    def mc_clean_old_history(self, days: int = 30) -> int:
        """Clean old history entries. With ring buffer, this is handled automatically.
        Returns 0 since JSONL ring buffer self-manages retention."""
        return 0

    # --- MC Preferences ---

    def mc_get_preferences(self, user_id: str) -> dict:
        """Get user MC preferences."""
        try:
            state = self._mc_preferences.load()
            return state.get(str(user_id), {
                "default_volume": 100,
                "default_quality": "medium",
                "autoplay": False,
            })
        except Exception as e:
            logger.exception(f"Failed to get MC preferences: {e}")
            return {}

    def mc_set_preferences(self, user_id: str, **kwargs) -> bool:
        """Set user MC preferences."""
        try:
            def updater(state: Dict) -> Dict:
                current = state.get(str(user_id), {
                    "default_volume": 100,
                    "default_quality": "medium",
                    "autoplay": False,
                })
                current.update(kwargs)
                current["updated_at"] = datetime.now().isoformat()
                state[str(user_id)] = current
                return state
            self._mc_preferences.update(updater)
            return True
        except Exception as e:
            logger.exception(f"Failed to set MC preferences: {e}")
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
