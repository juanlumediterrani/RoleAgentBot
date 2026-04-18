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
from postprocessor import postprocess_response, is_readme_response, is_nothing_to_say_response
from agent_db import set_current_server, get_server_id, get_db_instance
from behavior.db_behavior import get_behavior_db_instance
from agent_logging import get_logger, update_log_file_path
from discord_bot.discord_utils import (
    get_server_key, send_dm_or_channel,
    get_db_for_server, check_chat_rate_limit,
    set_is_connected, is_role_enabled_check,
    send_personality_embed_dm,
)
try:
    from discord_bot.canvas.server_config import get_server_language as _get_server_language
except Exception:
    _get_server_language = None
from discord_bot.entitlement_manager import EntitlementManager, set_entitlement_manager

logger = get_logger('discord')


# --- CONFIGURATION ---

def _build_readme_prompt(user_question: str, server_id: str = None) -> str:
    """Build enhanced prompt with README content for LLM.
    
    Args:
        user_question: The original user question
        server_id: Discord server/guild ID used to resolve the server language
        
    Returns:
        Enhanced prompt string with README documentation
        
    Raises:
        Exception: If README file cannot be loaded
    """
    base_dir = os.path.dirname(os.path.dirname(__file__))
    manuals_dir = os.path.join(base_dir, "manuals")
    fallback_lang = "en-US"

    lang = fallback_lang
    if server_id and _get_server_language is not None:
        lang = _get_server_language(str(server_id))

    readme_path = os.path.join(manuals_dir, lang, "README_LLM.md")
    readme_source = f"manuals/{lang}"

    readme_content = None

    if os.path.exists(readme_path):
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                readme_content = f.read()
            logger.info(f"📖 Using README_LLM: {readme_path}")
        except Exception as e:
            logger.warning(f"⚠️ Could not load README_LLM for language '{lang}': {e}")

    # Fallback to en-US if language-specific README not found or failed to load
    if readme_content is None and lang != fallback_lang:
        fallback_path = os.path.join(manuals_dir, fallback_lang, "README_LLM.md")
        logger.warning(f"README_LLM.md not found for language '{lang}', falling back to {fallback_lang}")
        try:
            with open(fallback_path, 'r', encoding='utf-8') as f:
                readme_content = f.read()
            readme_source = f"manuals/{fallback_lang} (fallback)"
            logger.info(f"📖 Using fallback README_LLM: {fallback_path}")
        except Exception as e:
            logger.error(f"❌ Error loading fallback README_LLM.md: {e}")
            raise

    if readme_content is None:
        raise FileNotFoundError(f"README_LLM.md not found in {readme_path}")
    
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


# Import dynamic _personality_answers from discord_core_commands (server-specific loading)
from discord_bot.discord_core_commands import _personality_answers

_discord_cfg = _personality_answers
_cmd_prefix = _discord_cfg.get("command_prefix", "!")
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
# Note: intents.entitlements requires discord.py 2.4+ - not supported in current version
# Premium entitlement events will not work until library is updated

bot = commands.Bot(command_prefix=_cmd_prefix, intents=intents)


def get_bot_instance():
    """Get the global bot instance."""
    return bot

# --- AUTOMATIC TASKS ---

@tasks.loop(minutes=1)
async def discord_task_scheduler():
    """Run all Discord-dependent scheduled tasks inside the bot process.
    
    This scheduler executes tasks that need access to Discord (like beggar, news_watcher)
    from within the bot process where the bot instance is actually connected to Discord.
    Tasks that don't need Discord (memory operations) run in the main scheduler process.
    """
    if not bot.is_ready():
        return
    
    try:
        from agent_db import get_all_server_ids
        from agent_engine import get_due_subrole_tasks_for_server, execute_subrole_internal_task
        
        server_ids = get_all_server_ids()
        if not server_ids:
            return
        
        for server_id in server_ids:
            tasks_to_execute = get_due_subrole_tasks_for_server(server_id)
            if not tasks_to_execute:
                continue
            
            logger.info(f"[BOT_SCHEDULER] Server {server_id}: executing {len(tasks_to_execute)} subrole task(s): {[name for name, _ in tasks_to_execute]}")
            
            for subrole_name, subrole_config in tasks_to_execute:
                try:
                    await execute_subrole_internal_task(
                        subrole_name, subrole_config,
                        bot_instance=bot,  # Pass the actual connected bot instance
                        server_id=server_id
                    )
                except Exception as e:
                    logger.error(f"[BOT_SCHEDULER] Error in {subrole_name} for {server_id}: {e}")
    except Exception as e:
        logger.error(f"[BOT_SCHEDULER] Error in task scheduler: {e}")

@discord_task_scheduler.before_loop
async def _before_task_scheduler():
    await bot.wait_until_ready()

@tasks.loop(hours=24)
async def database_cleanup():
    active_server_key = (get_server_id() or "").strip()
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
    rows = await asyncio.to_thread(db_instance.clean_old_interactions, 30)
    from discord_bot.discord_utils import get_server_key
    server_key = get_server_key(target_guild)
    logger.info(f"🧹 Cleanup in {target_guild.name} ({server_key}): {rows} records deleted.")


async def set_bot_presence_message(guild=None, bot_instance=None):
    """Set bot presence status message from server-specific configuration.
    
    Args:
        guild: Optional Discord guild to get server_id from. If None, uses first available guild.
        bot_instance: Optional bot instance to use for changing presence. If None, uses global bot.
    """
    from agent_runtime import get_personality_message
    from discord_bot.discord_utils import get_server_key
    
    try:
        # Use provided bot or global bot
        target_bot = bot_instance or bot
        if not target_bot:
            logger.warning("No bot instance available for setting presence")
            return
        
        # Use provided guild or get first available
        target_guild = guild or (target_bot.guilds[0] if target_bot.guilds else None)
        if not target_guild:
            logger.warning("No guild available for setting bot presence")
            return
        
        server_id = get_server_key(target_guild)
        discord_cfg = {}
        presence_message = discord_cfg.get("mc_messages", {}).get("presence_status", "Use !canvas to interact")
        await target_bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name=presence_message)
        )
        logger.info(f"Display status: {presence_message}")
    except Exception as e:
        logger.error(f"Error setting bot presence: {e}")


async def set_mc_presence_if_enabled(guild=None):
    """Set bot presence status if MC role is active.
    
    Args:
        guild: Optional Discord guild to get server_id from. If None, uses first available guild.
    """
    try:
        if is_role_enabled_check("mc", agent_config):
            await set_bot_presence_message(guild)
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


async def _create_banker_wallets_on_startup():
    """Create banker wallets for all members of all connected servers."""
    logger.info("💰 Creating banker wallets for all server members...")
    
    try:
        from roles.banker.banker_db import get_banker_roles_db_instance
        from agent_roles_db import get_roles_db_instance
        
        # Process all guilds the bot is connected to
        for guild in bot.guilds:
            guild_id = str(guild.id)
            guild_name = guild.name
            
            logger.info(f"💰 Processing guild: {guild_name} ({guild_id})")
            
            try:
                # Get banker database for this server using server ID
                db_banker = get_banker_roles_db_instance(guild_id)
                
                # Create system accounts first
                db_banker.create_wallet("dice_game_pot", "Dice Game Pot", wallet_type='system')
                db_banker.create_wallet("beggar_fund", "Beggar Fund", wallet_type='system')
                
                # Set default TAE if not configured
                current_tae = db_banker.get_tae(guild_id)
                if current_tae == 0:
                    db_banker.set_tae(guild_id, 10)  # Default 10 coins per day
                    logger.info(f"💰 Set default TAE to 10 coins per day for {guild_name}")
                
                created_count = 0
                existing_count = 0
                
                # Create wallets for all members in this guild
                for member in guild.members:
                    if member.bot:
                        continue  # Skip bot accounts
                    
                    member_id = str(member.id)
                    member_name = member.display_name
                    
                    # Create wallet with opening bonus (10x TAE)
                    was_created = db_banker.create_wallet(
                        member_id, member_name, wallet_type='user'
                    )
                    
                    if was_created:
                        created_count += 1
                        initial_balance = db_banker.get_balance(member_id)
                        logger.info(f"💰 Created wallet for {member_name} with {initial_balance} coins")
                    else:
                        existing_count += 1
                
                # Initialize dice game accounts for all members
                try:
                    roles_db = get_roles_db_instance(guild_id)
                    if roles_db:
                        for member in guild.members:
                            if not member.bot:
                                roles_db.save_dice_game_stats(str(member.id), 0, 0, 0, 0, 0, None)
                        logger.info(f"🎲 Dice game accounts initialized for {guild_name}")
                except Exception as dice_error:
                    logger.warning(f"Could not initialize dice game accounts for {guild_name}: {dice_error}")
                
                logger.info(f"💰 Guild {guild_name}: {created_count} new wallets, {existing_count} existing wallets")
                
            except Exception as guild_error:
                logger.error(f"Error processing guild {guild_name}: {guild_error}")
        
        logger.info("✅ Banker wallet creation completed for all servers")
        
    except Exception as e:
        logger.exception(f"💰 Error in banker wallet creation: {e}")


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

    # Initialize all servers on startup
    from discord_bot.db_init import initialize_server_complete
    from discord_bot.canvas.server_config import detect_and_set_default_language
    
    if bot.guilds:
        logger.info(f"🚀 Initializing {len(bot.guilds)} servers on startup...")
        
        for guild in bot.guilds:
            logger.info(f"🚀 Initializing server: '{guild.name}' ({guild.id})")
            server_id = str(guild.id)
            
            # Step 1: Detect and set default language FIRST
            try:
                detected_lang = detect_and_set_default_language(server_id, guild)
                logger.info(f"🌐 Server language detected/set to: {detected_lang} for '{guild.name}'")
            except Exception as e:
                logger.warning(f"⚠️ Could not detect server language for '{guild.name}': {e}")
                detected_lang = "en-US"
            
            # Step 2: Initialize with detected language
            logger.info(f"🚀 About to call initialize_server_complete for '{guild.name}' with language={detected_lang}")
            try:
                init_success = await initialize_server_complete(guild, agent_config, is_startup=True, language=detected_lang)
                logger.info(f"🚀 initialize_server_complete returned: {init_success}")
            except Exception as e:
                logger.error(f"❌ initialize_server_complete failed with exception: {e}")
                import traceback
                logger.error(traceback.format_exc())
                init_success = False
            
            if init_success:
                logger.info(f"✅ Server initialization completed successfully for '{guild.name}'")
            else:
                logger.warning(f"⚠️ Some initialization tasks failed for '{guild.name}'")
                
        logger.info(f"🎯 All {len(bot.guilds)} servers initialization completed")
    else:
        logger.warning("⚠️ No guilds available for initialization")

    logger.info(f"🤖 Bot connected as {bot.user}")
    logger.info(f"🤖 Prefix: {_cmd_prefix} | Intents: members={bot.intents.members}, presences={bot.intents.presences}")

    from agent_mind import set_bot_discord_id
    set_bot_discord_id(bot.user.id)
    logger.info(f"🤖 Bot Discord ID registered: {bot.user.id}")

    # Automatic tasks
    if not database_cleanup.is_running():
        database_cleanup.start()
        logger.info("🧹 DB cleanup task started")
    
    # Start Discord task scheduler for Discord-dependent tasks (beggar, news_watcher, etc)
    if not discord_task_scheduler.is_running():
        discord_task_scheduler.start()
        logger.info("🎭 Discord task scheduler started")
    
    await set_mc_presence_if_enabled()
    
    # Create banker wallets for all server members
    await _create_banker_wallets_on_startup()
    
    # Initialize entitlement manager for premium SKU support
    entitlement_mgr = EntitlementManager(bot)
    set_entitlement_manager(entitlement_mgr)
    logger.info("💎 Entitlement manager initialized for premium SKU support")


@bot.event
async def on_guild_join(guild):
    """Runs when the bot joins a new server."""
    from discord_bot.db_init import initialize_server_complete, copy_personality_to_server
    from discord_bot.canvas.server_config import detect_and_set_default_language
    
    logger.info(f"🏰 Joining new guild: '{guild.name}'")
    server_id = str(guild.id)
    
    # Step 1: Detect and set default language FIRST
    # This must happen before personality copy so the correct language version is used
    try:
        detected_lang = detect_and_set_default_language(server_id, guild)
        logger.info(f"� Server language detected/set to: {detected_lang} for '{guild.name}'")
    except Exception as e:
        logger.warning(f"⚠️ Could not detect server language for '{guild.name}': {e}")
        detected_lang = "en-US"
    
    # Step 2: Copy "rab" personality with detected language
    # This ensures the server gets the correct language version from the start
    try:
        logger.info(f"📁 Copying 'rab' personality with language '{detected_lang}' for '{guild.name}'")
        personality_success = copy_personality_to_server(
            server_id, 
            personality_name="rab", 
            language=detected_lang,
            update_config=True
        )
        if personality_success:
            logger.info(f"✅ 'rab' personality ({detected_lang}) copied for '{guild.name}'")
        else:
            logger.warning(f"⚠️ Failed to copy 'rab' personality for '{guild.name}'")
    except Exception as e:
        logger.warning(f"⚠️ Error copying personality for '{guild.name}': {e}")
    
    # Step 3: Continue with unified server initialization
    # This will use the already-copied personality and detected language
    init_success = await initialize_server_complete(guild, agent_config, is_startup=False)
    
    if init_success:
        logger.info(f"🎉 New guild initialization completed successfully for '{guild.name}'")
    else:
        logger.warning(f"⚠️ Some initialization tasks failed for '{guild.name}'")

    # MC welcome message removed - no longer sends message when joining new servers


@bot.event
async def on_member_join(member):
    """Runs when a new user joins the server."""
    from behavior.welcome import handle_member_join
    from agent_runtime import get_personality_message
    from discord_bot.discord_utils import get_server_key
    
    server_id = get_server_key(member.guild)
    discord_cfg = {}
    await handle_member_join(member, discord_cfg)


@bot.event
async def on_presence_update(before, after):
    """Runs when a member goes from offline to online."""
    from behavior.greet import handle_presence_update
    from agent_runtime import get_personality_message
    from discord_bot.discord_utils import get_server_key
    
    server_id = get_server_key(after.guild)
    discord_cfg = {}
    bot_display_name = PERSONALITY.get("bot_display_name", "Bot")
    await handle_presence_update(before, after, discord_cfg, bot_display_name, bot)


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
                        from agent_runtime import get_personality_message
                        from discord_bot.discord_utils import get_server_key
                        
                        mc_commands = get_mc_commands_instance()
                        server_id = get_server_key(guild)
                        mc_cfg = {}
                        msg = mc_cfg.get("voice_leave_empty", "👋 The voice channel is empty, leaving now.")
                        
                        if mc_commands:
                            # Use MC message system to support Canvas callbacks
                            channel = next(
                                (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),
                                None
                            )
                            if channel:
                                await mc_commands._send_message(channel, msg)
                        else:
                            # Fallback to direct message if MC instance not available
                            channel = next(
                                (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),
                                None
                            )
                            if channel:
                                await channel.send(msg)
                    except Exception:
                        pass


@bot.event
async def on_entitlement_create(entitlement):
    """Handle new entitlement creation (user subscribed to premium)."""
    logger.info(f"💎 Entitlement created: User={entitlement.user_id}, Guild={entitlement.guild_id}, SKU={entitlement.sku_id}")
    
    # Get entitlement manager and handle the event
    from discord_bot.entitlement_manager import get_entitlement_manager
    entitlement_mgr = get_entitlement_manager()
    if entitlement_mgr:
        entitlement_mgr.handle_entitlement_create(entitlement)


@bot.event
async def on_entitlement_update(entitlement):
    """Handle entitlement update (subscription status changed)."""
    logger.info(f"💎 Entitlement updated: User={entitlement.user_id}, Guild={entitlement.guild_id}, SKU={entitlement.sku_id}, Ends={entitlement.ends_at}")
    
    # Get entitlement manager and handle the event
    from discord_bot.entitlement_manager import get_entitlement_manager
    entitlement_mgr = get_entitlement_manager()
    if entitlement_mgr:
        entitlement_mgr.handle_entitlement_update(entitlement)


@bot.event
async def on_entitlement_delete(entitlement):
    """Handle entitlement deletion (subscription cancelled/expired)."""
    logger.info(f"💎 Entitlement deleted: User={entitlement.user_id}, Guild={entitlement.guild_id}, SKU={entitlement.sku_id}")
    
    # Get entitlement manager and handle the event
    from discord_bot.entitlement_manager import get_entitlement_manager
    entitlement_mgr = get_entitlement_manager()
    if entitlement_mgr:
        entitlement_mgr.handle_entitlement_delete(entitlement)


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
                server_id = get_server_key(message.guild)
                
                # Process taboo trigger using extracted function
                from behavior.taboo.taboo import process_taboo_trigger
                await process_taboo_trigger(message, taboo_keyword, server_id)
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

        # If bot is mentioned, check if it's a !canvas command (skip mention for those)
        if message.guild and bot.user.mentioned_in(message):
            # For !canvas @Bot commands, remove only the bot mention
            if content.strip().startswith('!canvas'):
                bot_mention = f'<@{bot.user.id}>'
                bot_mention_bang = f'<@!{bot.user.id}>'
                content = content.replace(bot_mention, '').replace(bot_mention_bang, '').strip()
            # For all other mentions, pass the full message (mention will be handled naturally)

        # Get bot name from personality for mention replacement
        from agent_engine import _get_personality
        server_id = None
        if message.guild:
            from discord_bot.discord_utils import get_server_key
            server_id = get_server_key(message.guild)
        personality = _get_personality(server_id) if server_id else {}
        bot_name = personality.get("name", "Bot")

        # Replace bot mention with personality name
        bot_mention = f'<@{bot.user.id}>'
        bot_mention_bang = f'<@!{bot.user.id}>'
        content = content.replace(bot_mention, f'@{bot_name}')
        content = content.replace(bot_mention_bang, f'@{bot_name}')

        # Replace other user mentions with display names
        for mention in message.mentions:
            if mention.id != bot.user.id:  # Skip bot's own mention (already handled)
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


async def _process_accuse_flag(message, llm_response: str, server_id: str, is_public: bool) -> str | None:
    """Process ACCUSE <USERNAME> flag from LLM response."""
    try:
        # Import the ring extraction function
        from roles.trickster.subroles.ring.ring import extract_accuse_flag
        
        # Extract the username from ACCUSE flag
        accused_username = extract_accuse_flag(llm_response)
        
        if not accused_username:
            logger.warning("ACCUSE flag found but could not extract username")
            return None
            
        logger.info(f"🎯 ACCUSE flag detected: {accused_username} (from user {message.author.name})")
        
        # Find a server where both the accuser and the target can be found
        guild = None
        if message.guild:
            # We're already in a server
            guild = message.guild
        else:
            # We're in a DM, find a mutual server
            for server in bot.guilds:
                if message.author in server.members:
                    # Check if trickster role is enabled for this server
                    from discord_bot.discord_utils import is_role_enabled_check
                    if is_role_enabled_check("trickster", guild=server):
                        guild = server
                        break
        
        if not guild:
            logger.info("ACCUSE flag ignored - no suitable server found")
            return
            
        # Get server ID for logging
        server_id = str(guild.id)
            
        logger.info(f"🎯 Processing ACCUSE flag in server: {guild.name}")
        
        # Validate the username against server members
        target_member = None
        for member in guild.members:
            if member.bot:
                continue
            # Check display name and username
            if (member.display_name.lower() == accused_username.lower() or 
                member.name.lower() == accused_username.lower()):
                target_member = member
                break
                
        if target_member:
            logger.info(f"✅ User '{accused_username}' found in server: {target_member.name}")
            return await _handle_valid_accusation(message, target_member, guild, server_id, is_public)
        else:
            logger.info(f"❌ User '{accused_username}' not found in server")
            return await _handle_false_accusation(message, accused_username, guild, server_id, is_public)
            
    except Exception as e:
        logger.exception(f"Error processing ACCUSE flag: {e}")
        return None


async def _handle_valid_accusation(message, target_member, guild, server_id: str, is_public: bool) -> str:
    """Handle accusation when the user exists in the server."""
    try:
        server_id = str(guild.id)
        
        # Record accusation and update state (this will save the target info)
        from roles.trickster.subroles.ring.ring_discord import _record_accusation
        await _record_accusation(server_id, f"ACCUSE {target_member.display_name}", guild, str(target_member.id), target_member.display_name, message.author.display_name, str(message.author.id))
        
        logger.info(f"🎯 Ring accusation target updated to: {target_member.display_name}")
        
        # Build denial prompt for LLM
        from agent_engine import PERSONALITY, _get_personality
        from agent_mind import call_llm
        
        # Get server-specific personality
        server_personality = _get_personality(server_id) if server_id else PERSONALITY
        
        # Get ring prompts from personality
        prompts_config = server_personality.get("roles", {}).get("trickster", {}).get("subroles", {}).get("ring", {})
        denial_config = prompts_config.get("denial", {})
        
        task_template = denial_config.get("task", f"Task: The human {target_member.display_name} denies having the ring, warn them not to lie to you and leave them alone")
        # Replace placeholders with actual names
        task = task_template.replace("{target_name}", target_member.display_name)
        task = task.replace("{user_name}", message.author.display_name)
        rules = denial_config.get("golden_rules", [])
        
        # Build the prompt with actual memory data using existing functions
        from agent_mind import _build_prompt_memory_block, _build_prompt_relationship_block
        from agent_db import get_global_db
        
        # Get database instance for memory retrieval
        db_instance = get_global_db(server_id) if server_id else get_global_db()
        
        # Build memory sections using existing functions (for the user who sent the message)
        memory_block = _build_prompt_memory_block(server=server_id)
        relationship_block = _build_prompt_relationship_block(
            user_id=message.author.id, 
            user_name=message.author.display_name, 
            server=server_id
        )
        
        # Get recent interactions for context (for the user who sent the message)
        recent_interactions = []
        try:
            if db_instance:
                recent_interactions = db_instance.get_user_recent_interactions(message.author.id, limit=5)
        except Exception as e:
            logger.debug(f"Could not get recent interactions: {e}")
        
        # Build recent dialogue section
        if recent_interactions:
            dialogue_lines = []
            for interaction in recent_interactions:
                dialogue_lines.append(f"- {interaction.get('user_name', 'Unknown')}: {interaction.get('content', '')[:100]}...")
            recent_dialogue = "\n".join(dialogue_lines)
        else:
            recent_dialogue = "No recent interactions recorded."
        
        # Build the prompt
        prompt_parts = [
            memory_block,
            relationship_block,
            recent_dialogue,
            "",
        ]
        
        # Add rules
        for rule in rules:
            prompt_parts.append(rule)
        
        prompt_parts.extend([
            "",
            task,
            "",
            server_personality.get("closing", "## Personality RESPONSE:"),
        ])
        
        denial_prompt = "\n".join(prompt_parts)
        
        # Generate the denial response
        from agent_engine import _build_system_prompt, _get_personality
        server_personality = _get_personality(server_id) if server_id else PERSONALITY
        system_instruction = _build_system_prompt(server_personality, server_id)
        
        response = call_llm(
            system_instruction=system_instruction,
            prompt=denial_prompt,
            async_mode=False,
            call_type="ring_denial",
            critical=True,
            logger=logger,
            user_id=str(message.author.id),
            user_name=message.author.display_name,
            server_id=server_id
        )
        
        if response and response.strip():
            return response
        else:
            return f"GRRR! {target_member.display_name}! Don't lie to me, I know you have the ring! Leave it alone or I'll rip your fingers off!"
            
    except Exception as e:
        logger.exception(f"Error handling valid accusation: {e}")
        return f"GRAAAH! {target_member.display_name}! Don't lie to me, I know you have the ring! Leave it alone or I'll rip your fingers off!"


async def _handle_false_accusation(message, accused_username: str, guild, server_id: str, is_public: bool) -> str:
    """Handle accusation when the user doesn't exist in the server."""
    try:
        # Build false accusation prompt for LLM
        from agent_engine import PERSONALITY, _get_personality
        from agent_mind import call_llm
        
        # Get server-specific personality
        server_personality = _get_personality(server_id) if server_id else PERSONALITY
        
        # Get ring prompts from personality
        prompts_config = server_personality.get("roles", {}).get("trickster", {}).get("subroles", {}).get("ring", {})
        false_accusation_config = prompts_config.get("false_accusation", {})
        
        mission = false_accusation_config.get("mission", "MISSION ACTIVE - RING: The human falsely accused someone of having the ring.")
        task_template = false_accusation_config.get("task", f"Task: The human has accused '{accused_username}' who doesn't exist in the server, respond appropriately")
        # Replace placeholders with actual names
        task = task_template.replace("{target_name}", accused_username)
        task = task.replace("{user_name}", message.author.display_name)
        rules = false_accusation_config.get("golden_rules", [])
        
        # Build memory sections using existing functions (using accuser's context)
        from agent_mind import _build_prompt_memory_block, _build_prompt_relationship_block, _build_prompt_last_interactions_block
        from agent_db import get_global_db
        
        # Get database instance for memory retrieval
        db_instance = get_global_db(server_id) if server_id else get_global_db()
        
        # Build memory sections using proper functions
        memory_block = _build_prompt_memory_block(server=server_id)
        
        # Use message.author for relationship context
        relationship_block = _build_prompt_relationship_block(
            user_id=message.author.id,
            user_name=message.author.display_name,
            server=server_id
        )
        last_interactions_block = _build_prompt_last_interactions_block(
            user_id=message.author.id,
            server=server_id
        )
        
        # Build the prompt with proper memory sections
        prompt_parts = []
        
        # Add memory block if available
        if memory_block:
            prompt_parts.append(memory_block)
        
        # Add relationship block if available
        if relationship_block:
            prompt_parts.append(relationship_block)
        
        # Add last interactions block if available
        if last_interactions_block:
            prompt_parts.append(last_interactions_block)
        
        # Add mission and task
        prompt_parts.extend([
            "",
            mission,
            "",
        ])
        
        # Add rules with their own label
        if rules: 
            for rule in rules:
                prompt_parts.append(rule)

        prompt_parts.extend([
            "",
            task,
            "",
            server_personality.get("closing", "## Personality RESPONSE:"),
        ])
        
        false_accusation_prompt = "\n".join(prompt_parts)
        
        # Generate the false accusation response
        from agent_engine import _build_system_prompt, _get_personality
        server_personality = _get_personality(server_id) if server_id else PERSONALITY
        system_instruction = _build_system_prompt(server_personality, server_id)
        
        response = call_llm(
            system_instruction=system_instruction,
            prompt=false_accusation_prompt,
            async_mode=False,
            call_type="ring_false_accusation",
            critical=True,
            logger=logger,
            user_id=str(message.author.id),
            user_name=message.author.display_name,
            server_id=server_id
        )
        
        if response and response.strip():
            return response
        else:
            return f"GRAAAH! Who are you accusing? '{accused_username}' doesn't exist in this server! Stop wasting my time, stupid human!"
            
    except Exception as e:
        logger.exception(f"Error handling false accusation: {e}")
        return f"GRAAAH! Who are you accusing? '{accused_username}' doesn't exist in this server! Stop wasting my time, stupid human!"


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
        server_id = None
        if message.guild:
            from discord_bot.discord_utils import get_server_key
            server_id = get_server_key(message.guild)
            server_context = f"Server: {message.guild.name} ({server_id})"
            # Ensure active server is set for this message's guild
            current_active = get_server_id()
            if current_active != server_id:
                set_current_server(server_id)
        else:
            # DM message - resolve server: pin (set by reply button) > last interaction in DB
            from agent_db import get_pinned_dm_server, get_user_last_server_id
            pinned = get_pinned_dm_server(message.author.id)
            if pinned:
                server_id = pinned
                server_context = f"DM (pinned: {server_id})"
                logger.info(f"DM from {message.author.name} - using pinned server: {server_id}")
            else:
                last_server = get_user_last_server_id(str(message.author.id))
                if last_server:
                    server_id = last_server
                    server_context = f"DM (last server: {server_id})"
                    logger.info(f"DM from {message.author.name} - last server from DB: {server_id}")
                else:
                    server_context = "DM (no server context)"
                    logger.info(f"DM from {message.author.name} - no server history found")

        active_roles = []
        roles_config = AGENT_CFG.get("roles", {})
        # Only show roles that inject prompts for context

        # Build system instruction for call_llm (use server-specific personality)
        from agent_engine import _build_system_prompt, _get_personality
        server_personality = _get_personality(server_id) if server_id else PERSONALITY
        system_instruction = _build_system_prompt(server_personality, server_id)

        # Choose the appropriate prompt builder based on context
        if is_public:
            # Channel message - use channel prompt builder
            from agent_mind import _build_conversation_channel_prompt
            contextual_prompt = await _build_conversation_channel_prompt(
                user_content=clean_content,
                server=server_id,
                user_id=message.author.id,
                user_name=message.author.name,
                channel_id=message.channel.id,
                bot_id=str(bot.user.id),
                discord_channel=message.channel
            )
        else:
            # DM message - use user prompt builder
            from agent_mind import _build_conversation_user_prompt
            contextual_prompt = _build_conversation_user_prompt(
                user_id=message.author.id,
                user_content=clean_content,
                server=server_id,
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
                "role": "bot",
                "server": server_id,
                "channel_id": message.channel.id if is_public else None,
                "is_mention": is_mention
            },
            logger=logger,
            user_id=str(message.author.id),
            user_name=message.author.display_name,
            server_id=server_id
        )

        # Check if this is a README response
        if is_readme_response(response):
            logger.info(f"🔍 README response detected from {message.author.name}")
            
            # Build enhanced prompt with README content
            try:
                enhanced_prompt = _build_readme_prompt(clean_content, server_id=server_id)
                
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
                        "role": "bot",
                        "server": server_id,
                        "channel_id": message.channel.id if is_public else None,
                        "is_mention": is_mention,
                        "readme_enhanced": True
                    },
                    logger=logger,
                    user_id=str(message.author.id),
                    user_name=message.author.display_name,
                    server_id=server_id
                )
                
                logger.info(f"✅ README enhanced response generated")
                
            except Exception as e:
                logger.error(f"❌ Error building README prompt: {e}")
                # Continue with original README response if README file fails

        # Check if this is a NADA_QUE_DECIR response (nothing to say)
        nothing_to_say_keyword = server_personality.get("behaviors", {}).get("nothing_to_say_keyword", "NOTHING_TO_SAY")
        nothing_to_say_description = server_personality.get("behaviors", {}).get("nothing_to_say_description", "(You didn't respond to their last message)")
        if is_nothing_to_say_response(response, keyword=nothing_to_say_keyword):
            logger.info(f"🔇 NADA_QUE_DECIR response detected from {message.author.name} - skipping response sending")
            
            # Register interaction in database with description instead of literal keyword
            db_instance = get_db_for_server(message.guild) if message.guild else get_db_instance(server_id or get_server_id() or "0")
            interaction_type = "CHANNEL" if is_public else "DM"
            await asyncio.to_thread(
                db_instance.register_interaction,
                message.author.id, message.author.name, interaction_type,
                clean_content,
                message.channel.id if message.channel else None,
                server_id,
                {"response": nothing_to_say_description, "is_public": is_public, "is_mention": is_mention, "nothing_to_say": True}
            )
            
            # Mark user as replied to greeting if they message the bot
            if message.guild:
                from behavior.db_behavior import get_behavior_db_instance
                from discord_bot.discord_utils import get_server_key
                server_id = get_server_key(message.guild)
                behavior_db = get_behavior_db_instance(server_id)
                await asyncio.to_thread(behavior_db.mark_user_replied, message.author.id, message.guild.id)
            else:
                import glob
                from behavior.db_behavior import get_behavior_db_instance
                
                db_paths = glob.glob("databases/*/behavior*.db")
                for db_path in db_paths:
                    try:
                        server_id = os.path.basename(os.path.dirname(db_path))
                        behavior_db = get_behavior_db_instance(server_id)
                        replied = await asyncio.to_thread(behavior_db.mark_user_replied, message.author.id, "dm_context")
                        if replied:
                            logger.info(f"Marked user {message.author.name} as replied via DM for server {server_id}")
                            break
                    except Exception as e:
                        logger.error(f"Error marking user replied via DM: {e}")
            
            # Return early - don't send response
            return

        # Register interaction in database
        db_instance = get_db_for_server(message.guild) if message.guild else get_db_instance(server_id or get_server_id() or "0")
        interaction_type = "CHANNEL" if is_public else "DM"
        await asyncio.to_thread(
            db_instance.register_interaction,
            message.author.id, message.author.name, interaction_type,
            clean_content,
            message.channel.id if message.channel else None,
            server_id,
            {"response": response, "is_public": is_public, "is_mention": is_mention}
        )

        # Mark user as replied to greeting if they message the bot
        if message.guild:
            # Server message - use guild context
            from behavior.db_behavior import get_behavior_db_instance
            from discord_bot.discord_utils import get_server_key
            server_id = get_server_key(message.guild)
            behavior_db = get_behavior_db_instance(server_id)
            await asyncio.to_thread(behavior_db.mark_user_replied, message.author.id, message.guild.id)
        else:
            # DM message - check all guilds where user might have received greetings
            import os
            import glob
            from behavior.db_behavior import get_behavior_db_instance
            
            # Get all server databases
            db_paths = glob.glob("databases/*/behavior*.db")
            for db_path in db_paths:
                try:
                    # Extract server name from path (use different var to avoid shadowing outer server_id)
                    _loop_server_id = os.path.basename(os.path.dirname(db_path))
                    behavior_db = get_behavior_db_instance(_loop_server_id)
                    # Try to mark user as replied in this server
                    replied = await asyncio.to_thread(behavior_db.mark_user_replied, message.author.id, "dm_context")
                    if replied:
                        logger.info(f"Marked user {message.author.name} as replied via DM for server {_loop_server_id}")
                except Exception as e:
                    logger.debug(f"Could not mark user replied for server {_loop_server_id}: {e}")

        # If a DM was received, reset ring unanswered counter for this user across all servers
        if message.guild is None:
            try:
                from roles.trickster.subroles.ring.ring_discord import _get_ring_state, _save_ring_state
                for guild in bot.guilds:
                    _srv = str(guild.id)
                    rstate = _get_ring_state(_srv, force_refresh=True)
                    if rstate.get('target_user_id') == str(message.author.id) and rstate.get('unanswered_dm_count', 0) > 0:
                        rstate['unanswered_dm_count'] = 0
                        _save_ring_state(_srv, "target_replied")
                        logger.info(f"🎭 [RING] {message.author.name} replied via DM — unanswered count reset for server {_srv}")
            except Exception as e:
                logger.debug(f"Could not reset ring unanswered count: {e}")

        # Check for ACCUSE flag in LLM response
        accusation_response = None
        if response and "ACCUSE" in response:
            accusation_response = await _process_accuse_flag(message, response, server_id, is_public)

        # Send response to user (either original LLM response or accusation-specific response)
        # For DMs, send personality embed first with server-specific identity
        if not is_public:
            # Use the same server_id that was used for the LLM response
            # Don't try to resolve guild to avoid using the wrong server
            logger.info(f"📨 DM embed call: server_id={server_id} (using same as LLM response)")
            await send_personality_embed_dm(message.author, bot, None, server_id)
            # Pin is only set/changed via greeting buttons — no refresh here
        
        if accusation_response:
            # Send the accusation-specific response
            await message.channel.send(accusation_response)
        elif response and response.strip():
            # Send the original LLM response
            await message.channel.send(response)

    except Exception as e:
        logger.exception(f"Error processing chat message: {e}")
        fallbacks = PERSONALITY.get("emergency_fallbacks", [])
        if fallbacks:
            # For DMs, send personality embed first with server-specific identity
            if message.guild is None:
                # Get server_id from locals if available, otherwise None
                error_server_id = locals().get('server_id', None)
                # Use the same server_id without resolving guild
                await send_personality_embed_dm(message.author, bot, None, error_server_id)
            await message.channel.send(random.choice(fallbacks))


# --- BOT STARTUP ---
if __name__ == "__main__":
    try:
        import sys
        logger.info("🚀 Starting Discord bot initialization...")
        logger.info(f"📋 Python version: {sys.version}")
        logger.info(f"🔑 Discord token configured: {bool(get_discord_token())}")
        logger.info(f"🎭 Personality: {PERSONALITY.get('name', 'unknown')}")
        logger.info(f"🤖 Bot display name: {_personality_name}")
        logger.info(f"🔧 Command prefix: {_cmd_prefix}")
        logger.info("⏳ Calling bot.run()...")
        bot.run(get_discord_token())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
