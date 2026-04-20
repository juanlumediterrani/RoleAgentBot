"""Canvas builder for Juggler role."""

import discord
import asyncio
import json
from agent_logging import get_logger
from agent_db import AgentDatabase

from discord_bot import discord_core_commands as core
_personality_answers = core._personality_answers

logger = get_logger('canvas_juggler')


def _get_ring_message(key: str, fallback: str) -> str:
    """Get ring message from answers.json with fallback."""
    ring_messages = _personality_answers.get("ring_messages", {})
    return ring_messages.get(key, fallback)


def _get_canvas_ring_state(guild) -> dict:
    """Get ring state for Canvas UI."""
    from roles.juggler.subroles.ring.ring_discord import _get_ring_state
    server_id = str(guild.id) if guild else None
    try:
        return _get_ring_state(server_id)
    except Exception as e:
        logger.warning(f"Could not load ring state for Canvas: {e}")
        return {
            "enabled": False,
            "target_user_name": "Unknown bearer",
            "frequency_hours": 24,
            "base_frequency_hours": 24,
            "current_frequency_hours": 24,
            "frequency_iteration": 0
        }


def build_canvas_role_juggler(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the Juggler role view."""
    from .content import _get_personality_descriptions
    
    personality_descriptions = _get_personality_descriptions(str(guild.id) if guild else None)
    juggler_messages = personality_descriptions.get("role_descriptions", {}).get("juggler", {})
    
    title = juggler_messages.get("title", "**🎯 Centro de Coordinación de Servicios**")
    description = juggler_messages.get("description", "Nexo que gesta múltiples flujos operativos para mantener la armonía de la red.")
    
    content = f"{title}\n{description}\n"
    
    # Add subrole descriptions if any
    subrole_descriptions = juggler_messages.get("canvas_juggler_subrole_descriptions", {})
    if subrole_descriptions:
        content += "\n**Subroles:**\n"
        for subrole, description in subrole_descriptions.items():
            content += f"{description}\n"
    
    return content


def build_canvas_role_juggler_detail(detail_name: str, admin_visible: bool, guild=None) -> str:
    """Build the Juggler role detail view."""
    from .content import _get_personality_descriptions
    
    personality_descriptions = _get_personality_descriptions(str(guild.id) if guild else None)
    juggler_messages = personality_descriptions.get("role_descriptions", {}).get("juggler", {})
    roles_messages = personality_descriptions.get("role_descriptions", {})
    
    if detail_name == "overview":
        return build_canvas_role_juggler({}, admin_visible, guild)
    
    if detail_name in {"ring"}:
        ring_state = _get_canvas_ring_state(guild)
        ring_messages = juggler_messages.get("ring", {})

        title = ring_messages.get("title", "👁️ **RASTREO DEL ARTEFACTO CERO** 👁️")
        clean_title = title.replace("**", "")
        description = ring_messages.get("description", "🔍 Un objeto anómalo altera la red. Señala a otros avatares para ayudar al algoritmo a depurar la amenaza.")

        current_target_label = ring_messages.get("current_target", "🎯 **PUNTO DE INTERÉS:**")
        target_unknown = ring_messages.get("target_unknown", "👤 Las coordenadas están limpias de sospechas")
        investigation_title = ring_messages.get("investigation_title", "🔍 **INFORMAR DE ANOMALÍA:**")
        investigation_instructions = ring_messages.get("investigation_instructions", "• Inicia **Artefacto: Acusar** desde la consola de abajo\n• Escribe la mención (@) o ID del avatar sospechoso\n• Mi algoritmo procesará un interrogatorio directo\n• El análisis se hará público para transparentar el código")
        investigation_warning = ring_messages.get("investigation_warning", "⚠️ **RESTRICCIONES FÍSICAS:**\n• Un avatar no puede auto-denunciarse\n• Las entidades artificiales (bots) no pueden portar el artefacto\n• El barrido debe estar inicializado por un Arconte")
        inactive_title = ring_messages.get("inactive_title", "⚠️ **RADARES APAGADOS**")
        inactive_instructions = ring_messages.get("inactive_instructions", "Para restablecer el rastreo:\n• Un Arconte debe acceder a la terminal **Admin Artefacto**\n• Ejecutar **Rastreo: Iniciado**\n• Calibrar el ciclo temporal del barrido\n\nHecho esto, podrás señalar firmas de carbono sospechosas.")

        parts = [
            clean_title,
            description,
            "-" * 45,
        ]
        
        parts.append("")
        if ring_state["enabled"]:
            parts.extend([
                investigation_title,
                investigation_instructions,
                "-" * 45,
                investigation_warning,
                "-" * 45,
                current_target_label,
                f"👤 {ring_state['target_user_name']}" if ring_state['target_user_name'] != "Unknown bearer" else target_unknown,
                "-" * 45,
            ])
        else:
            parts.extend([inactive_title, "", inactive_instructions])

        # Use general descriptions for status
        general = personality_descriptions.get("general", {})
        status_label = general.get("status", "Status:")
        active_text = general.get("active", "✅ Active")
        inactive_text = general.get("inactive", "❌ Inactive")
        
        parts.append(f"**{status_label}** { active_text if ring_state['enabled'] else  inactive_text}")
        
        return "\n".join(parts)

    if detail_name in {"ring_admin"}:
        ring_state = _get_canvas_ring_state(guild)
        ring_messages = juggler_messages.get("ring", {})
        # Use general descriptions for admin panel
        general = personality_descriptions.get("general", {})
        ring_descriptions = juggler_messages.get("ring", {})
        
        admin_status = general.get("status", "Status:")
        active_text = general.get("active", "Active")
        inactive_text = general.get("inactive", "Inactive")
        base_freq_label = general.get("base_frequency", "Base Frequency:")
        current_freq_label = general.get("current", "Current Frequency:")
        freq_format = general.get("frequency_format", "Every {hours}h")
        hot_potato_format = ring_descriptions.get("hot_potato", "🔥 **Transferencia de Carga:** Iteración {iteration} (Latencia reducida {multiplier}x)")
        description = ring_messages.get("description", "🔍 Un objeto anómalo altera la red. Señala a otros avatares para ayudar al algoritmo a depurar la amenaza.")

        base_freq = ring_state.get('base_frequency_hours', ring_state['frequency_hours'])
        current_freq = ring_state.get('current_frequency_hours', ring_state['frequency_hours'])
        
        parts = [
            description,
            f"**{admin_status}** {active_text if ring_state['enabled'] else inactive_text}",
            f"**{base_freq_label}** {freq_format.format(hours=base_freq)}",
            f"**{current_freq_label}** {freq_format.format(hours=current_freq)}",
        ]
        
        # Add hot potato information if active
        if ring_state.get('frequency_iteration', 0) > 0:
            iteration = ring_state.get('frequency_iteration', 0)
            multiplier = 2 ** iteration
            parts.append(hot_potato_format.format(iteration=iteration, multiplier=multiplier))
        
        controls = ring_descriptions.get("controls", "**Controles de Sistema**\n- Alternar estado de barrido\n- Parámetro de ciclo temporal (afecta la transferencia de carga)")
        
        parts.extend(["", controls])
        
        return "\n".join(parts)

    # Default fallback
    return f"**Detalle: {detail_name}**\nVista de detalle para {detail_name}."


class JugglerActionModal(discord.ui.Modal, title="Juggler Action"):
    def __init__(self, action_name: str, author_id: int, guild, admin_visible: bool, view=None):
        from .ui import CanvasModal
        titles = {
            "ring_frequency": "Ring Frequency",
            "ring_accuse": "Accuse User",
        }
        super().__init__(title=titles.get(action_name, "Juggler Action"))
        self.action_name = action_name
        self.guild = guild
        self.admin_visible = admin_visible
        self.view = view
        self.author_id = author_id
        label_map = {
            "ring_frequency": "Hours",
            "ring_accuse": "User mention, id, or name",
        }
        placeholder_map = {
            "ring_frequency": "24",
            "ring_accuse": "@user",
        }
        self.value_input = discord.ui.TextInput(
            label=label_map.get(action_name, "Value"),
            placeholder=placeholder_map.get(action_name, ""),
            required=True,
            max_length=120,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        await handle_canvas_juggler_modal_submit(
            interaction,
            self.action_name,
            str(self.value_input.value).strip(),
            self.guild,
            self.author_id,
            self.admin_visible,
            self.view,
        )


async def handle_canvas_juggler_modal_submit(interaction: discord.Interaction, action_name: str, raw_value: str, guild, author_id: int, admin_visible: bool, view=None) -> None:
    # Defer immediately to prevent interaction timeout
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)
    
    server_key = None
    server_id = str(guild.id) if guild else None
    server_name = guild.name if guild else "Unknown"

    from discord_bot.agent_discord import AGENT_CFG
    from agent_engine import PERSONALITY
    from .content import _build_canvas_role_embed, _build_canvas_sections, _build_canvas_embed
    from discord_bot.canvas.ui import CanvasRoleDetailView, _safe_edit_interaction_message
    from .content import get_server_key

    server_key = get_server_key(guild)

    if action_name == "ring_accuse":
        try:
            from roles.juggler.subroles.ring.ring_discord import _get_ring_state, _save_ring_state, _record_accusation

            ring_state = _get_ring_state(server_id)
            if not ring_state.get("enabled", False):
                await interaction.followup.send("❌ Ring is not enabled on this server.", ephemeral=True)
                return

            raw_target = raw_value.strip()
            mentioned_user = None
            if guild is not None:
                cleaned = raw_target.replace("<@", "").replace("!", "").replace(">", "").strip()
                if cleaned.isdigit():
                    mentioned_user = guild.get_member(int(cleaned))

                if mentioned_user is None:
                    lowered = raw_target.lower()
                    for member in getattr(guild, "members", []) or []:
                        if getattr(member, "bot", False):
                            continue
                        names = {member.name.lower(), member.display_name.lower()}
                        if lowered in names:
                            mentioned_user = member
                            break

                if mentioned_user is None and cleaned.isdigit():
                    try:
                        mentioned_user = await interaction.client.fetch_user(int(cleaned))
                    except Exception:
                        pass

                if mentioned_user is None:
                    lowered = raw_target.lower()
                    for member in getattr(guild, "members", []) or []:
                        if getattr(member, "bot", False):
                            continue
                        names = {member.name.lower(), member.display_name.lower()}
                        if any(lowered in name for name in names):
                            mentioned_user = member
                            break

            if mentioned_user is None:
                await interaction.followup.send("❌ Enter a valid user mention, id, or visible name.", ephemeral=True)
                return

            target_name = mentioned_user.display_name if hasattr(mentioned_user, "display_name") else mentioned_user.name
            ring_state["target_user_id"] = str(mentioned_user.id)
            ring_state["target_user_name"] = target_name
            _save_ring_state(server_id, "canvas_accuse")

            try:
                logger.info(f"🎯 [CANVAS] Executing immediate ring accusation against {target_name}")
                await _record_accusation(
                    server_id=server_id,
                    accusation_text=f"ACCUSE {target_name}",
                    guild=guild,
                    target_user_id=str(mentioned_user.id),
                    target_user_name=target_name,
                    accuser_name=interaction.user.display_name,
                    accuser_id=str(interaction.user.id)
                )
                logger.info(f"🎭 [CANVAS] Immediate accusation executed for {target_name}")
            except Exception as e:
                logger.error(f"🎭 [CANVAS] Error executing immediate accusation: {e}")

            # Get target change message from personality (prompts.json)
            juggler_role = PERSONALITY.get("roles", {}).get("juggler", {})
            ring_subrole = juggler_role.get("subroles", {}).get("ring", {})
            target_change_msg = ring_subrole.get("target_change", "Changed ring target to")
            
            db_instance = AgentDatabase(server_id=server_id)
            await asyncio.to_thread(
                db_instance.register_interaction,
                interaction.user.id,
                interaction.user.name,
                "RING_TARGET_CHANGE",
                f"{target_change_msg} {target_name}",
                interaction.channel.id if interaction.channel else None,
                server_name,
            )

            target_changed_msg = _get_ring_message("target_changed", "✅ Ring target changed to {target_name}")
            await interaction.followup.send(target_changed_msg.format(target_name=target_name), ephemeral=True)

            # Refresh the view
            if view and hasattr(view, 'refresh'):
                await view.refresh()
        except Exception as e:
            logger.exception(f"Error handling ring_accuse: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        return

    if action_name in {"ring_on", "ring_off"}:
        from roles.juggler.subroles.ring.ring_discord import _get_ring_state, _save_ring_state

        enabled = action_name == "ring_on"
        
        # Use roles_config database for independent ring subrole management
        from agent_roles_db import get_roles_db_instance
        if get_roles_db_instance is None:
            await interaction.response.send_message("❌ Ring configuration system is not available.", ephemeral=True)
            return
            
        roles_db = get_roles_db_instance(server_key)
        
        # Save to roles_config
        config_data = roles_db.get_role_config('ring')
        if not config_data:
            config_data = {}
        config_data['enabled'] = enabled
        ok = roles_db.save_role_config('ring', True, json.dumps(config_data))
        
        if ok:
            # Also update ring state for immediate effect
            state = _get_ring_state(server_id)
            state["enabled"] = enabled
            _save_ring_state(server_id, "canvas_admin")
            
            enabled_msg = _get_ring_message("enabled", "✅ Ring enabled in roles_config.")
            disabled_msg = _get_ring_message("disabled", "✅ Ring disabled in roles_config.")
            message = enabled_msg if enabled else disabled_msg
        else:
            message = "❌ Failed to update ring configuration."
        
        await interaction.followup.send(message, ephemeral=True)
        
        # Refresh the view
        if view and hasattr(view, 'refresh'):
            await view.refresh()
        return

    if action_name == "ring_frequency":
        from roles.juggler.subroles.ring.ring_discord import _get_ring_state, _save_ring_state
        from agent_roles_db import get_roles_db_instance
        
        try:
            hours = int(raw_value)
            if hours < 1:
                await interaction.followup.send("❌ Frequency must be at least 1 hour.", ephemeral=True)
                return
        except ValueError:
            await interaction.followup.send("❌ Please enter a valid number.", ephemeral=True)
            return

        # Use roles_config database for independent ring subrole management
        from agent_roles_db import get_roles_db_instance
        if get_roles_db_instance is None:
            await interaction.response.send_message("❌ Ring configuration system is not available.", ephemeral=True)
            return
            
        roles_db = get_roles_db_instance(server_key)
        
        # Update frequency in roles_config
        config_data = roles_db.get_role_config('ring')
        if not config_data:
            config_data = {}
        config_data['frequency_hours'] = hours
        config_data['base_frequency_hours'] = hours
        config_data['current_frequency_hours'] = hours
        config_data['frequency_iteration'] = 0
        ok = roles_db.save_role_config('ring', True, json.dumps(config_data))
        
        if ok:
            # Also update ring state for immediate effect
            from roles.juggler.subroles.ring.ring_discord import _get_ring_state, _save_ring_state
            state = _get_ring_state(server_id)
            state["frequency_hours"] = hours
            state["base_frequency_hours"] = hours
            state["current_frequency_hours"] = hours
            state["frequency_iteration"] = 0
            _save_ring_state(server_id, "canvas_admin")
            
            message = (
                f"✅ Ring frequency updated to `{hours}` hours in roles_config.\n"
                f"🔥 Hot potato counter reset.\n"
            )
        else:
            message = "❌ Failed to update ring frequency."
        
        await interaction.followup.send(message, ephemeral=True)
        
        # Refresh the view
        if view and hasattr(view, 'refresh'):
            await view.refresh()
        return
