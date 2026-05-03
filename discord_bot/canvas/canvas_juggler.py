"""Canvas builder for Juggler role."""

import discord
from agent_logging import get_logger

from discord_bot import discord_core_commands as core
_personality_answers = core._personality_answers

logger = get_logger('canvas_juggler')


def build_canvas_role_juggler(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the Juggler role view."""
    from .content import _get_personality_descriptions

    personality_descriptions = _get_personality_descriptions(str(guild.id) if guild else None)
    juggler_messages = personality_descriptions.get("role_descriptions", {}).get("juggler", {})
    general_messages = personality_descriptions.get("general", {})

    description = juggler_messages.get("description", "Nexus that manages multiple operational flows to maintain network harmony.")

    content = f"{description}\n"

    # Add subrole descriptions if any (for future subroles)
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

    if detail_name == "overview":
        return build_canvas_role_juggler({}, admin_visible, guild)
    
    if detail_name == "poetry":
        return build_canvas_role_juggler_poetry_detail(admin_visible, guild)

    # Default fallback
    return f"**Detail: {detail_name}**\nDetail view for {detail_name}."


def build_canvas_role_juggler_poetry_detail(admin_visible: bool, guild=None) -> str:
    """Build the Poetry subrole detail view."""
    from .content import _get_personality_descriptions

    server_id = str(guild.id) if guild else None
    personality_descriptions = _get_personality_descriptions(server_id)
    poetry_messages = personality_descriptions.get("role_descriptions", {}).get("juggler", {}).get("poetry", {})

    title = poetry_messages.get("title", "📝 Poetry")
    description = poetry_messages.get("description", "Request a poem dedicated to another user.")
    
    content = f"**{title}**\n{description}\n"
    
    # Add compose action description
    if admin_visible:
        action_compose = poetry_messages.get("action_compose", "✍️ Compose Poem")
        action_compose_desc = poetry_messages.get("action_compose_desc", "Write a poem for another user")
        content += f"\n**{action_compose}**\n{action_compose_desc}\n"
    
    return content


class PoetryActionModal(discord.ui.Modal):
    """Modal for composing a poem dedication."""
    
    def __init__(self, author_id: int, guild):
        from .content import _get_personality_descriptions
        server_id = str(guild.id) if guild else None
        personality_descriptions = _get_personality_descriptions(server_id)
        poetry_messages = personality_descriptions.get("role_descriptions", {}).get("juggler", {}).get("poetry", {})
        
        title = poetry_messages.get("modal_title", "Compose Poem")
        super().__init__(title=title)
        
        self.author_id = author_id
        self.guild = guild
        self.server_id = server_id
        
        target_label = poetry_messages.get("modal_target_label", "Target User")
        target_placeholder = poetry_messages.get("modal_target_placeholder", "@user or user ID")
        dedication_label = poetry_messages.get("modal_dedication_label", "Dedication/Premise")
        dedication_placeholder = poetry_messages.get("modal_dedication_placeholder", "A short theme or message (max 150 chars)")
        
        self.target_input = discord.ui.TextInput(
            label=target_label,
            placeholder=target_placeholder,
            required=True,
            max_length=100
        )
        
        self.dedication_input = discord.ui.TextInput(
            label=dedication_label,
            placeholder=dedication_placeholder,
            required=True,
            max_length=150,
            style=discord.TextStyle.paragraph
        )
        
        self.add_item(self.target_input)
        self.add_item(self.dedication_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        from .canvas_base import CanvasModal
        from .server_config import get_role_config_value
        from roles.juggler.subroles.poetry.poetry_discord import check_and_charge_cost, generate_poem
        from roles.juggler.subroles.poetry.poetry_messages import get_poetry_message
        from roles.juggler.subroles.poetry.poetry import POETRY_MAX_DEDICATION_LENGTH
        
        # Check if interaction user is the original author
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This modal belongs to another user.", ephemeral=True)
            return
        
        # Check if poetry subrole is enabled
        try:
            poetry_enabled = get_role_config_value(self.server_id, "juggler", "config.subroles.poetry.enabled", default=False)
            if not poetry_enabled:
                error_msg = get_poetry_message(self.server_id, "error_subrole_disabled")
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
        except Exception as e:
            logger.warning(f"Error checking poetry enabled status: {e}")
            # On error, allow the request to proceed
        
        await interaction.response.defer(ephemeral=True)
        
        target_user_str = self.target_input.value.strip()
        dedication = self.dedication_input.value.strip()
        
        # Validate dedication length
        if len(dedication) > POETRY_MAX_DEDICATION_LENGTH:
            error_msg = get_poetry_message(self.server_id, "error_dedication_too_long")
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        
        # Validate and resolve target user
        target_user = await self._resolve_target_user(target_user_str)
        if not target_user:
            error_msg = get_poetry_message(self.server_id, "error_target_invalid")
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        
        target_name = target_user.display_name
        target_user_id = target_user.id
        sender_id = interaction.user.id
        sender_name = interaction.user.display_name
        
        # Check and charge cost (TAE if Banker enabled)
        cost_success, cost_error = await check_and_charge_cost(sender_id, self.server_id)
        if not cost_success:
            await interaction.followup.send(cost_error, ephemeral=True)
            return
        
        # Generate poem
        poem_success, poem_error, poem = await generate_poem(
            target_name,
            dedication,
            self.server_id,
            sender_id,
            sender_name,
            target_user_id
        )
        
        if not poem_success:
            await interaction.followup.send(poem_error, ephemeral=True)
            return
        
        # Send preview DM with confirmation button
        from roles.juggler.subroles.poetry.poetry_discord import send_poem_preview
        
        # Get bot instance from interaction
        bot = interaction.client
        
        preview_sent = await send_poem_preview(
            sender_id,
            poem,
            target_user_id,
            self.server_id,
            sender_name,
            target_name,
            bot
        )
        
        if preview_sent:
            preview_title = get_poetry_message(self.server_id, "preview_title")
            preview_desc = get_poetry_message(self.server_id, "preview_description")
            await interaction.followup.send(f"{preview_title}\n{preview_desc}\n\nCheck your DMs!", ephemeral=True)
        else:
            error_msg = get_poetry_message(self.server_id, "error_failed_preview_dm")
            await interaction.followup.send(error_msg, ephemeral=True)
    
    async def _resolve_target_user(self, target_user_str: str):
        """Resolve target user from mention, username, nickname, or ID."""
        # Try to parse as mention
        if target_user_str.startswith('<@') and target_user_str.endswith('>'):
            user_id = int(target_user_str.strip('<@!>'))
            return self.guild.get_member(user_id)
        
        # Try to parse as numeric ID
        if target_user_str.isdigit():
            return self.guild.get_member(int(target_user_str))
        
        # Try to find by display name (case-insensitive)
        target_lower = target_user_str.lower()
        for member in self.guild.members:
            if member.display_name.lower() == target_lower or member.name.lower() == target_lower:
                return member
        
        # Try to find by global name (case-insensitive)
        for member in self.guild.members:
            if member.global_name and member.global_name.lower() == target_lower:
                return member
        
        return None


async def handle_canvas_juggler_poetry_compose(interaction: discord.Interaction, guild):
    """Handle the compose poetry action."""
    modal = PoetryActionModal(interaction.user.id, guild)
    await interaction.response.send_modal(modal)


async def handle_canvas_juggler_action(interaction: discord.Interaction, action_name: str, view) -> None:
    """Handle Juggler canvas actions including poetry enable/disable."""
    from .server_config import set_role_config_value, get_role_config_value
    from .content import _get_personality_descriptions, _build_canvas_role_detail_view
    from .ui import CanvasRoleDetailView
    
    # Effective guild: fall back to the view's resolved guild in DM.
    eff_guild = interaction.guild or getattr(view, 'guild', None)
    server_key = core.get_server_key(eff_guild) if eff_guild else None
    ok = True
    current_detail = "poetry"
    applied_text = None
    
    try:
        if action_name == "poetry_on":
            enabled = True
            set_role_config_value(server_key, "juggler", "config.subroles.poetry.enabled", enabled)
            ok = True
            server_id = str(eff_guild.id) if eff_guild else None
            personality_descriptions = _get_personality_descriptions(server_id)
            poetry_messages = personality_descriptions.get("role_descriptions", {}).get("juggler", {}).get("poetry", {})
            applied_text = poetry_messages.get("enabled", "Poetry enabled for this server.")
        elif action_name == "poetry_off":
            enabled = False
            set_role_config_value(server_key, "juggler", "config.subroles.poetry.enabled", enabled)
            ok = True
            server_id = str(eff_guild.id) if eff_guild else None
            personality_descriptions = _get_personality_descriptions(server_id)
            poetry_messages = personality_descriptions.get("role_descriptions", {}).get("juggler", {}).get("poetry", {})
            applied_text = poetry_messages.get("disabled", "Poetry disabled for this server.")
        elif action_name == "poetry_compose":
            if not eff_guild:
                from roles.juggler.subroles.poetry.poetry_messages import get_poetry_message
                server_id = str(eff_guild.id) if eff_guild else None
                error_msg = get_poetry_message(server_id, "error_server_only")
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
            
            # Check if poetry subrole is enabled
            poetry_enabled = False
            if view.agent_config:
                poetry_enabled = view.agent_config.get("roles", {}).get("juggler", {}).get("subroles", {}).get("poetry", {}).get("enabled", False)
            
            # Also check server_config
            try:
                poetry_enabled = get_role_config_value(server_key, "juggler", "config.subroles.poetry.enabled", default=poetry_enabled)
            except Exception:
                pass
            
            if not poetry_enabled:
                server_id = str(eff_guild.id) if eff_guild else None
                personality_descriptions = _get_personality_descriptions(server_id)
                poetry_messages = personality_descriptions.get("role_descriptions", {}).get("juggler", {}).get("poetry", {})
                error_msg = poetry_messages.get("error_subrole_disabled", "❌ The Poetry subrole is disabled on this server. Contact an administrator to enable it.")
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
            
            await handle_canvas_juggler_poetry_compose(interaction, eff_guild)
            return
        else:
            from roles.juggler.subroles.poetry.poetry_messages import get_poetry_message
            server_id = str(eff_guild.id) if eff_guild else None
            error_msg = get_poetry_message(server_id, "error_unknown_action", action=action_name)
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        if ok:
            # Refresh the view with navigation buttons instead of removing them
            content = _build_canvas_role_detail_view(
                "juggler",
                current_detail,
                view.agent_config,
                view.admin_visible,
                guild=eff_guild,
                author_id=view.author_id
            )
            detail_view = CanvasRoleDetailView(
                view.author_id,
                "juggler",
                view.agent_config,
                view.admin_visible,
                {},
                current_detail=current_detail,
                guild=eff_guild,
                message=interaction.message
            )
            detail_view.auto_response_preview = applied_text
            role_embed = _build_canvas_role_embed("juggler", content, view.admin_visible, current_detail, None, detail_view.auto_response_preview, server_id=server_id)
            await interaction.response.edit_message(content=None, embed=role_embed, view=detail_view)
        else:
            server_id = str(eff_guild.id) if eff_guild else None
            personality_descriptions = _get_personality_descriptions(server_id)
            poetry_messages = personality_descriptions.get("role_descriptions", {}).get("juggler", {}).get("poetry", {})
            error_msg = poetry_messages.get("error_config_failed", "❌ Failed to update configuration.")
            await interaction.response.send_message(error_msg, ephemeral=True)
    
    except Exception as e:
        logger.error(f"Error handling juggler action {action_name}: {e}")
        from roles.juggler.subroles.poetry.poetry_messages import get_poetry_message
        server_id = str(eff_guild.id) if eff_guild else None
        error_msg = get_poetry_message(server_id, "error_generic", error=str(e))
        await interaction.response.send_message(error_msg, ephemeral=True)
