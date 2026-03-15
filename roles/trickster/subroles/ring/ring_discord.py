"""
Ring subrole Discord commands.
Admins can enable or configure ring suspicion; users can accuse a target with `!accuse`.
"""

from __future__ import annotations

import asyncio

from agent_engine import think, PERSONALIDAD
from agent_logging import get_logger
from agent_db import AgentDatabase
from behavior.db_behavior import get_behavior_db_instance
from discord_bot.discord_utils import is_admin, get_db_for_server

logger = get_logger('ring_discord')

_ring_state_by_server_id: dict[str, dict] = {}


def _get_ring_state(server_id: str) -> dict:
    state = _ring_state_by_server_id.get(server_id)
    if state is None:
        defaults = {
            "enabled": False,
            "frequency_hours": 24,
            "target_user_name": "Unknown bearer",
            "target_user_id": "",
            "title": "Ring",
            "description": "",
        }
        try:
            db = get_behavior_db_instance(server_id)
            persisted = db.get_feature_state("ring")
            config = persisted.get("config") or {}
            state = {
                "enabled": bool(persisted.get("enabled", defaults["enabled"])),
                "frequency_hours": int(config.get("frequency_hours", defaults["frequency_hours"])),
                "target_user_name": str(config.get("target_user_name", defaults["target_user_name"])),
                "target_user_id": str(config.get("target_user_id", defaults["target_user_id"])),
                "title": str(config.get("title", defaults["title"])),
                "description": str(config.get("description", defaults["description"])),
            }
        except Exception as e:
            logger.warning(f"Error loading ring state for server {server_id}: {e}")
            state = defaults
        _ring_state_by_server_id[server_id] = state
    return state


def _save_ring_state(server_id: str, updated_by: str | None = None) -> bool:
    state = _get_ring_state(server_id)
    payload = {
        "frequency_hours": int(state.get("frequency_hours", 24)),
        "target_user_name": state.get("target_user_name", "Unknown bearer"),
        "target_user_id": state.get("target_user_id", ""),
        "title": state.get("title", "Ring"),
        "description": state.get("description", ""),
    }
    try:
        db = get_behavior_db_instance(server_id)
        db.set_feature_state("ring", bool(state.get("enabled", False)), payload, updated_by)
        return True
    except Exception as e:
        logger.error(f"Error saving ring state for server {server_id}: {e}")
        return False


async def execute_ring_accusation(guild, target_user_id: str, target_user_name: str, channel_id: int = None) -> str:
    """Execute a ring accusation using the new prompt system."""
    try:
        # Build the accusation prompt
        prompts_config = PERSONALIDAD.get("role_system_prompts", {}).get("subroles", {}).get("ring", {})
        accusation_config = prompts_config.get("accusation", {})
        
        if channel_id:  # Public channel
            config = accusation_config.get("public_channel", {})
        else:  # DM
            config = accusation_config.get("direct_message", {})
        
        # Get mission and rules
        mission = config.get("mission", "MISION ACTIVA - RING: Eres el investigador del anillo único que tu jefe encargó encontrar.")
        rules = config.get("golden_rules", [])
        task = config.get("task", f"Tarea: Acusa al usuario {target_user_name} de poser el anillo, intimidale para que te lo entregue")
        
        # Build the prompt
        prompt_parts = [
            "## MEMORIA DE PUTRE (Lo que recuerdas):",
            "[RECUERDOS]",
            "GRAAAH! dia de mierda sin kombate y sin sangre ke beber, puro aburrimiento y trankilidad de eskorias, putre kerer aplastar kabeza de algun umano fofo ya mismo porke este dia no valer ni una moneda de oro, BLEGH!",
            "[RECUERDOS RECIENTES]",
            "Putre estar tranquilo, sin suzesos reseñables recientes.",
            "[RECUERDOS con el usuario]",  # TODO: Implementar función para obtener recuerdos específicos del usuario
            "[Ultimas interaciones//situaciones]",  # TODO: Implementar función para obtener situaciones recientes
            "",
            f"{mission}",
            "",
            "## REGLAS DE ORO:",
        ]
        
        # Add rules
        for rule in rules:
            prompt_parts.append(rule)
        
        prompt_parts.extend([
            "",
            task,
            "",
            "## RESPUESTA DE PUTRE:",
        ])
        
        accusation_prompt = "\n".join(prompt_parts)
        
        # Generate the accusation
        accusation = await asyncio.to_thread(
            think,
            role_context="Ring accusation",
            user_content=accusation_prompt,
            is_public=True,
            user_id=None,  # System-generated
            user_name="Putre",
            server_name=str(guild.id),
            interaction_type="scheduled_task",
        )
        
        # Log the accusation
        db_instance = AgentDatabase(server_name=str(guild.name))
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            None,  # System user
            "Putre",
            "RING_ACCUSE",
            f"Accused {target_user_name} of holding the ring",
            channel_id,
            guild.id,
            {"target_user_id": target_user_id, "accusation": accusation},
        )
        
        return accusation
        
    except Exception as e:
        logger.exception(f"Error executing ring accusation: {e}")
        return f"GRRR! {target_user_name} TU TENER EL ANILLO! ENTREGALO O TE KASO LA KABEZA!"


async def cmd_trickster_ring(ctx, *args):
    if not ctx.guild:
        await ctx.send('❌ This command only works on servers, not in private messages.')
        return

    if not args:
        state = _get_ring_state(str(ctx.guild.id))
        await ctx.send(
            f"👁️ **Ring status**\n"
            f"- Enabled: {'yes' if state['enabled'] else 'no'}\n"
            f"- Frequency: {state['frequency_hours']}h\n"
            f"- Current target: {state['target_user_name']}"
        )
        return

    action = str(args[0]).lower().strip()
    if action in {'enable', 'on', 'disable', 'off'}:
        await _cmd_ring_toggle(ctx, action)
        return
    if action == 'frequency':
        await _cmd_ring_frequency(ctx, args[1:])
        return
    if action == 'target':
        await _cmd_ring_target(ctx)
        return
    if action == 'help':
        await _cmd_ring_help(ctx)
        return

    await ctx.send('❌ Action not recognized. Use `enable`, `disable`, `frequency`, `target`, or `help`.')


async def _cmd_ring_toggle(ctx, action: str):
    if not is_admin(ctx):
        await ctx.send('❌ Only administrators can enable or disable ring on the server.')
        return
    state = _get_ring_state(str(ctx.guild.id))
    enabled = action in {'enable', 'on'}
    state['enabled'] = enabled
    _save_ring_state(str(ctx.guild.id), getattr(ctx.author, "name", "admin_command"))
    if enabled:
        await ctx.send('👁️ **Ring enabled for the server** - Users can accuse and the ring surface is active.')
    else:
        await ctx.send('🚫 **Ring disabled for the server** - Suspicion tools are now inactive.')


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
    state = _get_ring_state(str(ctx.guild.id))
    state['frequency_hours'] = hours
    _save_ring_state(str(ctx.guild.id), getattr(ctx.author, "name", "admin_command"))
    await ctx.send(f'⏰ **Ring frequency updated** - Suspicion cadence set to every {hours} hours.')


async def _cmd_ring_target(ctx):
    state = _get_ring_state(str(ctx.guild.id))
    await ctx.send(f"👁️ **Current ring target** - {state['target_user_name']}")


async def _cmd_ring_help(ctx):
    help_text = (
        '👁️ **RING SUBROLE - HELP** 👁️\n\n'
        '**Admin commands**\n'
        '- `!trickster ring enable`\n'
        '- `!trickster ring disable`\n'
        '- `!trickster ring frequency <hours>`\n\n'
        '**User command**\n'
        '- `!accuse @user`\n'
    )
    await ctx.send(help_text)


async def cmd_accuse_ring(ctx, target: str = ''):
    if not ctx.guild:
        await ctx.send('❌ This command only works on servers.')
        return

    state = _get_ring_state(str(ctx.guild.id))
    if not state.get('enabled', False):
        await ctx.send('❌ Ring is not enabled on this server.')
        return

    mentioned_user = None
    for user in ctx.message.mentions:
        if not user.bot and user.id != ctx.author.id:
            mentioned_user = user
            break

    if mentioned_user is None:
        await ctx.send('❌ Mention a valid user to accuse. Example: `!accuse @user`')
        return

    # Update the target in state (no immediate accusation)
    target_name = mentioned_user.display_name
    state['target_user_id'] = str(mentioned_user.id)
    state['target_user_name'] = target_name
    _save_ring_state(str(ctx.guild.id), getattr(ctx.author, "name", "target_change"))

    # Log the target change
    db_instance = get_db_for_server(ctx.guild)
    await asyncio.to_thread(
        db_instance.registrar_interaccion,
        ctx.author.id,
        ctx.author.name,
        'RING_TARGET_CHANGE',
        f'Changed ring target to {target_name}',
        ctx.channel.id,
        ctx.guild.id,
        {'target_user_id': mentioned_user.id, 'target_user_name': target_name},
    )

    await ctx.send(
        f'👁️ **New target selected:** {target_name}\n'
        f'The next ring investigation will focus on this user.'
    )
