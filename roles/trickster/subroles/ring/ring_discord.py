"""
Ring subrole Discord commands.
Admins can enable or configure ring suspicion; users can accuse a target with `!accuse`.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import datetime

from agent_engine import PERSONALITY, _build_system_prompt
from agent_mind import call_llm
from agent_logging import get_logger
from agent_db import AgentDatabase
from behavior.db_behavior import get_behavior_db_instance
from behavior.greet import ReplyButton, ReplyButtonView
from discord_bot.discord_utils import is_admin, get_db_for_server, set_role_enabled, send_personality_embed_dm
from .ring_db import RingDB, get_ring_db_instance

logger = get_logger('ring_discord')

_ring_state_by_server_id: dict[str, dict] = {}


def _get_ring_state(server_id: str, force_refresh: bool = False) -> dict:
    # Clear cache if force_refresh is requested
    if force_refresh and server_id in _ring_state_by_server_id:
        del _ring_state_by_server_id[server_id]
    
    state = _ring_state_by_server_id.get(server_id)
    if state is None:
        defaults = {
            "enabled": False,
            "frequency_hours": 24,
            "base_frequency_hours": 24,
            "current_frequency_hours": 24,
            "frequency_iteration": 0,
            "unanswered_dm_count": 0,
            "last_accusation": "",
            "last_accusation_time": None,
            "target_user_name": "Unknown bearer",
            "target_user_id": "",
            "title": "Ring",
            "description": "",
            "current_accusation": "",
        }
        try:
            # PRIMARY: Check ring subrole directly in roles_config
            ring_enabled = False
            
            try:
                from agent_roles_db import get_roles_db_instance
                roles_db = get_roles_db_instance(server_id)
                ring_config = roles_db.get_role_config('ring')
                if ring_config:
                    ring_enabled = ring_config.get('enabled', False)
            except Exception as e:
                logger.warning(f"Error checking ring enabled in roles_config: {e}")
            
            # SECONDARY: Check if trickster role is enabled (fallback)
            trickster_enabled = False
            if not ring_enabled:
                try:
                    trickster_config = roles_db.get_role_config('trickster')
                    if trickster_config:
                        trickster_enabled = trickster_config.get('enabled', False)
                except Exception as e:
                    logger.warning(f"Error checking trickster enabled in roles_config: {e}")
                
                # TERTIARY: Check behavior roles table (final fallback)
                if not trickster_enabled:
                    try:
                        db = get_behavior_db_instance(server_id)
                        trickster_state = db.get_behavior_state('trickster')
                        trickster_enabled = trickster_state.get('enabled', False)
                    except Exception as e:
                        logger.warning(f"Error checking trickster enabled in behavior: {e}")
            
            # Get ring config from roles_config
            ring_config_data = roles_db.get_role_config('ring')
            
            # Parse ring configuration
            ring_config = {}
            current_accusation = ""
            
            if ring_config_data and ring_config_data.get('config_data'):
                try:
                    ring_config = json.loads(ring_config_data['config_data'])
                except json.JSONDecodeError:
                    ring_config = {}
            
            # Set accused_user_id from ring config (check both locations for compatibility)
            accused_user_id = ring_config_data.get('accused_user_id', '') if ring_config_data else ''
            if not accused_user_id:
                accused_user_id = ring_config.get('accused_user_id', '')
            if not accused_user_id:
                accused_user_id = ring_config.get('target_user_id', defaults["target_user_id"])
            
            # Set accused_user_name from ring config (check both locations for compatibility)
            accused_user_name = ring_config_data.get('accused_user_name', '') if ring_config_data else ''
            if not accused_user_name:
                accused_user_name = ring_config.get('accused_user_name', defaults["target_user_name"])
            
            # Log what we loaded for debugging
            logger.info(f"🎭 [RING LOAD] Server {server_id} - Loaded from DB: accused_user_id='{accused_user_id}', accused_user_name='{accused_user_name}'")
            
            state = {
                "enabled": ring_enabled,
                "frequency_hours": int(ring_config.get('frequency_hours', defaults["frequency_hours"])),
                "base_frequency_hours": int(ring_config.get('base_frequency_hours', defaults["base_frequency_hours"])),
                "current_frequency_hours": int(ring_config.get('current_frequency_hours', defaults["current_frequency_hours"])),
                "frequency_iteration": int(ring_config.get('frequency_iteration', defaults["frequency_iteration"])),
                "unanswered_dm_count": int(ring_config.get('unanswered_dm_count', defaults["unanswered_dm_count"])),
                "last_accusation": ring_config.get('last_accusation', defaults["last_accusation"]),
                "last_accusation_time": ring_config.get('last_accusation_time', defaults["last_accusation_time"]),
                "target_user_id": accused_user_id,  # Use accused_user_id as target_user_id for compatibility
                "target_user_name": accused_user_name,  # Use the correctly loaded accused_user_name
                "title": str(ring_config.get('title', defaults["title"])),
                "description": str(ring_config.get('description', defaults["description"])),
                "current_accusation": "",  # Don't store accusation text in state
            }
        except Exception as e:
            logger.warning(f"Error loading ring state for server {server_id}: {e}")
            state = defaults
        _ring_state_by_server_id[server_id] = state
    return state


def _save_ring_state(server_id: str, updated_by: str | None = None) -> bool:
    state = _get_ring_state(server_id)
    try:
        # Log what we're about to save for debugging
        logger.info(f"🎭 [RING SAVE] Server {server_id} - Saving state: target_user_id='{state.get('target_user_id', 'None')}', target_user_name='{state.get('target_user_name', 'None')}', enabled={state.get('enabled', False)}")
        
        # Save ring config to roles.db using centralized adapter
        ring_db = RingDB(server_id)
        
        # Convert state to config_data JSON - only save essential configuration
        config_data = json.dumps({
            'frequency_hours': state['frequency_hours'],
            'base_frequency_hours': state['base_frequency_hours'],
            'current_frequency_hours': state['current_frequency_hours'],
            'frequency_iteration': state['frequency_iteration'],
            'unanswered_dm_count': state.get('unanswered_dm_count', 0),
            'accused_user_id': state['target_user_id'],  # Save user ID, not username
            'accused_user_name': state['target_user_name'],  # Also save username for display
            'updated_by': updated_by
        })
        
        # Save to roles.db - only pass accused_user_id if we have a valid target
        accused_user_id = state['target_user_id'] if state['target_user_id'] and state['target_user_id'] != "" else None
        
        success = ring_db.save_config(
            enabled=state['enabled'],
            current_accusation=None,  # Don't save accusation text in config
            accused_user=accused_user_id,  # Pass user ID, not username
            config_data=config_data
        )
        
        if success:
            logger.info(f"🎭 [RING] Saved ring state for server {server_id}")
        else:
            logger.error(f"🎭 [RING] Failed to save ring state for server {server_id}")
        
        return True
    except Exception as e:
        logger.error(f"Error saving ring state for server {server_id}: {e}")
        return False


def _auto_reset_ring_accusation(server_id: str, recent_users: list) -> str | None:
    """Pick a new random target from recent_users and reset ring state to base frequency.
    Returns the new target_user_id or None if no users available."""
    import random as _random
    if not recent_users:
        return None
    new_target_id, new_target_name = _random.choice(recent_users)
    state = _get_ring_state(server_id, force_refresh=True)
    state['target_user_id'] = new_target_id
    state['target_user_name'] = new_target_name
    state['unanswered_dm_count'] = 0
    state['frequency_iteration'] = 0
    state['current_frequency_hours'] = state['base_frequency_hours']
    state['last_accusation_time'] = None
    _save_ring_state(server_id, "auto_reset_ignored")
    logger.info(f"🔄 [RING] Auto-reset: new target {new_target_name} ({new_target_id}), frequency back to {state['base_frequency_hours']}h")
    return new_target_id


def _calculate_next_frequency(server_id: str) -> int:
    """Calculate the next frequency using hot potato logic."""
    state = _get_ring_state(server_id)
    base_frequency = state["base_frequency_hours"]
    current_iteration = state["frequency_iteration"]
    
    # Calculate next frequency: halve each iteration, minimum 1 hour
    next_frequency = max(1, base_frequency // (2 ** current_iteration))
    
    # Update iteration counter
    state["frequency_iteration"] = current_iteration + 1
    state["current_frequency_hours"] = next_frequency
    
    # Save the updated state
    _save_ring_state(server_id, "frequency_calculation")
    
    logger.info(f"🔥 Ring frequency for server {server_id}: {next_frequency}h (iteration {current_iteration + 1})")
    return next_frequency


def _reset_frequency_to_base(server_id: str, reason: str = "accusation_change"):
    """Reset frequency to base when accusation changes."""
    state = _get_ring_state(server_id)
    state["frequency_iteration"] = 0
    state["current_frequency_hours"] = state["base_frequency_hours"]
    
    # Save the updated state
    _save_ring_state(server_id, reason)
    
    logger.info(f"🔄 Ring frequency reset for server {server_id}: {state['base_frequency_hours']}h (reason: {reason})")


def _can_make_accusation(server_id: str) -> bool:
    """Check if enough time has passed since last accusation based on current frequency."""
    state = _get_ring_state(server_id)
    last_time_str = state.get("last_accusation_time")
    
    if not last_time_str:
        return True
    
    try:
        last_time = datetime.datetime.fromisoformat(last_time_str)
        current_frequency = state["current_frequency_hours"]
        time_passed = datetime.datetime.now() - last_time
        
        return time_passed > datetime.timedelta(hours=current_frequency)
    except Exception as e:
        logger.warning(f"Error checking accusation timing for server {server_id}: {e}")
        return True


async def _record_accusation(server_id: str, accusation_text: str, guild=None, target_user_id: str = None, target_user_name: str = None, accuser_name: str = None, accuser_id: str = None):
    """Record an accusation, update frequency, and execute immediate accusation if target provided."""
    state = _get_ring_state(server_id)
    
    # Update the target user information if provided
    if target_user_id and target_user_name:
        state["target_user_id"] = target_user_id
        state["target_user_name"] = target_user_name
        logger.info(f"🎭 [RING] Updated target: {target_user_name} (ID: {target_user_id})")
    
    # Check if this is a different accusation from the last one
    last_accusation = state.get("last_accusation", "")
    if last_accusation != accusation_text:
        # Reset frequency if accusation changed
        logger.info(f"🔄 Ring accusation changed, resetting frequency")
        _reset_frequency_to_base(server_id, "accusation_changed")
    else:
        # Calculate next frequency (hot potato effect)
        _calculate_next_frequency(server_id)
    
    # Record the accusation
    state["last_accusation"] = accusation_text
    state["last_accusation_time"] = datetime.datetime.now().isoformat()
    state["current_accusation"] = accusation_text
    
    # Save the updated state
    _save_ring_state(server_id, "accusation_record")

    # Persist next_run_at so the scheduler picks up the correct next fire time
    try:
        from agent_engine import mark_subrole_executed
        next_freq = _get_ring_state(server_id).get('current_frequency_hours', 24)
        mark_subrole_executed('ring', datetime.datetime.now() + datetime.timedelta(hours=next_freq), server_id=server_id)
        logger.info(f"🎭 [RING] next_run_at persisted: +{next_freq}h from now")
    except Exception as _e:
        logger.warning(f"🎭 [RING] Could not persist next_run_at: {_e}")

    # Execute immediate accusation if guild and target provided
    if guild and target_user_id and target_user_name:
        try:
            logger.info(f"🎯 Executing immediate ring accusation against {target_user_name}")
            
            # Try to send the accusation via DM to the target
            try:
                # Import bot to get user instance
                from discord_bot.agent_discord import get_bot_instance
                bot = get_bot_instance()
                if bot:
                    # Try to get user from guild first (most reliable for shared servers)
                    target_user = None
                    try:
                        target_user = guild.get_member(int(target_user_id))
                    except Exception:
                        pass
                    
                    # Fallback to bot cache
                    if not target_user:
                        target_user = bot.get_user(int(target_user_id))
                    
                    if target_user:
                        server_id = str(guild.id)
                        
                        # Send personality embed first (server-specific avatar and name)
                        await send_personality_embed_dm(target_user, bot, guild, server_id)
                        
                        # Generate the accusation before sending
                        accusation = await execute_ring_accusation(guild, target_user_id, target_user_name, user_name=accuser_name, accuser_id=accuser_id)
                        
                        # Create the reply button view for this server
                        view = ReplyButtonView(guild, server_id, timeout=300.0)
                        
                        # Send header + accusation text + reply button in a single message
                        combined_message = await target_user.send(
                            f"👁️ **RING ACCUSATION**\n{accusation}",
                            view=view
                        )
                        view.message = combined_message
                        
                        logger.info(f"🎭 [RING] Immediate accusation sent via DM to {target_user_name} with personality embed and reply button")
                    else:
                        logger.warning(f"🎭 [RING] Could not find target user {target_user_id} for DM")
                else:
                    logger.warning(f"🎭 [RING] Bot instance not available for immediate accusation")
            except Exception as dm_error:
                logger.error(f"🎭 [RING] Error sending immediate DM: {dm_error}")
                
        except Exception as e:
            logger.error(f"🎭 [RING] Error executing immediate accusation: {e}")


async def execute_ring_accusation(guild, target_user_id: str, target_user_name: str, channel_id: int = None, user_name: str = None, accuser_id: str = None) -> str:
    """Execute a ring accusation using the new prompt system with memory injections."""
    try:
        server_id = str(guild.id) if guild else "unknown_server"
        
        from agent_mind import (
            _build_prompt_memory_block, 
            _build_prompt_relationship_block, 
            _build_prompt_last_interactions_block
        )
        from agent_db import get_global_db
        from agent_engine import _get_personality
        
        server_personality = _get_personality(server_id) if server_id else PERSONALITY
        prompts_config = server_personality.get("roles", {}).get("trickster", {}).get("subroles", {}).get("ring", {})
        accusation_config = prompts_config.get("accusation", {})
        
        task_template = accusation_config.get("task", f"Task: Accuse user {target_user_name} of possessing the ring, intimidate them to hand it over")
        task = task_template.replace("{target_name}", target_user_name)
        task = task.replace("{user_name}", user_name if user_name else "a user")
        base_rules = accusation_config.get("golden_rules", [])
        
        additional_rules = (
            accusation_config.get("public_channel", {}).get("additional_rules", [])
            if channel_id
            else accusation_config.get("direct_message", {}).get("additional_rules", [])
        )
        rules = base_rules + additional_rules
        
        db_instance = get_global_db(server_id=server_id)
        memory_block = _build_prompt_memory_block(server=server_id)
        
        relationship_block = _build_prompt_relationship_block(
            user_id=target_user_id,
            user_name=target_user_name,
            server=server_id
        )
        last_interactions_block = _build_prompt_last_interactions_block(
            user_id=target_user_id,
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
        
        # Add task
        prompt_parts.extend([
            "",
            task,
            "",
        ])
        
        # Add rules with their own label
        if rules: 
            for rule in rules:
                prompt_parts.append(rule)

        prompt_parts.extend([
            "",
            server_personality.get("closing", "## Personality RESPONSE:"),
        ])
        
        
        accusation_prompt = "\n".join(prompt_parts)
        
        # Generate the accusation — offload to thread to avoid blocking the event loop
        from agent_engine import _get_personality
        server_personality = _get_personality(server_id) if server_id else PERSONALITY
        system_instruction = _build_system_prompt(server_personality, server_id)

        accusation = await asyncio.to_thread(
            call_llm,
            system_instruction=system_instruction,
            prompt=accusation_prompt,
            async_mode=False,
            call_type="ring_accusation",
            critical=False,
            server_id=server_id
        )
        
        # Log the accusation and save to roles.db
        ring_db = RingDB(server_id)
        # Use the provided accuser_id if available, otherwise fallback to system
        accuser_id_to_save = accuser_id if accuser_id else 'system'
        logger.info(f"🔍 [RING SAVE DEBUG] Saving accusation - accuser_id: {accuser_id_to_save}, accuser_name: {user_name}")
        await asyncio.to_thread(
            ring_db.save_accusation,
            accuser_id_to_save,
            target_user_id,
            accusation,
            f"Evidence: {accusation[:200]}..." if len(accusation) > 200 else accusation
        )
        
        return accusation
        
    except Exception as e:
        logger.exception(f"Error executing ring accusation: {e}")
        return f"GRRR! {target_user_name} YOU HAVE THE RING! HAND IT OVER OR I'LL CRUSH YOUR SKULL!"


async def _cmd_ring_toggle(ctx, action: str):
    if not is_admin(ctx):
        await ctx.send('❌ Only administrators can enable or disable ring on the server.')
        return
    
    server_id = str(ctx.guild.id)
    enabled = action in {'enable', 'on'}
    
    # Update trickster role in roles table
    success = set_role_enabled(ctx.guild, 'trickster', enabled, getattr(ctx.author, "name", "admin_command"))
    
    if success:
        # Update ring state in roles table config_data
        # Force refresh to get current database state
        state = _get_ring_state(server_id, force_refresh=True)
        state['enabled'] = enabled
        
        # Log current accused info for debugging
        logger.info(f"🎭 [RING TOGGLE] Server {server_id} - Current accused: ID={state.get('target_user_id', 'None')}, Name={state.get('target_user_name', 'None')}")
        
        _save_ring_state(server_id, getattr(ctx.author, "name", "admin_command"))
        
        if enabled:
            await ctx.send('👁️ **Ring enabled for the server** - Users can accuse and the ring surface is active.')
        else:
            await ctx.send('🚫 **Ring disabled for the server** - Suspicion tools are now inactive.')
    else:
        await ctx.send('❌ Failed to update ring status in database.')


async def _cmd_ring_frequency(ctx, args):
    if not is_admin(ctx):
        await ctx.send('❌ Only administrators can adjust ring frequency.')
        return
    if not args:
        await ctx.send('❌ You must specify a number of hours. Example: `!trickster ring frequency 24`')
        return
    try:
        hours = int(str(args[0]).strip())
    except ValueError:
        await ctx.send('❌ You must specify a valid number of hours.')
        return
    if hours < 1 or hours > 168:
        await ctx.send('❌ Frequency must be between 1 and 168 hours.')
        return
    
    server_id = str(ctx.guild.id)
    state = _get_ring_state(server_id)
    
    # Update both base and current frequency, reset iteration
    state['frequency_hours'] = hours
    state['base_frequency_hours'] = hours
    state['current_frequency_hours'] = hours
    state['frequency_iteration'] = 0
    
    _save_ring_state(server_id, getattr(ctx.author, "name", "admin_command"))
    
    await ctx.send(
        f'⏰ **Ring frequency updated** - Base frequency set to {hours}h.\n'
        f'🔥 Hot potato counter reset. Next accusation will use {hours}h frequency.'
    )


async def _cmd_ring_target(ctx):
    state = _get_ring_state(str(ctx.guild.id))
    await ctx.send(f"👁️ **Current ring target** - {state['target_user_name']}")


async def _cmd_ring_help(ctx):
    help_text = (
        '👁️ **RING SUBROLE - HELP** 👁️\n\n'
        '**Admin commands**\n'
        '- `!trickster ring enable`\n'
        '- `!trickster ring disable`\n'
        '- `!trickster ring frequency <hours>` - Set base frequency (1-168 hours)\n'
        '- `!trickster ring target @user`\n'
        '- `!trickster ring help`\n\n'
        '**Hot Potato Frequency System** 🔥\n'
        '- Frequency starts at the configured base hours\n'
        '- Each identical accusation halves the frequency (minimum 1 hour)\n'
        '- Frequency resets to base when accusation text changes\n'
        '- Status shows current iteration and frequency reduction\n\n'
        '**User command**\n'
        '- Ask an administrator to update the current target with `!trickster ring target @user`\n'
    )
    await ctx.send(help_text)


