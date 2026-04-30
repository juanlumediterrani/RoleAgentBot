"""Public API for Shaman role.

This module provides a stable public API for Canvas and other external callers.
Internal implementations may change, but this API should remain stable.
"""

from roles.shaman.subroles.nordic_runes.nordic_runes_discord import get_nordic_runes_commands_instance
from roles.shaman.subroles.nordic_runes.nordic_runes_messages import get_runes_page_data, get_message, ENGLISH_MESSAGES
from roles.shaman.subroles.astrology.astrology import Astrology
from roles.shaman.subroles.astrology.astrology_messages import (
    get_letter_translations,
    get_position_translation,
    get_hebrew_letters_page_data,
    get_hebrew_letters_list_content,
)

__all__ = [
    "get_nordic_runes_commands_instance",
    "get_runes_page_data",
    "get_message",
    "ENGLISH_MESSAGES",
    "Astrology",
    "get_letter_translations",
    "get_position_translation",
    "get_hebrew_letters_page_data",
    "get_hebrew_letters_list_content",
]
