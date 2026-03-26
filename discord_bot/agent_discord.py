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

from agent_engine import PERSONALITY, get_discord_token, AGENT_CFG, _personality_descriptions
from agent_mind import call_llm, _build_conversation_user_prompt
from postprocessor import postprocess_response, is_readme_response
from agent_db import set_current_server, get_active_server_name
from behavior.db_behavior import get_behavior_db_instance
from agent_logging import get_logger, update_log_file_path
from discord_bot.discord_utils import (
    get_server_key, send_dm_or_channel,
    get_db_for_server, check_chat_rate_limit,
    set_is_connected, is_role_enabled_check,
)

logger = get_logger('discord')

# --- CONFIGURATION ---

def _build_readme_prompt(user_question: str) -> str:
    """Build enhanced prompt with README content for LLM.
    
    Args:
        user_question: The original user question
        
    Returns:
        Enhanced prompt string with README documentation
        
    Raises:
        Exception: If README file cannot be loaded
    """
    # Try to load personality-specific README_LLM.md first, then fallback to root
    personality_rel = AGENT_CFG.get("personality", "")
    personality_dir = os.path.dirname(os.path.join(os.path.dirname(os.path.dirname(__file__)), personality_rel))
    personality_readme_path = os.path.join(personality_dir, 'README_LLM.md')
    root_readme_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'README_LLM.md')
    
    readme_content = None
    readme_source = ""
    
    # First try personality-specific README
    if os.path.exists(personality_readme_path):
        try:
            with open(personality_readme_path, 'r', encoding='utf-8') as f:
                readme_content = f.read()
            readme_source = "personality-specific"
            logger.info(f"📖 Using personality-specific README: {personality_readme_path}")
        except Exception as e:
            logger.warning(f"⚠️ Could not load personality-specific README: {e}")
    
    # Fallback to root README if personality-specific failed or doesn't exist
    if readme_content is None:
        try:
            with open(root_readme_path, 'r', encoding='utf-8') as f:
                readme_content = f.read()
            readme_source = "root"
            logger.info(f"📖 Using root README: {root_readme_path}")
        except Exception as e:
            logger.error(f"❌ Error loading root README_LLM.md: {e}")
            raise
    
    # Get README response rules
    try:
        from agent_engine import _get_readme_response_rules_lines
        readme_rules = _get_readme_response_rules_lines()
        readme_rules_text = '\n'.join(readme_rules)
    except Exception as e:
        logger.warning(f"Could not load README response rules: {e}")
        readme_rules_text = ""
    
    # Build enhanced prompt with README content
    readme_descriptions = _personality_descriptions.get("readme", {})
    label_user_question = readme_descriptions.get("label_user_question", "User Question:")
    label_documentation = readme_descriptions.get("label_documentation", "Documentation:")
    task_readme = readme_descriptions.get("task", "Please answer the user's question using the documentation above.")
    enhanced_prompt = f"""{label_user_question} {user_question}

{label_documentation}
{readme_content}

{readme_rules_text}

{task_readme}"""
    
    return enhanced_prompt


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
        
        # Load default roles for this server
        try:
            from behavior.db_behavior import get_behavior_db_instance as get_behaviors_db_instance
            if get_behaviors_db_instance is not None:
                db = get_behaviors_db_instance(server_key)
                default_roles = ["news_watcher", "treasure_hunter", "trickster", "banker"]
                db.load_default_roles(default_roles, "system")
                logger.info(f"🎭 Default roles loaded for server '{active_guild.name}'")
        except Exception as e:
            logger.warning(f"Failed to load default roles for server '{active_guild.name}': {e}")

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

    # Initialize news watcher feeds for this server
    if is_role_enabled_check("news_watcher", agent_config):
        try:
            from roles.news_watcher.db_role_news_watcher import DatabaseRoleNewsWatcher
            news_db = DatabaseRoleNewsWatcher(server_key)
            # Run feed health check when joining a new server
            news_db._ensure_feed_health()
            logger.info(f"📡 News watcher feeds initialized and health-checked for server {guild.name}")
        except Exception as e:
            logger.error(f"❌ Error initializing news watcher for server {guild.name}: {e}")

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
                
                # Process taboo trigger using extracted function
                from behavior.taboo.taboo import process_taboo_trigger
                await process_taboo_trigger(message, taboo_keyword, server_name)
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
        is_public = message.guild is not None  # True for channel, False for DM
        is_mention = bot.user.mentioned_in(message)

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

        # Build system instruction for call_llm
        from agent_engine import _build_system_prompt
        system_instruction = _build_system_prompt(PERSONALITY)

        # Choose the appropriate prompt builder based on context
        if is_public:
            # Channel message - use channel prompt builder
            from agent_mind import _build_conversation_channel_prompt
            contextual_prompt = _build_conversation_channel_prompt(
                user_content=clean_content,
                server=server_name,
                user_id=message.author.id,
                user_name=message.author.name,
                channel_id=message.channel.id,
            )
        else:
            # DM message - use user prompt builder
            from agent_mind import _build_conversation_user_prompt
            contextual_prompt = _build_conversation_user_prompt(
                user_id=message.author.id,
                user_content=clean_content,
                server=server_name,
                user_name=message.author.name,
            )

        response = call_llm(
            system_instruction=system_instruction,
            prompt=contextual_prompt,
            async_mode=False,
            call_type="think",
            critical=True,
            metadata={
                "interaction_type": "channel" if is_public else "dm",
                "is_public": is_public,
                "user_id": message.author.id,
                "role": _bot_display_name,
                "server": server_name,
                "channel_id": message.channel.id if is_public else None,
                "is_mention": is_mention
            },
            logger=logger
        )

        # Check if this is a README response (deprecated is_help_request removed)
        if is_readme_response(response):
            logger.info(f"🔍 README response detected from {message.author.name}")
            
            # Build enhanced prompt with README content
            try:
                enhanced_prompt = _build_readme_prompt(clean_content)
                
                logger.info(f"📖 Making second LLM call with README documentation")
                
                # Make second LLM call with README content
                response = call_llm(
                    system_instruction=system_instruction,
                    prompt=enhanced_prompt,
                    async_mode=False,
                    call_type="readme_enhanced",
                    critical=True,
                    metadata={
                        "interaction_type": "channel" if is_public else "dm",
                        "is_public": is_public,
                        "user_id": message.author.id,
                        "role": _bot_display_name,
                        "server": server_name,
                        "channel_id": message.channel.id if is_public else None,
                        "is_mention": is_mention,
                        "readme_enhanced": True
                    },
                    logger=logger
                )
                
                logger.info(f"✅ README enhanced response generated")
                
            except Exception as e:
                logger.error(f"❌ Error building README prompt: {e}")
                # Continue with original README response if README file fails

        # Register interaction in database
        db_instance = get_db_for_server(message.guild) if message.guild else get_db_for_server(None)
        interaction_type = "CHANNEL" if is_public else "DM"
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            message.author.id, message.author.name, interaction_type,
            message.content,
            message.channel.id if message.channel else None,
            message.guild.id if message.guild else None,
            {"response": response, "is_public": is_public, "is_mention": is_mention}
        )

        # Schedule relationship refresh after interaction
        await asyncio.to_thread(
            db_instance.schedule_relationship_refresh,
            message.author.id,
            delay_minutes=60
        )

        # Mark user as replied to greeting if they message the bot
        if message.guild:
            # Server message - use guild context
            from behavior.db_behavior import get_behavior_db_instance
            from discord_bot.discord_utils import get_server_key
            server_name = get_server_key(message.guild)
            behavior_db = get_behavior_db_instance(server_name)
            await asyncio.to_thread(behavior_db.mark_user_replied, message.author.id, message.guild.id)
        else:
            # DM message - check all guilds where user might have received greetings
            import os
            import glob
            from behavior.db_behavior import get_behavior_db_instance
            
            # Get all server databases
            db_paths = glob.glob("databases/*/behavior.db")
            for db_path in db_paths:
                try:
                    # Extract server name from path
                    server_name = os.path.basename(os.path.dirname(db_path))
                    behavior_db = get_behavior_db_instance(server_name)
                    # Try to mark user as replied in this server
                    replied = await asyncio.to_thread(behavior_db.mark_user_replied, message.author.id, "dm_context")
                    if replied:
                        logger.info(f"Marked user {message.author.name} as replied via DM for server {server_name}")
                except Exception as e:
                    logger.debug(f"Could not mark user replied for server {server_name}: {e}")

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
