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

def _load_personality_answers() -> dict:
    try:
        from agent_runtime import get_personality_file_path
        answers_path = get_personality_file_path("answers.json")
        if answers_path:
            import json
            with open(answers_path, encoding="utf-8") as f:
                return json.load(f).get("discord", {})
    except Exception as e:
        logger.warning(f"Could not load personality answers.json: {e}")
    return {}


# Dynamic personality answers with server-specific cache
_personality_answers_cache = {}
_personality_answers_cache_server_id = None

def _get_personality_answers() -> dict:
    """
    Get personality answers with server-specific caching.
    
    This function dynamically loads answers based on the active server,
    caching the result to avoid repeated file reads for the same server.
    """
    global _personality_answers_cache, _personality_answers_cache_server_id
    
    try:
        from agent_db import get_server_id
        current_server_id = get_server_id()
    except:
        current_server_id = None
    
    # Check if we need to reload (different server or no cache)
    if current_server_id != _personality_answers_cache_server_id or not _personality_answers_cache:
        _personality_answers_cache = _load_personality_answers()
        _personality_answers_cache_server_id = current_server_id
        if os.getenv('ROLE_AGENT_PROCESS') != '1':
            logger.info(f"💬 [ANSWERS] Loaded for server: {current_server_id}")
    
    return _personality_answers_cache


# Create dynamic _personality_answers proxy
class _PersonalityAnswersProxy:
    """Proxy for dynamic personality answers loading."""
    def __getitem__(self, key):
        return _get_personality_answers().get(key)
    
    def get(self, key, default=None):
        return _get_personality_answers().get(key, default)
    
    def __contains__(self, key):
        return key in _get_personality_answers()
    
    def keys(self):
        return _get_personality_answers().keys()
    
    def values(self):
        return _get_personality_answers().values()
    
    def items(self):
        return _get_personality_answers().items()
    
    def __repr__(self):
        return repr(_get_personality_answers())


_discord_cfg = _get_personality_answers()
_personality_name = PERSONALITY.get("name", "bot").lower()
_insult_cfg = PERSONALITY.get("insult_command", {})  # Moved from discord.insult_command to prompts.json
_personality_answers = _PersonalityAnswersProxy()
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
        role_cfg = _personality_answers.get("role_messages", {})
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
        help_sent_msg = _personality_answers.get("general_messages", {}).get("help_sent_private", "📩 Help sent by direct message.")
        await send_dm_or_channel(ctx, help_msg, help_sent_msg)


    # --- CANVAS HUB COMMAND ---
    register_canvas_command(
        bot,
        agent_config,
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

                readme_sent_msg = _personality_answers.get("general_messages", {}).get("readme_sent_private", "📩 Full user guide sent by direct message.")
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
            role_cfg = _personality_answers.get("role_messages", {})
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

    # --- Log registered commands ---
    logger.info(f"Core commands registered: agenthelp, canvas, {role_cmd_name}, readme, testpersonalityevolution")
