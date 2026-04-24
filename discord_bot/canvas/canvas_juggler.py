"""Canvas builder for Juggler role."""

import discord
import asyncio
import json
from agent_logging import get_logger
from agent_db import AgentDatabase

from discord_bot import discord_core_commands as core
_personality_answers = core._personality_answers

logger = get_logger('canvas_juggler')


def _get_ring_message(key: str, fallback: str, server_id: str = None) -> str:
    """Get ring message from answers.json with fallback."""
    from .content import _get_personality_descriptions
    personality_descriptions = _get_personality_descriptions(server_id)
    ring_messages = personality_descriptions.get("ring_messages", {})
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
    general_messages = personality_descriptions.get("general", {})
    
    description = juggler_messages.get("description", "Nexo que gesta múltiples flujos operativos para mantener la armonía de la red.")

    content = f"{description}\n"
    
    # Add subrole descriptions if any
    subrole_descriptions = juggler_messages.get("canvas_juggler_subrole_descriptions", {})
    if subrole_descriptions:
        available_subroles_label = general_messages.get("available_subroles", "Available subroles")
        content += f"\n**{available_subroles_label}**\n"
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

        title = ring_messages.get("title", "👁️ **Ring Tracker** 👁️")
        clean_title = title.replace("**", "")
        description = ring_messages.get("description", "Track and identify the target. Point to other users to help the algorithm resolve the anomaly.")

        current_target_label = ring_messages.get("current_target", "🎯 **Current Target:**")
        target_unknown = ring_messages.get("target_unknown", "👤 No target detected")
        investigation_title = ring_messages.get("investigation_title", "🔍 **Report Anomaly:**")
        investigation_instructions = ring_messages.get("investigation_instructions", "• Start **Artifact: Accuse** from the console below\n• Enter the mention (@) or ID of the suspected user\n• The algorithm will process a direct interrogation\n• The analysis will be made public for transparency")
        investigation_warning = ring_messages.get("investigation_warning", "⚠️ **Restrictions:**\n• A user cannot accuse themselves\n• Artificial entities (bots) cannot carry the artifact\n• The sweep must be initiated by an admin")
        inactive_title = ring_messages.get("inactive_title", "⚠️ **Radars Offline**")
        inactive_instructions = ring_messages.get("inactive_instructions", "To restore tracking:\n• An admin must access the **Admin Artifact** terminal\n• Execute **Tracking: Started**\n• Calibrate the temporal cycle of the sweep\n\nOnce done, you can point to suspicious carbon signatures.")

        parts = [
            description,
            "-" * 45,
        ]
        
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
            parts.extend([inactive_title, inactive_instructions])

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
        hot_potato_format = ring_descriptions.get("hot_potato", "🔥 **Load Transfer:** Iteration {iteration} (Latency reduced {multiplier}x)")
        description = ring_messages.get("description", "Track and identify the target. Point to other users to help the algorithm resolve the anomaly.")

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
        
        controls = ring_descriptions.get("controls", "**System Controls**\n- Toggle sweep state\n- Temporal cycle parameter (affects load transfer)")
        
        parts.extend([controls])
        
        return "\n".join(parts)

    # Default fallback
    return f"**Detail: {detail_name}**\nDetail view for {detail_name}."


class JugglerActionModal(discord.ui.Modal, title="Juggler Action"):
    def __init__(self, action_name: str, author_id: int, guild, admin_visible: bool, view=None):
        from .ui import CanvasModal
        from .content import _get_personality_descriptions

        server_id = str(guild.id) if guild else None
        personality_descriptions = _get_personality_descriptions(server_id)
        juggler_messages = personality_descriptions.get("role_descriptions", {}).get("juggler", {})
        ring_messages = juggler_messages.get("ring", {})
        ring_dropdown_messages = ring_messages.get("dropdown", {})

        titles = {
            "ring_frequency": "Ring Frequency",
            "ring_accuse": ring_messages.get("dm_accusation_header", "Accuse User").replace("**", ""),
        }
        super().__init__(title=titles.get(action_name, "Juggler Action"))
        self.action_name = action_name
        self.guild = guild
        self.admin_visible = admin_visible
        self.view = view
        self.author_id = author_id

        label_map = {
            "ring_frequency": "Hours",
            "ring_accuse": ring_dropdown_messages.get("ring_accuse_description", "User mention, id, or name")[:45],
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
        
        # Save to server_config as subrole of juggler
        try:
            from .server_config import set_role_config_value
            set_role_config_value(server_id, "juggler", "config.subroles.ring.enabled", enabled)
            ok = True
        except Exception as e:
            logger.error(f"Failed to update ring config in server_config: {e}")
            ok = False
        
        if ok:
            # Also update ring state for immediate effect
            state = _get_ring_state(server_id)
            state["enabled"] = enabled
            _save_ring_state(server_id, "canvas_admin")
        
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
            
        # Update frequency in server_config as subrole of juggler
        try:
            from .server_config import set_role_config_value
            set_role_config_value(server_id, "juggler", "config.subroles.ring.config.frequency_hours", hours)
            set_role_config_value(server_id, "juggler", "config.subroles.ring.config.base_frequency_hours", hours)
            set_role_config_value(server_id, "juggler", "config.subroles.ring.config.current_frequency_hours", hours)
            set_role_config_value(server_id, "juggler", "config.subroles.ring.config.frequency_iteration", 0)
            ok = True
        except Exception as e:
            logger.error(f"Failed to update ring frequency in server_config: {e}")
            ok = False
        
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
                f"✅ Ring frequency updated to `{hours}` hours.\n"
                f"🔥 Hot potato counter reset.\n"
            )
        else:
            message = "❌ Failed to update ring frequency."
        
        await interaction.followup.send(message, ephemeral=True)
        
        # Refresh the view
        if view and hasattr(view, 'refresh'):
            await view.refresh()
        return
