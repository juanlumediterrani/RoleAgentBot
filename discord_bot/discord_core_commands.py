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
import sys
import asyncio

# Add parent directory to Python path to import root modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_logging import get_logger
from agent_engine import PERSONALIDAD, think, AGENT_CFG
from discord_bot.discord_utils import (
    is_admin, is_duplicate_command, send_dm_or_channel,
    set_greeting_enabled, get_greeting_enabled,
    is_role_enabled_check,
)

logger = get_logger('discord_core')

_discord_cfg = PERSONALIDAD.get("discord", {})
_personality_name = PERSONALIDAD.get("name", "bot").lower()
_bot_display_name = PERSONALIDAD.get("bot_display_name", PERSONALIDAD.get("name", "Bot"))
_insult_cfg = PERSONALIDAD.get("insult_command", {})  # Moved from discord.insult_command to prompts.json


_talk_state_by_guild_id: dict[int, dict] = {}


def _get_enabled_roles(agent_config: dict) -> list[str]:
    roles_cfg = (agent_config or {}).get("roles", {})
    enabled = []
    for role_name, cfg in roles_cfg.items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("enabled", False):
            enabled.append(role_name)
    return enabled


def _load_role_mission_prompts(role_names: list[str]) -> list[str]:
    prompts: list[str] = []
    role_prompts_cfg = PERSONALIDAD.get("role_system_prompts", {})

    for role_name in role_names:
        try:
            if role_name == "mc":
                from roles.mc.mc import get_mc_system_prompt
                prompts.append(get_mc_system_prompt())
                continue
            if role_name == "banker":
                from roles.banker.banker import get_banker_system_prompt
                prompts.append(get_banker_system_prompt())
                continue
            if role_name == "treasure_hunter":
                from roles.treasure_hunter.treasure_hunter import get_treasure_hunter_system_prompt
                prompts.append(get_treasure_hunter_system_prompt())
                continue
            if role_name == "trickster":
                from roles.trickster.trickster import get_trickster_system_prompt
                prompts.append(get_trickster_system_prompt())
                continue

            prompt = role_prompts_cfg.get(role_name)
            if prompt:
                prompts.append(prompt)
        except Exception as e:
            logger.warning(f"Could not load role prompt for {role_name}: {e}")
            prompt = role_prompts_cfg.get(role_name)
            if prompt:
                prompts.append(prompt)

    return [p for p in prompts if isinstance(p, str) and p.strip()]


def _build_mission_commentary_prompt(agent_config: dict) -> str:
    enabled_roles = _get_enabled_roles(agent_config)
    mission_prompts = _load_role_mission_prompts(enabled_roles)

    roles_text = "\n".join([f"- {r}" for r in enabled_roles]) if enabled_roles else "- none"
    missions_text = "\n\n".join(mission_prompts) if mission_prompts else "(no mission prompts found)"

    # Try to load custom prompt from personality JSON, fallback to default
    custom_cfg = PERSONALIDAD.get("prompts", {}).get("mission_commentary", {})
    if custom_cfg and isinstance(custom_cfg, dict):
        instructions = custom_cfg.get("instructions", [])
        closing = custom_cfg.get("closing", "")
        if instructions:
            rules_section = "\n".join(instructions) + "\n"
        else:
            rules_section = ""
        if closing:
            closing_section = f"\n{closing}"
        else:
            closing_section = ""
    else:
        rules_section = ""
        closing_section = ""

    return (
        "You are the agent speaking in-character. "
        "Give a short, entertaining status commentary about your active missions (roles). "
        "Be concise and do not repeat yourself.\n\n"
        f"{rules_section}"
        f"ACTIVE ROLES:\n{roles_text}\n\n"
        f"MISSION CONTEXT:\n{missions_text}\n\n"
        "Now produce your commentary."
        f"{closing_section}"
    )


def register_core_commands(bot, agent_config):
    """Register all base bot commands."""

    # --- Dynamic names based on personality ---
    greet_name = f"greet{_personality_name}"
    nogreet_name = f"nogreet{_personality_name}"
    welcome_name = f"welcome{_personality_name}"
    nowelcome_name = f"nowelcome{_personality_name}"
    insult_name = f"insult{_personality_name}"
    role_cmd_name = f"role{_personality_name}"
    talk_cmd_name = f"talk{_personality_name}"

    # --- PRESENCE GREETINGS ---

    async def _cmd_saluda_toggle(ctx, enabled: bool):
        """Generic command to enable/disable presence greetings."""
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can modify presence greetings."))
            return

        set_greeting_enabled(ctx.guild, enabled)

        presence_cfg = _discord_cfg.get("member_presence")
        if not isinstance(presence_cfg, dict):
            _discord_cfg["member_presence"] = {}
            presence_cfg = _discord_cfg["member_presence"]
        presence_cfg["enabled"] = enabled

        greeting_cfg = PERSONALIDAD.get("discord", {}).get("member_greeting", {})
        mensaje_activado = greeting_cfg.get("greetings_enabled", "GRRR {_bot_name} will watch for humans! {_bot_name} will greet when humans appear!")
        mensaje_desactivado = greeting_cfg.get("greetings_disabled", "BRRR {_bot_name} will no longer watch humans! {_bot_name} will stop greeting, too much work!")

        mensaje = mensaje_activado.format(_bot_name=_bot_display_name) if enabled else mensaje_desactivado.format(_bot_name=_bot_display_name)
        await ctx.send(mensaje)

        action = "enabled" if enabled else "disabled"
        logger.info(f"{ctx.author.name} {action} presence greetings in {ctx.guild.name}")

    # --- GREETING CONTROL COMMANDS ---
    try:
        @bot.command(name=greet_name)
        async def cmd_greet_enable(ctx):
            await _cmd_saluda_toggle(ctx, True)
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {greet_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {greet_name}: {e}")

    try:
        @bot.command(name=nogreet_name)
        async def cmd_greet_disable(ctx):
            await _cmd_saluda_toggle(ctx, False)
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {nogreet_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {nogreet_name}: {e}")

    # --- WELCOME ---

    async def _cmd_bienvenida_toggle(ctx, enabled: bool):
        """Generic command to enable/disable welcome greetings."""
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can modify welcome greetings."))
            return

        greeting_cfg = _discord_cfg.get("member_greeting", {})
        greeting_cfg["enabled"] = enabled

        greeting_messages_cfg = PERSONALIDAD.get("discord", {}).get("member_greeting", {})
        if enabled:
            mensaje = greeting_messages_cfg.get("greetings_enabled", "✅ Welcome greetings enabled on this server.")
        else:
            mensaje = greeting_messages_cfg.get("greetings_disabled", "✅ Welcome greetings disabled on this server.")

        logger.info(f"{ctx.author.name} {'enabled' if enabled else 'disabled'} welcome greetings in {ctx.guild.name}")
        await ctx.send(mensaje)

    try:
        @bot.command(name=welcome_name)
        async def cmd_welcome_enable(ctx):
            await _cmd_bienvenida_toggle(ctx, True)
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {welcome_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {welcome_name}: {e}")

    try:
        @bot.command(name=nowelcome_name)
        async def cmd_welcome_disable(ctx):
            await _cmd_bienvenida_toggle(ctx, False)
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {nowelcome_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {nowelcome_name}: {e}")

    # --- INSULT ---

    async def _cmd_insult(ctx, obj=""):
        target = obj if obj else ctx.author.mention
        if "@everyone" in target or "@here" in target:
            prompt = _insult_cfg.get("prompt_everyone", "Lanza un insulto breve a TODO EL MUNDO, maximo 1 frase")
        else:
            prompt = _insult_cfg.get("prompt_target", "Lanza un insulto breve a una persona especifica, maximo 1 frase")
        res = await asyncio.to_thread(think, prompt, logger=logger)
        await ctx.send(f"{target} {res}")

    try:
        bot.command(name=insult_name)(_cmd_insult)
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {insult_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {insult_name}: {e}")

    # --- TEST ---

    try:
        @bot.command(name="test")
        async def cmd_test(ctx):
            """Test command to verify the bot works."""
            role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
            logger.info(f"Test command executed by {ctx.author.name}")
            await ctx.send(role_cfg.get("test_command", "✅ Test command works!"))
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info("Command test already registered, skipping...")
        else:
            logger.error(f"Error registering test: {e}")

    async def _start_talk_loop_for_guild(guild_id: int):
        state = _talk_state_by_guild_id.get(guild_id)
        if not state:
            return

        interval_minutes = int(state.get("interval_minutes", 180))
        if interval_minutes < 5:
            interval_minutes = 5
            state["interval_minutes"] = interval_minutes

        while state.get("enabled", False):
            try:
                channel_id = state.get("channel_id")
                channel = bot.get_channel(int(channel_id)) if channel_id else None
                if channel is None:
                    state["enabled"] = False
                    break

                prompt = _build_mission_commentary_prompt(agent_config)
                res = await asyncio.to_thread(think, prompt, logger=logger)
                if res and str(res).strip():
                    await channel.send(str(res).strip())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in talk loop for guild_id={guild_id}: {e}")

            await asyncio.sleep(interval_minutes * 60)

    async def _talk_enable(ctx, interval_minutes: int | None = None):
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can modify this feature."))
            return

        guild_id = int(ctx.guild.id)
        state = _talk_state_by_guild_id.get(guild_id) or {}
        state["enabled"] = True
        state["channel_id"] = int(ctx.channel.id)
        if interval_minutes is not None:
            try:
                state["interval_minutes"] = int(interval_minutes)
            except Exception:
                pass
        if "interval_minutes" not in state:
            state["interval_minutes"] = 180

        task = state.get("task")
        if task and not task.done():
            task.cancel()

        state["task"] = asyncio.create_task(_start_talk_loop_for_guild(guild_id))
        _talk_state_by_guild_id[guild_id] = state

        await ctx.send(
            f"✅ Mission commentary enabled in this channel (every {state['interval_minutes']} minutes)."
        )

    async def _talk_disable(ctx):
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can modify this feature."))
            return

        guild_id = int(ctx.guild.id)
        state = _talk_state_by_guild_id.get(guild_id)
        if not state or not state.get("enabled", False):
            await ctx.send("ℹ️ Mission commentary is already disabled for this server.")
            return

        state["enabled"] = False
        task = state.get("task")
        if task and not task.done():
            task.cancel()
        await ctx.send("✅ Mission commentary disabled for this server.")

    async def _talk_now(ctx):
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return

        prompt = _build_mission_commentary_prompt(agent_config)
        res = await asyncio.to_thread(think, prompt, logger=logger)
        if res and str(res).strip():
            await ctx.send(str(res).strip())
        else:
            await ctx.send("⚠️ Could not generate a commentary right now.")

    async def _talk_status(ctx):
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return

        guild_id = int(ctx.guild.id)
        state = _talk_state_by_guild_id.get(guild_id) or {}
        enabled = bool(state.get("enabled", False))
        channel_id = state.get("channel_id")
        interval_minutes = state.get("interval_minutes", 180)
        channel_mention = f"<#{channel_id}>" if channel_id else "(not set)"
        await ctx.send(
            f"Mission commentary: {'ON' if enabled else 'OFF'} | channel={channel_mention} | interval={interval_minutes} minutes"
        )

    async def _talk_frequency(ctx, minutes: int):
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can modify this feature."))
            return

        guild_id = int(ctx.guild.id)
        state = _talk_state_by_guild_id.get(guild_id) or {}
        state["interval_minutes"] = int(minutes)
        _talk_state_by_guild_id[guild_id] = state

        if state.get("enabled", False):
            task = state.get("task")
            if task and not task.done():
                task.cancel()
            state["task"] = asyncio.create_task(_start_talk_loop_for_guild(guild_id))

        await ctx.send(f"✅ Mission commentary interval set to {state['interval_minutes']} minutes.")

    try:
        @bot.command(name=talk_cmd_name)
        async def cmd_talk(ctx, action: str = "", value: str = ""):
            if not action:
                await ctx.send(
                    f"❌ Usage: `!{talk_cmd_name} on/off/now/status/frequency <minutes>`"
                )
                return

            action_lower = action.lower()
            if action_lower in ["on", "enable", "true", "1"]:
                interval = None
                if value:
                    try:
                        interval = int(value)
                    except Exception:
                        interval = None
                await _talk_enable(ctx, interval_minutes=interval)
                return
            if action_lower in ["off", "disable", "false", "0"]:
                await _talk_disable(ctx)
                return
            if action_lower in ["now", "say", "ping"]:
                await _talk_now(ctx)
                return
            if action_lower in ["status", "info"]:
                await _talk_status(ctx)
                return
            if action_lower in ["frequency", "interval"]:
                if not value:
                    await ctx.send(f"❌ Usage: `!{talk_cmd_name} frequency <minutes>`")
                    return
                try:
                    minutes = int(value)
                except Exception:
                    await ctx.send("❌ Minutes must be an integer.")
                    return
                await _talk_frequency(ctx, minutes)
                return

            await ctx.send(
                f"❌ Unknown action `{action}`. Use: on/off/now/status/frequency."
            )

    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {talk_cmd_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {talk_cmd_name}: {e}")

    # --- ROLE CONTROL ---

    async def _cmd_role_toggle(ctx, role_name: str, enabled: bool):
        """Generic command to enable/disable roles dynamically."""
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("role_no_permission", "❌ Only administrators can modify roles."))
            return

        valid_roles = ["news_watcher", "treasure_hunter", "trickster", "banker"]
        if role_name not in valid_roles:
            await ctx.send(role_cfg.get("role_not_found", "❌ Role '{role}' not valid.").format(role=role_name))
            return

        env_var_name = f"{role_name.upper()}_ENABLED"
        env_value = "true" if enabled else "false"
        os.environ[env_var_name] = env_value

        if "roles" not in agent_config:
            agent_config["roles"] = {}
        if role_name not in agent_config["roles"]:
            agent_config["roles"][role_name] = {}
        agent_config["roles"][role_name]["enabled"] = enabled

        # Register role commands if activating
        if enabled:
            from discord_bot.discord_role_loader import register_single_role
            await register_single_role(bot, role_name, agent_config, PERSONALIDAD)

        if enabled:
            await ctx.send(role_cfg.get("role_activated", "✅ Role '{role}' activated successfully.").format(role=role_name))
            logger.info(f"{ctx.author.name} activated role {role_name} in {ctx.guild.name}")
        else:
            await ctx.send(role_cfg.get("role_deactivated", "✅ Role '{role}' deactivated successfully.").format(role=role_name))
            logger.info(f"{ctx.author.name} deactivated role {role_name} in {ctx.guild.name}")

    try:
        @bot.command(name=role_cmd_name)
        async def cmd_role_control(ctx, role_name: str = "", action: str = ""):
            """Role control. Usage: !role<name> <role> <on/off>"""
            if not role_name:
                await ctx.send("❌ Usage: `!{}<role> <action>` where <action> is on/off, true/false, 1/0, enable/disable".format(_personality_name))
                return

            if not action:
                await ctx.send("❌ Usage: `!{}<role> <action>` where <action> is on/off, true/false, 1/0, enable/disable".format(_personality_name))
                return

            action_lower = action.lower()
            if action_lower in ["on", "true", "1", "enable"]:
                await _cmd_role_toggle(ctx, role_name, True)
            elif action_lower in ["off", "false", "0", "disable"]:
                await _cmd_role_toggle(ctx, role_name, False)
            else:
                await ctx.send("❌ Invalid action. Use: on/off, true/false, 1/0, enable/disable")

    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {role_cmd_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {role_cmd_name}: {e}")

    # --- ENGLISH HELP COMMAND WITH PERSONALITY SUPPORT ---
    try:
        @bot.command(name="agenthelp")
        async def cmd_help(ctx, personality_name: str = ""):
            """Show all available commands for this agent (English)."""
            if is_duplicate_command(ctx, "agenthelp"):
                return

            # If personality name provided, check if it matches this agent
            if personality_name:
                if personality_name.lower() != _personality_name:
                    return  # Don't respond to help for other personalities
                
                # Show help for this specific personality
                await _show_agent_help(ctx, personality_name)
                return
            
            # No personality specified: always show help.
            # NOTE: ctx.guild can be None (DMs, some edge cases). Avoid accessing ctx.guild.members.
            await _show_agent_help(ctx, personality_name)

    except Exception as e:
        if "already an existing command" in str(e):
            logger.info("Command agenthelp already registered, skipping...")
        else:
            logger.error(f"Error registering agenthelp: {e}")

    async def _show_agent_help(ctx, requested_personality):
        """Internal function to show agent help - replicates Spanish help behavior with English commands."""
        roles_config = AGENT_CFG.get("roles", {})
        
        # Use requested personality name or current personality
        display_name = requested_personality or _personality_name
        help_msg = f"🤖 **Available Commands for {bot.user.name} ({display_name})** 🤖\n\n"

        # STATIC PART - Control commands 
        help_msg += "🎛️ **CONTROL COMMANDS**\n"
        help_msg += f"• `!{greet_name}` - Enable presence greetings (DM)\n"
        help_msg += f"• `!{nogreet_name}` - Disable presence greetings\n"
        help_msg += f"• `!{welcome_name}` - Enable new member welcome\n"
        help_msg += f"• `!{nowelcome_name}` - Disable new member welcome\n"
        help_msg += f"• `!{insult_name}` - Send orc insult\n"
        help_msg += f"• `!{role_cmd_name} <role> <on/off>` - Enable/disable roles dynamically\n"
        help_msg += f"• `!agenthelp {display_name}` - Show help for this personality\n"
        help_msg += "• `!readme` - Get complete command reference by private message\n\n"

        # DYNAMIC PART - Role commands
        help_msg += "🎭 **ROLE COMMANDS**\n"

        # News Watcher - 
        if is_role_enabled_check("news_watcher", agent_config):
            interval = roles_config.get("news_watcher", {}).get("interval_hours", 1)
            help_msg += f"📡 **News Watcher** - Smart alerts (every {interval}h)\n"
            help_msg += "  • **Main:** `!watcher` | `!nowatcher` | `!watchernotify`\n"
            help_msg += "  • **Help:** `!watcherhelp` (users) | `!watcherchannelhelp` (admins)\n"
            help_msg += "  • **Channel:** `!watcherchannel` group (subscribe, unsubscribe, status, keywords, premises)\n"
            help_msg += "  • **Subscription:** `!watcher feeds/categories/status/subscribe/unsubscribe/keywords/general/reset`\n\n"
        # Treasure Hunter - 
        if is_role_enabled_check("treasure_hunter", agent_config):
            interval = roles_config.get("treasure_hunter", {}).get("interval_hours", 1)
            help_msg += f"💎 **Treasure Hunter** - POE2 item alerts (every {interval}h)\n"
            help_msg += "  • **Admin:** `!hunter poe2 on//off`, `!hunterfrequency <h>` In a Channel for admins\n"
            help_msg += "  • **League:**`!hunter poe2 league \"Standard\"` | `!hunter poe2 \"Fate of the Vaal\"`\n"
            help_msg += "  • **Items:** `!hunteradd/ \"item\"` | `!hunterdel \"item\"` | `!hunterdel <number>` | `!hunterlist`\n"
            help_msg += "  • **Help:** `!hunterhelp` | `!hunter poe2 help` \n\n"
        # Trickster - 
        if is_role_enabled_check("trickster", agent_config):
            trickster_config = roles_config.get("trickster", {})
            interval = trickster_config.get("interval_hours", 12)
            subroles = trickster_config.get("subroles", {})
            
            help_msg += f"🎭 **Trickster** - Multiple subroles:\n"
            
            if subroles.get("beggar", {}).get("enabled", False):
                help_msg += "  • 🙏 **Beggar:** `!trickster beggar enable/disable/frequency <h>/status/help`\n"
            
            if subroles.get("ring", {}).get("enabled", False):
                help_msg += "  • 👁️ **Ring:** `!accuse @user` | `!trickster ring enable/disable/frequency <h>/help`\n"
            
            if subroles.get("dice_game", {}).get("enabled", False):
                help_msg += "  • 🎲 **Dice Game:** `!dice play/help/balance/stats/ranking/history` | `!dice config bet <amount>` | `!dice config announcements on/off`\n"
            
            help_msg += "  • **Main:** `!trickster help`\n\n"
        # Banker - 
        if is_role_enabled_check("banker", agent_config):
            help_msg += f"💰 **Banker** - Economic management\n"
            help_msg += "  • **Main:** `!banker help`\n"
            help_msg += "  • **Balance:** `!banker balance` (On a channel, he will DM you)\n"
            help_msg += "  • **Config:**  | `!banker bonus <amount>`(admins)\n\n"
        # Music - Always available 
        help_msg += f"🎵  **MC** - Music Bot request a song in a voice channel\n"
        help_msg += "  • **Common use** `!mc play \"ADCD TNT\"`,`!mc add \"Queen Bycicle\"`,`!mc queue`\n"
        help_msg += "  • **Main:** `!mc help`\n    \n" # Jumpline for max characters in discord fix

        # Multiple agents info (only when no specific personality requested)
        if not requested_personality: 
            help_msg += "🔀 **MULTIPLE AGENTS**\n"
            help_msg += f"• Use `!agenthelp {display_name}` for help specific to this agent\n"
            help_msg += "• Each agent has its own personality and commands\n\n"

        # Basic conversation 
        help_msg += "💬 **BASIC CONVERSATION**\n"
        help_msg += "• Mention the bot to talk\n"
        help_msg += "• Responds using the agent's personality\n"
        help_msg += f"• Bot will respond as its character ({_bot_display_name})\n\n"
        
        # Active and inactive roles (exact same logic as Spanish help)
        help_msg += "🎭 **ACTIVE AND INACTIVE ROLES**\n"
        role_descriptions = {
            "mc": "🎵 **Music** - Always available (no activation required)",
            "news_watcher": "📡 **News Watcher** - Critical news alerts",
            "treasure_hunter": "💎 **Treasure Hunter** - Purchase opportunity alerts",
            "trickster": "🎭 **Trickster** - Beggar, ring, and dice game subroles",
            "banker": "💰 **Banker** - Economic management and daily TAE",
        }

        for role_name_key, role_cfg_val in roles_config.items():
            enabled = is_role_enabled_check(role_name_key, agent_config)
            if role_name_key == "mc":
                status_emoji = "✅"
            else:
                status_emoji = "✅" if enabled else "❌"
            # Same logic as Spanish help - use role_descriptions
            display = role_descriptions.get(role_name_key, f"**{role_name_key.replace('_', ' ').title()}**")
            help_msg += f"• {status_emoji} {display}\n"

        # Send help (use personality message with fallback)
        help_sent_msg = PERSONALIDAD.get("discord", {}).get("general_messages", {}).get("help_sent_private", "📩 Help sent by private message.")
        await send_dm_or_channel(ctx, help_msg, help_sent_msg)


    # --- README COMMAND ---
    try:
        @bot.command(name="readme")
        async def cmd_readme(ctx):
            """Send user-friendly README content privately to user."""
            try:
                # Read the README_USER.md file
                readme_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README_USER.md")
                with open(readme_path, 'r', encoding='utf-8') as f:
                    readme_content = f.read()
                
                # Discord has a 2000 character limit, so we need to split long content
                max_length = 1900  # Leave some buffer for formatting
                
                if len(readme_content) <= max_length:
                    # Send as single message if short enough
                    await ctx.author.send(f"📖 **RoleAgentBot - Complete User Guide**\n\n{readme_content}")
                else:
                    # Split into multiple messages
                    await ctx.author.send("📖 **RoleAgentBot - Complete User Guide**")
                    
                    # Split content into chunks
                    chunks = []
                    current_chunk = ""
                    
                    for line in readme_content.split('\n'):
                        # If adding this line would exceed limit, start new chunk
                        if len(current_chunk) + len(line) + 1 > max_length:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                                current_chunk = line
                            else:
                                # Line itself is too long, force split
                                while len(line) > max_length:
                                    chunks.append(line[:max_length])
                                    line = line[max_length:]
                                current_chunk = line
                        else:
                            if current_chunk:
                                current_chunk += '\n' + line
                            else:
                                current_chunk = line
                    
                    # Add the last chunk
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    
                    # Send chunks with part numbers
                    for i, chunk in enumerate(chunks, 1):
                        header = f"**Part {i}/{len(chunks)}**\n\n" if len(chunks) > 1 else ""
                        await ctx.author.send(f"{header}```md\n{chunk}\n```")
                
                # Confirm in channel (use personality message with fallback)
                readme_sent_msg = PERSONALIDAD.get("discord", {}).get("general_messages", {}).get("readme_sent_private", "📩 Complete user guide sent by private message.")
                await ctx.send(readme_sent_msg)
                
                logger.info(f"README command executed by {ctx.author.name} in {ctx.guild.name if ctx.guild else 'DM'}")
                
            except FileNotFoundError:
                await ctx.send("❌ User guide file not found.")
                logger.error("README_USER.md file not found")
            except Exception as e:
                await ctx.send("❌ Error sending user guide.")
                logger.error(f"Error in README command: {e}")
                
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info("Command readme already registered, skipping...")
        else:
            logger.error(f"Error registering readme: {e}")

    # --- Log registered commands ---
    logger.info(f"Core commands registered: {greet_name}, {nogreet_name}, {welcome_name}, {nowelcome_name}, {insult_name}, agenthelp, {role_cmd_name}, test, readme")
