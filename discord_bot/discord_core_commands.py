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
from agent_engine import PERSONALIDAD, pensar, AGENT_CFG
from discord_bot.discord_utils import (
    is_admin, is_duplicate_command, send_dm_or_channel,
    set_greeting_enabled, get_greeting_enabled,
    is_role_enabled_check,
)

logger = get_logger('discord_core')

_discord_cfg = PERSONALIDAD.get("discord", {})
_personality_name = PERSONALIDAD.get("name", "bot").lower()
_bot_display_name = PERSONALIDAD.get("bot_display_name", PERSONALIDAD.get("name", "Bot"))
_insult_cfg = _discord_cfg.get("insult_command", {})


def register_core_commands(bot, agent_config):
    """Registra todos los comandos base del bot."""

    # --- Dynamic names based on personality ---
    greet_name = f"greet{_personality_name}"
    nogreet_name = f"nogreet{_personality_name}"
    welcome_name = f"welcome{_personality_name}"
    nowelcome_name = f"nowelcome{_personality_name}"
    insult_name = f"insult{_personality_name}"
    role_cmd_name = f"role{_personality_name}"

    # --- PRESENCE GREETINGS ---

    async def _cmd_saluda_toggle(ctx, enabled: bool):
        """Generic command to enable/disable presence greetings."""
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can modify presence greetings."))
            return

        set_greeting_enabled(ctx.guild, enabled)

        greeting_cfg = PERSONALIDAD.get("discord", {}).get("greeting_messages", {})
        mensaje_activado = greeting_cfg.get("saludos_activados", "GRRR Kronk will watch for humans! Kronk will greet when humans appear!")
        mensaje_desactivado = greeting_cfg.get("saludos_desactivados", "BRRR Kronk will no longer watch humans! Kronk will stop greeting, too much work!")

        mensaje = mensaje_activado if enabled else mensaje_desactivado
        await ctx.send(mensaje)

        action = "enabled" if enabled else "disabled"
        logger.info(f"{ctx.author.name} {action} presence greetings in {ctx.guild.name}")

    # --- GREETING CONTROL COMMANDS ---

    @bot.command(name=greet_name)
    async def cmd_greet_enable(ctx):
        await _cmd_saluda_toggle(ctx, True)

    @bot.command(name=nogreet_name)
    async def cmd_greet_disable(ctx):
        await _cmd_saluda_toggle(ctx, False)

    # --- WELCOME ---

    async def _cmd_bienvenida_toggle(ctx, enabled: bool):
        """Generic command to enable/disable welcome greetings."""
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can modify welcome greetings."))
            return

        greeting_cfg = _discord_cfg.get("member_greeting", {})
        greeting_cfg["enabled"] = enabled

        greeting_messages_cfg = PERSONALIDAD.get("discord", {}).get("greeting_messages", {})
        if enabled:
            mensaje = greeting_messages_cfg.get("bienvenida_activados", "✅ Welcome greetings enabled on this server.")
        else:
            mensaje = greeting_messages_cfg.get("bienvenida_desactivados", "✅ Welcome greetings disabled on this server.")

        logger.info(f"{ctx.author.name} {'enabled' if enabled else 'disabled'} welcome greetings in {ctx.guild.name}")
        await ctx.send(mensaje)

    @bot.command(name=welcome_name)
    async def cmd_welcome_enable(ctx):
        await _cmd_bienvenida_toggle(ctx, True)

    @bot.command(name=nowelcome_name)
    async def cmd_welcome_disable(ctx):
        await _cmd_bienvenida_toggle(ctx, False)

    # --- INSULT ---

    async def _cmd_insulta(ctx, obj=""):
        target = obj if obj else ctx.author.mention
        if "@everyone" in target or "@here" in target:
            prompt = _insult_cfg.get("prompt_everyone", "Lanza un insulto breve a TODO EL MUNDO, maximo 1 frase")
        else:
            prompt = _insult_cfg.get("prompt_target", "Lanza un insulto breve a una persona especifica, maximo 1 frase")
        res = await asyncio.to_thread(pensar, prompt, logger=logger)
        await ctx.send(f"{target} {res}")

    bot.command(name=insult_name)(_cmd_insulta)

    # --- TEST ---

    @bot.command(name="test")
    async def cmd_test(ctx):
        """Test command to verify the bot works."""
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        logger.info(f"Test command executed by {ctx.author.name}")
        await ctx.send(role_cfg.get("test_command", "✅ Comando test funciona!"))

    # --- ROLE CONTROL ---

    async def _cmd_role_toggle(ctx, role_name: str, enabled: bool):
        """Generic command to enable/disable roles dynamically."""
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("role_no_permission", "❌ Only administrators can modify roles."))
            return

        valid_roles = ["news_watcher", "treasure_hunter", "trickster", "banker",
                       "vigia_noticias", "buscador_tesoros", "trilero", "banquero"]
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

        # Registrar comandos del rol si se está activando
        if enabled:
            from discord_bot.discord_role_loader import register_single_role
            await register_single_role(bot, role_name, agent_config, PERSONALIDAD)

        if enabled:
            await ctx.send(role_cfg.get("role_activated", "✅ Role '{role}' activated successfully.").format(role=role_name))
            logger.info(f"{ctx.author.name} activated role {role_name} in {ctx.guild.name}")
        else:
            await ctx.send(role_cfg.get("role_deactivated", "✅ Role '{role}' deactivated successfully.").format(role=role_name))
            logger.info(f"{ctx.author.name} deactivated role {role_name} in {ctx.guild.name}")

    @bot.command(name=role_cmd_name)
    async def cmd_role_control(ctx, role_name: str = "", action: str = ""):
        """Role control. Usage: !role<name> <role> <on/off>"""
        if not role_name:
            await ctx.send(f"❌ You must specify a role. Example: !{role_cmd_name} trickster on")
            return
        if not action:
            await ctx.send(f"❌ You must specify an action. Example: !{role_cmd_name} trickster on")
            return

        action_lower = action.lower()
        if action_lower in ["on", "true", "1", "enable"]:
            await _cmd_role_toggle(ctx, role_name, True)
        elif action_lower in ["off", "false", "0", "disable"]:
            await _cmd_role_toggle(ctx, role_name, False)
        else:
            await ctx.send("❌ Invalid action. Use: on/off, true/false, 1/0, enable/disable")

    # --- ENGLISH HELP COMMAND WITH PERSONALITY SUPPORT ---
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

        # No personality specified - check if this agent should respond
        # Use bot ID as tiebreaker to ensure only one agent responds
        bot_id = str(bot.user.id)
        bot_ids_in_server = []
        
        # Try to get list of bot IDs in this server
        if ctx.guild:
            bot_ids_in_server = [str(bot.id) for bot in ctx.guild.members if bot.bot]
        
        # Sort bot IDs and use the smallest one as the "primary" help responder
        if bot_ids_in_server:
            sorted_bot_ids = sorted(bot_ids_in_server)
            primary_bot_id = sorted_bot_ids[0]
            
            # Only respond if this is the primary bot
            if bot_id != primary_bot_id:
                return  # Let the primary bot handle general help
        
        # This agent should respond to general help
        await _show_agent_help(ctx, None)

    async def _show_agent_help(ctx, requested_personality):
        """Internal function to show agent help - replicates Spanish help behavior with English commands."""
        roles_config = AGENT_CFG.get("roles", {})
        
        # Use requested personality name or current personality
        display_name = requested_personality or _personality_name
        help_msg = f"🤖 **Available Commands for {bot.user.name} ({display_name})** 🤖\n\n"

        # STATIC PART - Control commands (English only)
        help_msg += "🎛️ **CONTROL COMMANDS**\n"
        help_msg += f"• `!{greet_name}` - Enable presence greetings (DM)\n"
        help_msg += f"• `!{nogreet_name}` - Disable presence greetings\n"
        help_msg += f"• `!{welcome_name}` - Enable new member welcome\n"
        help_msg += f"• `!{nowelcome_name}` - Disable new member welcome\n"
        help_msg += f"• `!{insult_name}` - Send orc insult\n"
        help_msg += f"• `!{role_cmd_name} <role> <on/off>` - Enable/disable roles dynamically\n"
        help_msg += f"• `!agenthelp {display_name}` - Show help for this personality\n\n"

        # DYNAMIC PART - Role commands (only show active roles, exactly like Spanish help)
        help_msg += "🎭 **ROLE COMMANDS**\n"

        # News Watcher - Check English first, then Spanish (exact same logic as Spanish help)
        if is_role_enabled_check("news_watcher", agent_config):
            interval = roles_config.get("news_watcher", {}).get("interval_hours", 1)
            help_msg += f"📡 **News Watcher** - Smart alerts (every {interval}h)\n"
            help_msg += "  • **Main:** `!watcher` | `!nowatcher` | `!watchernotify`\n"
            help_msg += "  • **Help:** `!watcherhelp` (users) | `!watcherchannelhelp` (admins)\n"
            help_msg += "  • **Channel:** `!watcherchannel` group (subscribe, unsubscribe, status, keywords, premises)\n"
            help_msg += "  • **Subscription:** `!watcher feeds/categories/status/subscribe/unsubscribe/keywords/general/reset`\n"
            help_msg += "  • **Spanish legacy:** `!vigia`, `!vigiaayuda` (deprecated)\n\n"
        elif is_role_enabled_check("vigia_noticias", agent_config):
            interval = roles_config.get("vigia_noticias", {}).get("interval_hours", 1)
            help_msg += f"📡 **Vigía de Noticias** (Spanish) - Alertas inteligentes (cada {interval}h)\n"
            help_msg += "  • **Main:** `!vigia` | `!novigia` | `!avisanoticias`\n"
            help_msg += "  • **Help:** `!vigiaayuda` (usuarios) | `!vigiacanalayuda` (admins)\n"
            help_msg += "  • **Channel:** `!vigiacanal` comandos\n\n"

        # Treasure Hunter - Check English first, then Spanish
        if is_role_enabled_check("treasure_hunter", agent_config):
            interval = roles_config.get("treasure_hunter", {}).get("interval_hours", 1)
            help_msg += f"💎 **Treasure Hunter** - POE2 item alerts (every {interval}h)\n"
            help_msg += "  • **Main:** `!hunter poe2` | `!nohunter poe2`\n"
            help_msg += "  • **League:** `!hunterpoe2` | `!hunterpoe2 Standard` | `!hunterpoe2 Fate of the Vaal`\n"
            help_msg += "  • **Items:** `!hunteradd \"item\"` | `!hunterdel \"item\"` | `!hunterdel <number>` | `!hunterlist`\n"
            help_msg += "  • **Help:** `!hunterhelp` | `!hunterfrequency <h>`\n"
            help_msg += "  • **Spanish legacy:** `!buscartesoros`, `!poe2ayuda` (deprecated)\n\n"
        elif is_role_enabled_check("buscador_tesoros", agent_config):
            interval = roles_config.get("buscador_tesoros", {}).get("interval_hours", 1)
            help_msg += f"💎 **Buscador de Tesoros** (Spanish) - Alertas POE2 (cada {interval}h)\n"
            help_msg += "  • **Main:** `!buscartesoros poe2` | `!nobuscartesoros poe2`\n"
            help_msg += "  • **League:** `!poe2liga` | `!poe2liga Standard`\n"
            help_msg += "  • **Items:** `!poe2add \"item\"` | `!poe2del \"item\"` | `!poe2list`\n"
            help_msg += "  • **Help:** `!poe2ayuda` | `!tesorosfrecuencia <h>`\n\n"

        # Trickster - Check English first, then Spanish
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
            
            help_msg += "  • **Main:** `!trickster help`\n"
            help_msg += "  • **Spanish legacy:** `!trilero`, `!bote`, `!acusaranillo` (deprecated)\n\n"
        elif is_role_enabled_check("trilero", agent_config):
            trilero_config = roles_config.get("trilero", {})
            interval = trilero_config.get("interval_hours", 12)
            subroles = trilero_config.get("subroles", {})
            
            help_msg += f"🎭 **Trilero** (Spanish) - Múltiples subroles:\n"
            
            if subroles.get("limosna", {}).get("enabled", False):
                help_msg += "  • 🙏 **Limosna:** `!trilero limosna on/off/frecuencia <h>`\n"
            
            if subroles.get("anillo", {}).get("enabled", False):
                help_msg += "  • 👁️ **Anillo:** `!acusaranillo @usuario` | `!trilero anillo on/off`\n"
            
            if subroles.get("bote", {}).get("enabled", False):
                help_msg += "  • 🎲 **Bote:** `!bote` comandos | `!bote jugar`\n"
            
            help_msg += "  • **Help:** `!trilero ayuda` | `!bote ayuda`\n\n"

        # Banker - Check English first, then Spanish
        if is_role_enabled_check("banker", agent_config):
            help_msg += f"💰 **Banker** - Economic management\n"
            help_msg += "  • **Main:** `!banker help`\n"
            help_msg += "  • **Balance:** `!banker balance` (DM)\n"
            help_msg += "  • **Config:** `!banker tae <amount>` | `!banker tae` | `!banker bonus <amount>` | `!banker bonus` (admins)\n"
            help_msg += "  • **Spanish legacy:** `!banquero` (deprecated)\n\n"
        elif is_role_enabled_check("banquero", agent_config):
            help_msg += f"💰 **Banquero** (Spanish) - Gestión económica\n"
            help_msg += "  • **Main:** `!banquero comandos | `!banquero saldo`\n"
            help_msg += "  • **Config:** `!banquero tae <cantidad>` | `!banquero bono <cantidad>` (admins)\n\n"

        # Music - Always available (same as Spanish help)
        music_help_msg = PERSONALIDAD.get("discord", {}).get("role_messages", {}).get("music_help", "🎵 **Music** - `!mc play <song>` / `!mc queue` | `!mc help` for complete help (always available)")
        help_msg += f"{music_help_msg}\n\n"

        # Basic conversation (same as Spanish help)
        help_msg += "💬 **BASIC CONVERSATION**\n"
        help_msg += "• Mention the bot to talk\n"
        help_msg += "• Responds using the agent's personality\n"
        help_msg += f"• Bot will respond as its character ({_bot_display_name})\n\n"

        # Multiple agents info (only when no specific personality requested)
        if not requested_personality:
            help_msg += "🔀 **MULTIPLE AGENTS**\n"
            help_msg += f"• Use `!agenthelp {display_name}` for help specific to this agent\n"
            help_msg += "• Each agent has its own personality and commands\n\n"

        # Active and inactive roles (exact same logic as Spanish help)
        help_msg += "🎭 **ACTIVE AND INACTIVE ROLES**\n"
        role_descriptions = {
            "vigia_noticias": "📡 **Vigía de Noticias** - Alertas de noticias críticas",
            "buscador_tesoros": "💎 **Buscador de Tesoros** - Alertas de oportunidades de compra",
            "trilero": "🎭 **Trilero** - Subroles limosna, anillo y bote",
            "banquero": "💰 **Banquero** - Gestión económica y TAE diaria",
            "mc": "🎵 **Música** - Siempre disponible (no requiere activación)",
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

        # Send help (same as Spanish help but English confirmation)
        await send_dm_or_channel(ctx, help_msg, "📩 Help sent by private message.")

    # --- Log registered commands ---
    logger.info(f"Core commands registered: {greet_name}, {nogreet_name}, {welcome_name}, {nowelcome_name}, {insult_name}, agenthelp, {role_cmd_name}, test")
