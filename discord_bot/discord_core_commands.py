"""
Core Discord bot commands.
Includes: help, insult, presence/welcome greetings, test, role control.

⚠️ **IMPORTANT - ROLE MAINTENANCE:**
When modifying roles (add/remove/rename), ALWAYS update:
1. 'valid_roles' list in _cmd_role_toggle (~line 125)
2. 'role_descriptions' dict in cmd_help (~line 237)
3. Help logic in cmd_help for each affected role
4. Verify all used variables are defined (e.g. role_descriptions vs role_display)

COMMON ERROR: NameError from using wrong variable after modifying roles.
"""

import os
import json
import asyncio
import discord
from pathlib import Path

from agent_db import AgentDatabase
from agent_logging import get_logger
from agent_engine import PERSONALITY, AGENT_CFG
from discord_bot.discord_utils import (
    is_admin, is_duplicate_command, send_dm_or_channel, send_embed_dm_or_channel,
    set_greeting_enabled, get_greeting_enabled,
    is_role_enabled_check,
    get_server_key,
    set_role_enabled,
)

try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None

try:
    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
except Exception:
    get_news_watcher_db_instance = None

try:
    from roles.news_watcher.watcher_messages import get_watcher_messages
except Exception:
    get_watcher_messages = None

try:
    from roles.treasure_hunter.poe2.poe2_subrole_manager import get_poe2_manager
except Exception:
    get_poe2_manager = None

try:
    from behavior.db_behavior import get_behavior_db_instance
except Exception:
    get_behavior_db_instance = None

logger = get_logger('discord_core')

def _get_discord_config(server_id: str) -> dict:
    """
    Get discord configuration for a specific server using the new universal loader.
    
    Args:
        server_id: Server ID for server-specific configuration
        
    Returns:
        dict: Discord configuration from answers.json
    """
    try:
        from agent_runtime import get_personality_message
        return get_personality_message("answers.json", ["discord"], server_id, {})
    except Exception as e:
        logger.warning(f"Could not load discord config for server {server_id}: {e}")
        return {}


def _get_personality_answers() -> dict:
    """
    Legacy compatibility function for canvas.state.py.
    
    Returns the entire answers.json content for backward compatibility.
    This should be replaced with specific get_personality_message() calls.
    """
    try:
        from agent_runtime import get_personality_message
        from agent_db import get_server_id
        server_id = get_server_id()
        return get_personality_message("answers.json", [], server_id, {})
    except Exception:
        return {}


# Legacy compatibility variables for canvas imports
_personality_name = PERSONALITY.get("name", "bot").lower()
_insult_cfg = PERSONALITY.get("insult_command", {})  # Moved from discord.insult_command to prompts.json
_personality_answers = _get_personality_answers()  # Legacy compatibility for canvas.state.py
_discord_cfg = PERSONALITY.get("discord", {})  # Legacy compatibility for canvas.content.py
# _personality_descriptions is now dynamic from agent_engine


_talk_state_by_guild_id: dict[int, dict] = {}
_taboo_state_by_guild_id: dict[int, dict] = {}


def get_taboo_state(guild_id: int) -> dict:
    """Get taboo state from behavior database, initializing from prompts.json if needed."""
    state = _taboo_state_by_guild_id.get(guild_id)
    if state is None:
        # Try to get from behavior database first
        try:
            server_key = str(guild_id)
            db_behavior = get_behavior_db_instance(server_key)
            
            # Get default keywords from prompts.json/behaviors/taboo
            taboo_defaults = PERSONALITY.get("behaviors", {}).get("taboo", {})
            default_keywords = list(taboo_defaults.get("keywords", [])) if isinstance(taboo_defaults.get("keywords", []), list) else []
            
            # Initialize database with defaults if empty
            db_behavior.initialize_taboo_defaults(default_keywords)
            
            # Get current state from behavior database
            state = {
                "enabled": db_behavior.is_taboo_enabled(),
                "keywords": db_behavior.get_taboo_keywords(),
                "response": taboo_defaults.get("response", "WARNING: That word is not appropriate here!")
            }
            
            # Cache the state
            _taboo_state_by_guild_id[guild_id] = state
            
        except Exception as e:
            logger.error(f"Error getting taboo state from behavior database: {e}")
            # Fallback to empty state
            state = {
                "enabled": False,
                "keywords": [],
                "response": "WARNING: That word is not appropriate here!"
            }
            _taboo_state_by_guild_id[guild_id] = state
    
    return state


def update_taboo_state(guild_id: int, enabled: bool = None, keywords: list = None) -> bool:
    """Update taboo state in behavior database."""
    try:
        server_key = str(guild_id)
        db_behavior = get_behavior_db_instance(server_key)
        
        # Update enabled status if provided
        if enabled is not None:
            # Get all keywords from database (including disabled ones)
            # For now, we'll use a different approach: store default keywords and toggle them
            default_keywords = PERSONALITY.get("behaviors", {}).get("taboo", {}).get("keywords", [])
            
            if enabled:
                # Enable taboo: restore default keywords
                for keyword in default_keywords:
                    db_behavior.add_taboo_keyword(keyword, "admin_enable")
            else:
                # Disable taboo: remove all keywords
                current_keywords = db_behavior.get_taboo_keywords()
                for keyword in current_keywords:
                    db_behavior.remove_taboo_keyword(keyword)
            
            # Update cache
            if guild_id in _taboo_state_by_guild_id:
                _taboo_state_by_guild_id[guild_id]["enabled"] = enabled
                _taboo_state_by_guild_id[guild_id]["keywords"] = db_behavior.get_taboo_keywords()
        
        # Update keywords if provided
        if keywords is not None:
            # Get current keywords
            current_keywords = set(db_behavior.get_taboo_keywords())
            new_keywords = set(kw.lower().strip() for kw in keywords if kw.strip())
            
            # Add new keywords
            for keyword in new_keywords - current_keywords:
                db_behavior.add_taboo_keyword(keyword, "admin_update")
            
            # Remove keywords not in new list
            for keyword in current_keywords - new_keywords:
                db_behavior.remove_taboo_keyword(keyword)
            
            # Update cache
            if guild_id in _taboo_state_by_guild_id:
                _taboo_state_by_guild_id[guild_id]["keywords"] = list(new_keywords)
                _taboo_state_by_guild_id[guild_id]["enabled"] = db_behavior.is_taboo_enabled()
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating taboo state: {e}")
        return False


def is_taboo_triggered(guild_id: int, content: str) -> tuple[bool, str | None]:
    state = get_taboo_state(guild_id)
    if not state.get("enabled", False):
        return False, None
    text = (content or "").lower()
    for keyword in state.get("keywords", []):
        kw = str(keyword).strip().lower()
        if kw and kw in text:
            return True, kw
    return False, None


from discord_bot.canvas.state import (
    _get_canvas_watcher_method_label,
    _get_canvas_watcher_frequency_hours,
    _get_canvas_dice_state,
    _get_canvas_dice_ranking,
    _get_canvas_dice_history,
    _get_canvas_beggar_state,
    _get_canvas_ring_state,
    _get_canvas_poe2_state,
)
from discord_bot.canvas.content import (
    _build_canvas_sections,
    _build_canvas_embed,
    _split_canvas_blocks,
    _build_canvas_role_embed,
    _truncate_canvas_field_value,
    _merge_canvas_block_with_auto_response,
    _get_canvas_auto_response_preview,
    _build_canvas_behavior_embed,
    _get_canvas_role_detail_items,
    _get_canvas_role_action_items_for_detail,
    _get_canvas_role_action_items,
    _build_canvas_behavior_action_view,
    _build_canvas_home,
    _build_canvas_roles,
    _build_canvas_personal,
    _build_canvas_help,
    _build_canvas_role_view,
    _build_canvas_role_detail_view,
)
from discord_bot.canvas.ui import (
    CanvasSectionSelect,
    CanvasRoleSelect,
    CanvasRoleDetailSelect,
    CanvasWatcherMethodSelect,
    CanvasWatcherSubscriptionSelect,
    CanvasWatcherAdminMethodSelect,
    CanvasWatcherAdminActionSelect,
    CanvasRoleActionSelect,
    CanvasMCActionSelect,
    CanvasBehaviorActionSelect,
    CanvasNavigationView,
    CanvasRolesView,
    CanvasRoleButton,
    CanvasRoleDetailButton,
    CanvasMCSongModal,
    CanvasMCVolumeModal,
    CanvasWatcherSubscribeModal,
    CanvasWatcherAddModal,
    CanvasWatcherDeleteModal,
    CanvasWatcherListModal,
    CanvasWatcherChannelSubscribeModal,
    CanvasWatcherChannelUnsubscribeModal,
    CanvasWatcherFrequencyModal,
    CanvasRoleDetailView,
    CanvasBehaviorView,
    CanvasBehaviorDetailButton,
    _get_enabled_roles,
)
from discord_bot.canvas.command import register_canvas_command

# Export for use by canvas modules
__all__ = ['register_core_commands']


def register_core_commands(bot, agent_config):

    # --- GET PERSONALITY AND CONFIGURATION ---
    _personality_name = PERSONALITY.get("name", "unknown")
    _personality_answers = PERSONALITY.get("answers", {})
    _discord_cfg = PERSONALITY.get("discord", {})
    
    # --- COMMAND NAMES ---
    greet_name = f"greet{_personality_name}"
    nogreet_name = f"nogreet{_personality_name}"
    welcome_name = f"welcome{_personality_name}"
    nowelcome_name = f"nowelcome{_personality_name}"
    insult_name = f"insult{_personality_name}"
    role_cmd_name = f"role{_personality_name}"
    talk_cmd_name = f"talk{_personality_name}"

    # --- ROLE CONTROL FUNCTIONS (accessible within this scope) ---

    async def _cmd_role_toggle(ctx, role_name: str, enabled: bool):
        """Enable or disable roles dynamically."""
        server_id = str(ctx.guild.id) if ctx.guild else None
        role_cfg = get_personality_message("answers.json", ["role_messages"], server_id, {})
        
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("role_no_permission", "❌ Only administrators can enable or disable roles."))
            return

        valid_roles = ["news_watcher", "treasure_hunter", "trickster", "banker"]
        if role_name not in valid_roles:
            await ctx.send(role_cfg.get("role_not_found", "❌ Unknown role `{role}`.").format(role=role_name))
            return

        env_var_name = f"{role_name.upper()}_ENABLED"
        env_value = "true" if enabled else "false"
        os.environ[env_var_name] = env_value

        set_role_enabled(ctx.guild, role_name, enabled, agent_config, getattr(ctx.author, "name", "admin_command"))

        # Register role commands if activating
        if enabled:
            from discord_bot.discord_role_loader import register_single_role
            await register_single_role(bot, role_name, agent_config, PERSONALITY)

        if enabled:
            await ctx.send(role_cfg.get("role_activated", "✅ Role '{role}' enabled.").format(role=role_name))
            logger.info(f"{ctx.author.name} activated role {role_name} in {ctx.guild.name}")
        else:
            await ctx.send(role_cfg.get("role_deactivated", "✅ Role '{role}' disabled.").format(role=role_name))
            logger.info(f"{ctx.author.name} deactivated role {role_name} in {ctx.guild.name}")

    # Make the function available globally for import
    globals()['_cmd_role_toggle'] = _cmd_role_toggle

    # --- ROLE CONTROL COMMAND ---
    if bot.get_command(role_cmd_name) is None:
        @bot.command(name=role_cmd_name)
        async def cmd_role_control(ctx, role_name: str = "", action: str = ""):
            """Toggle a role with `!role<personality> <role> <action>`."""
            usage_message = f"❌ Usage: `!{role_cmd_name} <role> <action>`. Use `on/off`, `true/false`, `1/0`, or `enable/disable` for `<action>`."
            if not role_name:
                await ctx.send(usage_message)
                return

            if not action:
                await ctx.send(usage_message)
                return

            action_lower = action.lower()
            if action_lower in ["on", "true", "1", "enable"]:
                await _cmd_role_toggle(ctx, role_name, True)
            elif action_lower in ["off", "false", "0", "disable"]:
                await _cmd_role_toggle(ctx, role_name, False)
            else:
                await ctx.send(usage_message)
    else:
        logger.info(f"Command {role_cmd_name} already registered, skipping...")

    # --- PRESENCE GREETINGS ---

    # --- ENGLISH HELP COMMAND WITH PERSONALITY SUPPORT ---
    if bot.get_command("agenthelp") is None:
        @bot.command(name="agenthelp")
        async def cmd_help(ctx, personality_name: str = ""):
            """Show all available commands for this agent."""
            if is_duplicate_command(ctx, "agenthelp"):
                return

            if personality_name:
                if personality_name.lower() != _personality_name:
                    return
                await _show_agent_help(ctx, personality_name)
                return

            await _show_agent_help(ctx, personality_name)
    else:
        logger.info("Command agenthelp already registered, skipping...")

    async def _show_agent_help(ctx, requested_personality):
        """Show agent help using the English command surface."""
        roles_config = AGENT_CFG.get("roles", {})
        
        # Use requested personality name or current personality
        display_name = requested_personality or _personality_name
        help_msg = f"🤖 **Available Commands for {bot.user.name} ({display_name})** 🤖\n\n"

        # Control commands
        help_msg += "🎛️ **CONTROL COMMANDS**\n"
        help_msg += f"• `!{greet_name}` - Enable presence greetings by direct message\n"
        help_msg += f"• `!{nogreet_name}` - Disable presence greetings\n"
        help_msg += f"• `!{welcome_name}` - Enable new member welcome\n"
        help_msg += f"• `!{nowelcome_name}` - Disable new member welcome\n"
        help_msg += f"• `!{insult_name}` - Send an orc insult\n"
        help_msg += f"• `!{role_cmd_name} <role> <on/off>` - Enable or disable roles dynamically\n"
        help_msg += f"• `!agenthelp {display_name}` - Show help for this personality\n"
        help_msg += "• `!readme` - Receive the full user guide by direct message\n\n"

        # Role commands
        help_msg += "🎭 **ROLE COMMANDS**\n"

        # News Watcher
        if is_role_enabled_check("news_watcher", agent_config, ctx.guild):
            interval = 1  # Default interval for news_watcher
            help_msg += f"📡 **News Watcher** - Important alerts every {interval}h\n"
            help_msg += "  • **Main:** `!watcher` | `!nowatcher` | `!watchernotify`\n"
            help_msg += "  • **Help:** `!watcherhelp` (users) | `!watcherchannelhelp` (admins)\n"
            help_msg += "  • **Channel:** `!watcherchannel` group (subscribe, unsubscribe, status, keywords, premises)\n"
            help_msg += "  • **Subscription:** `!watcher feeds/categories/status/subscribe/unsubscribe/keywords/general/reset`\n\n"
        # Treasure Hunter
        if is_role_enabled_check("treasure_hunter", agent_config, ctx.guild):
            interval = 1  # Default interval for treasure_hunter
            help_msg += f"💎 **Treasure Hunter** - POE2 item alerts every {interval}h\n"
            help_msg += "  • **Admin:** `!hunter poe2 on/off`, `!hunterfrequency <h>` (admins only, from a server channel)\n"
            help_msg += "  • **League:** `!hunter poe2 league \"Standard\"` | `!hunter poe2 \"Fate of the Vaal\"`\n"
            help_msg += "  • **Items:** `!hunteradd \"item\"` | `!hunterdel \"item\"` | `!hunterdel <number>` | `!hunterlist`\n"
            help_msg += "  • **Help:** `!hunterhelp` | `!hunter poe2 help`\n\n"
        # Trickster
        if is_role_enabled_check("trickster", agent_config, ctx.guild):
            trickster_config = roles_config.get("trickster", {})
            interval = trickster_config.get("interval_hours", 12)
            subroles = trickster_config.get("subroles", {})
            
            help_msg += "🎭 **Trickster** - Multiple subroles:\n"
            
            if subroles.get("beggar", {}).get("enabled", False):
                help_msg += "  • 🙏 **Beggar:** `!trickster beggar enable/disable/frequency <h>/status/help`\n"
            
            if subroles.get("ring", {}).get("enabled", False):
                help_msg += "  • 👁️ **Ring:** `!trickster ring enable/disable/frequency <h>/target @user/help`\n"
            
            if subroles.get("dice_game", {}).get("enabled", False):
                help_msg += "  • 🎲 **Dice Game:** `!dice play/help/balance/stats/ranking/history` | `!dice config bet <amount>` | `!dice config announcements on/off`\n"
            
            help_msg += "  • **Main:** `!trickster help`\n\n"
        # Banker
        if is_role_enabled_check("banker", agent_config, ctx.guild):
            help_msg += "💰 **Banker** - Economy and daily rewards\n"
            help_msg += "  • **Main:** `!banker help`\n"
            help_msg += "  • **Balance:** `!banker balance` (also available in Canvas)\n"
            help_msg += "  • **Config:** `!banker bonus <amount>` (admins)\n\n"
        # Music
        help_msg += "🎵 **MC** - Request a song while connected to a voice channel\n"
        help_msg += "  • **Common use:** `!mc play \"ACDC TNT\"` | `!mc add \"Queen Bicycle\"` | `!mc queue`\n"
        help_msg += "  • **Main:** `!mc help`\n\n"

        # Multiple agents info (only when no specific personality requested)
        if not requested_personality: 
            help_msg += "🔀 **MULTI-AGENT SETUP**\n"
            help_msg += f"• Use `!agenthelp {display_name}` for personality-specific help\n"
            help_msg += "• Each agent has its own personality and commands\n\n"

        # Basic conversation
        help_msg += "💬 **BASIC CONVERSATION**\n"
        help_msg += "• Mention the bot to start a conversation\n"
        help_msg += "• It responds in character, following the agent's personality\n"
        help_msg += "• It replies according to its personality\n\n"
        
        # Active and inactive roles
        help_msg += "🎭 **ROLE STATUS**\n"
        role_descriptions = {
            "mc": "🎵 **Music** - Always available (no activation required)",
            "news_watcher": "📡 **News Watcher** - Important alerts",
            "treasure_hunter": "💎 **Treasure Hunter** - Item alerts",
            "trickster": "🎭 **Trickster** - Beggar, ring, and dice game subroles",
            "banker": "💰 **Banker** - Economy and daily rewards",
        }

        for role_name_key in roles_config:
            enabled = is_role_enabled_check(role_name_key, agent_config, ctx.guild)
            if role_name_key == "mc":
                status_emoji = "✅"
            else:
                status_emoji = "✅" if enabled else "❌"
            # Reuse the same role description mapping
            display = role_descriptions.get(role_name_key, f"**{role_name_key.replace('_', ' ').title()}**")
            help_msg += f"• {status_emoji} {display}\n"

        # Send help
        server_id = str(ctx.guild.id) if ctx.guild else None
        help_sent_msg = get_personality_message("answers.json", ["general_messages", "help_sent_private"], server_id, "📩 Help sent by direct message.")
        await send_dm_or_channel(ctx, help_msg, help_sent_msg)


    # --- CANVAS HUB COMMAND ---
    canvas_cmd_name = f"canvas{_personality_name}"
    register_canvas_command(
        bot,
        agent_config,
        canvas_cmd_name,
        greet_name,
        nogreet_name,
        welcome_name,
        nowelcome_name,
        role_cmd_name,
        talk_cmd_name,
    )

    # --- README COMMAND ---
    if bot.get_command("readme") is None:
        @bot.command(name="readme")
        async def cmd_readme(ctx):
            """Send the user guide privately to the user."""
            try:
                readme_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README_USER.md")
                with open(readme_path, 'r', encoding='utf-8') as f:
                    readme_content = f.read()

                max_length = 1900

                if len(readme_content) <= max_length:
                    await ctx.author.send(f"📖 **RoleAgentBot - Full User Guide**\n\n{readme_content}")
                else:
                    await ctx.author.send("📖 **RoleAgentBot - Full User Guide**")

                    chunks = []
                    current_chunk = ""

                    for line in readme_content.split('\n'):
                        if len(current_chunk) + len(line) + 1 > max_length:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                                current_chunk = line
                            else:
                                while len(line) > max_length:
                                    chunks.append(line[:max_length])
                                    line = line[max_length:]
                                current_chunk = line
                        else:
                            if current_chunk:
                                current_chunk += '\n' + line
                            else:
                                current_chunk = line

                    if current_chunk:
                        chunks.append(current_chunk.strip())

                    for i, chunk in enumerate(chunks, 1):
                        header = f"**Part {i}/{len(chunks)}**\n\n" if len(chunks) > 1 else ""
                        await ctx.author.send(f"{header}```md\n{chunk}\n```")

                server_id = str(ctx.guild.id) if ctx.guild else None
                readme_sent_msg = get_personality_message("answers.json", ["general_messages", "readme_sent_private"], server_id, "📩 Full user guide sent by direct message.")
                await ctx.send(readme_sent_msg)

                logger.info(f"README command executed by {ctx.author.name} in {ctx.guild.name if ctx.guild else 'DM'}")

            except FileNotFoundError:
                await ctx.send("❌ The full user guide file could not be found.")
                logger.error("README_USER.md file not found")
            except Exception as e:
                await ctx.send("❌ The full user guide could not be sent.")
                logger.error(f"Error in README command: {e}")
    else:
        logger.info("Command readme already registered, skipping...")

    # --- TEST PERSONALITY EVOLUTION ---

    if bot.get_command("testpersonalityevolution") is None:
        @bot.command(name="testpersonalityevolution")
        async def cmd_test_personality_evolution(ctx):
            """Test weekly personality evolution with synthetic daily memories."""
            server_id = str(ctx.guild.id) if ctx.guild else None
            role_cfg = get_personality_message("answers.json", ["role_messages"], server_id, {})
            if not is_admin(ctx):
                await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can test personality evolution."))
                return

            if not ctx.guild:
                await ctx.send("❌ This command only works in servers, not in direct messages.")
                return

            server_key = get_server_key(ctx.guild)
            logger.info(f"Test personality evolution command executed by {ctx.author.name} in {ctx.guild.name}")

            await ctx.send("🧬 Starting test personality evolution... This may take a moment.")

            try:
                from agent_mind import generate_test_personality_evolution
                result = await asyncio.to_thread(generate_test_personality_evolution, server_key)

                if result.get("success"):
                    response = (
                        f"✅ **Test personality evolution completed**\n\n"
                        f"📅 Week: {result.get('week_start')} to {result.get('week_end')}\n"
                        f"📝 Evolved paragraphs: {result.get('evolved_paragraphs_count')}\n"
                        f"💾 Backup: `{os.path.basename(result.get('backup_path', 'N/A'))}`\n"
                        f"📄 Check `logs/{result.get('server_id')}/prompt.log` for prompt and LLM response."
                    )
                    await ctx.send(response)
                else:
                    error_msg = result.get("error", "Unknown error")
                    await ctx.send(f"❌ Test evolution failed: {error_msg}")
                    logger.error(f"Test personality evolution failed: {error_msg}")

            except Exception as e:
                logger.exception(f"Error in test personality evolution command: {e}")
                await ctx.send(f"❌ Error during test evolution: {e}")
    else:
        logger.info("Command testpersonalityevolution already registered, skipping...")

    # --- BOT IDENTITY COMMANDS ---

    if bot.get_command("setnickname") is None:
        @bot.command(name="setnickname")
        async def cmd_set_nickname(ctx, *, nickname: str = None):
            """Set bot nickname for this server (admin only)."""
            if not is_admin(ctx):
                await ctx.send("❌ Only administrators can change the bot's nickname.")
                return

            if not ctx.guild:
                await ctx.send("❌ This command only works in servers.")
                return

            try:
                from discord_bot.discord_utils import update_server_identity
                success = await update_server_identity(ctx.guild, nickname=nickname, avatar_bytes=None)
                if success:
                    if nickname:
                        await ctx.send(f"✅ Bot nickname updated to: **{nickname}**")
                    else:
                        await ctx.send("✅ Bot nickname reset to default.")
                else:
                    await ctx.send("⚠️ Could not update nickname. Check bot permissions.")
            except Exception as e:
                logger.error(f"Error in setnickname command: {e}")
                await ctx.send(f"❌ Error updating nickname: {e}")
    else:
        logger.info("Command setnickname already registered, skipping...")

    if bot.get_command("identity") is None:
        @bot.command(name="identity")
        async def cmd_identity(ctx):
            """Show current bot identity configuration for this server."""
            if not ctx.guild:
                await ctx.send("❌ This command only works in servers.")
                return

            try:
                from discord_bot.discord_utils import (
                    get_server_personality_display_name, 
                    get_server_personality_avatar_path,
                    get_server_key
                )
                server_id = get_server_key(ctx.guild)
                current_nick = ctx.guild.me.nick
                configured_name = get_server_personality_display_name(server_id)
                avatar_path = get_server_personality_avatar_path(server_id)

                # Check avatar status
                avatar_status = "Not configured"
                if avatar_path:
                    avatar_size = os.path.getsize(avatar_path)
                    avatar_ext = os.path.splitext(avatar_path)[1].upper()
                    avatar_status = f"{avatar_ext} ({avatar_size:,} bytes)"

                response = (
                    f"🤖 **Bot Identity for this server**\n\n"
                    f"**Nickname:**\n"
                    f"  Current: {current_nick or '(default - no nickname)'}\n"
                    f"  Configured: {configured_name or '(not configured)'}\n\n"
                    f"**Avatar:**\n"
                    f"  {avatar_status}\n\n"
                    f"**Server ID:** {server_id}\n\n"
                )

                # Status summary
                nick_synced = configured_name and current_nick == configured_name
                avatar_configured = avatar_path is not None
                
                if nick_synced and avatar_configured:
                    response += "✅ Identity fully synced with personality configuration."
                elif nick_synced:
                    response += "✅ Nickname synced. Avatar not configured."
                elif configured_name or avatar_configured:
                    response += "⚠️ Identity differs from configuration.\n"
                    response += "Use `!setpersonality <name>` to change or restart to sync."
                else:
                    response += "ℹ️ Add 'bot_display_name' and avatar.webp/png to personality folder to customize identity."

                await ctx.send(response)
            except Exception as e:
                logger.error(f"Error in identity command: {e}")
                await ctx.send(f"❌ Error retrieving identity: {e}")
    else:
        logger.info("Command identity already registered, skipping...")

    # --- SET PERSONALITY COMMAND ---

    if bot.get_command("setpersonality") is None:
        @bot.command(name="setpersonality")
        async def cmd_set_personality(ctx, personality_name: str = None):
            """Change server personality and sync identity (admin only)."""
            if not is_admin(ctx):
                await ctx.send("❌ Only administrators can change the server personality.")
                return

            if not ctx.guild:
                await ctx.send("❌ This command only works in servers.")
                return

            if not personality_name:
                await ctx.send("❌ Please specify a personality name. Usage: `!setpersonality <name>`")
                return

            server_key = get_server_key(ctx.guild)
            logger.info(f"Set personality command by {ctx.author.name}: {personality_name} for server {ctx.guild.name}")

            try:
                # Check if personality exists in global personalities folder
                base_dir = os.path.dirname(os.path.dirname(__file__))
                
                # Get server's language to check correct subdirectory
                from discord_bot.canvas.server_config import get_server_language
                server_language = get_server_language(server_key)
                
                # New structure: personalities/<name>/<language>/
                global_personality_path = os.path.join(base_dir, 'personalities', personality_name, server_language)
                
                # Fallback to old structure if language subdirectory doesn't exist
                if not os.path.exists(global_personality_path):
                    global_personality_path = os.path.join(base_dir, 'personalities', personality_name)
                
                if not os.path.exists(global_personality_path):
                    # List available personalities
                    available = []
                    personalities_dir = os.path.join(base_dir, 'personalities')
                    if os.path.exists(personalities_dir):
                        available = [d for d in os.listdir(personalities_dir) 
                                   if os.path.isdir(os.path.join(personalities_dir, d)) 
                                   and not d.startswith('.')]
                    
                    await ctx.send(
                        f"❌ Personality '{personality_name}' not found.\n"
                        f"Available: {', '.join(available) if available else 'None'}"
                    )
                    return

                # Check for required personality.json (in language subdirectory or root)
                if not os.path.exists(os.path.join(global_personality_path, 'personality.json')):
                    await ctx.send(f"❌ Invalid personality folder: missing personality.json (checked {global_personality_path})")
                    return

                await ctx.send(f"🔄 Changing personality to '{personality_name}' ({server_language})... This may take a moment.")

                # 1. Copy personality to server-specific directory and update config
                from discord_bot.db_init import copy_personality_to_server
                copy_success = copy_personality_to_server(server_key, personality_name, language=server_language, update_config=True)
                
                if not copy_success:
                    await ctx.send("❌ Failed to copy personality files. Check logs.")
                    return

                # 2. Sync identity (nickname + avatar) - single API call
                from discord_bot.discord_utils import sync_bot_identity_to_server_personality
                identity_result = await sync_bot_identity_to_server_personality(ctx.guild)

                # Build success message
                changes = []
                if identity_result['nickname_changed']:
                    changes.append("nickname")
                if identity_result['avatar_changed']:
                    changes.append("avatar")
                
                if identity_result['success']:
                    change_msg = f"({', '.join(changes)} updated)" if changes else "(no visual changes)"
                    await ctx.send(
                        f"✅ **Personality changed to '{personality_name}'** {change_msg}\n\n"
                        f"The bot will now use this personality's behavior, name, and avatar "
                        f"in this server. Changes are immediate."
                    )
                else:
                    await ctx.send(
                        f"⚠️ **Personality changed to '{personality_name}'** "
                        f"but identity sync failed.\n"
                        f"Errors: {', '.join(identity_result['errors'])}\n\n"
                        f"The personality behavior is active, but you may need to "
                        f"update nickname/avatar manually with `!setnickname`."
                    )

            except Exception as e:
                logger.exception(f"Error in setpersonality command: {e}")
                await ctx.send(f"❌ Error changing personality: {e}")
    else:
        logger.info("Command setpersonality already registered, skipping...")

    # --- Log registered commands ---
    logger.info(f"Core commands registered: agenthelp, canvas, {role_cmd_name}, readme, testpersonalityevolution, setnickname, identity, setpersonality")
