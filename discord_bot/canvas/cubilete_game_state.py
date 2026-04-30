"""Cubilete game state management for Canvas UI."""

from typing import Optional, List, Dict, Any
from datetime import datetime
import json
from agent_logging import get_logger

logger = get_logger('cubilete_canvas_state')


class CubileteCanvasGame:
    """Manages the state of an active cubilete game in Canvas."""

    def __init__(self, user_id: int, guild_id: int, bet: int):
        self.user_id = user_id
        self.guild_id = guild_id
        self.bet = bet
        self.dice: List[int] = []
        self.kept_dice: List[bool] = [False, False, False, False, False]  # Which dice are kept
        self.roll_count: int = 0
        self.max_rolls: int = 3
        self.game_active: bool = True
        self.waiting_for_bet: bool = True  # Waiting for player to pay bet
        self.started_at: datetime = datetime.now()
        self.final_combination: Optional[str] = None
        self.final_prize: int = 0

    def roll_dice(self, keep_indices: List[int] = None) -> List[int]:
        """Roll dice, keeping the ones specified by keep_indices."""
        if keep_indices is None:
            keep_indices = []

        new_dice = []
        for i in range(5):
            if i in keep_indices or self.kept_dice[i]:
                # Keep this die
                new_dice.append(self.dice[i])
            else:
                # Roll new die
                import random
                new_dice.append(random.randint(1, 6))

        self.dice = new_dice
        self.roll_count += 1

        # Update kept_dice based on keep_indices
        self.kept_dice = [i in keep_indices for i in range(5)]

        return self.dice

    def toggle_keep(self, die_index: int) -> bool:
        """Toggle whether a die is kept."""
        if 0 <= die_index < 5:
            self.kept_dice[die_index] = not self.kept_dice[die_index]
            return self.kept_dice[die_index]
        return False

    def get_kept_indices(self) -> List[int]:
        """Get indices of kept dice."""
        return [i for i, kept in enumerate(self.kept_dice) if kept]

    def can_roll(self) -> bool:
        """Check if player can roll again."""
        return self.game_active and self.roll_count < self.max_rolls

    def can_confirm(self) -> bool:
        """Check if player can confirm (at least one roll done)."""
        return self.game_active and self.roll_count > 0

    def confirm(self, combination: str, prize: int) -> None:
        """Confirm the final result and end the game."""
        self.final_combination = combination
        self.final_prize = prize
        self.game_active = False


# Global game state storage
_active_games: Dict[str, CubileteCanvasGame] = {}


def get_game_key(user_id: int, guild_id: int) -> str:
    """Generate a unique key for a game."""
    return f"{guild_id}_{user_id}"


def get_active_game(user_id: int, guild_id: int) -> Optional[CubileteCanvasGame]:
    """Get an active game for a user."""
    key = get_game_key(user_id, guild_id)
    return _active_games.get(key)


def create_game(user_id: int, guild_id: int, bet: int) -> CubileteCanvasGame:
    """Create a new game for a user."""
    key = get_game_key(user_id, guild_id)
    game = CubileteCanvasGame(user_id, guild_id, bet)
    _active_games[key] = game
    return game


def end_game(user_id: int, guild_id: int) -> None:
    """End and remove an active game."""
    key = get_game_key(user_id, guild_id)
    if key in _active_games:
        del _active_games[key]


def cleanup_old_games(max_age_minutes: int = 30) -> int:
    """Clean up old inactive games."""
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(minutes=max_age_minutes)
    removed = 0

    keys_to_remove = []
    for key, game in _active_games.items():
        if not game.game_active or game.started_at < cutoff:
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del _active_games[key]
        removed += 1

    return removed
