"""
Discord commands for the Treasure Hunter role (English version).
Enhanced POE2 subrole management with admin controls and shared databases.
"""

import asyncio
import discord
from agent_logging import get_logger
from discord_bot.discord_utils import get_server_name, send_dm_or_channel

logger = get_logger('treasure_hunter_discord')

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

    # --- !hunter (group command) ---
    if bot.get_command("hunter") is None:
        @bot.group(name="hunter")
        async def cmd_hunter_group(ctx):
            """Main hunter command - manages subroles."""
            if ctx.invoked_subcommand is None:
                # Show general help about available subroles
                help_text = _build_general_help_text(POE2_AVAILABLE)
                await send_dm_or_channel(ctx, help_text, "📩 Hunter help sent by private message.")
                return
        
        logger.info("🔮 Hunter group command registered")
    else:
        cmd_hunter_group = bot.get_command("hunter")
        logger.info("🔮 Hunter group command already exists, adding subcommands")

    # --- !hunter poe2 (subgroup) ---
    if POE2_AVAILABLE and poe2_manager:
        try:
            @cmd_hunter_group.group(name="poe2")
            async def cmd_hunter_poe2_group(ctx):
                """POE2 subrole management."""
                if ctx.invoked_subcommand is None:
                    # Show POE2-specific help
                    help_text = _build_poe2_help_text()
                    await send_dm_or_channel(ctx, help_text, "📩 POE2 help sent by private message.")
                    return
            
            logger.info("🔮 Hunter POE2 group registered")
        except Exception as e:
            logger.error(f"Error registering hunter poe2 group: {e}")

        # Register POE2 subcommands
        if cmd_hunter_group.get_command("poe2"):
            cmd_poe2_group = cmd_hunter_group.get_command("poe2")
            
            # !hunter poe2 on/off (admin only)
            @cmd_poe2_group.command(name="on")
            async def cmd_poe2_on(ctx):
                """Activate POE2 subrole (admin only)."""
                if not poe2_manager.is_admin(ctx):
                    await ctx.send("❌ Only administrators can activate the POE2 subrole.")
                    return
                
                server_id = str(ctx.guild.id)
                if poe2_manager.is_activated(server_id):
                    await ctx.send("ℹ️ POE2 subrole is already activated on this server.")
                    return
                
                # Download item list if needed
                league = poe2_manager.get_active_league(server_id)
                if poe2_manager.should_refresh_item_list(league):
                    await ctx.send("🔄 Downloading item list...")
                    success = await poe2_manager.download_item_list(league)
                    if not success:
                        await ctx.send("❌ Error downloading item list. Please try again.")
                        return
                
                if poe2_manager.activate_subrole(server_id):
                    await ctx.send("✅ POE2 subrole activated! Use `!hunter poe2 help` for commands.")
                else:
                    await ctx.send("❌ Error activating POE2 subrole.")
            
            @cmd_poe2_group.command(name="off")
            async def cmd_poe2_off(ctx):
                """Deactivate POE2 subrole (admin only)."""
                if not poe2_manager.is_admin(ctx):
                    await ctx.send("❌ Only administrators can deactivate the POE2 subrole.")
                    return
                
                server_id = str(ctx.guild.id)
                if not poe2_manager.is_activated(server_id):
                    await ctx.send("ℹ️ POE2 subrole is not activated on this server.")
                    return
                
                if poe2_manager.deactivate_subrole(server_id):
                    await ctx.send("❌ POE2 subrole deactivated.")
                else:
                    await ctx.send("❌ Error deactivating POE2 subrole.")
            
            # !hunter poe2 league <league>
            @cmd_poe2_group.command(name="league")
            async def cmd_poe2_league(ctx, league: str = ""):
                """Set or show the active league (admin only, DM only)."""
                # Check if in DM
                if ctx.guild is not None:
                    await ctx.send("❌ This command can only be used via DM.")
                    return
                
                # Check if admin
                if not poe2_manager.is_admin(ctx):
                    await ctx.send("❌ Only administrators can change the league.")
                    return
                
                user_id = str(ctx.author.id)
                server_id = poe2_manager.get_user_active_server(user_id)
                
                if not server_id:
                    await ctx.send("❌ No active servers found. Please activate POE2 on a server first.")
                    return
                
                if not league:
                    current_league = poe2_manager.get_user_league(user_id, server_id)
                    await ctx.send(f"🏆 **Current POE2 League**: {current_league}")
                    return
                
                # Validate league
                valid_leagues = ["Standard", "Fate of the Vaal", "Hardcore", "Hardcore Fate of the Vaal"]
                if league not in valid_leagues:
                    await ctx.send(f"❌ Invalid league. Available: {', '.join(valid_leagues)}")
                    return
                
                if poe2_manager.set_user_league(user_id, league, server_id):
                    # Download item list for new league if needed
                    if poe2_manager.should_refresh_item_list(league):
                        await ctx.send("🔄 Downloading item list for new league...")
                        await poe2_manager.download_item_list(league)
                    
                    # Add default objectives for this league
                    poe2_manager._add_default_objectives(user_id, league)
                    
                    # Download price history for default objectives
                    poe2_manager._download_default_objectives_history(user_id, league)
                    
                    await ctx.send(f"✅ Your personal league changed to: {league}")
                    await ctx.send("💡 Default objectives added and price history downloaded.")
                else:
                    await ctx.send("❌ Error changing league (POE2 subrole not activated).")
            
            # !hunter poe2 help
            @cmd_poe2_group.command(name="help")
            async def cmd_poe2_help(ctx):
                """Show POE2-specific help."""
                if not poe2_manager.is_activated(str(ctx.guild.id)):
                    await ctx.send("❌ POE2 subrole is not activated on this server.")
                    return
                
                help_text = _build_poe2_help_text()
                await send_dm_or_channel(ctx, help_text, "📩 POE2 help sent by private message.")
            
            # !hunter poe2 add <item>
            @cmd_poe2_group.command(name="add")
            async def cmd_poe2_add(ctx, item_name: str = ""):
                """Add an item to objectives (DM only)."""
                # Check if in DM
                if ctx.guild is not None:
                    await ctx.send("❌ This command can only be used via DM.")
                    return
                
                user_id = str(ctx.author.id)
                server_id = poe2_manager.get_user_active_server(user_id)
                
                if not server_id:
                    await ctx.send("❌ No active servers found. Please activate POE2 on a server first.")
                    return
                
                if not item_name:
                    await ctx.send("❌ Please specify an item name. Usage: `!hunter poe2 add \"item name\"`")
                    return
                
                success, message = poe2_manager.add_objective(server_id, user_id, item_name)
                await ctx.send(message)
            
            # !hunter poe2 del <item>
            @cmd_poe2_group.command(name="del")
            async def cmd_poe2_del(ctx, item_name: str = ""):
                """Remove an item from objectives (DM only)."""
                # Check if in DM
                if ctx.guild is not None:
                    await ctx.send("❌ This command can only be used via DM.")
                    return
                
                user_id = str(ctx.author.id)
                server_id = poe2_manager.get_user_active_server(user_id)
                
                if not server_id:
                    await ctx.send("❌ No active servers found. Please activate POE2 on a server first.")
                    return
                
                if not item_name:
                    await ctx.send("❌ You must specify an item name or number. Example: `!hunter poe2 del \"Ancient Rib\"`")
                    return
                
                success, message = poe2_manager.remove_objective(server_id, user_id, item_name)
                await ctx.send(message)
            
            # !hunter poe2 list
            @cmd_poe2_group.command(name="list")
            async def cmd_poe2_list(ctx):
                """Show current objectives with prices (DM only)."""
                # Check if in DM
                if ctx.guild is not None:
                    await ctx.send("❌ This command can only be used via DM.")
                    return
                
                user_id = str(ctx.author.id)
                server_id = poe2_manager.get_user_active_server(user_id)
                
                if not server_id:
                    await ctx.send("❌ No active servers found. Please activate POE2 on a server first.")
                    return
                
                success, message = poe2_manager.list_objectives(server_id, user_id)
                
                if success:
                    await ctx.send(message)
                else:
                    await ctx.send("❌ " + message)
            
            logger.info("🔮 POE2 subcommands registered")
    
    # Register general help subcommand
    try:
        @cmd_hunter_group.command(name="help")
        async def cmd_hunter_help_subcommand(ctx):
            """Show general hunter help."""
            help_text = _build_general_help_text(POE2_AVAILABLE)
            await send_dm_or_channel(ctx, help_text, "📩 Hunter help sent by private message.")
        
        logger.info("🔮 Hunter help subcommand registered")
    except Exception as e:
        logger.error(f"Error registering hunter help subcommand: {e}")

    # --- !hunterfrequency ---
    if bot.get_command("hunterfrequency") is None:
        @bot.command(name="hunterfrequency")
        async def cmd_hunter_frequency(ctx, hours: str = ""):
            """Configure automatic execution frequency of treasure hunter."""
            if not POE2_AVAILABLE:
                await ctx.send("❌ The treasure hunter is not available on this server.")
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

    if "roles" not in agent_config:
        agent_config["roles"] = {}
    if role_name not in agent_config["roles"]:
        agent_config["roles"][role_name] = {}
    agent_config["roles"][role_name]["interval_hours"] = hours_int

    role_cfg = personality.get("discord", {}).get("role_messages", {})
    await ctx.send(role_cfg.get("frequency_updated", "✅ Frequency of '{role}' updated to {hours} hours.").format(role=role_name, hours=hours_int))
    logger = get_logger('treasure_hunter_discord')
    logger.info(f"🎭 {ctx.author.name} updated frequency of {role_name} to {hours_int} hours in {ctx.guild.name}")
