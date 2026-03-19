"""
Discord bot core — setup, events, automatic tasks and message processing.
Role commands are delegated to roles/*_discord.py.
Dynamic loading is managed from discord_role_loader.py.
"""

import os
import json
import discord
import asyncio
import random
import time
from discord.ext import commands, tasks

from agent_engine import PERSONALITY, think, get_discord_token, AGENT_CFG
from agent_db import set_current_server, get_active_server_name
from agent_logging import get_logger, update_log_file_path
from discord_bot.discord_utils import (
    get_db_for_server,
    get_greeting_enabled, check_chat_rate_limit,
    set_is_connected, is_role_enabled_check,
    get_server_key,
)

logger = get_logger('discord')

# --- CONFIGURATION ---

def _load_personality_answers() -> dict:
    try:
        personality_rel = AGENT_CFG.get("personality", "")
        personality_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), personality_rel)
        answers_path = os.path.join(os.path.dirname(personality_path), "answers.json")
        if os.path.exists(answers_path):
            with open(answers_path, encoding="utf-8") as f:
                return json.load(f).get("discord", {})
    except Exception as e:
        logger.warning(f"Could not load personality answers.json: {e}")
    return {}


_discord_cfg = _load_personality_answers()
_cmd_prefix = _discord_cfg.get("command_prefix", "!")
_bot_display_name = PERSONALITY.get("bot_display_name", PERSONALITY.get("name", "Bot"))
_personality_name = PERSONALITY.get("name", "bot").lower()


def load_agent_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading agent_config.json: {e}")
        return {"roles": {}}


agent_config = load_agent_config()

# --- INTENTS (only required ones — security fix: was Intents.all()) ---
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=_cmd_prefix, intents=intents)

# --- AUTOMATIC TASKS ---

@tasks.loop(hours=24)
async def database_cleanup():
    active_server_key = (get_active_server_name() or "").strip()
    target_guild = None
    if active_server_key:
        active_key_lower = active_server_key.lower()
        for g in bot.guilds:
            if str(getattr(g, "id", "")) == active_server_key:
                target_guild = g
                break
            if getattr(g, "name", "").lower() == active_key_lower:
                target_guild = g
                break
    if target_guild is None and bot.guilds:
        target_guild = bot.guilds[0]
    if target_guild is None:
        return
    db_instance = get_db_for_server(target_guild)
    rows = await asyncio.to_thread(db_instance.limpiar_interacciones_antiguas, 30)
    from discord_bot.discord_utils import get_server_key
    server_key = get_server_key(target_guild)
    logger.info(f"🧹 Cleanup in {target_guild.name} ({server_key}): {rows} records deleted.")


async def set_mc_presence_if_enabled():
    """Set bot presence status if MC role is active."""
    try:
        if is_role_enabled_check("mc", agent_config):
            mc_cfg = _discord_cfg.get("mc_messages", {})
            presence_message = mc_cfg.get("presence_status", "🎵 MC is ready. Use !mc play")
            await bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.listening, name=presence_message)
            )
            logger.info(f"🎵 MC status: {presence_message}")
    except Exception as e:
        logger.error(f"Error setting MC status: {e}")


set_is_connected(False)

# --- EVENTS ---

_commands_registered = False


async def _register_bot_commands():
    """Register core and role commands once during startup."""
    from discord_bot.discord_core_commands import register_core_commands
    from discord_bot.discord_role_loader import register_all_role_commands

    logger.info("Importing core commands...")
    register_core_commands(bot, agent_config)
    logger.info(f"✅ Core commands registered: {len(bot.commands)}")

    logger.info("📦 Importing role commands...")
    await register_all_role_commands(bot, agent_config, PERSONALITY)
    logger.info(f"✅ Role commands registered: {len(bot.commands)}")


@bot.event
async def on_ready():
    """Runs when the bot is ready."""
    global _commands_registered, logger

    logger.info(f"on_ready called - current commands: {len(bot.commands)}")
    if bot.commands:
        logger.info(f"🔍 Existing commands: {[cmd.name for cmd in bot.commands]}")

    logger.info("🚀 Initializing bot...")

    if _commands_registered:
        logger.info("Commands already registered via startup flag - skipping...")
        return

    logger.info("🚀 Starting command registration...")

    try:
        await _register_bot_commands()
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info("📋 Commands already registered, skipping...")
        else:
            logger.error(f"❌ Error registering commands: {e}")
            return

    logger.info(f"🤖 Total commands registered: {len(bot.commands)}")
    for cmd in bot.commands:
        logger.info(f"  → {cmd.name}")

    _commands_registered = True

    # Choose active server
    preferred_guild = os.getenv("DISCORD_ACTIVE_GUILD", "").strip().lower()
    active_guild = None
    if preferred_guild:
        for g in bot.guilds:
            if g.name.lower() == preferred_guild:
                active_guild = g
                break
    if active_guild is None and bot.guilds:
        active_guild = bot.guilds[0]

    if active_guild is not None:
        from discord_bot.discord_utils import get_server_key
        server_key = get_server_key(active_guild)
        set_current_server(server_key)
        update_log_file_path(server_key, _personality_name)
        logger = get_logger('discord')
        logger.info(f"📁 Active server: '{active_guild.name}' ({server_key})")

    logger.info(f"🤖 Bot {_bot_display_name} connected as {bot.user}")
    logger.info(f"🤖 Prefix: {_cmd_prefix} | Intents: members={bot.intents.members}, presences={bot.intents.presences}")

    # Automatic tasks
    if not database_cleanup.is_running():
        database_cleanup.start()
        logger.info("🧹 DB cleanup task started")
    await set_mc_presence_if_enabled()


@bot.event
async def on_guild_join(guild):
    """Runs when the bot joins a new server."""
    from discord_bot.discord_utils import get_server_key
    server_key = get_server_key(guild)
    update_log_file_path(server_key, _personality_name)
    logger.info(f"📁 New server: '{guild.name}' ({server_key})")

    if is_role_enabled_check("mc", agent_config):
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                mc_cfg = _discord_cfg.get("mc_messages", {})
                msg = mc_cfg.get("welcome_message",
                    "🎵 **MC has arrived!** 🎵\n"
                    "• `!mc play <song>` - Play music\n"
                    "• `!mc help` - Show all commands\n"
                    "🎤 **Join a voice channel to begin!**")
                await channel.send(msg)
                break


@bot.event
async def on_member_join(member):
    """Runs when a new user joins the server."""
    from behavior.welcome import handle_member_join
    await handle_member_join(member, _discord_cfg)


@bot.event
async def on_presence_update(before, after):
    """Runs when a member goes from offline to online."""
    from behavior.greet import handle_presence_update
    await handle_presence_update(before, after, _discord_cfg, _bot_display_name)


@bot.event
async def on_voice_state_update(member, before, after):
    """Disconnect the bot from voice if the channel is empty (MC feature)."""
    if member.bot:
        return
    for vc in list(bot.voice_clients):
        if not vc.is_connected():
            continue
        human_users = [m for m in vc.channel.members if not m.bot]
        if len(human_users) == 0:
            await asyncio.sleep(30)
            if vc.is_connected():
                current_users = [m for m in vc.channel.members if not m.bot]
                if len(current_users) == 0:
                    guild = vc.guild
                    await vc.disconnect()
                    
                    # Try to get MC instance to send message through callback system
                    try:
                        from roles.mc.mc_discord import get_mc_commands_instance
                        mc_commands = get_mc_commands_instance()
                        if mc_commands:
                            # Use MC message system to support Canvas callbacks
                            mc_cfg = _discord_cfg.get("mc_messages", {})
                            msg = mc_cfg.get("voice_leave_empty", "👋 The voice channel is empty, leaving now.")
                            channel = next(
                                (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),
                                None
                            )
                            if channel:
                                await mc_commands._send_message(channel, msg)
                        else:
                            # Fallback to direct message if MC instance not available
                            mc_cfg = _discord_cfg.get("mc_messages", {})
                            msg = mc_cfg.get("voice_leave_empty", "👋 The voice channel is empty, leaving now.")
                            channel = next(
                                (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),
                                None
                            )
                            if channel:
                                await channel.send(msg)
                    except Exception:
                        pass


@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    logger.error(f"Command error: {error}")
    if isinstance(error, commands.CommandNotFound):
        logger.warning(f"Command not found: {ctx.message.content}")
        logger.info(f"Available commands: {[cmd.name for cmd in bot.commands]}")
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        return


@bot.event
async def on_message(message):
    """Handle messages: commands (!) and chat (mentions/DMs)."""
    if message.author == bot.user:
        return

    # Debug logging
    if message.content.startswith(bot.command_prefix):
        logger.info(f"🔍 Command detected: {message.content}")
        logger.info(f"🔍 Available commands: {[cmd.name for cmd in bot.commands]}")
        await bot.process_commands(message)
        return

    if message.guild is not None:
        try:
            from discord_bot.discord_core_commands import is_taboo_triggered
            taboo_hit, taboo_keyword = is_taboo_triggered(int(message.guild.id), message.content)
            if taboo_hit:
                server_name = get_server_key(message.guild)
                
                # Get taboo response from prompts.json
                taboo_prompt_cfg = (PERSONALITY.get("role_system_prompts", {}).get("subroles", {}) or {}).get("taboo", {})
                taboo_response_msg = taboo_prompt_cfg.get("response", "TABOO WARNING: That word is not appropriate here.")
                
                # Build the complete taboo prompt following the standard structure
                taboo_user_message = f"TABOO DETECTION: The user {message.author.display_name} said the forbidden keyword '{taboo_keyword}'. Respond in character, briefly, and call it out."
                
                # Use the same think function as normal chat to get full memory context
                taboo_response = await asyncio.to_thread(
                    think,
                    role_context=f"{_bot_display_name} - taboo",
                    user_content=taboo_user_message,
                    is_public=True,
                    logger=logger,
                    user_id=message.author.id,
                    user_name=message.author.name,
                    server_name=server_name,
                    interaction_type="taboo",
                )
                
                # If LLM response is good, use it, otherwise fallback to prompts.json response
                if taboo_response and str(taboo_response).strip():
                    await message.channel.send(str(taboo_response).strip())
                else:
                    # Fallback to direct response from prompts.json
                    await message.channel.send(taboo_response_msg)
                return
        except Exception as e:
            logger.exception(f"Error processing taboo trigger: {e}")

    # Only process if DM or direct mention
    if message.guild is None or bot.user.mentioned_in(message):
        await _process_chat_message(message)


def _clean_message_content(message):
    """Clean message content by replacing Discord mentions with readable names and extracting user content after bot mention."""
    try:
        content = message.content
        
        # If bot is mentioned, extract only the user's content after the mention
        if message.guild and bot.user.mentioned_in(message):
            # Find bot mention and extract content after it
            bot_mention = f'<@{bot.user.id}>'
            bot_mention_bang = f'<@!{bot.user.id}>'
            
            if bot_mention in content:
                parts = content.split(bot_mention, 1)
                if len(parts) > 1:
                    content = parts[1].strip()
            elif bot_mention_bang in content:
                parts = content.split(bot_mention_bang, 1)
                if len(parts) > 1:
                    content = parts[1].strip()
        
        # Replace other user mentions with display names (except bot's own mention which we already handled)
        for mention in message.mentions:
            if mention.id != bot.user.id:  # Skip bot's own mention
                content = content.replace(f'<@{mention.id}>', f'@{mention.display_name}')
                content = content.replace(f'<@!{mention.id}>', f'@{mention.display_name}')
        
        # Replace role mentions with role names
        for role_mention in message.role_mentions:
            content = content.replace(f'<@&{role_mention.id}>', f'@{role_mention.name}')
        
        # Replace channel mentions with channel names
        for channel_mention in message.channel_mentions:
            content = content.replace(f'<#{channel_mention.id}>', f'#{channel_mention.name}')
        
        # Clean @everyone and @here
        content = content.replace('@everyone', '@everyone')
        content = content.replace('@here', '@here')
        
        return content
    except Exception as e:
        logger.warning(f"Error cleaning message content: {e}")
        return message.content


async def _process_chat_message(message):
    """Process normal chat messages (DMs and mentions) with rate limiting."""
    # Rate limiting per user (security fix)
    if check_chat_rate_limit(message.author.id):
        return

    try:
        from agent_engine import think

        is_public = message.guild is not None

        # Clean message content to replace mentions with readable names
        clean_content = _clean_message_content(message)

        server_context = ""
        server_name = None
        if message.guild:
            from discord_bot.discord_utils import get_server_key
            server_name = get_server_key(message.guild)
            server_context = f"Server: {message.guild.name} ({server_name})"

        active_roles = []
        roles_config = AGENT_CFG.get("roles", {})
        # Only show roles that inject prompts for context

        response = think(
            role_context=_bot_display_name,  # Use bot display name as role context
            user_content=clean_content,  # Use cleaned content instead of raw message.content
            is_public=is_public,
            logger=logger,
            user_id=message.author.id,
            server_name=server_name,
            interaction_type="chat",
        )

        # Register interaction in database
        db_instance = get_db_for_server(message.guild) if message.guild else get_db_for_server(None)
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            message.author.id, message.author.name, "CHAT",
            message.content,
            message.channel.id if message.channel else None,
            message.guild.id if message.guild else None,
            {"response": response, "is_public": is_public}
        )

        if response and response.strip():
            await message.channel.send(response)

    except Exception as e:
        logger.exception(f"Error processing chat message: {e}")
        fallbacks = PERSONALITY.get("emergency_fallbacks", [])
        if fallbacks:
            await message.channel.send(random.choice(fallbacks))


# --- BOT STARTUP ---
if __name__ == "__main__":
    try:
        bot.run(get_discord_token())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
