"""
Discord commands for the Treasure Hunter role (English version).
Enhanced POE2 subrole management with admin controls and shared databases.
"""

import asyncio
import discord
import json
import os
from agent_logging import get_logger
from discord_bot.discord_utils import send_dm_or_channel, set_role_enabled

# Import get_message for personality support
try:
    from agent_engine import get_message
except ImportError:
    # Fallback for direct loading
    def get_message(personality, key, default):
        return personality.get("discord", {}).get("treasure_hunter_messages", {}).get(key, default)

logger = get_logger('treasure_hunter_discord')


def _get_treasure_description(key: str, default: str) -> str:
    return default

# Availability flags
try:
    from roles.treasure_hunter.poe2.poe2_subrole_manager import get_poe2_manager
    POE2_MODULE_AVAILABLE = True
except ImportError:
    POE2_MODULE_AVAILABLE = False
    get_poe2_manager = None


def _is_poe2_available(agent_config):
    """Check if POE2 is available (module + role enabled)."""
    import os
    if not POE2_MODULE_AVAILABLE:
        return False
    enabled = os.getenv("TREASURE_HUNTER_ENABLED", "false").lower() == "true"
    if not enabled:
        enabled = agent_config.get("roles", {}).get("treasure_hunter", {}).get("enabled", False)
    return enabled


def register_treasure_hunter_commands(bot, personality, agent_config):
    """Register all Treasure Hunter commands (idempotent)."""

    POE2_AVAILABLE = _is_poe2_available(agent_config)
    poe2_manager = get_poe2_manager() if POE2_AVAILABLE else None

    # NOTE: All !hunter commands have been removed. Use !canvas → Treasure Hunter instead.
    # The POE2 manager is still available for Canvas UI integration.

    # --- !hunterfrequency ---
    if bot.get_command("hunterfrequency") is None:
        @bot.command(name="hunterfrequency")
        async def cmd_hunter_frequency(ctx, hours: str = ""):
            """Configure automatic execution frequency of treasure hunter."""
            if not POE2_AVAILABLE:
                await ctx.send(get_message(personality, "treasure_hunter_unavailable", "❌ The treasure hunter is not available on this server."))
                return
            await _cmd_role_frequency(ctx, "treasure_hunter", hours, personality, agent_config)

        logger.info("💎 Hunter frequency command registered")

    logger.info("🔮 All Treasure Hunter commands registered")


# --- Help text builders ---

def _build_general_help_text(poe2_available: bool) -> str:
    """Build general hunter help text."""
    help_text = "🔮 **TREASURE HUNTER - GENERAL HELP** 🔮\n\n"
    
    if poe2_available:
        help_text += "🎯 **Available Subroles:**\n"
        help_text += "• **POE2** - Path of Exile 2 treasure hunting\n"
        help_text += "  - Admin activation: `!hunter poe2 on/off`\n"
        help_text += "  - User commands: `!hunter poe2 help`\n\n"
    else:
        help_text += "❌ **No subroles available** - POE2 module not loaded\n\n"
    
    help_text += "📋 **COMMANDS:**\n"
    help_text += "• `!hunter help` - Show this help\n"
    if poe2_available:
        help_text += "• `!hunter poe2 help` - Show POE2-specific help\n"
    
    help_text += "• `!hunterfrequency <hours>` - Set execution frequency (1-168h)\n\n"
    
    help_text += "💡 **USAGE EXAMPLES:**\n"
    if poe2_available:
        help_text += "```\n# Admin activation\n!hunter poe2 on\n!hunter poe2 league \"Fate of the Vaal\"\n\n# User commands\n!hunter poe2 help\n!hunter poe2 add \"Ancient Rib\"\n!hunter poe2 list\n```"
    else:
        help_text += "```\n!hunter help\n!hunterfrequency 6\n```"
    
    return help_text


def _build_poe2_help_text() -> str:
    """Build POE2-specific help text."""
    help_text = "🔮 **TREASURE HUNTER - POE2 SUBROLE** 🔮\n\n"
    
    help_text += "🎯 **ACTIVATION (Admin Only):**\n"
    help_text += "• `!hunter poe2 on` - Activate POE2 subrole\n"
    help_text += "• `!hunter poe2 off` - Deactivate POE2 subrole\n"
    help_text += "• `!hunter poe2 league <name>` - Set league (Standard/Fate of the Vaal)\n\n"
    
    help_text += "🎯 **USER COMMANDS:**\n"
    help_text += "• `!hunter poe2 help` - Show this help\n"
    help_text += "• `!hunter poe2 add \"Item Name\"` - Add item to objectives\n"
    help_text += "• `!hunter poe2 del \"Item Name\"` - Remove item from objectives\n"
    help_text += "• `!hunter poe2 del <number>` - Remove item by number\n"
    help_text += "• `!hunter poe2 list` - Show objectives with current prices\n\n"
    
    help_text += "🏆 **AVAILABLE LEAGUES:**\n"
    help_text += "• Standard\n"
    help_text += "• Fate of the Vaal\n"
    help_text += "• Hardcore\n"
    help_text += "• Hardcore Fate of the Vaal\n\n"
    
    help_text += "⚖️ **BUY/SELL LOGIC:**\n"
    help_text += "• **BUY**: Price ≤ historical minimum × 1.15\n"
    help_text += "• **SELL**: Price ≥ historical maximum × 0.85\n\n"
    
    help_text += "💡 **USAGE EXAMPLES:**\n"
    help_text += "```\n# Admin setup\n!hunter poe2 on\n!hunter poe2 league \"Fate of the Vaal\"\n\n# User commands\n!hunter poe2 add \"Ancient Rib\"\n!hunter poe2 add \"Fracturing Orb\"\n!hunter poe2 list\n!hunter poe2 del \"Ancient Rib\"\n!hunter poe2 del 1\n```"
    
    return help_text


# --- Helper functions ---

async def _cmd_role_frequency(ctx, role_name: str, hours: str, personality, agent_config):
    """Configure role execution frequency."""
    if not hours:
        role_cfg = personality.get("discord", {}).get("role_messages", {})
        await ctx.send(role_cfg.get("frequency_usage", f"❌ Usage: !{role_name}frequency <hours> (1-168)"))
        return
    
    try:
        hours_int = int(hours)
        if hours_int < 1 or hours_int > 168:
            role_cfg = personality.get("discord", {}).get("role_messages", {})
            await ctx.send(role_cfg.get("frequency_invalid", "❌ Hours must be between 1 and 168."))
            return
    except ValueError:
        role_cfg = personality.get("discord", {}).get("role_messages", {})
        await ctx.send(role_cfg.get("frequency_invalid", "❌ You must specify a valid number of hours."))
        return

    persisted = set_role_interval_hours(
        ctx.guild,
        role_name,
        hours_int,
        agent_config,
        getattr(ctx.author, "name", "admin_command"),
    )
    if not persisted:
        if "roles" not in agent_config:
            agent_config["roles"] = {}
        if role_name not in agent_config["roles"]:
            agent_config["roles"][role_name] = {}
        agent_config["roles"][role_name]["interval_hours"] = hours_int

    role_cfg = personality.get("discord", {}).get("role_messages", {})
    await ctx.send(role_cfg.get("frequency_updated", "✅ Frequency of '{role}' updated to {hours} hours.").format(role=role_name, hours=hours_int))
    logger = get_logger('treasure_hunter_discord')
    logger.info(f"🎭 {ctx.author.name} updated frequency of {role_name} to {hours_int} hours in {ctx.guild.name}")
