"""Canvas Scholar content builders."""

import discord

from discord_bot import discord_core_commands as core
from .canvas_base import CanvasModal
from .server_config import get_role_config_value

get_server_key = core.get_server_key

logger = core.logger
AgentDatabase = core.AgentDatabase
is_admin = core.is_admin
set_role_enabled = core.set_role_enabled


def _get_scholar_descriptions(server_id):
    """Load scholar role descriptions from personality."""
    from .content import _get_personality_descriptions
    try:
        return _get_personality_descriptions(server_id).get("role_descriptions", {}).get("scholar", {})
    except Exception:
        return {}


def build_canvas_role_scholar(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the Scholar role overview."""
    server_id = get_server_key(guild) if guild else None
    scholar_messages = _get_scholar_descriptions(server_id)
    
    # Get general messages
    general_messages = {}
    try:
        from .content import _get_personality_descriptions
        personality_descriptions = _get_personality_descriptions(server_id)
        general_messages = personality_descriptions.get("general", {})
    except Exception:
        pass

    def _scholar_text(key: str, fallback: str) -> str:
        value = scholar_messages.get(key)
        return str(value).strip() if value else fallback

    def _general_text(key: str, fallback: str) -> str:
        """Get text from general messages."""
        value = general_messages.get(key)
        return str(value).strip() if value else fallback

    # Check if scholar is enabled from server_config
    scholar_enabled = False
    try:
        server_id = str(guild.id) if guild else None
        if server_id:
            from .server_config import is_role_enabled
            scholar_enabled = is_role_enabled(server_id, "scholar", default_enabled=False)
    except Exception as e:
        logger.warning(f"Error loading scholar state from server_config: {e}")
        # Fallback to agent_config
        scholar_enabled = (agent_config or {}).get("roles", {}).get("scholar", {}).get("enabled", False)

    description = _scholar_text("description", "Access the vast records of human civilization through my synthetic and mystical perspective. Ask any question, and I shall share what the archives hold.")

    # Get localized labels
    action_labels = general_messages.get("action_labels", {})
    label_enabled = action_labels.get("enabled", "Enabled")
    label_disabled = action_labels.get("disabled", "Disabled")

    parts = [
        description,
        "",
        f"**Status:** {'✅ ' + label_enabled if scholar_enabled else '❌ ' + label_disabled}",
    ]

    return "\n".join(parts)


def build_canvas_role_scholar_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None, agent_config: dict | None = None) -> str | None:
    """Build a detailed Scholar view."""
    if detail_name == "overview":
        return build_canvas_role_scholar(agent_config or {}, admin_visible, guild)

    if detail_name == "personal":
        server_id = get_server_key(guild) if guild else None
        scholar_messages = _get_scholar_descriptions(server_id)

        def _scholar_text(key: str, fallback: str) -> str:
            value = scholar_messages.get(key)
            return str(value).strip() if value else fallback

        title = _scholar_text("title", "📚 **Archivist of the Great Library**")
        description = _scholar_text("description", "Access the vast records of human civilization through my synthetic and mystical perspective.")

        return "\n".join([
            title,
            description,
            "-" * 45,
        ])

    if detail_name == "admin":
        server_id = get_server_key(guild) if guild else None
        scholar_messages = _get_scholar_descriptions(server_id)
        general_messages = {}
        try:
            from .content import _get_personality_descriptions
            personality_descriptions = _get_personality_descriptions(server_id)
            general_messages = personality_descriptions.get("general", {})
        except Exception:
            pass

        def _scholar_text(key: str, fallback: str) -> str:
            value = scholar_messages.get(key)
            return str(value).strip() if value else fallback

        # Check if scholar is enabled from server_config
        scholar_enabled = False
        try:
            server_id = str(guild.id) if guild else None
            if server_id:
                from .server_config import is_role_enabled
                scholar_enabled = is_role_enabled(server_id, "scholar", default_enabled=False)
        except Exception as e:
            logger.warning(f"Error loading scholar state from server_config: {e}")
            scholar_enabled = (agent_config or {}).get("roles", {}).get("scholar", {}).get("enabled", False)

        # Get localized labels
        action_labels = general_messages.get("action_labels", {})
        label_enabled = action_labels.get("enabled", "Enabled")
        label_disabled = action_labels.get("disabled", "Disabled")

        controls_title = _scholar_text("controls_title", "**Controls**")
        controls = _scholar_text("controls", "- Enable or disable the Scholar role")
        admin_flows = _scholar_text("admin_flows", "Toggle the Scholar role to enable or disable it.")

        return "\n".join([
            "Configure Scholar role settings and availability for this server.",
            f"**Status:** {'✅ ' + label_enabled if scholar_enabled else '❌ ' + label_disabled}",
            "",
            controls_title,
            controls,
            "",
            admin_flows,
            "",
            "**Routing**",
            "- Back only from here",
            "- No other subrole buttons are shown in this admin screen",
        ])

    return None


async def handle_canvas_scholar_action(interaction: discord.Interaction, action_name: str, view) -> None:
    """Handle Scholar canvas actions."""
    # Effective guild: fall back to the view's resolved guild in DM.
    eff_guild = interaction.guild or getattr(view, 'guild', None)
    server_key = get_server_key(eff_guild) if eff_guild else None
    ok = True
    current_detail = "overview"
    applied_text = None

    try:
        # --- Admin: enable/disable scholar ---
        if action_name in {"scholar_on", "scholar_off"}:
            enabled = action_name == "scholar_on"
            try:
                from .server_config import set_role_config
                ok = set_role_config(server_key, "scholar", enabled)
                current_detail = "admin"
                applied_text = f"Scholar {'enabled' if enabled else 'disabled'}."
            except Exception as e:
                logger.exception(f"Failed to update scholar config: {e}")
                ok = False
                current_detail = "admin"
                applied_text = "Failed to update scholar configuration."
        else:
            await interaction.response.send_message("❌ Unknown scholar action.", ephemeral=True)
            return

    except Exception as e:
        logger.exception(f"Canvas scholar action failed: {e}")
        ok = False

    # --- Re-render view ---
    try:
        from .content import _build_canvas_role_embed, _get_canvas_role_actions
        from discord_bot.canvas.ui import CanvasRoleDetailView

        detail_content = build_canvas_role_scholar_detail(current_detail, view.admin_visible, eff_guild, view.author_id, view.agent_config)
        actions = _get_canvas_role_actions("scholar", current_detail, view.admin_visible, view.agent_config, eff_guild)
        role_embed = _build_canvas_role_embed("scholar", detail_content, view.admin_visible, current_detail, applied_text)

        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name="scholar",
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail=current_detail,
            guild=view.guild,
            previous_view=view,
        )

        try:
            await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)
        except discord.InteractionResponded:
            await interaction.followup.edit_message(interaction.message.id, embed=role_embed, view=next_view)
        except discord.NotFound:
            try:
                await interaction.followup.send(embed=role_embed, view=next_view, ephemeral=True)
            except discord.NotFound:
                logger.debug("Canvas scholar interaction expired completely")
    except Exception as e:
        logger.exception(f"Failed to re-render scholar canvas: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Error al actualizar vista.", ephemeral=True)
