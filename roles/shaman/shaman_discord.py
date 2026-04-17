"""
Discord commands for the Shaman role.
NOTE: All commands are accessible via Canvas UI (!canvas).
"""

from agent_logging import get_logger

logger = get_logger('shaman_discord')


def register_shaman_commands(bot, personality, agent_config):
    """Register shaman commands (idempotent).

    NOTE: Shaman subroles are accessible through Canvas UI.
    The subrole modules are available for Canvas UI integration.
    """
    logger.info("🔮 Shaman commands registration complete - subroles available via Canvas UI")
