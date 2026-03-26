"""Canvas Discord UI components."""

import os
import asyncio
import discord
from pathlib import Path

# Import core components directly to avoid circular imports
try:
    from agent_db import AgentDatabase
    from agent_logging import get_logger
    from agent_engine import PERSONALITY
except ImportError:
    AgentDatabase = None
    get_logger = None
    PERSONALITY = {}

# Import Canvas-specific functions
try:
    from discord_bot.canvas.content import _get_canvas_behavior_detail, _get_enabled_roles, _load_role_mission_prompts, _build_canvas_embed
except ImportError:
    _get_canvas_behavior_detail = None
    _get_enabled_roles = None
    _load_role_mission_prompts = None
    _build_canvas_embed = None

logger = get_logger('canvas_ui') if get_logger else None


class TimeoutResetMixin:
    """Mixin to reset view timeout on user interaction."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_timeout = self.timeout
        self._timeout_task = None
    
    def _reset_timeout(self):
        """Reset the timeout timer."""
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
        
        # Create a new timeout task
        self._timeout_task = asyncio.create_task(self._timeout_handler())
    
    async def _timeout_handler(self):
        """Handle timeout after the specified duration."""
        try:
            await asyncio.sleep(self._original_timeout)
            if not self.is_finished():
                await self.on_timeout()
        except asyncio.CancelledError:
            # Timeout was reset, this is normal
            pass
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Reset timeout on valid interaction."""
        # First check if this is the authorized user
        if hasattr(super(), '_check_user_permission'):
            if not await super()._check_user_permission(interaction):
                return False
        elif hasattr(super(), 'interaction_check'):
            if not await super().interaction_check(interaction):
                return False
        
        # Reset timeout for valid interactions
        self._reset_timeout()
        return True


def _is_unknown_interaction_error(error: Exception) -> bool:
    return isinstance(error, discord.NotFound) and (
        getattr(error, "code", None) == 10062 or "Unknown interaction" in str(error)
    )


async def _safe_send_interaction_message(interaction: discord.Interaction, content: str, ephemeral: bool = True) -> bool:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral)
        return True
    except discord.InteractionResponded:
        try:
            await interaction.followup.send(content, ephemeral=ephemeral)
            return True
        except Exception as send_error:
            logger.warning(f"Canvas followup send failed: {send_error}")
            return False
    except Exception as send_error:
        if _is_unknown_interaction_error(send_error):
            logger.info(f"Canvas interaction expired before send_message: {send_error}")
            return False
        logger.warning(f"Canvas send_message failed: {send_error}")
        return False


async def _safe_edit_interaction_message(interaction: discord.Interaction, content=None, embed=None, view=None) -> bool:
    try:
        if interaction.response.is_done():
            await interaction.followup.edit_message(interaction.message.id, content=content, embed=embed, view=view)
        else:
            await interaction.response.edit_message(content=content, embed=embed, view=view)
        return True
    except discord.InteractionResponded:
        try:
            await interaction.followup.edit_message(interaction.message.id, content=content, embed=embed, view=view)
            return True
        except Exception as edit_error:
            logger.warning(f"Canvas followup edit failed: {edit_error}")
    except Exception as edit_error:
        if _is_unknown_interaction_error(edit_error):
            logger.info(f"Canvas interaction expired before edit_message: {edit_error}")
        else:
            logger.warning(f"Canvas interaction edit failed: {edit_error}")

        try:
            if interaction.message:
                await interaction.message.edit(content=content, embed=embed, view=view)
                return True
        except Exception as message_edit_error:
            logger.warning(f"Canvas direct message edit fallback failed: {message_edit_error}")
        return False


async def _get_canvas_announcement_channel(interaction: discord.Interaction, guild: discord.Guild):
    if guild is None:
        return None

    current_channel = interaction.channel
    if isinstance(current_channel, discord.TextChannel) and current_channel.guild and current_channel.guild.id == guild.id:
        permissions = current_channel.permissions_for(guild.me)
        if permissions.send_messages:
            return current_channel

    preferred_names = ("general", "chat", "principal", "general-chat")
    for channel in guild.text_channels:
        permissions = channel.permissions_for(guild.me)
        if permissions.send_messages and any(name in channel.name.lower() for name in preferred_names):
            return channel

    for channel in guild.text_channels:
        permissions = channel.permissions_for(guild.me)
        if permissions.send_messages:
            return channel

    return None


async def _send_canvas_dice_announcements(interaction: discord.Interaction, guild: discord.Guild, announcements: list[str]) -> None:
    valid_announcements = [announcement for announcement in announcements if announcement]
    logger.info(f"📢 Canvas dice announcements queued: {len(valid_announcements)}")
    if not valid_announcements:
        return

    channel = await _get_canvas_announcement_channel(interaction, guild)
    if channel is None:
        logger.warning("📢 Canvas dice announcement skipped: no valid channel found")
        return

    logger.info(f"📢 Canvas dice announcement channel: {channel.name} ({channel.id})")
    for announcement in valid_announcements:
        await channel.send(announcement)
        logger.info(f"📢 Canvas dice announcement sent to {channel.name}")


# Helper function for back button navigation
async def navigate_back(interaction, current_view, target_view=None, target_content=None):
    """Navigate back to previous view or specific target."""
    
    if target_view and target_content:
        # Navigate to specific target view
        target_view.message = interaction.message
        embed = _build_canvas_embed(target_view, target_content, current_view.admin_visible)
        await _safe_edit_interaction_message(interaction, content=None, embed=embed, view=target_view)
        return target_view
    else:
        # Default: navigate to home
        home_content = current_view.sections.get("home")
        if not home_content:
            await _safe_send_interaction_message(interaction, "❌ The Canvas home is not available.", ephemeral=True)
            return None
        
        CanvasNavigationView = globals().get('CanvasNavigationView')
        if CanvasNavigationView is None:
            await _safe_send_interaction_message(interaction, "❌ Navigation not available.", ephemeral=True)
            return None
        
        nav_view = CanvasNavigationView(current_view.author_id, current_view.sections, current_view.admin_visible, current_view.agent_config, show_dropdown=False)
        nav_view.update_visibility()
        nav_view.message = interaction.message
        home_embed = _build_canvas_embed("home", home_content, current_view.admin_visible)
        await _safe_edit_interaction_message(interaction, content=None, embed=home_embed, view=nav_view)
        return nav_view


class BackButtonMixin:
    """Mixin class to add a standardized back button to any Canvas view.
    
    Usage:
        class MyCanvasView(BackButtonMixin, discord.ui.View):
            def __init__(self, ...):
                super().__init__(timeout=600)
                # ... your initialization code ...
                
                # Add back button with default settings
                self.add_back_button()
                
                # Or add back button with custom label and row
                # self.add_back_button(row=3, label="← Go Back")
    """
    
    def add_back_button(self, row=4, label=None):
        """Add a back button to this view."""
        button_label = label or _personality_descriptions.get("canvas_home_messages", {}).get("button_back", "Back")
        
        # Create a button instance
        button = CanvasBackButton(label=button_label, row=row)
        self.add_item(button)


class SmartBackButtonMixin:
    """Mixin class to add a standardized smart back button to any Canvas view.
    
    Usage:
        class MyCanvasView(SmartBackButtonMixin, discord.ui.View):
            def __init__(self, ...):
                super().__init__(timeout=600)
                # ... your initialization code ...
                
                # Add smart back button with default settings
                self.add_smart_back_button()
                
                # Or add smart back button with custom label and row
                # self.add_smart_back_button(row=3, label="← Go Back")
    """
    
    def add_smart_back_button(self, row=4, label=None):
        """Add a smart back button to this view."""
        button_label = label or _personality_descriptions.get("canvas_home_messages", {}).get("button_back", "Back")
        
        # Create a button instance
        button = CanvasSmartBackButton(label=button_label, row=row)
        self.add_item(button)


class CanvasSmartBackButton(discord.ui.Button):
    """Universal smart back button that automatically detects where to navigate."""
    
    def __init__(self, label="Back", row=4):
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=row)
    
    async def callback(self, interaction: discord.Interaction):
        view = self.view
        
        # Smart navigation logic based on view type and current state
        if hasattr(view, 'current_detail') and hasattr(view, 'role_name'):
            # This is a CanvasRoleDetailView
            if hasattr(view, 'previous_view') and view.previous_view:
                # Navigate back to previous view (before action execution)
                previous_view = view.previous_view
                previous_view.message = interaction.message
                await _safe_edit_interaction_message(
                    content=None, 
                    embed=previous_view.current_embed if hasattr(previous_view, 'current_embed') else None,
                    view=previous_view,
                    interaction=interaction,
                )
                return
            
            if view.current_detail == "overview":
                # Navigate back to roles view
                roles_content = view.sections.get("roles")
                if not roles_content:
                    await _safe_send_interaction_message(interaction, "❌ The Canvas roles view is not available.", ephemeral=True)
                    return
                
                from discord_bot.canvas.ui import CanvasRolesView, _build_canvas_embed
                roles_view = CanvasRolesView(view.author_id, view.agent_config, view.admin_visible, view.sections)
                roles_view.message = interaction.message
                roles_embed = _build_canvas_embed("roles", roles_content, view.admin_visible)
                await _safe_edit_interaction_message(interaction, content=None, embed=roles_embed, view=roles_view)
            else:
                # Navigate back to role overview
                from discord_bot.canvas.content import _build_canvas_role_view
                content = _build_canvas_role_view(view.role_name, view.agent_config, view.admin_visible, view.guild, view.author_id)
                if not content:
                    await _safe_send_interaction_message(interaction, "❌ This role is not available.", ephemeral=True)
                    return
                
                from discord_bot.canvas.ui import CanvasRoleDetailView
                from discord_bot.canvas.content import _build_canvas_role_embed
                detail_view = CanvasRoleDetailView(
                    author_id=view.author_id,
                    role_name=view.role_name,
                    agent_config=view.agent_config,
                    admin_visible=view.admin_visible,
                    sections=view.sections,
                    current_detail="overview",
                    guild=view.guild
                )
                detail_view.message = interaction.message
                role_embed = _build_canvas_role_embed(
                    view.role_name,
                    content,
                    view.admin_visible,
                    "overview",
                    interaction.user,
                    detail_view.auto_response_preview,
                )
                await _safe_edit_interaction_message(interaction, content=None, embed=role_embed, view=detail_view)
        else:
            # For other views, use default navigation to home
            from discord_bot.canvas.ui import navigate_back
            await navigate_back(interaction, view)


class HomeButtonMixin:
    """Mixin class to add a standardized home button to any Canvas view.
    
    Usage:
        class MyCanvasView(HomeButtonMixin, discord.ui.View):
            def __init__(self, ...):
                super().__init__(timeout=600)
                # ... your initialization code ...
                
                # Add home button with default settings
                self.add_home_button()
                
                # Or add home button with custom label and row
                # self.add_home_button(row=3, label="🏠 Home")
    """
    
    def add_home_button(self, row=4, label=None):
        """Add a home button to this view."""
        button_label = label or _personality_descriptions.get("canvas_home_messages", {}).get("button_home", "Home")
        
        # Create a button instance
        button = CanvasHomeButton(label=button_label, row=row)
        self.add_item(button)


class CanvasHomeButton(discord.ui.Button):
    """Standard home button for Canvas views."""
    
    def __init__(self, label="Home", row=4):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=row)
    
    async def callback(self, interaction: discord.Interaction):
        view = self.view
        home_content = view.sections.get("home")
        if not home_content:
            await _safe_send_interaction_message(interaction, "❌ The Canvas home is not available.", ephemeral=True)
            return
        
        CanvasNavigationView = globals().get('CanvasNavigationView')
        if CanvasNavigationView is None:
            await _safe_send_interaction_message(interaction, "❌ Navigation not available.", ephemeral=True)
            return
        
        nav_view = CanvasNavigationView(view.author_id, view.sections, view.admin_visible, view.agent_config, show_dropdown=False)
        nav_view.update_visibility()
        nav_view.message = interaction.message
        
        home_embed = _build_canvas_embed("home", home_content, view.admin_visible)
        await _safe_edit_interaction_message(interaction, content=None, embed=home_embed, view=nav_view)


class NavigationButtonsMixin(BackButtonMixin, HomeButtonMixin):
    """Combined mixin that adds both Back and Home buttons.
    
    Usage:
        class MyCanvasView(NavigationButtonsMixin, discord.ui.View):
            def __init__(self, ...):
                super().__init__(timeout=600)
                # ... your initialization code ...
                
                # Add both navigation buttons
                self.add_navigation_buttons()
                
                # Or add buttons with custom settings
                # self.add_back_button(row=3, label="← Back")
                # self.add_home_button(row=3, label="🏠 Home")
    """
    
    def add_navigation_buttons(self, back_row=4, home_row=4, back_label=None, home_label=None):
        """Add both back and home buttons to this view."""
        self.add_back_button(row=back_row, label=back_label)
        self.add_home_button(row=home_row, label=home_label)

# Import Discord utilities and other functions
from discord_bot import discord_core_commands as core

os = core.os
asyncio = core.asyncio
discord = core.discord
Path = core.Path
AgentDatabase = core.AgentDatabase
logger = core.logger
PERSONALITY = core.PERSONALITY
AGENT_CFG = core.AGENT_CFG

try:
    from discord_bot.discord_utils import (
        send_embed_dm_or_channel, set_greeting_enabled, get_greeting_enabled,
        is_role_enabled_check, get_server_key, get_role_interval_hours, set_role_enabled, is_admin
    )
    from roles.banker.db_role_banker import get_banker_db_instance
    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
    from roles.news_watcher.watcher_messages import get_watcher_messages
    from roles.treasure_hunter.poe2.poe2_subrole_manager import get_poe2_manager
    from roles.trickster.subroles.dice_game.db_dice_game import get_dice_game_db_instance
    from roles.trickster.subroles.dice_game.dice_game import DiceGame
    from roles.trickster.trickster_discord import get_beggar_db_instance
    from behavior.db_behavior import get_behavior_db_instance
    
    # Get variables from core
    _discord_cfg = core._discord_cfg
    _personality_name = core._personality_name
    _bot_display_name = core._bot_display_name
    _insult_cfg = core._insult_cfg
    _personality_answers = core._personality_answers
    _personality_descriptions = core._personality_descriptions
    _talk_state_by_guild_id = core._talk_state_by_guild_id
    get_taboo_state = core.get_taboo_state
    update_taboo_state = core.update_taboo_state
    is_taboo_triggered = core.is_taboo_triggered
    
except ImportError:
    # Fallback values if imports fail
    send_embed_dm_or_channel = None
    set_greeting_enabled = None
    get_greeting_enabled = None
    is_role_enabled_check = None
    get_server_key = None
    get_role_interval_hours = None
    set_role_enabled = None
    get_banker_db_instance = None
    get_news_watcher_db_instance = None
    get_watcher_messages = None
    get_poe2_manager = None
    get_dice_game_db_instance = None
    DiceGame = None
    get_beggar_db_instance = None
    get_behavior_db_instance = None
    
    # Core fallbacks
    _discord_cfg = {}
    _personality_name = "Unknown"
    _bot_display_name = "Bot"
    _insult_cfg = {}
    _personality_answers = {}
    _personality_descriptions = {}
    _talk_state_by_guild_id = {}
    get_taboo_state = None
    update_taboo_state = None
    is_taboo_triggered = None

# Load descriptions directly if import failed
if not _personality_descriptions:
    try:
        import json
        from pathlib import Path
        descriptions_path = Path(__file__).parent.parent.parent / "personalities" / "putre" / "descriptions.json"
        if descriptions_path.exists():
            with open(descriptions_path, 'r', encoding='utf-8') as f:
                _personality_descriptions = json.load(f)
    except Exception:
        _personality_descriptions = {}

try:
    from roles.trickster.subroles.dice_game.dice_game import process_play
except Exception:
    process_play = None

try:
    from roles.trickster.subroles.nordic_runes.db_nordic_runes import get_nordic_runes_db_instance
except Exception:
    get_nordic_runes_db_instance = None

try:
    from roles.mc.db_role_mc import get_mc_db_instance
except Exception:
    get_mc_db_instance = None

try:
    from roles.trickler.subroles.ring.ring_discord import _get_ring_state, execute_ring_accusation
except Exception:
    _get_ring_state = None
    execute_ring_accusation = None

try:
    from roles.trickster.subroles.nordic_runes.nordic_runes_discord import get_nordic_runes_commands_instance
except Exception:
    get_nordic_runes_commands_instance = None

from .content import (
    _build_canvas_behavior_action_view,
    _build_canvas_behavior_embed,
    _build_canvas_embed,
    _build_canvas_role_detail_view,
    _build_canvas_role_embed,
    _build_canvas_role_view,
    _build_canvas_sections,
    _get_canvas_auto_response_preview,
    _get_canvas_role_action_items_for_detail,
    _get_canvas_role_detail_items,
)
from .state import (
    _build_mission_commentary_prompt,
    _get_canvas_dice_state,
    _get_canvas_dice_ranking,
    _get_canvas_watcher_method_label,
    _get_enabled_roles,
)
from .canvas_mc import (
    CanvasMCActionSelect,
    CanvasMCSongModal,
    CanvasMCVolumeModal,
    _handle_canvas_mc_action,
)
from .canvas_news_watcher import build_canvas_role_news_watcher_detail as _build_canvas_role_news_watcher_detail
from .canvas_trickster import build_canvas_role_trickster_detail as _build_canvas_role_trickster_detail
from .canvas_behavior import (
    get_canvas_behavior_action_items_for_detail as _get_canvas_behavior_action_items_for_detail,
    get_canvas_behavior_detail_items as _get_canvas_behavior_detail_items,
    build_canvas_behavior_detail as _build_canvas_behavior_detail,
)

class CanvasSectionSelect(discord.ui.Select):
    def __init__(self, admin_visible: bool):
        # Get personalized labels from descriptions.json
        canvas_home = _personality_descriptions.get("canvas_home_messages", {})
        home_label = canvas_home.get("section_home", "Home")
        roles_label = canvas_home.get("section_roles", "Roles")
        behavior_label = canvas_home.get("section_behavior", "Behavior")
        personal_label = canvas_home.get("section_personal", "Personal")
        help_label = canvas_home.get("section_help", "Help")
        setup_label = canvas_home.get("section_setup", "Setup")
        
        options = [
            discord.SelectOption(label=home_label, value="home", description="Canvas hub and overview"),
            discord.SelectOption(label=roles_label, value="roles", description="Browse role surfaces"),
            discord.SelectOption(label=behavior_label, value="behavior", description="Shared bot behavior"),
            discord.SelectOption(label=personal_label, value="personal", description="Private and user flows"),
            discord.SelectOption(label=help_label, value="help", description="Troubleshooting and commands"),
        ]
        if admin_visible:
            options.append(discord.SelectOption(label=setup_label, value="setup", description="Server administration"))
        
        placeholder = canvas_home.get("placeholder", "Choose a Canvas surface...")
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, row=3)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasNavigationView):
            await interaction.response.send_message("❌ Canvas section navigation is not available.", ephemeral=True)
            return
        selected = self.values[0]
        if selected == "roles":
            roles_content = view.sections.get("roles")
            if not roles_content:
                await interaction.response.send_message("❌ This Canvas section is not available.", ephemeral=True)
                return
            roles_view = CanvasRolesView(view.author_id, view.agent_config, view.admin_visible, view.sections)
            roles_embed = _build_canvas_embed("roles", roles_content, view.admin_visible)
            await interaction.response.edit_message(content=None, embed=roles_embed, view=roles_view)
            # Set the message reference for timeout deletion
            roles_view.message = interaction.message
            return
        if selected == "behavior":
            behavior_content = view.sections.get("behavior")
            if not behavior_content:
                await interaction.response.send_message("❌ This Canvas section is not available.", ephemeral=True)
                return
            behavior_view = CanvasBehaviorView(view.author_id, view.sections, view.admin_visible, view.agent_config, current_detail="conversation", guild=interaction.guild)
            behavior_embed = _build_canvas_behavior_embed(behavior_content, view.admin_visible)
            await interaction.response.edit_message(content=None, embed=behavior_embed, view=behavior_view)
            # Set the message reference for timeout deletion
            behavior_view.message = interaction.message
            return
        await view._show_section(interaction, selected)


class CanvasRoleSelect(discord.ui.Select):
    def __init__(self, agent_config: dict):
        role_labels = {
            "news_watcher": ("Watcher", "Alerts and subscriptions"),
            "treasure_hunter": ("Treasure Hunter", "Tracked item opportunities"),
            "trickster": ("Trickster", "Subroles and player surfaces"),
            "banker": ("Banker", "Wallet and economy"),
            "mc": ("MC", "Music and queue controls"),
        }
        options = []
        for role_name in _get_enabled_roles(agent_config):
            label, description = role_labels.get(role_name, (role_name.replace("_", " ").title(), "Role surface"))
            options.append(discord.SelectOption(label=label, value=role_name, description=description))
        if (agent_config or {}).get("roles", {}).get("mc", {}).get("enabled", False) and not any(option.value == "mc" for option in options):
            options.append(discord.SelectOption(label="MC", value="mc", description="Music and queue controls"))
        # Add list option to show all available roles
        options.append(discord.SelectOption(label="List All Roles", value="list", description="Show complete list of available roles"))
        super().__init__(placeholder="Choose a role surface...", min_values=1, max_values=1, options=options[:25], row=3)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRolesView):
            await interaction.response.send_message("❌ Canvas role navigation is not available.", ephemeral=True)
            return
        role_name = self.values[0]
        
        # Handle list option
        if role_name == "list":
            await self._handle_list_option(interaction, view)
            return
            
        content = _build_canvas_role_view(role_name, view.agent_config, view.admin_visible, interaction.guild, view.author_id)
        if not content:
            await interaction.response.send_message("❌ This role is not available.", ephemeral=True)
            return
        
        # Load current method for news watcher to preserve selection
        watcher_selected_method = None
        if role_name == "news_watcher":
            watcher_selected_method = _get_canvas_watcher_method_label(str(interaction.guild.id)).lower()
            watcher_selected_method = watcher_selected_method if watcher_selected_method != "unknown" else None
        
        detail_view = CanvasRoleDetailView(
            view.author_id, 
            role_name, 
            view.agent_config, 
            view.admin_visible, 
            view.sections, 
            guild=interaction.guild,
            watcher_selected_method=watcher_selected_method
        )
        role_embed = _build_canvas_role_embed(role_name, content, view.admin_visible, "overview", interaction.user, detail_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=role_embed, view=detail_view)
        # Set the message reference for timeout deletion
        detail_view.message = interaction.message

    async def _handle_list_option(self, interaction: discord.Interaction, view):
        """Handle the 'list' option to show all available roles."""
        all_roles = ["news_watcher", "treasure_hunter", "trickster", "banker", "mc"]
        enabled_roles = _get_enabled_roles(view.agent_config)
        
        role_labels = {
            "news_watcher": ("Watcher", "Alerts and subscriptions"),
            "treasure_hunter": ("Treasure Hunter", "Tracked item opportunities"),
            "trickster": ("Trickster", "Subroles and player surfaces"),
            "banker": ("Banker", "Wallet and economy"),
            "mc": ("MC", "Music and queue controls"),
        }
        
        embed = discord.Embed(
            title=f"📋 {_bot_display_name} - All Available Roles",
            description="Complete list of available roles and their status",
            color=discord.Color.blue()
        )
        
        for role_name in all_roles:
            label, description = role_labels.get(role_name, (role_name.replace("_", " ").title(), "Role surface"))
            status = "✅ Enabled" if role_name in enabled_roles else "❌ Disabled"
            embed.add_field(
                name=f"{label} {status}",
                value=description,
                inline=False
            )
        
        await interaction.response.edit_message(embed=embed, view=view)


class CanvasRoleDetailSelect(discord.ui.Select):
    def __init__(self, role_name: str, admin_visible: bool):
        options = [
            discord.SelectOption(label=label, value=detail_name, description=f"Focus on {label.lower()} tasks")
            for label, detail_name in _get_canvas_role_detail_items(role_name, admin_visible)
        ]
        super().__init__(placeholder="Choose a role surface...", min_values=1, max_values=1, options=options[:25], row=3)
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRoleDetailView):
            await interaction.response.send_message("❌ Canvas role detail navigation is not available.", ephemeral=True)
            return
        detail_name = self.values[0]
        content = _build_canvas_role_detail_view(self.role_name, detail_name, view.agent_config, view.admin_visible, view.guild, view.author_id)
        if not content:
            await interaction.response.send_message("❌ This role detail is not available.", ephemeral=True)
            return
        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail=detail_name,
            guild=view.guild,
            message=interaction.message,  # Add message reference
            watcher_selected_method=getattr(view, 'watcher_selected_method', None),
            watcher_last_action=getattr(view, 'watcher_last_action', None)
        )
        detail_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, detail_name, None, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


class CanvasWatcherMethodSelect(discord.ui.Select):
    """Dynamic method selection dropdown for News Watcher."""
    
    def __init__(self, view: "CanvasRoleDetailView"):
        # Get descriptions for watcher
        from discord_bot import discord_core_commands as core
        _personality_descriptions = core._personality_descriptions
        watcher_descriptions = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {})
        
        def _watcher_text(key: str, fallback: str) -> str:
            value = watcher_descriptions.get(key)
            return str(value).strip() if value else fallback
        
        options = [
            discord.SelectOption(
                label=_watcher_text("flat_method", "Method: Flat"), 
                value="method_flat", 
                description=_watcher_text("option_flat_description", "All news with AI opinions"), 
                emoji="📰"
            ),
            discord.SelectOption(
                label=_watcher_text("keyword_method", "Method: Keyword"), 
                value="method_keyword", 
                description=_watcher_text("option_keyword_description", "News filtered by keywords"), 
                emoji="🔍"
            ),
            discord.SelectOption(
                label=_watcher_text("general_method", "Method: General"), 
                value="method_general", 
                description=_watcher_text("option_general_description", "AI critical news analysis"), 
                emoji="🤖"
            ),
        ]
        title_select_method = _watcher_text("select_method", "🔧 Select method...")
        # Set placeholder to show current selection
        placeholder = title_select_method
        if view.watcher_selected_method:
            method_display = view.watcher_selected_method.title()
            placeholder = f"🔧 Method: {method_display} (selected)"
        
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1, row=0)
        self.canvas_view = view

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        self.canvas_view.watcher_selected_method = action_name.replace("method_", "")
        self.canvas_view.watcher_last_action = None
        self.canvas_view.auto_response_preview = _get_canvas_auto_response_preview(self.canvas_view.role_name, action_name)
        
        # Update the subscription dropdown options based on the selected method
        for child in self.canvas_view.children:
            if isinstance(child, CanvasWatcherSubscriptionSelect):
                child.set_method(self.canvas_view.watcher_selected_method)
                break
        
        # Update the placeholder to reflect the selection
        method_display = self.canvas_view.watcher_selected_method.title()
        self.placeholder = f"🔧 Method: {method_display} (selected)"
        
        await _handle_canvas_watcher_action(interaction, action_name, self.canvas_view)


class CanvasWatcherSubscriptionSelect(discord.ui.Select):
    """Dynamic subscription dropdown for News Watcher based on selected method."""
    
    def __init__(self, view: "CanvasRoleDetailView"):
        super().__init__(placeholder="📋 Select action...", options=self._build_options(view.watcher_selected_method), min_values=1, max_values=1, row=1)
        self.canvas_view = view

    def _build_options(self, method: str | None) -> list[discord.SelectOption]:
        # Fixed options for listing categories and feeds
        options = [
            discord.SelectOption(label="Categories", value="list_categories", description="List available categories", emoji="📂"),
            discord.SelectOption(label="Feeds by Category", value="list_feeds_by_category", description="List feeds from a specific category", emoji="🔗"),
        ]
        # Add method-specific options for subscription
        if method:
            options.append(discord.SelectOption(label="Subscribe Categories", value="subscribe_categories", description=f"Subscribe to categories with {method} method", emoji="➕"))
        # Add method-specific configuration options
        if method == "keyword":
            options.append(discord.SelectOption(label="Keywords", value="list_keywords", description="View your configured keywords", emoji="🔍"))
            options.append(discord.SelectOption(label="Add Keywords", value="add_keywords", description="Add new keywords", emoji="➕"))
            options.append(discord.SelectOption(label="Delete Keywords", value="delete_keywords", description="Remove keywords", emoji="🗑️"))
        elif method == "general":
            options.append(discord.SelectOption(label="Premises", value="list_premises", description="View your AI analysis premises", emoji="🤖"))
            options.append(discord.SelectOption(label="Add Premises", value="add_premises", description="Add new premises", emoji="➕"))
            options.append(discord.SelectOption(label="Delete Premises", value="delete_premises", description="Remove premises", emoji="🗑️"))
        return options

    def set_method(self, method: str | None) -> None:
        self.options = self._build_options(method)

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        self.canvas_view.watcher_last_action = action_name
        
        # Handle subscription actions with modal
        if action_name == "subscribe_categories":
            await interaction.response.send_modal(CanvasWatcherSubscribeModal(action_name, self.canvas_view, interaction.client))
            return
        
        # Handle add actions with modal
        if action_name in {"add_keywords", "add_premises"}:
            await interaction.response.send_modal(CanvasWatcherAddModal(action_name, self.canvas_view, interaction.client))
            return
        
        # Handle delete actions with modal
        if action_name in {"delete_keywords", "delete_premises"}:
            await interaction.response.send_modal(CanvasWatcherDeleteModal(action_name, self.canvas_view, interaction.client))
            return
        
        # Handle listing actions by updating the view
        if action_name in {"list_categories", "list_feeds", "list_keywords", "list_premises"}:
            content = _build_canvas_role_news_watcher_detail(
                self.canvas_view.current_detail,
                self.canvas_view.admin_visible,
                self.canvas_view.guild,
                self.canvas_view.author_id,
                selected_method=self.canvas_view.watcher_selected_method,
                last_action=action_name,
            )
            embed = _build_canvas_role_embed(
                self.canvas_view.role_name,
                content or "",
                self.canvas_view.admin_visible,
                self.canvas_view.current_detail,
                None,
                self.canvas_view.auto_response_preview,
            )
            
            # Create a new view to preserve the method selection
            next_view = CanvasRoleDetailView(
                self.canvas_view.author_id,
                self.canvas_view.role_name,
                self.canvas_view.agent_config,
                self.canvas_view.admin_visible,
                self.canvas_view.sections,
                self.canvas_view.current_detail,
                self.canvas_view.guild,
                interaction.message,
                self.canvas_view.watcher_selected_method,
                self.canvas_view.watcher_last_action,
                getattr(self.canvas_view, 'watcher_selected_category', None)
            )
            next_view.auto_response_preview = self.canvas_view.auto_response_preview
            
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        elif action_name == "list_feeds_by_category":
            # Ask for category with modal
            await interaction.response.send_modal(CanvasWatcherFeedsByCategoryModal(self.canvas_view))


class CanvasWatcherAdminMethodSelect(discord.ui.Select):
    """Dynamic method selection dropdown for News Watcher Admin."""
    
    def __init__(self, view: "CanvasRoleDetailView"):
        options = [
            discord.SelectOption(label="Method: Flat", value="method_flat", description="All news with AI opinions (server default)", emoji="📰"),
            discord.SelectOption(label="Method: Keyword", value="method_keyword", description="News filtered by keywords (server default)", emoji="🔍"),
            discord.SelectOption(label="Method: General", value="method_general", description="AI critical news analysis (server default)", emoji="🤖"),
        ]
        
        # Set placeholder to show current selection
        placeholder = "🔧 Set server method..."
        if view.watcher_selected_method:
            method_display = view.watcher_selected_method.title()
            placeholder = f"🔧 Server Method: {method_display} (selected)"
        
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1, row=0)
        self.canvas_view = view

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        self.canvas_view.watcher_selected_method = action_name.replace("method_", "")
        self.canvas_view.watcher_last_action = None
        self.canvas_view.auto_response_preview = _get_canvas_auto_response_preview(self.canvas_view.role_name, action_name)
        
        # Update the action dropdown options based on the selected method
        for child in self.canvas_view.children:
            if isinstance(child, CanvasWatcherAdminActionSelect):
                child.update_options_for_method(self.canvas_view.watcher_selected_method)
                break
        
        await _handle_canvas_watcher_action(interaction, action_name, self.canvas_view)


class CanvasWatcherAdminActionSelect(discord.ui.Select):
    """Dynamic admin action dropdown for News Watcher."""
    
    def __init__(self, view: "CanvasRoleDetailView"):
        # Base options that are always available
        base_options = [
            discord.SelectOption(label="Feeds by Category", value="list_feeds_by_category", description="List feeds from a specific category", emoji="🔗"),
            discord.SelectOption(label="List categories", value="list_categories", description="List available categories", emoji="📂"),
        ]
        
        # Method-specific options
        method_specific_options = []
        selected_method = getattr(view, 'watcher_selected_method', None)
        
        if selected_method == "general":
            method_specific_options = [
                discord.SelectOption(label="Subscribe Category", value="channel_subscribe_category", description="Subscribe category <name> <optional feed> for channel", emoji="➕"),
                discord.SelectOption(label="Unsubscribe Category", value="channel_unsubscribe_category", description="Unsubscribe category <name> <optional feed> for channel", emoji="🗑️"),
                discord.SelectOption(label="List premises", value="list_premises", description="List premises for next subscription for channel", emoji="🤖"),
                discord.SelectOption(label="Add premise", value="add_premise", description="Add new premise for channel", emoji="➕"),
                discord.SelectOption(label="Delete premise", value="delete_premise", description="Delete premise <number> for current", emoji="🗑️"),
            ]
        elif selected_method == "keyword":
            method_specific_options = [
                discord.SelectOption(label="Subscribe Category", value="channel_subscribe_category", description="Subscribe category <name> <optional feed> for channel", emoji="➕"),
                discord.SelectOption(label="Unsubscribe Category", value="channel_unsubscribe_category", description="Unsubscribe category <name> <optional feed> for channel", emoji="🗑️"),
                discord.SelectOption(label="List keywords", value="list_keywords", description="List keywords for channel", emoji="🔍"),
                discord.SelectOption(label="Add keywords", value="add_keywords", description="Add new keywords for channel", emoji="➕"),
                discord.SelectOption(label="Delete keywords", value="delete_keywords", description="Delete keywords for channel", emoji="🗑️"),
            ]
        else:  # flat method or no method selected
            method_specific_options = [
                discord.SelectOption(label="Subscribe Category", value="channel_subscribe_category", description="Subscribe category <name> <optional feed> for channel", emoji="➕"),
                discord.SelectOption(label="Unsubscribe Category", value="channel_unsubscribe_category", description="Unsubscribe category <name> <optional feed> for channel", emoji="🗑️"),
            ]
        
        # Server management options (always available)
        server_options = [
            discord.SelectOption(label="Modify watcher task frequency", value="watcher_frequency", description="Set news check frequency", emoji="⏰"),
            discord.SelectOption(label="Force watcher channel now", value="watcher_run_now", description="Run news check immediately", emoji="▶️"),
            discord.SelectOption(label="Force personal subscriptions now", value="watcher_run_personal", description="Run personal subscriptions immediately", emoji="👤"),
        ]
        
        # Combine all options
        options = base_options + method_specific_options + server_options
        
        super().__init__(placeholder="⚙️ Select admin action...", options=options, min_values=1, max_values=1, row=1)
        self.canvas_view = view

    def update_options_for_method(self, method: str):
        """Update dropdown options based on selected method."""
        
        # Base options that are always available
        base_options = [
            discord.SelectOption(label="List feeds", value="list_feeds", description="List available feeds", emoji="🔗"),
            discord.SelectOption(label="List categories", value="list_categories", description="List available categories", emoji="📂"),
        ]
        
        # Method-specific options
        method_specific_options = []
        
        if method == "general":
            method_specific_options = [
                discord.SelectOption(label="Subscribe Category", value="channel_subscribe_category", description="Subscribe category <name> <optional feed> for channel", emoji="➕"),
                discord.SelectOption(label="Unsubscribe Category", value="channel_unsubscribe_category", description="Unsubscribe category <name> <optional feed> for channel", emoji="🗑️"),
                discord.SelectOption(label="List premises", value="list_premises", description="List premises for next subscription for channel", emoji="🤖"),
                discord.SelectOption(label="Add premise", value="add_premise", description="Add new premise for channel", emoji="➕"),
                discord.SelectOption(label="Delete premise", value="delete_premise", description="Delete premise <number> for current", emoji="🗑️"),
            ]
        elif method == "keyword":
            method_specific_options = [
                discord.SelectOption(label="Subscribe Category", value="channel_subscribe_category", description="Subscribe category <name> <optional feed> for channel", emoji="➕"),
                discord.SelectOption(label="Unsubscribe Category", value="channel_unsubscribe_category", description="Unsubscribe category <name> <optional feed> for channel", emoji="🗑️"),
                discord.SelectOption(label="List keywords", value="list_keywords", description="List keywords for channel", emoji="🔍"),
                discord.SelectOption(label="Add keywords", value="add_keywords", description="Add new keywords for channel", emoji="➕"),
                discord.SelectOption(label="Delete keywords", value="delete_keywords", description="Delete keywords for channel", emoji="🗑️"),
            ]
        else:  # flat method or no method selected
            method_specific_options = [
                discord.SelectOption(label="Subscribe Category", value="channel_subscribe_category", description="Subscribe category <name> <optional feed> for channel", emoji="➕"),
                discord.SelectOption(label="Unsubscribe Category", value="channel_unsubscribe_category", description="Unsubscribe category <name> <optional feed> for channel", emoji="🗑️"),
            ]
        
        # Server management options (always available)
        server_options = [
            discord.SelectOption(label="Modify watcher task frequency", value="watcher_frequency", description="Set news check frequency", emoji="⏰"),
            discord.SelectOption(label="Force watcher channel now", value="watcher_run_now", description="Run news check immediately", emoji="▶️"),
            discord.SelectOption(label="Force personal subscriptions now", value="watcher_run_personal", description="Run personal subscriptions immediately", emoji="👤"),
        ]
        
        # Combine all options and update
        self.options = base_options + method_specific_options + server_options

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        self.canvas_view.watcher_last_action = action_name
        
        # Handle listing actions by updating the view
        if action_name in {"list_categories", "list_feeds", "list_premises", "list_keywords"}:
            content = _build_canvas_role_news_watcher_detail(
                "admin",
                self.canvas_view.admin_visible,
                self.canvas_view.guild,
                self.canvas_view.author_id,
                selected_method=self.canvas_view.watcher_selected_method,
                last_action=action_name,
                selected_category=getattr(self.canvas_view, 'watcher_selected_category', None)
            )
            embed = _build_canvas_role_embed(
                self.canvas_view.role_name,
                content or "",
                self.canvas_view.admin_visible,
                "admin",
                None,
                self.canvas_view.auto_response_preview,
            )
            try:
                await interaction.response.edit_message(content=None, embed=embed, view=self.canvas_view)
            except discord.InteractionResponded:
                # If interaction was already responded to, use followup
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self.canvas_view)
            except discord.NotFound:
                # Message was deleted, send a new one
                try:
                    await interaction.followup.send(embed=embed, view=self.canvas_view, ephemeral=True)
                except discord.NotFound:
                    # Interaction completely expired, nothing we can do
                    logger.warning("Canvas watcher admin interaction expired completely - unable to send followup")
                except Exception as e:
                    logger.exception(f"Failed to send canvas watcher admin followup: {e}")
            except Exception as e:
                logger.exception(f"Failed to edit canvas watcher admin message: {e}")
                try:
                    await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
                except discord.NotFound:
                    # Interaction expired, nothing we can do
                    logger.warning("Canvas watcher admin interaction expired during error handling")
                except Exception as followup_e:
                    logger.exception(f"Failed to send error followup: {followup_e}")
            return
        elif action_name == "list_feeds_by_category":
            # Ask for category with modal
            await interaction.response.send_modal(CanvasWatcherFeedsByCategoryModal(self.canvas_view))
        
        # Handle other actions through the main handler
        await _handle_canvas_watcher_action(interaction, action_name, self.canvas_view)


class CanvasRoleActionSelect(discord.ui.Select):
    def __init__(self, role_name: str, detail_name: str, admin_visible: bool):
        options = [
            discord.SelectOption(label=label, value=value, description=description)
            for label, value, description in _get_canvas_role_action_items_for_detail(role_name, detail_name, admin_visible)
        ]
        generic_option_label = _personality_descriptions.get("canvas_home_messages", {}).get("generic_option_label", "Choose a concrete option...")
        super().__init__(placeholder=generic_option_label, min_values=1, max_values=1, options=options[:25], row=2)
        self.role_name = role_name
        self.detail_name = detail_name

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRoleDetailView):
            await interaction.response.send_message("❌ Canvas role action selection is not available.", ephemeral=True)
            return
        action_name = self.values[0]
        view.auto_response_preview = _get_canvas_auto_response_preview(self.role_name, action_name)
        if self.role_name == "banker" and action_name in {"config_tae", "config_bonus"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This banker option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(BankerConfigModal(action_name))
            return
        if action_name in {"watcher_frequency", "hunter_frequency"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This role option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(RoleFrequencyModal(self.role_name, action_name, view.agent_config, view))
            return
        if self.role_name == "treasure_hunter" and action_name in {"poe2_item_add", "poe2_item_remove"}:
            # Allow POE2 item operations in DM
            guild = interaction.guild  # Will be None in DM
            await interaction.response.send_modal(Poe2ItemModal(action_name, view.author_id, guild, view))
            return
        if self.role_name == "treasure_hunter" and action_name in {"league_standard", "league_fate_of_the_vaal", "league_hardcore"}:
            # Allow league changes in DM (user-specific setting)
            guild = interaction.guild  # Will be None in DM
            await _handle_canvas_treasure_hunter_action(interaction, action_name, view)
            return
        if self.role_name == "treasure_hunter" and action_name in {"poe2_on", "poe2_off"}:
            # Keep admin restrictions for activation/deactivation
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This option is admin-only and requires a server.", ephemeral=True)
                return
            await _handle_canvas_treasure_hunter_action(interaction, action_name, view)
            return
        if self.role_name == "trickster" and action_name in {"dice_fixed_bet", "dice_pot_value", "ring_frequency", "beggar_frequency", "beggar_donate", "ring_accuse"}:
            if not interaction.guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return
            await interaction.response.send_modal(TricksterActionModal(action_name, view.author_id, interaction.guild, view.admin_visible))
            return
        if self.role_name == "trickster" and action_name in {"dice_play", "dice_ranking", "dice_history", "dice_help"}:
            # For dice actions, allow DM execution by using default server
            await _handle_canvas_dice_action(interaction, action_name, view)
            return
        if self.role_name == "trickster" and action_name in {"runes_single", "runes_three", "runes_cross"}:
            if not interaction.guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return
            await interaction.response.send_modal(RuneCastingModal(action_name, view.author_id, interaction.guild))
            return
        if self.role_name == "trickster" and action_name in {"runes_history", "runes_types", "runes_help"}:
            if not interaction.guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return
            await _handle_canvas_runes_action(interaction, action_name, view)
            return
        if self.role_name == "news_watcher" and action_name in {"method_flat", "method_keyword", "method_general", "watcher_run_now", "watcher_run_personal"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This watcher option is admin-only.", ephemeral=True)
                return
            await _handle_canvas_watcher_action(interaction, action_name, view)
            return
        if self.role_name == "trickster" and action_name in {"announcements_on", "announcements_off", "ring_on", "ring_off", "beggar_on", "beggar_off"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This trickster option is admin-only.", ephemeral=True)
                return
            await _handle_canvas_trickster_action(interaction, action_name, view)
            return
        if self.role_name == "mc":
            if not interaction.guild:
                await interaction.response.send_message("❌ MC actions are only available in a server.", ephemeral=True)
                return
            await _handle_canvas_mc_action(interaction, action_name, view)
            return
        # This should never be reached as all roles have specific handlers
        await interaction.response.send_message("❌ This role option is not available.", ephemeral=True)
        return


class CanvasBehaviorActionSelect(discord.ui.Select):
    def __init__(self, detail_name: str, admin_visible: bool):
        options = [
            discord.SelectOption(label=label, value=value, description=description)
            for label, value, description in _get_canvas_behavior_action_items_for_detail(detail_name, admin_visible)
        ]
        generic_option_label = _personality_descriptions.get("canvas_home_messages", {}).get("generic_option_label", "Choose a concrete option...")
        super().__init__(placeholder=generic_option_label, min_values=1, max_values=1, options=options[:25], row=2)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasBehaviorView):
            await interaction.response.send_message("❌ Canvas behavior action selection is not available.", ephemeral=True)
            return
        action_name = self.values[0]
        view.auto_response_preview = _get_canvas_auto_response_preview(action_name=action_name)
        if action_name == "commentary_frequency":
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(CommentaryFrequencyModal(view))
            return
        if action_name in {"taboo_add", "taboo_del"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(TabooKeywordModal(action_name, int(interaction.guild.id), view))
            return
        if action_name == "role_control_open":
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This role option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(RoleControlModal(view))
            return
        if action_name in {"taboo_on", "taboo_off"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            guild_id = int(interaction.guild.id)
            enabled = action_name == "taboo_on"
            if update_taboo_state(guild_id, enabled=enabled):
                content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config)
                view.auto_response_preview = f"Taboo {'enabled' if enabled else 'disabled'} for this server."
                behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
            else:
                await interaction.response.send_message("❌ Failed to update taboo state. Check logs for details.", ephemeral=True)
            return
        
        # Handle greetings toggle
        if action_name in {"greetings_on", "greetings_off"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            enabled = action_name == "greetings_on"
            try:
                from discord_bot.discord_utils import set_greeting_enabled
                set_greeting_enabled(interaction.guild, enabled)
                content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config)
                view.auto_response_preview = f"Greetings {'enabled' if enabled else 'disabled'} for this server."
                behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
            except Exception as e:
                logger.error(f"Error updating greetings state: {e}")
                await interaction.response.send_message("❌ Failed to update greetings state. Check logs for details.", ephemeral=True)
            return
        
        # Handle welcome toggle
        if action_name in {"welcome_on", "welcome_off"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            enabled = action_name == "welcome_on"
            try:
                # Update in-memory config
                greeting_cfg = _discord_cfg.get("member_greeting", {})
                greeting_cfg["enabled"] = enabled

                # Save to behaviors database
                if get_behavior_db_instance is not None:
                    guild_id = str(interaction.guild.id)
                    db = get_behavior_db_instance(guild_id)
                    db.set_welcome_enabled(enabled, f"{interaction.user.name}")
                
                content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config)
                view.auto_response_preview = f"Welcome messages {'enabled' if enabled else 'disabled'} for this server."
                behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
            except Exception as e:
                logger.error(f"Error updating welcome state: {e}")
                await interaction.response.send_message("❌ Failed to update welcome state. Check logs for details.", ephemeral=True)
            return
        
        # Handle commentary toggle
        if action_name in {"commentary_on", "commentary_off"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            enabled = action_name == "commentary_on"
            try:
                guild_id = int(interaction.guild.id)
                state = _talk_state_by_guild_id.get(guild_id, {})
                state["enabled"] = enabled
                
                # Save to behaviors database
                if get_behavior_db_instance is not None:
                    db = get_behavior_db_instance(str(guild_id))
                    config = {
                        "channel_id": state.get("channel_id"),
                        "interval_minutes": state.get("interval_minutes", 180)
                    }
                    db.set_commentary_state(enabled, config, f"{interaction.user.name}")
                
                content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config)
                view.auto_response_preview = f"Commentary {'enabled' if enabled else 'disabled'} for this server."
                behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
            except Exception as e:
                logger.error(f"Error updating commentary state: {e}")
                await interaction.response.send_message("❌ Failed to update commentary state. Check logs for details.", ephemeral=True)
            return
        # Handle commentary now action
        if action_name == "commentary_now":
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            try:
                server_name = get_server_key(interaction.guild) if interaction.guild else "default"
                prompt = _build_mission_commentary_prompt(view.agent_config, server_name)
                
                # Build system instruction for call_llm
                from agent_engine import _build_system_prompt, PERSONALITY
                system_instruction = _build_system_prompt(PERSONALITY)
                
                # Add public context if needed
                public_suffix = PERSONALITY.get("public_context_suffix", "")
                if public_suffix:
                    system_instruction = f"{system_instruction}\n\n {public_suffix}"
                
                res = await asyncio.to_thread(
                    call_llm,
                    system_instruction=system_instruction,
                    prompt=prompt,
                    async_mode=False,
                    call_type="mission",
                    critical=True,
                    metadata={
                        "interaction_type": "mission",
                        "is_public": True,
                        "role": _bot_display_name,
                        "server": server_name
                    },
                    logger=logger
                )
                if res and str(res).strip():
                    content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config)
                    view.auto_response_preview = str(res).strip()
                    behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview)
                    await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
                else:
                    await interaction.response.send_message("⚠️ Could not generate commentary right now.", ephemeral=True)
            except Exception as e:
                logger.error(f"Error generating commentary: {e}")
                await interaction.response.send_message("❌ Failed to generate commentary. Check logs for details.", ephemeral=True)
            return
        
        # Fallback for other behavior actions
        content = _build_canvas_behavior_action_view(action_name, view.admin_visible)
        if not content:
            await interaction.response.send_message("❌ This behavior option is not available.", ephemeral=True)
            return
        behavior_embed = _build_canvas_behavior_embed(content, view.admin_visible, view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)


class CanvasNavigationView(TimeoutResetMixin, BackButtonMixin, HomeButtonMixin, discord.ui.View):
    """Interactive button-based Canvas navigation for top-level sections."""

    def __init__(self, author_id: int, sections: dict[str, str], admin_visible: bool, agent_config: dict, message=None, show_dropdown=True):
        super().__init__(timeout=600)  # 10 minutes instead of 10
        self.author_id = author_id
        self.sections = sections
        self.admin_visible = admin_visible
        self.agent_config = agent_config
        self.message = message  # Store the message to delete it later
        if show_dropdown:
            self.add_item(CanvasSectionSelect(admin_visible))
        
        # Start the timeout timer
        self._reset_timeout()

    async def on_timeout(self) -> None:
        """Called when the view times out - delete the entire message."""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if self.message:
                    await self.message.delete()
                self.stop()
                return  # Success, exit the method
            except discord.NotFound:
                # Message already deleted, just stop the view
                self.stop()
                return
            except discord.Forbidden:
                # If we can't delete the message, at least disable the buttons
                for child in self.children:
                    child.disabled = True
                self.stop()
                return
            except Exception as e:
                if attempt == max_attempts - 1:  # Last attempt
                    logger.warning(f"Could not delete Canvas message on timeout after {max_attempts} attempts: {e}")
                    # Fallback: disable buttons
                    for child in self.children:
                        child.disabled = True
                    self.stop()
                else:
                    # Brief delay before retry
                    await asyncio.sleep(0.1)

    async def _show_section(self, interaction: discord.Interaction, section_name: str):
        content = self.sections.get(section_name)
        if not content:
            await _safe_send_interaction_message(interaction, "❌ This Canvas section is not available.", ephemeral=True)
            return
        embed = _build_canvas_embed(section_name, content, self.admin_visible)
        await _safe_edit_interaction_message(interaction, content=None, embed=embed, view=self)

    async def _check_user_permission(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive Canvas to its original user."""
        if interaction.user.id != self.author_id:
            await _safe_send_interaction_message(interaction, "❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True

    button_roles = _personality_descriptions.get("canvas_home_messages", {}).get("button_roles", "Roles")
    @discord.ui.button(label=button_roles, style=discord.ButtonStyle.success)
    async def roles_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles_content = self.sections.get("roles")
        if not roles_content:
            await _safe_send_interaction_message(interaction, "❌ This Canvas section is not available.", ephemeral=True)
            return
        roles_view = CanvasRolesView(self.author_id, self.agent_config, self.admin_visible, self.sections)
        roles_view.message = interaction.message
        roles_embed = _build_canvas_embed("roles", roles_content, self.admin_visible)
        await _safe_edit_interaction_message(interaction, content=None, embed=roles_embed, view=roles_view)
        # Set the message reference for timeout deletion
        roles_view.message = interaction.message

    button_behavior = _personality_descriptions.get("canvas_home_messages", {}).get("button_behavior", "Behavior")
    @discord.ui.button(label=button_behavior, style=discord.ButtonStyle.success)
    async def behavior_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        behavior_content = self.sections.get("behavior")
        if not behavior_content:
            await _safe_send_interaction_message(interaction, "❌ This Canvas section is not available.", ephemeral=True)
            return
        behavior_view = CanvasBehaviorView(self.author_id, self.sections, self.admin_visible, self.agent_config, current_detail="conversation", guild=interaction.guild)
        behavior_embed = _build_canvas_behavior_embed(behavior_content, self.admin_visible)
        await _safe_edit_interaction_message(interaction, content=None, embed=behavior_embed, view=behavior_view)
        behavior_view.message = interaction.message

    
    button_help = _personality_descriptions.get("canvas_home_messages", {}).get("button_help", "Help")
    @discord.ui.button(label=button_help, style=discord.ButtonStyle.primary)
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show_section(interaction, "help")

    def update_visibility(self):
        """Hide or disable admin-only controls according to current permissions."""
        if not self.admin_visible:
            for child in self.children:
                if getattr(child, "label", "") == "Setup":
                    child.disabled = True
                    break


class CanvasRolesView(TimeoutResetMixin, SmartBackButtonMixin, HomeButtonMixin, discord.ui.View):
    """Interactive role navigation for enabled roles."""

    def __init__(self, author_id: int, agent_config: dict, admin_visible: bool, sections: dict[str, str], message=None):
        super().__init__(timeout=600)  # 10 minutes
        self.author_id = author_id
        self.agent_config = agent_config
        self.admin_visible = admin_visible
        self.sections = sections
        self.message = message  # Store the message to delete it later
        self._add_role_buttons()
        
        # Start the timeout timer
        self._reset_timeout()

    async def on_timeout(self) -> None:
        """Called when the view times out - delete the entire message."""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if self.message:
                    await self.message.delete()
                self.stop()
                return  # Success, exit the method
            except discord.NotFound:
                # Message already deleted, just stop the view
                self.stop()
                return
            except discord.Forbidden:
                # If we can't delete the message, at least disable the buttons
                for child in self.children:
                    child.disabled = True
                self.stop()
                return
            except Exception as e:
                if attempt == max_attempts - 1:  # Last attempt
                    logger.warning(f"Could not delete Canvas message on timeout after {max_attempts} attempts: {e}")
                    # Fallback: disable buttons
                    for child in self.children:
                        child.disabled = True
                    self.stop()
                else:
                    # Brief delay before retry
                    await asyncio.sleep(0.1)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive Canvas to its original user."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True

    def _add_role_buttons(self):
        """Add a button for each enabled role."""
        button_watcher = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {}).get("button", "Watcher")
        button_trickster = _personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("button", "Trickster")
        button_treasure_hunter = _personality_descriptions.get("roles_view_messages", {}).get("treasure_hunter", {}).get("button", "Hunter")
        button_banker = _personality_descriptions.get("roles_view_messages", {}).get("banker", {}).get("button", "Banker")
        button_mc = _personality_descriptions.get("roles_view_messages", {}).get("mc", {}).get("button", "MC")

        role_labels = {
            "news_watcher": button_watcher,
            "treasure_hunter": button_treasure_hunter,
            "trickster": button_trickster,
            "banker": button_banker,
            "mc": button_mc,
        }
        for role_name in _get_enabled_roles(self.agent_config):
            label = role_labels.get(role_name, role_name.replace("_", " ").title())
            self.add_item(CanvasRoleButton(label=label, role_name=role_name))

        # Add navigation buttons using mixins
        self.add_smart_back_button()
        self.add_home_button()


class CanvasRoleButton(discord.ui.Button):
    """Button that opens one Canvas role view."""

    def __init__(self, label: str, role_name: str):
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRolesView):
            await interaction.response.send_message("❌ Canvas role navigation is not available.", ephemeral=True)
            return

        content = _build_canvas_role_view(
            self.role_name,
            view.agent_config,
            view.admin_visible,
            interaction.guild,
            view.author_id,
        )
        if not content:
            await interaction.response.send_message("❌ This role is not available.", ephemeral=True)
            return

        detail_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=self.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            guild=interaction.guild,
        )
        detail_view.message = interaction.message
        role_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, "overview", None, detail_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=role_embed, view=detail_view)
        # Set the message reference for timeout deletion
        detail_view.message = interaction.message


class CanvasRoleDetailButton(discord.ui.Button):
    """Button that opens one detail view inside a role."""

    def __init__(self, label: str, role_name: str, detail_name: str):
        # Admin buttons should be red, others green
        if "admin" in detail_name.lower():
            button_style = discord.ButtonStyle.danger  # Red for admin
        else:
            button_style = discord.ButtonStyle.success  # Green for others
        super().__init__(label=label, style=button_style)
        self.role_name = role_name
        self.detail_name = detail_name

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRoleDetailView):
            await interaction.response.send_message("❌ Canvas role detail navigation is not available.", ephemeral=True)
            return

        content = _build_canvas_role_detail_view(
            self.role_name,
            self.detail_name,
            view.agent_config,
            view.admin_visible,
            view.guild,
            view.author_id,
        )
        if not content:
            await interaction.response.send_message("❌ This role detail is not available.", ephemeral=True)
            return

        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail=self.detail_name,
            guild=view.guild,
        )
        next_view.message = interaction.message
        detail_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, self.detail_name, None, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


class CanvasTreasureHunterPoe2Button(discord.ui.Button):
    """Button that opens the POE2 items view for Treasure Hunter."""

    def __init__(self, label: str = "POE2", style=discord.ButtonStyle.primary):
        super().__init__(label=label, style=style)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRoleDetailView):
            await interaction.response.send_message("❌ Canvas role detail navigation is not available.", ephemeral=True)
            return

        # Navigate to the items (personal) view
        detail_name = "personal"
        content = _build_canvas_role_detail_view(
            "treasure_hunter",
            detail_name,
            view.agent_config,
            view.admin_visible,
            view.guild,
            view.author_id,
        )
        if not content:
            await interaction.response.send_message("❌ POE2 items view is not available.", ephemeral=True)
            return

        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name="treasure_hunter",
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail=detail_name,
            guild=view.guild,
        )
        next_view.message = interaction.message
        detail_embed = _build_canvas_role_embed("treasure_hunter", content, view.admin_visible, detail_name, None, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


class BankerConfigModal(discord.ui.Modal):
    def __init__(self, action_name: str):
        title = "Banker TAE" if action_name == "config_tae" else "Banker Bonus"
        super().__init__(title=title)
        self.action_name = action_name
        label = "TAE value" if action_name == "config_tae" else "Bonus value"
        placeholder = "0-1000" if action_name == "config_tae" else "0-10000"
        self.value_input = discord.ui.TextInput(label=label, placeholder=placeholder, required=True, max_length=10)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Banker config is only available in a server.", ephemeral=True)
            return
        if not is_admin(interaction):
            await interaction.response.send_message("❌ This banker option is admin-only.", ephemeral=True)
            return
        if get_banker_db_instance is None:
            await interaction.response.send_message("❌ Banker database is not available.", ephemeral=True)
            return
        try:
            amount = int(str(self.value_input.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number.", ephemeral=True)
            return

        if self.action_name == "config_tae":
            if amount < 0 or amount > 1000:
                await interaction.response.send_message("❌ TAE must be between 0 and 1000.", ephemeral=True)
                return
        else:
            if amount < 0 or amount > 10000:
                await interaction.response.send_message("❌ Bonus must be between 0 and 10000.", ephemeral=True)
                return

        try:
            db_banker = get_banker_db_instance(str(interaction.guild.id))
            if self.action_name == "config_tae":
                ok = db_banker.configurar_tae(
                    str(interaction.guild.id),
                    interaction.guild.name,
                    amount,
                    str(interaction.user.id),
                )
                label = "TAE"
            else:
                ok = db_banker.configurar_bono(
                    str(interaction.guild.id),
                    interaction.guild.name,
                    amount,
                    str(interaction.user.id),
                )
                label = "Bonus"
        except Exception as e:
            logger.exception(f"Canvas banker config failed: {e}")
            await interaction.response.send_message("❌ Could not update banker configuration.", ephemeral=True)
            return

        if not ok:
            await interaction.response.send_message("❌ Could not update banker configuration.", ephemeral=True)
            return

        try:
            current_tae = db_banker.obtener_tae(str(interaction.guild.id))
            current_bonus = db_banker.obtener_opening_bonus(str(interaction.guild.id))
        except Exception:
            current_tae = amount if label == "TAE" else "Unknown"
            current_bonus = amount if label == "Bonus" else "Unknown"

        await interaction.response.send_message(
            f"✅ {label} updated to `{amount}`.\nCurrent config: TAE {current_tae}% | opening bonus {current_bonus}",
            ephemeral=True,
        )


class RoleFrequencyModal(discord.ui.Modal):
    def __init__(self, role_name: str, action_name: str, agent_config: dict, view):
        title = "Watcher Frequency" if action_name == "watcher_frequency" else "Hunter Frequency"
        super().__init__(title=title)
        self.role_name = role_name
        self.action_name = action_name
        self.agent_config = agent_config
        self.view = view
        placeholder = "1-24 hours" if action_name == "watcher_frequency" else "1-168 hours"
        self.value_input = discord.ui.TextInput(label="Hours", placeholder=placeholder, required=True, max_length=10)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
            return
        if not is_admin(interaction):
            await interaction.response.send_message("❌ This option is admin-only.", ephemeral=True)
            return
        try:
            hours = int(str(self.value_input.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number of hours.", ephemeral=True)
            return

        applied_text = ""
        if self.action_name == "watcher_frequency":
            if hours < 1 or hours > 24:
                await interaction.response.send_message("❌ Watcher frequency must be between 1 and 24 hours.", ephemeral=True)
                return
            if get_news_watcher_db_instance is None:
                await interaction.response.send_message("❌ Watcher database is not available.", ephemeral=True)
                return
            try:
                db_watcher = get_news_watcher_db_instance(str(interaction.guild.id))
                ok = db_watcher.set_frequency_setting(hours)
            except Exception as e:
                logger.exception(f"Canvas watcher frequency update failed: {e}")
                ok = False
            if not ok:
                await interaction.response.send_message("❌ Could not update watcher frequency.", ephemeral=True)
                return
            current_method = _get_canvas_watcher_method_label(str(interaction.guild.id))
            applied_text = f"Watcher frequency updated to `{hours}` hours.\nCurrent method: {current_method}"
        else:  # hunter_frequency
            if hours < 1 or hours > 168:
                await interaction.response.send_message("❌ Hunter frequency must be between 1 and 168 hours.", ephemeral=True)
                return
            roles_cfg = self.agent_config.setdefault("roles", {})
            hunter_cfg = roles_cfg.setdefault("treasure_hunter", {})
            hunter_cfg["interval_hours"] = hours
            applied_text = f"Hunter frequency updated to `{hours}` hours.\nCurrent admin interval now matches the Canvas setting."

        # Rebuild the Canvas role detail view with updated state
        content = ""  # Action view content is no longer needed
        next_view = CanvasRoleDetailView(
            author_id=self.view.author_id,
            role_name=self.view.role_name,
            agent_config=self.view.agent_config,
            admin_visible=self.view.admin_visible,
            sections=self.view.sections,
            current_detail="admin",
            guild=self.view.guild,
        )
        next_view.auto_response_preview = applied_text
        role_embed = _build_canvas_role_embed(self.role_name, content, self.view.admin_visible, "admin", None, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)


class CommentaryFrequencyModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Commentary Frequency")
        self.view = view
        self.value_input = discord.ui.TextInput(label="Minutes", placeholder="e.g. 180", required=True, max_length=10)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Commentary settings are only available in a server.", ephemeral=True)
            return
        if not is_admin(interaction):
            await interaction.response.send_message("❌ This option is admin-only.", ephemeral=True)
            return
        try:
            minutes = int(str(self.value_input.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number of minutes.", ephemeral=True)
            return
        if minutes < 1:
            await interaction.response.send_message("❌ Minutes must be greater than zero.", ephemeral=True)
            return
        guild_id = int(interaction.guild.id)
        state = _talk_state_by_guild_id.get(guild_id) or {}
        state["interval_minutes"] = minutes
        _talk_state_by_guild_id[guild_id] = state
        if state.get("enabled", False):
            task = state.get("task")
            if task and not task.done():
                task.cancel()
            state["task"] = asyncio.create_task(_start_talk_loop_for_guild(guild_id))
        enabled_text = "On" if state.get("enabled", False) else "Off"
        
        # Rebuild the Canvas behavior view with updated state
        content = _build_canvas_behavior_detail(self.view.current_detail, self.view.admin_visible, self.view.guild)
        next_view = CanvasBehaviorView(
            author_id=self.view.author_id,
            sections=self.view.sections,
            admin_visible=self.view.admin_visible,
            agent_config=self.view.agent_config,
            current_detail=self.view.current_detail,
            guild=self.view.guild,
        )
        next_view.auto_response_preview = f"Mission commentary interval set to `{minutes}` minutes.\nCurrent state: {enabled_text}"
        behavior_embed = _build_canvas_behavior_embed(content or "", self.view.admin_visible, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=behavior_embed, view=next_view)


class Poe2ItemModal(discord.ui.Modal):
    def __init__(self, action_name: str, author_id: int, guild, view):
        title = "Add POE2 Item" if action_name == "poe2_item_add" else "Remove POE2 Item"
        super().__init__(title=title)
        self.action_name = action_name
        self.author_id = author_id
        self.guild = guild
        self.view = view
        label = "Item name" if action_name == "poe2_item_add" else "Item name or item number"
        placeholder = "Ancient Rib" if action_name == "poe2_item_add" else "Ancient Rib or 1"
        self.value_input = discord.ui.TextInput(label=label, placeholder=placeholder, required=True, max_length=120)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        if get_poe2_manager is None:
            await interaction.response.send_message("❌ POE2 manager is not available.", ephemeral=True)
            return
        manager = get_poe2_manager()
        # Use empty string for DM - let manager find active server
        server_id = "" if self.guild is None else str(self.guild.id)
        user_id = str(self.author_id)
        item_value = str(self.value_input.value).strip()
        if not item_value:
            await interaction.response.send_message("❌ Enter a valid POE2 item.", ephemeral=True)
            return
        try:
            if self.action_name == "poe2_item_add":
                ok, message = manager.add_objective(server_id, user_id, item_value)
            else:
                ok, message = manager.remove_objective(server_id, user_id, item_value)
        except Exception as e:
            logger.exception(f"Canvas POE2 item update failed: {e}")
            await interaction.response.send_message("❌ Could not update POE2 items.", ephemeral=True)
            return
        if not ok:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return
        try:
            league = manager.get_user_league(user_id, server_id)
            list_ok, raw = manager.list_objectives(server_id, user_id)
            if list_ok and raw:
                visible_lines = [line.strip() for line in raw.splitlines() if line.strip() and line.strip()[0].isdigit()]
            else:
                visible_lines = []
        except Exception:
            league = "Unknown"
            visible_lines = []
        summary = "\n".join([f"- {line}" for line in visible_lines[:5]]) if visible_lines else "- No tracked items yet"
        content = _build_canvas_role_detail_view(
            "treasure_hunter",
            "personal",
            self.view.agent_config,
            self.view.admin_visible,
            self.view.guild,
            self.view.author_id,
        )
        next_view = CanvasRoleDetailView(
            author_id=self.view.author_id,
            role_name=self.view.role_name,
            agent_config=self.view.agent_config,
            admin_visible=self.view.admin_visible,
            sections=self.view.sections,
            current_detail="personal",
            guild=self.view.guild,
            message=interaction.message,
        )
        next_view.auto_response_preview = f"✅ {message}"
        detail_embed = _build_canvas_role_embed(
            "treasure_hunter",
            content or "",
            self.view.admin_visible,
            "personal",
            None,
            next_view.auto_response_preview,
        )
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


class TabooKeywordModal(discord.ui.Modal):
    def __init__(self, action_name: str, guild_id: int, view):
        super().__init__(title="Taboo Keyword")
        self.action_name = action_name
        self.guild_id = guild_id
        self.view = view
        self.value_input = discord.ui.TextInput(label="Keyword", placeholder="forbidden word", required=True, max_length=80)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        keyword = str(self.value_input.value).strip().lower()
        if not keyword:
            await interaction.response.send_message("❌ Enter a valid keyword.", ephemeral=True)
            return
        
        # Get current keywords from database
        state = get_taboo_state(self.guild_id)
        current_keywords = state.get("keywords", [])
        
        applied_text = ""
        success = False
        
        if self.action_name == "taboo_add":
            if keyword not in current_keywords:
                if update_taboo_state(self.guild_id, keywords=current_keywords + [keyword]):
                    applied_text = f"Added taboo keyword `{keyword}`."
                    success = True
                else:
                    applied_text = f"Failed to add keyword `{keyword}`. Check logs for details."
            else:
                applied_text = f"Keyword `{keyword}` was already in the list."
                success = True
        else:  # taboo_del
            if keyword in current_keywords:
                new_keywords = [kw for kw in current_keywords if kw != keyword]
                if update_taboo_state(self.guild_id, keywords=new_keywords):
                    applied_text = f"Removed taboo keyword `{keyword}`."
                    success = True
                else:
                    applied_text = f"Failed to remove keyword `{keyword}`. Check logs for details."
            else:
                applied_text = f"Keyword `{keyword}` was not in the list."
                success = True
        
        # Rebuild the Canvas behavior view with updated state
        content = _build_canvas_behavior_detail(self.view.current_detail, self.view.admin_visible, self.view.guild, self.view.agent_config)
        next_view = CanvasBehaviorView(
            author_id=self.view.author_id,
            sections=self.view.sections,
            admin_visible=self.view.admin_visible,
            agent_config=self.view.agent_config,
            current_detail=self.view.current_detail,
            guild=self.view.guild,
        )
        next_view.auto_response_preview = applied_text
        behavior_embed = _build_canvas_behavior_embed(content or "", self.view.admin_visible, next_view.auto_response_preview)
        
        if success:
            await interaction.response.edit_message(content=None, embed=behavior_embed, view=next_view)
        else:
            await interaction.response.send_message(applied_text, ephemeral=True)


class RoleControlModal(discord.ui.Modal):
    """Modal for role control with role selection and on/off toggle."""
    
    def __init__(self, view: "CanvasBehaviorView"):
        super().__init__(title="Role Control", timeout=300)
        self.view = view
        
        # Role selection dropdown
        self.role_input = discord.ui.TextInput(
            label="Role Name",
            placeholder="Enter role name: news_watcher, treasure_hunter, trickster, banker",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        self.add_item(self.role_input)
        
        # On/Off toggle
        self.state_input = discord.ui.TextInput(
            label="State (on/off)",
            placeholder="Enter 'on' to enable or 'off' to disable",
            style=discord.TextStyle.short,
            required=True,
            max_length=10
        )
        self.add_item(self.state_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if not interaction.guild or not self.view.admin_visible:
                await interaction.response.send_message("❌ This role option is admin-only.", ephemeral=True)
                return
                
            role_name = self.role_input.value.strip().lower()
            state = self.state_input.value.strip().lower()
            
            # Validate role name
            valid_roles = ["news_watcher", "treasure_hunter", "trickster", "banker"]
            if role_name not in valid_roles:
                await interaction.response.send_message("❌ Invalid role. Valid roles: news_watcher, treasure_hunter, trickster, banker", ephemeral=True)
                return
            
            # Validate state
            if state not in ["on", "off", "enable", "disable", "true", "false", "1", "0"]:
                await interaction.response.send_message("❌ Invalid state. Use: on/off, enable/disable, true/false, 1/0", ephemeral=True)
                return
            
            # Convert state to boolean
            enabled = state in ["on", "enable", "true", "1"]
            
            # Import role toggle function and agent config
            from discord_bot.discord_core_commands import _cmd_role_toggle, AGENT_CFG
            
            # Create mock context for the role toggle function
            class MockContext:
                def __init__(self, interaction, enabled_state):
                    self.guild = interaction.guild
                    self.author = interaction.user
                    self.enabled_state = enabled_state
                
                async def send(self, content):
                    # This will be handled by the modal response
                    pass
            
            # Execute role toggle
            mock_ctx = MockContext(interaction, enabled)
            await _cmd_role_toggle(mock_ctx, role_name, enabled)
            
            # Build success message
            result_msg = f"✅ Role '{role_name}' {'enabled' if enabled else 'disabled'} for this server."
            
            # Update the view
            content = _build_canvas_behavior_detail(self.view.current_detail, self.view.admin_visible, self.view.guild, self.view.agent_config)
            self.view.auto_response_preview = result_msg
            behavior_embed = _build_canvas_behavior_embed(content or "", self.view.admin_visible, self.view.auto_response_preview)
            await interaction.response.edit_message(content=None, embed=behavior_embed, view=self.view)
            
        except Exception as e:
            logger.exception(f"Error in role control modal: {e}")
            await interaction.response.send_message("❌ Error processing role control. Please try again.", ephemeral=True)


class TricksterActionModal(discord.ui.Modal):
    def __init__(self, action_name: str, author_id: int, guild, admin_visible: bool):
        titles = {
            "dice_fixed_bet": "Dice Fixed Bet",
            "dice_pot_value": "Dice Pot Value",
            "ring_frequency": "Ring Frequency",
            "beggar_frequency": "Beggar Frequency",
            "beggar_donate": "Beggar Donation",
            "ring_accuse": "Accuse User",
        }
        super().__init__(title=titles.get(action_name, "Trickster Action"))
        self.action_name = action_name
        self.author_id = author_id
        self.guild = guild
        self.admin_visible = admin_visible
        label_map = {
            "dice_fixed_bet": "Gold amount",
            "dice_pot_value": "New pot balance",
            "ring_frequency": "Hours",
            "beggar_frequency": "Hours",
            "beggar_donate": "Gold amount",
            "ring_accuse": "User mention, id, or name",
        }
        placeholder_map = {
            "dice_fixed_bet": "15",
            "dice_pot_value": "500",
            "ring_frequency": "24",
            "beggar_frequency": "6",
            "beggar_donate": "25",
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
        await _handle_canvas_trickster_modal_submit(interaction, self.action_name, str(self.value_input.value).strip(), self.guild, self.author_id, self.admin_visible)


async def _handle_canvas_trickster_modal_submit(interaction: discord.Interaction, action_name: str, raw_value: str, guild, author_id: int, admin_visible: bool) -> None:
    server_key = get_server_key(guild)
    server_id = str(guild.id)
    server_name = guild.name

    # Build canvas sections for navigation
    from discord_bot.agent_discord import AGENT_CFG
    sections = _build_canvas_sections(
        AGENT_CFG,
        "greetputre",
        "nogreetputre", 
        "welcomeputre",
        "nowelcomeputre",
        "roleputre",
        "talkputre",
        admin_visible,
        server_name,
        author_id
    )

    if action_name == "ring_accuse":
        try:
            ring_state = _get_ring_state(server_id)
            if not ring_state.get("enabled", False):
                await interaction.response.send_message("❌ Ring is not enabled on this server.", ephemeral=True)
                return

            raw_target = raw_value.strip()
            mentioned_user = None
            if guild is not None:
                # Try mention/ID format first
                cleaned = raw_target.replace("<@", "").replace("!", "").replace(">", "").strip()
                if cleaned.isdigit():
                    mentioned_user = guild.get_member(int(cleaned))
                
                # If mention/ID lookup failed, try name matching
                if mentioned_user is None:
                    lowered = raw_target.lower()
                    for member in getattr(guild, "members", []) or []:
                        if getattr(member, "bot", False) or member.id == interaction.user.id:
                            continue
                        names = {member.name.lower(), member.display_name.lower()}
                        if lowered in names:
                            mentioned_user = member
                            break
                
                # If still not found, try fetching by ID using fetch_user for offline members
                if mentioned_user is None and cleaned.isdigit():
                    try:
                        mentioned_user = await interaction.client.fetch_user(int(cleaned))
                    except:
                        pass
                
                # Final fallback: try partial name matching
                if mentioned_user is None:
                    lowered = raw_target.lower()
                    for member in getattr(guild, "members", []) or []:
                        if getattr(member, "bot", False) or member.id == interaction.user.id:
                            continue
                        names = {member.name.lower(), member.display_name.lower()}
                        # Check if any name contains the search term
                        if any(lowered in name for name in names):
                            mentioned_user = member
                            break
            if mentioned_user is None:
                await interaction.response.send_message("❌ Enter a valid user mention, id, or visible name.", ephemeral=True)
                return
            
            # Update the target in state (no immediate accusation)
            target_name = mentioned_user.display_name if hasattr(mentioned_user, 'display_name') else mentioned_user.name
            state["target_user_id"] = str(mentioned_user.id)
            state["target_user_name"] = target_name
            
            # Log the target change
            db_instance = AgentDatabase(server_name=server_name)
            await asyncio.to_thread(
                db_instance.registrar_interaccion,
                interaction.user.id,
                interaction.user.name,
                "RING_TARGET_CHANGE",
                f"Changed ring target to {target_name}",
                interaction.channel.id if interaction.channel else None,
                guild.id,
                {"target_user_id": mentioned_user.id, "target_user_name": target_name},
            )
            
            # Rebuild the view with updated target
            content = _build_canvas_role_trickster_detail("ring", admin_visible, guild, author_id)
            next_view = CanvasRoleDetailView(
                author_id=author_id,
                role_name="trickster",
                agent_config=AGENT_CFG,  # Use actual agent config
                admin_visible=admin_visible,
                sections=sections,  # ← Use the built sections
                current_detail="ring",
                guild=guild,
                message=interaction.message
            )
            next_view.auto_response_preview = f"New target: {target_name}\nThe next investigation will focus on this user."
            role_embed = _build_canvas_role_embed("trickster", content or "", admin_visible, "ring", None, next_view.auto_response_preview)
            await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)
        except Exception as e:
            logger.exception(f"Canvas ring accuse failed: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Could not submit accusation.", ephemeral=True)
            else:
                try:
                    await interaction.followup.send("❌ Could not submit accusation.", ephemeral=True)
                except discord.NotFound:
                    # Interaction expired, nothing we can do
                    logger.warning("Canvas ring accuse interaction expired - unable to send error followup")
                except Exception as followup_e:
                    logger.exception(f"Failed to send canvas ring accuse error followup: {followup_e}")
        return

    if action_name == "beggar_donate":
        if get_banker_db_instance is None or get_beggar_db_instance is None:
            await interaction.response.send_message("❌ Beggar donation systems are not available.", ephemeral=True)
            return
        try:
            amount = int(raw_value)
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid gold amount.", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("❌ Donation amount must be positive.", ephemeral=True)
            return
        db_banker = get_banker_db_instance(server_key)
        db_beggar = get_beggar_db_instance(server_key)
        donor_id = str(author_id)
        donor_name = interaction.user.display_name
        db_banker.create_wallet(donor_id, donor_name, server_id, server_name)
        db_banker.create_wallet("beggar_fund", "Beggar Fund", server_id, server_name)
        current_balance = db_banker.get_balance(donor_id, server_id)
        if current_balance < amount:
            await interaction.response.send_message(f"❌ You only have {current_balance:,} gold available.", ephemeral=True)
            return
        reason = db_beggar.get_last_reason(server_id) or "the current clan project"
        target_gold = db_beggar.get_target_gold(server_id)
        db_banker.update_balance(donor_id, donor_name, server_id, server_name, -amount, "BEGGAR_DONATION_OUT", "Donation sent to beggar")
        db_banker.update_balance("beggar_fund", "Beggar Fund", server_id, server_name, amount, "BEGGAR_DONATION_IN", f"Donation received from {donor_name}")
        fund_balance = db_banker.get_balance("beggar_fund", server_id)
        await interaction.response.send_message(
            f"✅ Donation accepted: {amount:,} gold.\n🪙 Fund: {fund_balance:,}\n🎯 Target: {target_gold:,}\n📣 Reason: {reason}",
            ephemeral=True,
        )
        return

    if not admin_visible or not is_admin(interaction):
        await interaction.response.send_message("❌ This trickster option is admin-only.", ephemeral=True)
        return

    if action_name in {"ring_frequency", "beggar_frequency"}:
        try:
            hours = int(raw_value)
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number of hours.", ephemeral=True)
            return
        if hours < 1 or hours > 168:
            await interaction.response.send_message("❌ Frequency must be between 1 and 168 hours.", ephemeral=True)
            return
        try:
            if action_name == "ring_frequency":
                from roles.trickster.subroles.ring.ring_discord import _get_ring_state
                state = _get_ring_state(server_id)
                state["frequency_hours"] = hours
                message = (
                    f"✅ Ring frequency updated to `{hours}` hours.\n"
                    f"Current state: {'On' if state.get('enabled', False) else 'Off'}"
                )
            else:
                db_beggar = get_beggar_db_instance(server_key)
                ok = db_beggar.set_frequency_hours(server_id, hours)
                if not ok:
                    raise RuntimeError("Could not update beggar frequency")
                target_gold = db_beggar.get_target_gold(server_id)
                message = (
                    f"✅ Beggar frequency updated to `{hours}` hours.\n"
                    f"Current target: {target_gold:,} gold"
                )
        except Exception as e:
            logger.exception(f"Canvas trickster frequency update failed: {e}")
            await interaction.response.send_message("❌ Could not update frequency.", ephemeral=True)
            return
        await interaction.response.send_message(message, ephemeral=True)
        return

    if action_name in {"dice_fixed_bet", "dice_pot_value"}:
        if get_dice_game_db_instance is None or get_banker_db_instance is None:
            await interaction.response.send_message("❌ Dice game systems are not available.", ephemeral=True)
            return
        try:
            amount = int(raw_value)
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid gold amount.", ephemeral=True)
            return
        if amount < 0:
            await interaction.response.send_message("❌ Amount must be zero or greater.", ephemeral=True)
            return
        try:
            if action_name == "dice_fixed_bet":
                if amount < 1 or amount > 1000:
                    await interaction.response.send_message("❌ Fixed bet must be between 1 and 1000 gold.", ephemeral=True)
                    return
                db_dice_game = get_dice_game_db_instance(server_key)
                ok = db_dice_game.configure_server(server_id, fixed_bet=amount)
                if not ok:
                    raise RuntimeError("Could not update fixed bet")
                state = _get_canvas_dice_state(guild)
                message = (
                    f"✅ Dice fixed bet updated to `{amount}` gold.\n"
                    f"Current pot: {state['pot_balance']:,} gold"
                )
            else:
                db_banker = get_banker_db_instance(server_key)
                db_banker.create_wallet("dice_game_pot", "Dice Game Pot", server_id, server_name)
                current_balance = db_banker.get_balance("dice_game_pot", server_id)
                delta = amount - current_balance
                ok = db_banker.update_balance("dice_game_pot", "Dice Game Pot", server_id, server_name, delta, "DICE_POT_ADMIN_SET", "Canvas pot update", str(interaction.user.id), interaction.user.display_name)
                if not ok:
                    raise RuntimeError("Could not update pot balance")
                state = _get_canvas_dice_state(guild)
                message = (
                    f"✅ Dice pot balance updated to `{amount}` gold.\n"
                    f"Current fixed bet: {state['bet']:,} gold"
                )
        except Exception as e:
            logger.exception(f"Canvas trickster dice update failed: {e}")
            await interaction.response.send_message("❌ Could not update dice settings.", ephemeral=True)
            return
        await interaction.response.send_message(message, ephemeral=True)
        return


async def _handle_canvas_watcher_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    if get_news_watcher_db_instance is None:
        await interaction.response.send_message("❌ Watcher database is not available.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)

    # Handle method selection
    if action_name in {"method_flat", "method_keyword", "method_general"}:
        method_name = action_name.replace("method_", "")
        try:
            db_watcher = get_news_watcher_db_instance(guild_id)
            ok = db_watcher.set_method_config(guild_id, method_name)
        except Exception as e:
            logger.exception(f"Canvas watcher method update failed: {e}")
            ok = False
        if not ok:
            await interaction.response.send_message("❌ Could not update watcher method.", ephemeral=True)
            return

        view.watcher_selected_method = method_name
        view.watcher_last_action = None
        current_detail = "admin" if view.current_detail == "admin" else "personal"
        content = _build_canvas_role_news_watcher_detail(
            current_detail,
            view.admin_visible,
            view.guild,
            view.author_id,
            selected_method=view.watcher_selected_method,
            last_action=view.watcher_last_action,
        )
        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail=current_detail,
            guild=view.guild,
            watcher_selected_method=view.watcher_selected_method,
            watcher_last_action=view.watcher_last_action,
        )
        next_view.message = interaction.message
        next_view.auto_response_preview = f"Method set to `{method_name}`."
        action_embed = _build_canvas_role_embed("news_watcher", content or "", view.admin_visible, current_detail, None, next_view.auto_response_preview)
        try:
            await interaction.response.edit_message(content=None, embed=action_embed, view=next_view)
        except discord.InteractionResponded:
            # If interaction was already responded to, use followup
            await interaction.followup.edit_message(interaction.message.id, embed=action_embed, view=next_view)
        except discord.NotFound:
            # Message was deleted, send a new one
            try:
                await interaction.followup.send(embed=action_embed, view=next_view, ephemeral=True)
            except discord.NotFound:
                # Interaction completely expired, nothing we can do
                logger.warning("Canvas watcher interaction expired completely - unable to send followup")
            except Exception as e:
                logger.exception(f"Failed to send canvas watcher followup: {e}")
        except Exception as e:
            logger.exception(f"Failed to edit canvas watcher message: {e}")
            try:
                await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
            except discord.NotFound:
                # Interaction expired, nothing we can do
                logger.warning("Canvas watcher interaction expired during error handling")
            except Exception as followup_e:
                logger.exception(f"Failed to send error followup: {followup_e}")
        return

    # Handle subscription actions
    if action_name == "subscribe_categories":
        # Show subscription modal
        await interaction.response.send_modal(CanvasWatcherSubscribeModal(action_name, view, interaction.client))
        return

    # Handle list actions
    if action_name in {"list_keywords", "list_premises"}:
        list_type = action_name.replace("list_", "")
        
        # Show list modal
        await interaction.response.send_modal(CanvasWatcherListModal(list_type, view, interaction.client))
        return

    if action_name == "channel_subscribe_categories":
        await interaction.response.send_modal(CanvasWatcherChannelSubscribeModal(action_name, view, interaction.client))
        return

    if action_name == "channel_unsubscribe":
        await interaction.response.send_modal(CanvasWatcherChannelUnsubscribeModal(view, interaction.client))
        return

    if action_name == "channel_subscribe_category":
        await interaction.response.send_modal(CanvasWatcherChannelSubscribeModal(action_name, view, interaction.client))
        return

    if action_name == "channel_unsubscribe_category":
        await interaction.response.send_modal(CanvasWatcherChannelUnsubscribeModal(view, interaction.client))
        return

    if action_name == "delete_premise":
        await interaction.response.send_modal(CanvasWatcherDeleteModal("delete_premises", view, interaction.client))
        return

    if action_name == "add_premise":
        await interaction.response.send_modal(CanvasWatcherAddModal("add_premises", view, interaction.client))
        return

    if action_name == "add_keywords":
        await interaction.response.send_modal(CanvasWatcherAddModal("add_keywords", view, interaction.client))
        return

    if action_name == "delete_keywords":
        await interaction.response.send_modal(CanvasWatcherDeleteModal("delete_keywords", view, interaction.client))
        return

    if action_name == "channel_view_subscriptions":
        view.watcher_last_action = action_name
        content = _build_canvas_role_news_watcher_detail(
            "admin",
            view.admin_visible,
            view.guild,
            view.author_id,
            selected_method=view.watcher_selected_method,
            last_action=view.watcher_last_action,
        )
        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail="admin",
            guild=view.guild,
            watcher_selected_method=view.watcher_selected_method,
            watcher_last_action=view.watcher_last_action,
        )
        next_view.message = interaction.message
        action_embed = _build_canvas_role_embed("news_watcher", content or "", view.admin_visible, "admin", None)
        try:
            await interaction.response.edit_message(content=None, embed=action_embed, view=next_view)
        except discord.InteractionResponded:
            # If interaction was already responded to, use followup
            await interaction.followup.edit_message(interaction.message.id, embed=action_embed, view=next_view)
        except discord.NotFound:
            # Message was deleted, send a new one
            try:
                await interaction.followup.send(embed=action_embed, view=next_view, ephemeral=True)
            except discord.NotFound:
                # Interaction completely expired, nothing we can do
                logger.warning("Canvas watcher interaction expired completely - unable to send followup")
            except Exception as e:
                logger.exception(f"Failed to send canvas watcher followup: {e}")
        except Exception as e:
            logger.exception(f"Failed to edit canvas watcher message: {e}")
            try:
                await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
            except discord.NotFound:
                # Interaction expired, nothing we can do
                logger.warning("Canvas watcher interaction expired during error handling")
            except Exception as followup_e:
                logger.exception(f"Failed to send error followup: {followup_e}")
        return

    # Handle admin actions
    if action_name == "watcher_frequency":
        await interaction.response.send_modal(CanvasWatcherFrequencyModal(view, interaction.client))
        return

    if action_name == "watcher_run_now":
        try:
            from roles.news_watcher.news_watcher import process_channel_subscriptions
            from roles.news_watcher.global_news_db import get_global_news_db
            from discord_bot.discord_http import DiscordHTTP
            from agent_engine import get_discord_token

            if not view.guild:
                await interaction.response.send_message("❌ Guild context is required to run watcher now.", ephemeral=True)
                return
            db_watcher = get_news_watcher_db_instance(guild_id)
            http = DiscordHTTP(get_discord_token())
            global_db = get_global_news_db()
            server_name = str(view.guild.id)
            await process_channel_subscriptions(http, db_watcher, global_db, server_name)
        except Exception as e:
            logger.exception(f"Canvas force watcher failed: {e}")
            await interaction.response.send_message("❌ Could not run watcher now.", ephemeral=True)
            return

        current_detail = "admin" if view.current_detail == "admin" else "personal"
        view.watcher_last_action = action_name
        content = _build_canvas_role_news_watcher_detail(
            current_detail,
            view.admin_visible,
            view.guild,
            view.author_id,
            selected_method=view.watcher_selected_method,
            last_action=view.watcher_last_action,
        )
        next_view = CanvasRoleDetailView(
            view.author_id,
            view.role_name,
            view.agent_config,
            view.admin_visible,
            view.sections,
            current_detail=current_detail,
            guild=view.guild,
            watcher_selected_method=view.watcher_selected_method,
            watcher_last_action=view.watcher_last_action,
        )
        next_view.message = interaction.message
        embed = _build_canvas_role_embed("news_watcher", content or "", view.admin_visible, current_detail, None, next_view.auto_response_preview)
        try:
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        except discord.InteractionResponded:
            # If interaction was already responded to, use followup
            try:
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=next_view)
            except (discord.NotFound, discord.HTTPException) as e:
                logger.warning(f"Failed to edit message via followup for watcher_run_now: {e}")
                return  # Silently fail - user can try again
        except (discord.NotFound, discord.HTTPException) as e:
            # Message was deleted or interaction expired
            logger.warning(f"Interaction not found for watcher_run_now: {e}")
            return  # Silently fail - user can try again
        except Exception as e:
            logger.exception(f"Unexpected error in canvas watcher_run_now interaction: {e}")
            return  # Silently fail - user can try again
        return

    if action_name == "watcher_run_personal":
        try:
            from roles.news_watcher.news_watcher import process_subscriptions
            from roles.news_watcher.global_news_db import get_global_news_db
            from discord_bot.discord_http import DiscordHTTP
            from agent_engine import get_discord_token

            if not view.guild:
                await interaction.response.send_message("❌ Guild context is required to run personal subscriptions.", ephemeral=True)
                return
            http = DiscordHTTP(get_discord_token())
            global_db = get_global_news_db()
            server_name = str(view.guild.id)
            await process_subscriptions(http, server_name)
        except Exception as e:
            logger.exception(f"Canvas force personal subscriptions failed: {e}")
            await interaction.response.send_message("❌ Could not run personal subscriptions now.", ephemeral=True)
            return

        current_detail = "admin" if view.current_detail == "admin" else "personal"
        view.watcher_last_action = action_name
        content = _build_canvas_role_news_watcher_detail(
            current_detail,
            view.admin_visible,
            view.guild,
            view.author_id,
            selected_method=view.watcher_selected_method,
            last_action=view.watcher_last_action,
        )
        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail=current_detail,
            guild=view.guild,
            watcher_selected_method=view.watcher_selected_method,
            watcher_last_action=view.watcher_last_action,
        )
        next_view.message = interaction.message
        embed = _build_canvas_role_embed("news_watcher", content or "", view.admin_visible, current_detail, None, next_view.auto_response_preview)
        try:
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        except discord.InteractionResponded:
            # If interaction was already responded to, use followup
            try:
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=next_view)
            except (discord.NotFound, discord.HTTPException) as e:
                logger.warning(f"Failed to edit message via followup for watcher_run_personal: {e}")
                return  # Silently fail - user can try again
        except (discord.NotFound, discord.HTTPException) as e:
            # Message was deleted or interaction expired
            logger.warning(f"Interaction not found for watcher_run_personal: {e}")
            return  # Silently fail - user can try again
        except Exception as e:
            logger.exception(f"Unexpected error in canvas watcher_run_personal interaction: {e}")
            return  # Silently fail - user can try again
        return
    await interaction.response.send_message("❌ Unknown watcher action.", ephemeral=True)


async def _handle_canvas_trickster_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    try:
        server_key = get_server_key(interaction.guild)
        server_id = str(interaction.guild.id)
        if action_name in {"announcements_on", "announcements_off"}:
            if get_dice_game_db_instance is None:
                await interaction.response.send_message("❌ Dice game database is not available.", ephemeral=True)
                return
            db_dice_game = get_dice_game_db_instance(server_key)
            enabled = action_name == "announcements_on"
            ok = db_dice_game.configure_server(server_id, announcements_active=enabled)
            current_detail = "dice_admin"
            applied_text = f"Dice announcements {'enabled' if enabled else 'disabled'}."
        elif action_name in {"ring_on", "ring_off"}:
            from roles.trickster.subroles.ring.ring_discord import _get_ring_state
            state = _get_ring_state(server_id)
            state["enabled"] = action_name == "ring_on"
            ok = True
            current_detail = "ring_admin"
            applied_text = f"Ring {'enabled' if state['enabled'] else 'disabled'}."
        elif action_name in {"beggar_on", "beggar_off"}:
            if get_beggar_db_instance is None:
                await interaction.response.send_message("❌ Beggar database is not available.", ephemeral=True)
                return
            db_beggar = get_beggar_db_instance(server_key)
            server_user_id = f"server_{server_id}"
            if action_name == "beggar_on":
                ok = db_beggar.add_subscription(server_user_id, interaction.guild.name, server_id)
            else:
                ok = db_beggar.remove_subscription(server_user_id, server_id)
            current_detail = "beggar_admin"
            applied_text = f"Beggar {'enabled' if action_name == 'beggar_on' else 'disabled'}."
        else:
            await interaction.response.send_message("❌ Unknown trickster action.", ephemeral=True)
            return
    except Exception as e:
        logger.exception(f"Canvas trickster action failed: {e}")
        ok = False

    if not ok:
        await interaction.response.send_message("❌ Could not update trickster settings.", ephemeral=True)
        return

    # Generate updated content for the current detail view
    from discord_bot.canvas.canvas_trickster import _get_canvas_trickster_detail_content
    content = _get_canvas_trickster_detail_content(current_detail, interaction.guild, view.admin_visible)
    
    next_view = CanvasRoleDetailView(
        author_id=view.author_id,
        role_name=view.role_name,
        agent_config=view.agent_config,
        admin_visible=view.admin_visible,
        sections=view.sections,
        current_detail=current_detail,
        guild=view.guild,
    )
    next_view.auto_response_preview = applied_text
    action_embed = _build_canvas_role_embed("trickster", content or "", view.admin_visible, current_detail, None, next_view.auto_response_preview)
    try:
        await interaction.response.edit_message(content=None, embed=action_embed, view=next_view)
    except discord.InteractionResponded:
        # If interaction was already responded to, use followup
        await interaction.followup.edit_message(interaction.message.id, embed=action_embed, view=next_view)
    except discord.NotFound:
        # Message was deleted, send a new one
        try:
            await interaction.followup.send(embed=action_embed, view=next_view, ephemeral=True)
        except discord.NotFound:
            # Interaction completely expired, nothing we can do
            logger.warning("Canvas trickster interaction expired completely - unable to send followup")
        except Exception as e:
            logger.exception(f"Failed to send canvas trickster followup: {e}")
    except Exception as e:
        logger.exception(f"Failed to edit canvas trickster message: {e}")
        try:
            await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
        except discord.NotFound:
            # Interaction expired, nothing we can do
            logger.warning("Canvas trickster interaction expired during error handling")
        except Exception as followup_e:
            logger.exception(f"Failed to send error followup: {followup_e}")


async def _get_default_guild_for_dm(interaction: discord.Interaction, messages_source: dict = None) -> tuple[discord.Guild | None, list[str]]:
    """Get default guild for DM interactions with error handling.
    
    Args:
        interaction: Discord interaction
        messages_source: Dictionary containing DM messages (optional)
        
    Returns:
        Tuple of (guild, content_parts) where content_parts may contain DM notification messages
    """
    guild = interaction.guild
    content_parts = []
    
    if not guild:
        # Get messages from descriptions.json or use defaults
        if messages_source is None:
            messages_source = _personality_descriptions.get("canvas_home_messages", {})
        
        # Get the first available guild as default
        try:
            bot = interaction.client
            if bot and bot.guilds:
                guild = bot.guilds[0]  # Use first guild as default
                logger.info(f"Using default server '{guild.name}' for Canvas action from DM")
                
                # Add DM notification
                content_parts.extend([
                    messages_source.get("dm_default_server_title", "🔔 **Using default server: {server_name}**").format(server_name=guild.name),
                    messages_source.get("dm_default_server_message", "*You're navigating from DM, using the first available server.*"),
                    messages_source.get("dm_default_server_separator", "─────────────────────────────────────────────"),
                    ""
                ])
            else:
                error_msg = messages_source.get("dm_no_servers_available", "❌ No servers available. Please execute actions from a server.")
                await interaction.response.send_message(error_msg, ephemeral=True)
                return None, []
        except Exception as e:
            logger.error(f"Could not get default server for DM Canvas action: {e}")
            error_msg = messages_source.get("dm_server_access_error", "❌ Could not access a server. Please execute actions from a server.")
            await interaction.response.send_message(error_msg, ephemeral=True)
            return None, []
    
    return guild, content_parts


async def _handle_canvas_dice_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    """Handle dice game actions with dynamic content display."""
    if get_dice_game_db_instance is None or get_banker_db_instance is None or DiceGame is None:
        await interaction.response.send_message("❌ Dice game systems are not available.", ephemeral=True)
        return

    # Handle DM case by using default server
    messages_source = _personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("dice_game", {})
    guild, dm_notification_parts = await _get_default_guild_for_dm(interaction, messages_source)
    if guild is None:
        return  # Error already handled by utility function

    server_key = get_server_key(guild)
    server_id = str(guild.id)
    server_name = guild.name
    
    # Get current dice state and personality messages
    dice_state = _get_canvas_dice_state(guild)
    answers = _personality_answers.get("dice_game_messages", {})
    descriptions = _personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("dice_game", {})
    
    # Build the base content with personality title and pot balance
    title = descriptions.get("current_pot_title", "🎲 **DICE GAME** 🎲")
    pot_title = descriptions.get("current_balance", "💎 **CURRENT POT:**")
    fixed_bet = descriptions.get("fixed_bet", "💎 **FIXED BET:**")
    content_parts = [
        title,
        "─" * 45,
        ""
    ]
    
    # Add DM notification if using default server
    if dm_notification_parts:
        content_parts.extend(dm_notification_parts)
    
    # Handle different actions
    if action_name == "dice_play":
        # Execute a dice play
        try:
            db_dice = get_dice_game_db_instance(server_key)
            db_banker = get_banker_db_instance(server_key)
            
            # Get or create player wallet
            player_id = str(interaction.user.id)
            player_name = interaction.user.display_name
            db_banker.create_wallet(player_id, player_name, server_id, server_name)
            db_banker.create_wallet("dice_game_pot", "Dice Game Pot", server_id, server_name)
            
            # Check balance
            player_balance = db_banker.get_balance(player_id, server_id)
            bet_amount = dice_state.get("bet", 1)  # Default to 1 if not set
            
            if player_balance < bet_amount:
                insufficient_msg = answers.get("insufficient_balance", "❌ Insufficient balance!")
                content_parts.extend([
                    #"**🎲 DICE PLAY RESULT**",
                    insufficient_msg.format(bet=bet_amount, balance=player_balance),
                    "",
                    f"Your balance: {player_balance:,} gold",
                    f"Required: {bet_amount:,} gold",
                ])
            else:
                result = process_play(player_id, player_name, server_id, server_name, dice_state['pot_balance']) if process_play else {"success": False, "message": "Dice game unavailable."}
                
                if result.get('success', False):
                    # Parse result
                    dice_str = result.get("dice", "")
                    combination = result.get("combination", "")
                    prize = result.get("prize", 0)
                    new_pot_balance = result.get("pot_after", dice_state['pot_balance'])
                    
                    # Format dice roll
                    dice_values = dice_str.split('-') if dice_str else []
                    dice_display = " ".join([f"🎲{d}" for d in dice_values])
                    roll_title = descriptions.get("roll_title", "🎲 **YOUR ROLL:**")
                    result_title = descriptions.get("combination_title", "📊 **RESULT:**")
                    prize_title = descriptions.get("prize_title", "💰 **PRIZE:**")
                    content_parts.extend([
                        #"**🎲 DICE PLAY RESULT**",
                        f"{roll_title}\n **{dice_display}**",
                        f"{result_title} **{combination}**",
                        "",
                    ])
                    if prize == dice_state['pot_balance']:
                        pot_winner_msg = answers.get("pot_won", "🎉 **POT WINNER!!!**")
                        content_parts.append(f"{prize_title} **{prize:,}** :coin:")
                        content_parts.append(f"\n{pot_winner_msg}\n")
                    elif prize > 0:
                        winner_msg = answers.get("winner", "🎉 **WINNER!!!**")
                        content_parts.append(f"{prize_title} **{prize:,}** :coin:")
                        content_parts.append(f"\n{winner_msg}\n")
                    else:
                        loser_msg = answers.get("loser", "😢 **LOSER!**")
                        content_parts.append(f"{prize_title} **{prize:,}** :coin:")
                        content_parts.append(f"\n{loser_msg}\n")
                    
                    # Get updated balances for display with +/- indicators
                    old_player_balance = player_balance
                    new_player_balance = db_banker.get_balance(player_id, server_id)
                    player_diff = new_player_balance - old_player_balance
                    
                    # Format player balance with +/- indicator
                    if player_diff > 0:
                        player_balance_line = f"Tu zako: {new_player_balance:,} +{player_diff:,} :coin:"
                    elif player_diff < 0:
                        player_balance_line = f"Tu zako: {new_player_balance:,} {player_diff:,} :coin:"
                    else:
                        player_balance_line = f"Tu zako: {new_player_balance:,} :coin:"
                    
                    # Calculate pot difference and format
                    old_pot_balance = dice_state['pot_balance']
                    pot_diff = new_pot_balance - old_pot_balance
                    if pot_diff > 0:
                        pot_balance_line = f"{pot_title} {new_pot_balance:,} +{pot_diff:,} :coin:"
                    elif pot_diff < 0:
                        pot_balance_line = f"{pot_title} {new_pot_balance:,} {pot_diff:,} :coin:"
                    else:
                        pot_balance_line = f"{pot_title} {new_pot_balance:,} :coin:"
                    
                    content_parts.extend([
                        "",
                        "─" * 45,
                        pot_balance_line,
                        f"{fixed_bet} {bet_amount:,} :coin:",
                        player_balance_line,
                    ])
                    await _send_canvas_dice_announcements(interaction, guild, result.get("announcements", []))
                else:
                    error_msg = answers.get("error_jugada", "❌ **ERROR!**")
                    content_parts.extend([
                        "**🎲 DICE PLAY RESULT**",
                        error_msg.format(error="Game execution failed"),
                    ])
        except Exception as e:
            logger.exception(f"Canvas dice play failed: {e}")
            content_parts.extend([
                "**🎲 DICE PLAY RESULT**",
                "❌ **ERROR!** Game execution failed.",
            ])
    
    elif action_name == "dice_ranking":
        # Show ranking using centralized function
        
        try:
            ranking_data = _get_canvas_dice_ranking(guild, 10)
            
            rankingtitle = descriptions.get("ranking", "**🏆 DICE RANKING**")
            content_parts.append(rankingtitle)
            content_parts.append("─" * 45)
            if ranking_data:
                for player in ranking_data:
                    medal = "🥇" if player["position"] == 1 else "🥈" if player["position"] == 2 else "🥉" if player["position"] == 3 else "🏅"
                    content_parts.append(
                        f"{medal} **#{player['position']}** {player['player_name']} | 🏆 Prize: {player['prize']:,} | Games: {player['total_plays']}"
                    )
            else:
                rankingvoid = descriptions.get("rankingvoid", "📊 No ranked players yet. Be the first to play!")
                content_parts.append(rankingvoid)
        except Exception as e:
            logger.exception(f"Canvas dice ranking failed: {e}")
            content_parts.extend([
                "**🏆 DICE RANKING**",
                "❌ **ERROR!** Could not load ranking.",
            ])
    
    elif action_name == "dice_history":
        # Show recent history
        try:
            db_dice = get_dice_game_db_instance(server_key)
            history = db_dice.get_game_history(server_id, 10)
            historytitle = descriptions.get("history", "**📜 DICE HISTORY**")
            content_parts.append(historytitle)
            content_parts.append("─" * 45)
            
            if history:
                for record in history:
                    # Parse tuple: (id, user_id, user_name, server_id, server_name, bet, dice, combination, prize, pot_before, pot_after, date)
                    user_name = record[2] if len(record) > 2 else "Unknown"
                    dice = record[6] if len(record) > 6 else ""
                    combination = record[7] if len(record) > 7 else ""
                    prize = record[8] if len(record) > 8 else 0
                    
                    dice_display = "🎲".join(dice.split('-')) if dice else "???"
                    prize_emoji = "💰" if prize > 0 else "💸"
                    
                    content_parts.append(
                        f"👤 {user_name} | {dice_display} → {combination} | {prize_emoji} {prize:,}"
                    )
            else:
                historyvoid = descriptions.get("historyvoid", "📊 Any play in the game. Be the first!")
                content_parts.append(historyvoid)
        except Exception as e:
            logger.exception(f"Canvas dice history failed: {e}")
            content_parts.extend([
                "**📜 DICE HISTORY**",
                "❌ **ERROR!** Could not load history.",
            ])
    
    elif action_name == "dice_help":
        # Show help
        helpmsgfallback = ([
            "**🎲 DICE GAME HELP**",
            "",
            "**How to play:**",
            "• Click **Dice: Play** to roll the dice",
            "• Cost: Fixed bet amount per game",
            "• Win: Get prizes based on dice combinations",
            "",
            "**Commands:**",
            "• `!dice play` - Play a game",
            "• `!dice ranking` - Show top players",
            "• `!dice history` - Show recent games",
            "• `!dice balance` - Check your gold",
            "",
            "**Prizes:**",
            "• Special combinations = Big prizes!",
            "• Regular combinations = Small prizes",
            "• No match = No prize (bet goes to pot)",
            "",
            f"**Current bet:** {dice_state.get('bet', 1):,} gold",
            f"**Current pot:** {dice_state['pot_balance']:,} gold",
        ])
        helpmsg = descriptions.get("help", helpmsgfallback)
        content_parts.append(helpmsg)
    
    # Rebuild the view with dynamic content
    content = "\n".join(content_parts)
    # Store current embed in view for back navigation
    role_embed = _build_canvas_role_embed("trickster", content, view.admin_visible, "dice", None, f"Executed {action_name.replace('_', ' ').title()}")
    view.current_embed = role_embed
    
    next_view = CanvasRoleDetailView(
        author_id=view.author_id,
        role_name=view.role_name,
        agent_config=view.agent_config,
        admin_visible=view.admin_visible,
        sections=view.sections,
        current_detail="dice",
        guild=guild,  # Use the determined guild (default or original)
        previous_view=view,  # Pass current view as previous_view
    )
    next_view.auto_response_preview = f"Executed {action_name.replace('_', ' ').title()}"
    try:
        await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)
    except discord.InteractionResponded:
        # If interaction was already responded to, use followup
        await interaction.followup.edit_message(interaction.message.id, embed=role_embed, view=next_view)
    except discord.NotFound:
        # Message was deleted, send a new one
        try:
            await interaction.followup.send(embed=role_embed, view=next_view, ephemeral=True)
        except discord.NotFound:
            # Interaction completely expired, nothing we can do
            logger.warning("Canvas dice interaction expired completely - unable to send followup")
        except Exception as e:
            logger.exception(f"Failed to send canvas dice followup: {e}")
    except Exception as e:
        logger.exception(f"Failed to edit canvas dice message: {e}")
        try:
            await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
        except discord.NotFound:
            # Interaction expired, nothing we can do
            logger.warning("Canvas dice interaction expired during error handling")
        except Exception as followup_e:
            logger.exception(f"Failed to send error followup: {followup_e}")


async def _handle_canvas_treasure_hunter_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    if get_poe2_manager is None:
        await interaction.response.send_message("❌ POE2 manager is not available.", ephemeral=True)
        return

    manager = get_poe2_manager()
    # Use empty string for DM - let manager find active server
    server_id = "" if interaction.guild is None else str(interaction.guild.id)
    user_id = str(interaction.user.id)

    if action_name in {"league_standard", "league_fate_of_the_vaal", "league_hardcore"}:
        league_map = {
            "league_standard": "Standard",
            "league_fate_of_the_vaal": "Fate of the Vaal",
            "league_hardcore": "Hardcore",
        }
        league = league_map[action_name]
        try:
            ok = manager.set_user_league(user_id, league, server_id)
            if ok:
                if manager.should_refresh_item_list(league):
                    await manager.download_item_list(league)
                manager._add_default_objectives(user_id, league)
                manager._download_default_objectives_history(user_id, league)
        except Exception as e:
            logger.exception(f"Canvas POE2 league update failed: {e}")
            ok = False
        if not ok:
            await interaction.response.send_message("❌ Could not update POE2 league.", ephemeral=True)
            return
        # Return to the view from where the league action was triggered
        # If user was in POE2 view (personal), return there, otherwise go to league
        target_detail = view.current_detail if view.current_detail == "personal" else "league"
        
        # Generate updated content for the target view after league action
        content = _build_canvas_role_detail_view(
            "treasure_hunter",
            target_detail,
            view.agent_config,
            view.admin_visible,
            view.guild,
            view.author_id,
        )
        next_view = CanvasRoleDetailView(view.author_id, view.role_name, view.agent_config, view.admin_visible, view.sections, current_detail=target_detail, guild=view.guild)
        next_view.auto_response_preview = f"✅ League changed to `{league}` and default items were synced."
        embed = _build_canvas_role_embed("treasure_hunter", content, view.admin_visible, target_detail, None, next_view.auto_response_preview)
        try:
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        except discord.InteractionResponded:
            # If interaction was already responded to, use followup
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=next_view)
        except discord.NotFound:
            # Message was deleted, send a new one
            try:
                await interaction.followup.send(embed=embed, view=next_view, ephemeral=True)
            except discord.NotFound:
                # Interaction completely expired, nothing we can do
                logger.warning("Canvas treasure hunter interaction expired completely - unable to send followup")
            except Exception as e:
                logger.exception(f"Failed to send canvas treasure hunter followup: {e}")
        except Exception as e:
            logger.exception(f"Failed to edit canvas treasure hunter message: {e}")
            try:
                await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
            except discord.NotFound:
                # Interaction expired, nothing we can do
                logger.warning("Canvas treasure hunter interaction expired during error handling")
            except Exception as followup_e:
                logger.exception(f"Failed to send error followup: {followup_e}")
        return

    if not view.admin_visible or not is_admin(interaction):
        await interaction.response.send_message("❌ This POE2 option is admin-only.", ephemeral=True)
        return

    try:
        if action_name == "poe2_on":
            # For admin actions, use a default league since no specific user is involved
            league = manager.get_active_league(user_id, server_id)
            if manager.should_refresh_item_list(league):
                await manager.download_item_list(league)
            ok = manager.activate_subrole(server_id)
        else:
            ok = manager.deactivate_subrole(server_id)
    except Exception as e:
        logger.exception(f"Canvas POE2 activation toggle failed: {e}")
        ok = False

    if not ok:
        await interaction.response.send_message("❌ Could not update POE2 activation state.", ephemeral=True)
        return

    # Return to the view from where the admin action was triggered
    # If user was in POE2 view (personal), return there, otherwise go to admin
    target_detail = view.current_detail if view.current_detail in {"personal", "league"} else "admin"
    
    # Generate updated content for the target view after admin action
    content = _build_canvas_role_detail_view(
        "treasure_hunter",
        target_detail,
        view.agent_config,
        view.admin_visible,
        view.guild,
        view.author_id,
    )
    next_view = CanvasRoleDetailView(view.author_id, view.role_name, view.agent_config, view.admin_visible, view.sections, current_detail=target_detail, guild=view.guild)
    next_view.auto_response_preview = f"POE2 {'enabled' if action_name == 'poe2_on' else 'disabled'}."
    embed = _build_canvas_role_embed("treasure_hunter", content, view.admin_visible, target_detail, None, next_view.auto_response_preview)
    try:
        await interaction.response.edit_message(content=None, embed=embed, view=next_view)
    except discord.InteractionResponded:
        # If interaction was already responded to, use followup
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=next_view)
    except discord.NotFound:
        # Message was deleted, send a new one
        try:
            await interaction.followup.send(embed=embed, view=next_view, ephemeral=True)
        except discord.NotFound:
            # Interaction completely expired, nothing we can do
            logger.warning("Canvas treasure hunter interaction expired completely - unable to send followup")
        except Exception as e:
            logger.exception(f"Failed to send canvas treasure hunter followup: {e}")
    except Exception as e:
        logger.exception(f"Failed to edit canvas treasure hunter message: {e}")
        try:
            await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
        except discord.NotFound:
            # Interaction expired, nothing we can do
            logger.warning("Canvas treasure hunter interaction expired during error handling")
        except Exception as followup_e:
            logger.exception(f"Failed to send error followup: {followup_e}")


async def _handle_canvas_banker_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    """Handle banker role actions like balance, TAE, and bonus display."""
    if get_banker_db_instance is None:
        await interaction.response.send_message("❌ Banker systems are not available.", ephemeral=True)
        return
    
    try:
        server_key = get_server_key(interaction.guild)
        db_banker = get_banker_db_instance(server_key)
        server_id = str(interaction.guild.id)
        user_id = str(view.author_id)
        
        # Get user and server info
        user_name = interaction.user.display_name
        server_name = interaction.guild.name
        
        # Build response content based on action
        content_parts = [f"🏦 **BANKER - {action_name.upper()}** 🏦", ""]
        
        if action_name == "balance":
            balance = db_banker.get_balance(user_id, server_id)
            content_parts.extend([
                f"💰 **Your Balance:** {balance:,} :coin:",
                f"👤 **Account:** {user_name}",
                f"🏛️ **Server:** {server_name}",
            ])
        
        elif action_name == "tae":
            # Get TAE configuration
            try:
                from agent_db import get_tae_config
                tae_config = get_tae_config(server_id)
                tae_rate = tae_config.get("rate", 1.0)
                tae_enabled = tae_config.get("enabled", False)
                
                content_parts.extend([
                    f"📊 **TAE Configuration**",
                    f"📈 **Rate:** {tae_rate:.2%}",
                    f"🔧 **Status:** {'✅ Enabled' if tae_enabled else '❌ Disabled'}",
                    f"🏛️ **Server:** {server_name}",
                ])
            except Exception as e:
                content_parts.extend([
                    f"📊 **TAE Configuration**",
                    "❌ **Error:** Could not load TAE configuration",
                ])
        
        elif action_name == "bonus":
            # Get bonus configuration
            try:
                from agent_db import get_bonus_config
                bonus_config = get_bonus_config(server_id)
                bonus_rate = bonus_config.get("rate", 10)
                bonus_enabled = bonus_config.get("enabled", False)
                
                content_parts.extend([
                    f"🎁 **Bonus Configuration**",
                    f"💎 **Rate:** {bonus_rate}%",
                    f"🔧 **Status:** {'✅ Enabled' if bonus_enabled else '❌ Disabled'}",
                    f"🏛️ **Server:** {server_name}",
                ])
            except Exception as e:
                content_parts.extend([
                    f"🎁 **Bonus Configuration**",
                    "❌ **Error:** Could not load bonus configuration",
                ])
        
        else:
            await interaction.response.send_message("❌ Unknown banker action.", ephemeral=True)
            return
        
        # Rebuild the view with the response content
        content = "\n".join(content_parts)
        
        # Store current embed and create new view
        from discord_bot.canvas.content import _build_canvas_role_embed
        role_embed = _build_canvas_role_embed("banker", content, view.admin_visible, "overview", None, f"Viewed {action_name.title()}")
        view.current_embed = role_embed
        
        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail="overview",
            guild=view.guild,
            previous_view=view,  # Pass current view as previous_view
        )
        next_view.auto_response_preview = f"Viewed {action_name.title()}"
        
        # Update the message
        try:
            await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)
        except discord.InteractionResponded:
            await interaction.followup.edit_message(interaction.message.id, embed=role_embed, view=next_view)
        except discord.NotFound:
            await interaction.followup.send(embed=role_embed, view=next_view, ephemeral=True)
            
    except Exception as e:
        logger.exception(f"Canvas banker action failed: {e}")
        await interaction.response.send_message("❌ Failed to process banker action.", ephemeral=True)


class CanvasWatcherSubscribeModal(discord.ui.Modal):
    """Modal for News Watcher subscription with unified interface."""
    
    def __init__(self, action_name: str, view: "CanvasRoleDetailView", bot):
        self.action_name = action_name
        self.view = view
        self.bot = bot
        
        if action_name == "subscribe_categories":
            title = "Subscribe to Categories"
        else:  # This should not happen since we removed subscribe_feeds
            title = "Subscribe to Categories"
            
        super().__init__(title=title, timeout=300)
        
        self.category_input = discord.ui.TextInput(
            label="Category",
            placeholder="Enter category (economy, technology, gaming, international, general, crypto)...",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        self.add_item(self.category_input)
        
        # Add optional feed_id input for subscribe_categories
        self.feed_id_input = discord.ui.TextInput(
            label="Feed ID (Optional)",
            placeholder="Enter specific feed ID number, 'all' for all feeds, or leave empty for first feed...",
            style=discord.TextStyle.short,
            required=False,  # Make it optional
            max_length=10,
            default=""  # Empty by default
        )
        self.add_item(self.feed_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands
            
            # Create mock message
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild
                    
            # Execute subscription command with return_result=True for canvas
            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            
            # Use guild-specific database for watcher commands
            if interaction.guild:
                server_name = str(interaction.guild.id)
                watcher_commands = WatcherCommands(self.bot)
                db_instance = get_news_watcher_db_instance(server_name)
                # Ensure database is properly initialized
                if not db_instance.db_path.exists() or db_instance.db_path.stat().st_size == 0:
                    db_instance._init_db()
                watcher_commands.db_watcher = db_instance
            else:
                watcher_commands = WatcherCommands(self.bot)
            
            # Build command arguments
            method = (self.view.watcher_selected_method or "flat").strip().lower()
            category = str(self.category_input.value).strip().lower()
            
            args = [method, category]
            
            # Add optional feed_id if provided
            feed_id = str(self.feed_id_input.value).strip()
            if feed_id:  # Only add if not empty
                args.append(feed_id)
            
            # Execute subscription command based on view type
            if self.view.current_detail == "admin":
                # Admin mode: create channel subscription
                channel_id = str(interaction.channel.id)
                channel_name = interaction.channel.name
                server_id = str(interaction.guild.id)
                server_name = interaction.guild.name
                
                # Use channel subscription method
                if method == "general":
                    # AI channel subscription
                    try:
                        db_watcher = get_news_watcher_db_instance(server_id)
                        default_premises_list = db_watcher._get_default_premises()
                        default_premises = ", ".join(default_premises_list)
                    except Exception:
                        default_premises = "interesting news, relevant events, important developments"
                    
                    # Validate and convert feed_id using the same validation function
                    feed_id_num = None
                    if feed_id:
                        # Use the validation function to convert category-relative to absolute database ID
                        feed_id_num = await watcher_commands._validate_category_and_feed(
                            mock_message, category, [method, feed_id], db_watcher
                        )
                    
                    if db_watcher.subscribe_channel_category_ai(
                        channel_id, channel_name, server_id, server_name, category, feed_id_num, default_premises
                    ):
                        result_msg = f"✅ General channel subscription created for {category}"
                        if feed_id:
                            result_msg += f" (feed #{feed_id})"
                    else:
                        result_msg = "❌ Failed to create channel subscription"
                else:
                    # For other methods, use channel subscription commands
                    args = [category] + ([feed_id] if feed_id else [])
                    await watcher_commands.cmd_channel_subscribe(mock_message, args)
                    result_msg = f"✅ {method.title()} channel subscription created for {category}"
                    if feed_id:
                        result_msg += f" (feed #{feed_id})"
            else:
                # Personal mode: create user subscription
                if method == "general":
                    # Call directly with return_result=True to avoid extra messages
                    user_id = str(interaction.user.id)
                    
                    # Validate and convert feed_id using the same validation function
                    feed_id_num = None
                    if feed_id:
                        # Use the validation function to convert category-relative to absolute database ID
                        feed_id_num = await watcher_commands._validate_category_and_feed(
                            mock_message, category, [method, feed_id], db_instance
                        )
                    
                    success, result_msg = await watcher_commands._handle_general_subscribe(
                        mock_message, user_id, category, feed_id_num, return_result=True
                    )
                    
                    if not success:
                        result_msg = f"❌ {result_msg}"
                else:
                    # For other methods, use the unified command (they don't send extra messages)
                    await watcher_commands.cmd_unified_subscribe(mock_message, args)
                    
                    method_titles = {
                        "flat": "Flat Subscription (All News)",
                        "keyword": "Keyword Subscription (Filtered)",
                        "general": "General Subscription (AI Analysis)"
                    }
                    
                    result_msg = f"✅ {method_titles.get(method, 'Subscription')} created for {category}"
                    if feed_id:
                        result_msg += f" (feed #{feed_id})"
                    else:
                        result_msg += " (all feeds in category)"
            
            # Try to respond, but handle expired interaction gracefully
            try:
                self.view.watcher_last_action = self.action_name
                # Maintain current detail instead of forcing "personal"
                current_detail = self.view.current_detail
                content = _build_canvas_role_news_watcher_detail(
                    current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = CanvasRoleDetailView(
                    author_id=self.view.author_id,
                    role_name=self.view.role_name,
                    agent_config=self.view.agent_config,
                    admin_visible=self.view.admin_visible,
                    sections=self.view.sections,
                    current_detail=current_detail,
                    guild=self.view.guild,
                    watcher_selected_method=self.view.watcher_selected_method,
                    watcher_last_action=self.view.watcher_last_action
                )
                next_view.watcher_selected_method = self.view.watcher_selected_method
                next_view.watcher_last_action = self.view.watcher_last_action
                next_view.auto_response_preview = result_msg
                embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                # Interaction expired - the action was successful, so just acknowledge silently
                logger.info(f"Watcher Canvas subscription {self.action_name} completed but interaction expired")
            except discord.HTTPException as e:
                # Other HTTP errors - log but don't send followup to keep Canvas clean
                logger.warning(f"Could not update Canvas for Watcher subscription {self.action_name}: {e}")
            
        except Exception as e:
            logger.exception(f"Error in Watcher subscription modal: {e}")
            # Don't try to respond on error - the interaction is likely expired anyway


class CanvasWatcherAddModal(discord.ui.Modal):
    """Modal for adding keywords and premises."""
    
    def __init__(self, action_name: str, view: "CanvasRoleDetailView", bot):
        self.action_name = action_name
        self.view = view
        self.bot = bot
        
        if action_name == "add_keywords":
            title = "Add Keywords"
            label = "Keywords"
            placeholder = "Enter keywords separated by commas (e.g., bitcoin, ethereum, crypto)..."
        else:  # add_premises
            title = "Add Premises"
            label = "Premise"
            placeholder = "Enter your AI analysis premise (e.g., Focus on market impact)..."
            
        super().__init__(title=title, timeout=300)
        
        self.content_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            style=discord.TextStyle.paragraph if action_name == "add_premises" else discord.TextStyle.short,
            required=True,
            max_length=500 if action_name == "add_premises" else 200
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands
            
            # Create mock message
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild
                    
            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            
            # Use guild-specific database for watcher commands
            if interaction.guild:
                server_name = str(interaction.guild.id)
                watcher_commands = WatcherCommands(self.bot)
                db_instance = get_news_watcher_db_instance(server_name)
                # Ensure database is properly initialized
                if not db_instance.db_path.exists() or db_instance.db_path.stat().st_size == 0:
                    db_instance._init_db()
                watcher_commands.db_watcher = db_instance
            else:
                watcher_commands = WatcherCommands(self.bot)
            
            content = str(self.content_input.value).strip()
            
            is_admin_channel_view = self.view.current_detail in {"admin", "channel", "setup"}

            # Execute appropriate command
            if self.action_name == "add_keywords":
                result_msg = await watcher_commands.cmd_keywords_add_canvas(mock_message, [content])
                if isinstance(result_msg, str):
                    result_msg = result_msg  # Use the returned message directly
            else:  # add_premises
                # Premises always use user functions, even in admin view
                result_msg = await watcher_commands.cmd_premises_add_canvas(mock_message, [content])
                if isinstance(result_msg, str):
                    result_msg = result_msg  # Use the returned message directly
            
            # Try to respond, but handle expired interaction gracefully
            try:
                self.view.watcher_last_action = "list_keywords" if self.action_name == "add_keywords" else "list_premises"
                content = _build_canvas_role_news_watcher_detail(
                    self.view.current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = CanvasRoleDetailView(
                    author_id=self.view.author_id,
                    role_name=self.view.role_name,
                    agent_config=self.view.agent_config,
                    admin_visible=self.view.admin_visible,
                    sections=self.view.sections,
                    current_detail=self.view.current_detail,
                    guild=self.view.guild,
                    watcher_selected_method=self.view.watcher_selected_method,
                    watcher_last_action=self.view.watcher_last_action
                )
                next_view.watcher_selected_method = self.view.watcher_selected_method
                next_view.watcher_last_action = self.view.watcher_last_action
                next_view.auto_response_preview = result_msg
                embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, self.view.current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                # Interaction expired - the action was successful, so just acknowledge silently
                logger.info(f"Watcher Canvas add {self.action_name} completed but interaction expired")
            except discord.HTTPException as e:
                # Other HTTP errors - log but don't send followup to keep Canvas clean
                logger.warning(f"Could not update Canvas for Watcher add {self.action_name}: {e}")
            
        except Exception as e:
            logger.exception(f"Error in Watcher add modal: {e}")
            # Don't try to respond on error - the interaction is likely expired anyway


class CanvasWatcherDeleteModal(discord.ui.Modal):
    """Modal for deleting keywords and premises."""
    
    def __init__(self, action_name: str, view: "CanvasRoleDetailView", bot):
        self.action_name = action_name
        self.view = view
        self.bot = bot
        
        if action_name == "delete_keywords":
            title = "Delete Keywords"
            label = "Keyword to Delete"
            placeholder = "Enter keyword to remove (e.g., bitcoin)..."
        else:  # delete_premises
            title = "Delete Premises"
            label = "Premise Number"
            placeholder = "Enter premise number to delete (e.g., 1, 2, 3)..."
            
        super().__init__(title=title, timeout=300)
        
        self.content_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            style=discord.TextStyle.short,
            required=True,
            max_length=100
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands
            
            # Create mock message
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild
                    
            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            
            # Use guild-specific database for watcher commands
            if interaction.guild:
                server_name = str(interaction.guild.id)
                watcher_commands = WatcherCommands(self.bot)
                db_instance = get_news_watcher_db_instance(server_name)
                # Ensure database is properly initialized
                if not db_instance.db_path.exists() or db_instance.db_path.stat().st_size == 0:
                    db_instance._init_db()
                watcher_commands.db_watcher = db_instance
            else:
                watcher_commands = WatcherCommands(self.bot)
            
            content = str(self.content_input.value).strip()
            
            is_admin_channel_view = self.view.current_detail in {"admin", "channel", "setup"}

            # Execute appropriate command
            if self.action_name == "delete_keywords":
                result_msg = await watcher_commands.cmd_keywords_del(mock_message, [content])
                if isinstance(result_msg, str):
                    result_msg = f"✅ Keyword deleted: {content}"
            else:  # delete_premises
                # Premises always use user functions, even in admin view
                result_msg = await watcher_commands.cmd_premises_del_canvas(mock_message, [content])
                if isinstance(result_msg, str):
                    result_msg = result_msg  # Use the returned message directly
            
            # Try to respond, but handle expired interaction gracefully
            try:
                self.view.watcher_last_action = "list_keywords" if self.action_name == "delete_keywords" else "list_premises"
                content = _build_canvas_role_news_watcher_detail(
                    self.view.current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = CanvasRoleDetailView(
                    author_id=self.view.author_id,
                    role_name=self.view.role_name,
                    agent_config=self.view.agent_config,
                    admin_visible=self.view.admin_visible,
                    sections=self.view.sections,
                    current_detail=self.view.current_detail,
                    guild=self.view.guild,
                    watcher_selected_method=self.view.watcher_selected_method,
                    watcher_last_action=self.view.watcher_last_action
                )
                next_view.watcher_selected_method = self.view.watcher_selected_method
                next_view.watcher_last_action = self.view.watcher_last_action
                next_view.auto_response_preview = result_msg
                embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, self.view.current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                # Interaction expired - the action was successful, so just acknowledge silently
                logger.info(f"Watcher Canvas delete {self.action_name} completed but interaction expired")
            except discord.HTTPException as e:
                # Other HTTP errors - log but don't send followup to keep Canvas clean
                logger.warning(f"Could not update Canvas for Watcher delete {self.action_name}: {e}")
            
        except Exception as e:
            logger.exception(f"Error in Watcher delete modal: {e}")
            # Don't try to respond on error - the interaction is likely expired anyway


class CanvasWatcherListModal(discord.ui.Modal):
    """Modal for listing keywords and premises."""
    
    def __init__(self, list_type: str, view: "CanvasRoleDetailView", bot):
        self.list_type = list_type
        self.view = view
        self.bot = bot
        
        titles = {
            "keywords": "View Keywords",
            "premises": "View Premises"
        }
        
        super().__init__(title=titles.get(list_type, "View Configuration"), timeout=300)
        
        self.action_input = discord.ui.TextInput(
            label="Action",
            placeholder="Enter: list, add, mod, or del",
            style=discord.TextStyle.short,
            required=True,
            max_length=10
        )
        self.add_item(self.action_input)
        
        if list_type == "keywords":
            self.value_input = discord.ui.TextInput(
                label="Keywords",
                placeholder="Enter keyword(s) separated by commas (for add/del)...",
                style=discord.TextStyle.short,
                required=False,
                max_length=200
            )
        else:  # premises
            self.value_input = discord.ui.TextInput(
                label="Premise Text",
                placeholder="For mod use: <number> | <new premise text>",
                style=discord.TextStyle.long,
                required=False,
                max_length=500
            )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands
            
            # Create mock message
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild
                    
            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            
            # Use guild-specific database for watcher commands
            if interaction.guild:
                server_name = str(interaction.guild.id)
                watcher_commands = WatcherCommands(self.bot)
                db_instance = get_news_watcher_db_instance(server_name)
                # Ensure database is properly initialized
                if not db_instance.db_path.exists() or db_instance.db_path.stat().st_size == 0:
                    db_instance._init_db()
                watcher_commands.db_watcher = db_instance
            else:
                watcher_commands = WatcherCommands(self.bot)
            
            # Build command arguments
            action = str(self.action_input.value).strip().lower()
            value = str(self.value_input.value).strip() if self.value_input.value else ""
            
            is_admin_channel_view = self.view.current_detail in {"admin", "channel", "setup"}

            if self.list_type == "keywords":
                if action == "add" and value:
                    args = ["add"] + [kw.strip() for kw in value.split(",")]
                    await watcher_commands.cmd_keywords_add(mock_message, args)
                    result_msg = f"✅ Keywords added: {value}"
                elif action == "list":
                    await watcher_commands.cmd_keywords_list(mock_message, [])
                    result_msg = "📋 Keywords list sent by DM"
                elif action == "del" and value:
                    args = ["del"] + [kw.strip() for kw in value.split(",")]
                    await watcher_commands.cmd_keywords_del(mock_message, args)
                    result_msg = f"🗑️ Keywords deleted: {value}"
                else:
                    result_msg = "❌ Invalid action or missing keywords"
                    
            else:  # premises
                if action == "add" and value:
                    args = [value]
                    # Premises always use user functions, even in admin view
                    result_msg = await watcher_commands.cmd_premises_add_canvas(mock_message, args)
                    if isinstance(result_msg, str):
                        result_msg = result_msg  # Use the returned message directly
                elif action == "list":
                    # Premises always use user functions, even in admin view
                    result_msg = await watcher_commands.cmd_premises_list_canvas(mock_message, [])
                    if isinstance(result_msg, str):
                        result_msg = result_msg  # Use the returned message directly
                elif action == "del" and value:
                    args = [value]
                    # Premises always use user functions, even in admin view
                    result_msg = await watcher_commands.cmd_premises_del_canvas(mock_message, args)
                    if isinstance(result_msg, str):
                        result_msg = result_msg  # Use the returned message directly
                elif action == "mod" and value:
                    if "|" not in value:
                        result_msg = "❌ For mod use: <number> | <new premise text>"
                    else:
                        index_text, premise_text = value.split("|", 1)
                        args = [index_text.strip(), premise_text.strip()]
                        # Premises always use user functions, even in admin view
                        result_msg = await watcher_commands.cmd_premises_mod_canvas(mock_message, args)
                        if isinstance(result_msg, str):
                            result_msg = result_msg
                else:
                    result_msg = "❌ Invalid action or missing premise text"
            
            # Try to respond, but handle expired interaction gracefully
            try:
                content = ""  # Action view content is no longer needed
                next_view = CanvasRoleDetailView(
                    author_id=self.view.author_id,
                    role_name=self.view.role_name,
                    agent_config=self.view.agent_config,
                    admin_visible=self.view.admin_visible,
                    sections=self.view.sections,
                    current_detail="overview",
                    guild=self.view.guild,
                    watcher_selected_method=self.view.watcher_selected_method,
                    watcher_last_action=self.view.watcher_last_action
                )
                next_view.auto_response_preview = result_msg
                embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, "overview", None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                # Interaction expired - the action was successful, so just acknowledge silently
                logger.info(f"Watcher Canvas list {self.list_type} completed but interaction expired")
            except discord.HTTPException as e:
                # Other HTTP errors - log but don't send followup to keep Canvas clean
                logger.warning(f"Could not update Canvas for Watcher list {self.list_type}: {e}")
            
        except Exception as e:
            logger.exception(f"Error in Watcher list modal: {e}")
            # Don't try to respond on error - the interaction is likely expired anyway


class CanvasWatcherChannelSubscribeModal(discord.ui.Modal):
    """Modal for channel subscriptions using the selected watcher method."""

    def __init__(self, action_name: str, view: "CanvasRoleDetailView", bot):
        self.action_name = action_name
        self.view = view
        self.bot = bot
        title = "Channel Subscribe Categories" if action_name == "channel_subscribe_categories" else "Channel Subscribe Feeds"
        super().__init__(title=title, timeout=300)

        # Add optional feed_id input for channel subscription (both singular and plural)
        if action_name in {"channel_subscribe_categories", "channel_subscribe_category"}:
            self.category_input = discord.ui.TextInput(
                label="Category",
                placeholder="Enter category (economy, technology, gaming, crypto)...",
                style=discord.TextStyle.short,
                required=True,
                max_length=50
            )
            self.add_item(self.category_input)
            
            # Add helpful feed info in the label
            self.feed_id_input = discord.ui.TextInput(
                label="Feed IDs (Optional)",
                placeholder="Enter feed number (1, 2, 3...)\nFeed 1 = First feed in category\nLeave empty for all feeds",
                style=discord.TextStyle.paragraph,  # Use paragraph style for longer text
                required=False,  # Make it optional
                max_length=50,  # Increased for multiple IDs
                default=""  # Empty by default
            )
            self.add_item(self.feed_id_input)
        elif action_name == "channel_subscribe_feeds":
            self.feed_id_input = discord.ui.TextInput(
                label="Feed ID",
                placeholder="Enter specific feed ID number...",
                style=discord.TextStyle.short,
                required=True,
                max_length=10,
            )
            self.add_item(self.feed_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if get_news_watcher_db_instance is None or not interaction.guild:
                await interaction.response.send_message("❌ Watcher database is not available.", ephemeral=True)
                return

            db = get_news_watcher_db_instance(str(interaction.guild.id))
            # Ensure database is properly initialized
            if not db.db_path.exists() or db.db_path.stat().st_size == 0:
                db._init_db()
            method = (self.view.watcher_selected_method or "flat").strip().lower()
            category = str(self.category_input.value).strip().lower()
            feed_id = None
            
            # Handle feed_ids for all channel subscription actions
            feed_ids = []
            if self.action_name in {"channel_subscribe_categories", "channel_subscribe_category", "channel_subscribe_feeds"}:
                feed_ids_str = str(self.feed_id_input.value).strip()
                if feed_ids_str:  # Only parse if not empty (optional for categories)
                    try:
                        # Parse multiple feed IDs separated by commas
                        feed_ids = [int(id_str.strip()) for id_str in feed_ids_str.split(',') if id_str.strip()]
                        if not feed_ids:
                            await interaction.response.send_message("❌ No valid Feed IDs found", ephemeral=True)
                            return
                    except ValueError:
                        await interaction.response.send_message("❌ Feed IDs must be numbers separated by commas", ephemeral=True)
                        return

            channel_id = str(interaction.channel.id)
            channel_name = interaction.channel.name
            server_id = str(interaction.guild.id)
            server_name = interaction.guild.name

            # Create subscriptions for each feed ID
            successful_subscriptions = 0
            failed_subscriptions = 0
            
            if feed_ids:
                # Subscribe to specific feeds - use category-relative indexing
                feeds = db.get_active_feeds(category)
                for feed_id in feed_ids:
                    if 1 <= feed_id <= len(feeds):
                        # Get feed by relative index (1-based to 0-based)
                        feed_data = feeds[feed_id - 1]
                        # Extract the global feed ID from feed_data
                        global_feed_id = feed_data[0]
                        
                        ok = False
                        if method == "flat":
                            ok = db.subscribe_channel_category(channel_id, channel_name, server_id, server_name, category, global_feed_id)
                        elif method == "keyword":
                            # For keyword method, we need to use the user's keywords
                            # Get keywords from the user who is creating the subscription
                            user_id = str(interaction.user.id)
                            user_keywords = db.get_user_keywords(user_id)
                            if user_keywords:
                                ok = db.subscribe_keywords(user_id, user_keywords, channel_id, category, global_feed_id)
                            else:
                                # No keywords configured, fail the subscription
                                ok = False
                        elif method == "general":
                            premises, _ = db.get_channel_premises_with_context(channel_id)
                            premises_str = ",".join(premises) if premises else ""
                            ok = db.subscribe_channel_category_ai(channel_id, channel_name, server_id, server_name, category, global_feed_id, premises_str)
                        
                        if ok:
                            successful_subscriptions += 1
                        else:
                            failed_subscriptions += 1
                    else:
                        failed_subscriptions += 1
            else:
                # Subscribe to all feeds in category (default behavior)
                ok = False
                if method == "flat":
                    ok = db.subscribe_channel_category(channel_id, channel_name, server_id, server_name, category, None)
                elif method == "keyword":
                    # For keyword method, we need to use the user's keywords
                    user_id = str(interaction.user.id)
                    user_keywords = db.get_user_keywords(user_id)
                    if user_keywords:
                        ok = db.subscribe_keywords(user_id, user_keywords, channel_id, category, None)
                    else:
                        # No keywords configured, fail the subscription
                        ok = False
                elif method == "general":
                    premises, _ = db.get_channel_premises_with_context(channel_id)
                    premises_str = ",".join(premises) if premises else ""
                    ok = db.subscribe_channel_category_ai(channel_id, channel_name, server_id, server_name, category, None, premises_str)
                
                if ok:
                    successful_subscriptions = 1
                else:
                    failed_subscriptions = 1

            if failed_subscriptions > 0 and successful_subscriptions == 0:
                # Provide helpful error message based on what failed
                if feed_ids:
                    if method == "keyword" and not db.get_user_keywords(str(interaction.user.id)):
                        # Special error for keyword method with no keywords
                        await interaction.response.send_message(
                            "❌ Cannot create keyword subscription: **No keywords configured**.\n\n"
                            "Please add keywords first using the 'Add Keywords' option in the Canvas UI.",
                            ephemeral=True
                        )
                    else:
                        feeds = db.get_active_feeds(category)
                        # Build dynamic feed list for error message
                        feed_list = []
                        for i, feed in enumerate(feeds[:10]):  # Show up to 10 feeds
                            feed_list.append(f"• Feed {i+1}: {feed[1]}")
                        
                        if len(feeds) > 10:
                            feed_list.append(f"• ... and {len(feeds) - 10} more feeds")
                        
                        await interaction.response.send_message(
                            f"❌ Could not create any channel subscriptions.\n\n"
                            f"**Available {category.title()} feeds:**\n"
                            + "\n".join(feed_list) +
                            f"\n\n• Total: {len(feeds)} feeds available\n\n"
                            f"**Try:** Use numbers 1-{len(feeds)} or leave empty for all {category} feeds.",
                            ephemeral=True
                        )
                else:
                    if method == "keyword" and not db.get_user_keywords(str(interaction.user.id)):
                        # Special error for keyword method with no keywords
                        await interaction.response.send_message(
                            "❌ Cannot create keyword subscription: **No keywords configured**.\n\n"
                            "Please add keywords first using the 'Add Keywords' option in the Canvas UI.",
                            ephemeral=True
                        )
                    else:
                        await interaction.response.send_message("❌ Could not create channel subscription. Please try again.", ephemeral=True)
                return

            self.view.watcher_last_action = self.action_name
            content = _build_canvas_role_news_watcher_detail(
                "admin",
                self.view.admin_visible,
                self.view.guild,
                self.view.author_id,
                selected_method=self.view.watcher_selected_method,
                last_action=self.view.watcher_last_action,
            )
            next_view = CanvasRoleDetailView(
                author_id=self.view.author_id,
                role_name=self.view.role_name,
                agent_config=self.view.agent_config,
                admin_visible=self.view.admin_visible,
                sections=self.view.sections,
                current_detail="admin",
                guild=self.view.guild,
                watcher_selected_method=self.view.watcher_selected_method,
                watcher_last_action=self.view.watcher_last_action
            )
            feed_suffix = f" (feed #{feed_id})" if feed_id is not None else ""
            
            # Create appropriate success message
            if feed_ids:
                if successful_subscriptions == len(feed_ids):
                    if successful_subscriptions == 1:
                        feed_list = f"feed #{feed_ids[0]}"
                    else:
                        feed_list = f"feeds {', '.join(map(str, feed_ids))}"
                    success_msg = f"✅ {method.title()} channel subscription created for `{category}` ({feed_list})."
                else:
                    success_msg = f"⚠️ {method.title()} channel subscription partially created for `{category}`. {successful_subscriptions}/{len(feed_ids)} feeds successful."
            else:
                success_msg = f"✅ {method.title()} channel subscription created for `{category}` (all feeds)."
            
            next_view.watcher_selected_method = self.view.watcher_selected_method
            next_view.watcher_last_action = self.view.watcher_last_action
            next_view.auto_response_preview = success_msg
            embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, "admin", None, next_view.auto_response_preview)
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        except ValueError:
            logger.warning("Invalid Feed ID in channel subscription modal")
        except Exception as e:
            logger.exception(f"Error in Watcher channel subscription modal: {e}")


class CanvasWatcherChannelUnsubscribeModal(discord.ui.Modal):
    """Modal to unsubscribe a channel subscription by numbered entry."""

    def __init__(self, view: "CanvasRoleDetailView", bot):
        self.view = view
        self.bot = bot
        super().__init__(title="Channel Unsubscribe", timeout=300)
        self.number_input = discord.ui.TextInput(
            label="Subscription Number",
            placeholder="Enter the numbered subscription from block 2...",
            style=discord.TextStyle.short,
            required=True,
            max_length=5,
        )
        self.add_item(self.number_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if get_news_watcher_db_instance is None or not interaction.guild:
                logger.warning("Watcher database not available for channel unsubscribe")
                return

            db = get_news_watcher_db_instance(str(interaction.guild.id))
            channel_id = str(interaction.channel.id)
            index = int(str(self.number_input.value).strip())

            all_subs = [("channel", category, feed_id) for category, feed_id, _ in db.get_channel_subscriptions(channel_id)]

            if index < 1 or index > len(all_subs):
                logger.warning(f"Invalid subscription number: {index}")
                return

            method, category, feed_id = all_subs[index - 1]
            ok = db.cancel_channel_subscription(channel_id, category, feed_id)
            if not ok:
                ok = db.cancel_category_subscription(f"channel_{channel_id}", category, feed_id)

            if not ok:
                logger.warning("Could not cancel channel subscription")
                return

            # Handle listing actions by updating the view
            if self.view.watcher_last_action in {"list_categories", "list_feeds", "list_keywords", "list_premises"}:
                content = _build_canvas_role_news_watcher_detail(
                    self.view.current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = CanvasRoleDetailView(
                    author_id=self.view.author_id,
                    role_name=self.view.role_name,
                    agent_config=self.view.agent_config,
                    admin_visible=self.view.admin_visible,
                    sections=self.view.sections,
                    current_detail=self.view.current_detail,
                    guild=self.view.guild,
                    watcher_selected_method=self.view.watcher_selected_method,
                    watcher_last_action=self.view.watcher_last_action
                )
                embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, self.view.current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            elif self.view.watcher_last_action == "list_feeds_by_category":
                # Ask for category with modal
                await interaction.response.send_modal(CanvasWatcherFeedsByCategoryModal(self.view))
            self.view.watcher_last_action = "channel_unsubscribe"
            content = _build_canvas_role_news_watcher_detail(
                "admin",
                self.view.admin_visible,
                self.view.guild,
                self.view.author_id,
                selected_method=self.view.watcher_selected_method,
                last_action=self.view.watcher_last_action,
            )
            next_view = CanvasRoleDetailView(
                author_id=self.view.author_id,
                role_name=self.view.role_name,
                agent_config=self.view.agent_config,
                admin_visible=self.view.admin_visible,
                sections=self.view.sections,
                current_detail="admin",
                guild=self.view.guild,
            )
            next_view.watcher_selected_method = self.view.watcher_selected_method
            next_view.watcher_last_action = self.view.watcher_last_action
            next_view.auto_response_preview = f"✅ Removed channel subscription #{index} from `{category}`."
            embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, "admin", None, next_view.auto_response_preview)
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in Watcher channel unsubscribe modal: {e}")


class CanvasWatcherFrequencyModal(discord.ui.Modal):
    """Modal for setting watcher frequency."""
    
    def __init__(self, view: "CanvasRoleDetailView", bot):
        self.view = view
        self.bot = bot
        
        super().__init__(title="Set Watcher Frequency", timeout=300)
        
        self.hours_input = discord.ui.TextInput(
            label="Hours",
            placeholder="Enter number of hours (1-24)...",
            style=discord.TextStyle.short,
            required=True,
            max_length=5
        )
        self.add_item(self.hours_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands
            
            # Create mock message
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild
                    
            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            
            # Use guild-specific database for watcher commands
            if interaction.guild:
                server_name = str(interaction.guild.id)
                watcher_commands = WatcherCommands(self.bot)
                db_instance = get_news_watcher_db_instance(server_name)
                # Ensure database is properly initialized
                if not db_instance.db_path.exists() or db_instance.db_path.stat().st_size == 0:
                    db_instance._init_db()
                watcher_commands.db_watcher = db_instance
            else:
                watcher_commands = WatcherCommands(self.bot)
            
            # Build command arguments
            hours = str(self.hours_input.value).strip()
            args = [hours]
            
            # Execute frequency command
            await watcher_commands.cmd_frequency(mock_message, args)
            
            result_msg = f"✅ Watcher frequency set to {hours} hours"
            
            # Try to respond, but handle expired interaction gracefully
            try:
                self.view.watcher_last_action = "watcher_frequency"
                current_detail = "admin" if self.view.current_detail == "admin" else "personal"
                content = _build_canvas_role_news_watcher_detail(
                    current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = CanvasRoleDetailView(
                    author_id=self.view.author_id,
                    role_name=self.view.role_name,
                    agent_config=self.view.agent_config,
                    admin_visible=self.view.admin_visible,
                    sections=self.view.sections,
                    current_detail=current_detail,
                    guild=self.view.guild,
                    watcher_selected_method=self.view.watcher_selected_method,
                    watcher_last_action=self.view.watcher_last_action
                )
                next_view.watcher_selected_method = self.view.watcher_selected_method
                next_view.watcher_last_action = self.view.watcher_last_action
                next_view.auto_response_preview = result_msg
                embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                # Interaction expired - the action was successful, so just acknowledge silently
                logger.info(f"Watcher Canvas frequency completed but interaction expired")
            except discord.HTTPException as e:
                # Other HTTP errors - log but don't send followup to keep Canvas clean
                logger.warning(f"Could not update Canvas for Watcher frequency: {e}")
            
        except Exception as e:
            logger.exception(f"Error in Watcher frequency modal: {e}")
            # Don't try to respond on error - the interaction is likely expired anyway


class CanvasBehaviorView(TimeoutResetMixin, SmartBackButtonMixin, HomeButtonMixin, discord.ui.View):
    def __init__(self, author_id: int, sections: dict[str, str], admin_visible: bool, agent_config: dict,
                 current_detail: str = "conversation", guild=None, message=None):
        super().__init__(timeout=600)  # 10 minutes
        self.author_id = author_id
        self.sections = sections
        self.admin_visible = admin_visible
        self.agent_config = agent_config
        self.current_detail = current_detail
        self.guild = guild
        self.message = message  # Store the message to delete it later
        self.auto_response_preview = None  # Initialize auto_response_preview
        self.update_visibility()
        
        # Add behavior detail buttons
        if current_detail in ["greetings", "welcome", "commentary", "taboo", "role_control"]:
            self.add_item(CanvasBehaviorActionSelect(current_detail, admin_visible))
        self._add_behavior_buttons()
        
        # Add navigation buttons using mixins
        self.add_smart_back_button()
        self.add_home_button()
        
        # Start the timeout timer
        self._reset_timeout()

    async def _check_user_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True

    def _add_behavior_buttons(self):
        """Add behavior-specific detail buttons."""
        detail_items = _get_canvas_behavior_detail_items(self.admin_visible, self.current_detail)
        for label, detail_name in detail_items:
            self.add_item(CanvasBehaviorDetailButton(label=label, detail_name=detail_name))

    def update_visibility(self):
        """Hide or disable admin-only controls according to current permissions."""
        if not self.admin_visible:
            for child in self.children:
                if getattr(child, "label", "") == "Setup":
                    child.disabled = True
                    break

    async def on_timeout(self) -> None:
        """Called when the view times out - delete the entire message and cleanup callbacks."""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if self.message:
                    await self.message.delete()
                self.stop()
                return  # Success, exit the method
            except discord.NotFound:
                # Message already deleted
                self.stop()
                return
            except discord.HTTPException as e:
                if attempt == max_attempts - 1:  # Last attempt
                    logger.warning(f"Canvas behavior view timeout cleanup failed: {e}")
                    self.stop()
                    return
                await asyncio.sleep(1)  # Wait before retry


class CanvasRoleDetailView(TimeoutResetMixin, SmartBackButtonMixin, HomeButtonMixin, discord.ui.View):
    """Interactive navigation for role-specific details."""

    def __init__(self, author_id: int, role_name: str, agent_config: dict, admin_visible: bool,
                 sections: dict[str, str], current_detail: str = "overview", guild=None, message=None,
                 watcher_selected_method: str = None, watcher_last_action: str = None, watcher_selected_category: str = None,
                 previous_view=None):
        super().__init__(timeout=600)  # 10 minutes
        self.author_id = author_id
        self.role_name = role_name
        self.agent_config = agent_config
        self.admin_visible = admin_visible
        self.sections = sections
        self.current_detail = current_detail
        self.guild = guild
        self.message = message  # Store the message to delete it later
        
        # Dynamic state for News Watcher
        self.watcher_selected_method = watcher_selected_method  # Will store "flat", "keyword", or "general"
        self.watcher_last_action = watcher_last_action  # Track last action for dynamic updates
        self.watcher_selected_category = watcher_selected_category  # Store selected category for feeds display
        self.auto_response_preview = None
        self.previous_view = previous_view  # Store reference to previous view for back navigation
        self.current_embed = None  # Store current embed for back navigation
        
        role_details = _get_canvas_role_detail_items(role_name, admin_visible, current_detail)
        current_actions = _get_canvas_role_action_items_for_detail(role_name, current_detail, admin_visible)
        if current_actions:
            # For News Watcher, create dynamic dropdowns
            if role_name == "news_watcher" and current_detail in {"personal", "overview"}:
                self.add_item(CanvasWatcherMethodSelect(self))
                self.add_item(CanvasWatcherSubscriptionSelect(self))
            elif role_name == "news_watcher" and current_detail == "admin":
                self.add_item(CanvasWatcherAdminMethodSelect(self))
                self.add_item(CanvasWatcherAdminActionSelect(self))
            # For MC, create action dropdown
            elif role_name == "mc" and current_detail == "overview":
                self.add_item(CanvasMCActionSelect(self))
            # For Banker, only create dropdown for admin (overview/wallet are info-only)
            elif role_name == "banker" and current_detail == "admin":
                self.add_item(CanvasRoleActionSelect(role_name, current_detail, admin_visible))
            # For other roles, create action dropdown
            else:
                self.add_item(CanvasRoleActionSelect(role_name, current_detail, admin_visible))
        for label, detail_name in role_details:
            self.add_item(CanvasRoleDetailButton(label=label, role_name=role_name, detail_name=detail_name))
        self._add_role_buttons()
        
        # Add navigation buttons using mixins
        self.add_smart_back_button()
        self.add_home_button()
        
        # Start the timeout timer
        self._reset_timeout()

    def _add_role_buttons(self):
        """Add role-specific buttons."""
        # Add POE2 button only for treasure_hunter main overview (not subrol views)
        if self.role_name == "treasure_hunter" and self.current_detail == "overview":
            button_poe2 = _personality_descriptions.get("roles_view_messages", {}).get("treasure_hunter", {}).get("button_poe2", "👺 POE2")
            self.add_item(CanvasTreasureHunterPoe2Button(label=button_poe2, style=discord.ButtonStyle.green))
        return

    async def on_timeout(self) -> None:
        """Called when the view times out - delete the entire message and cleanup callbacks."""
        # Cleanup MC callbacks before stopping
        if hasattr(self, '_mc_callbacks'):
            for mc_commands, original_callback in self._mc_callbacks:
                try:
                    mc_commands.set_message_callback(original_callback)
                except:
                    pass  # Ignore errors during cleanup
            self._mc_callbacks.clear()
        
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if self.message:
                    await self.message.delete()
                self.stop()
                return  # Success, exit the method
            except discord.NotFound:
                # Message already deleted, just stop the view
                self.stop()
                return
            except discord.Forbidden:
                for child in self.children:
                    child.disabled = True
                self.stop()
                return
            except Exception as e:
                if attempt == max_attempts - 1:  # Last attempt
                    logger.warning(f"Could not delete Canvas message on timeout after {max_attempts} attempts: {e}")
                    for child in self.children:
                        child.disabled = True
                    self.stop()
                else:
                    # Brief delay before retry
                    await asyncio.sleep(0.1)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive Canvas to its original user."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True

    def _add_behavior_buttons(self):
        """Add available shared behavior buttons."""
        items = _get_canvas_behavior_detail_items(self.admin_visible)
        for label, detail_name in items:
            self.add_item(CanvasBehaviorDetailButton(label=label, detail_name=detail_name))

    def _get_watcher_block3_content(self, action_name: str) -> str:
        """Get dynamic content for block 3 based on selected action."""
        if action_name == "subscribe_categories":
            return "\n".join([
                "**📂 Browse & Subscribe**",
                "",
                f"Selected: {action_name.replace('_', ' ').title()}",
                "",
                "**Available Categories**",
                "- 🏦 **Economy**: Financial markets, business news, economic policies",
                "- 💻 **Technology**: AI, software, hardware, tech innovations", 
                "- 🌍 **International**: Global politics, world events, diplomacy",
                "- 📰 **General**: Breaking news, general current events",
                "- 🪙 **Crypto**: Cryptocurrency, blockchain, DeFi news",
                "",
                "**How to subscribe**",
                f"- Use the dropdown to select `{action_name.replace('_', ' ').title()}`",
                "- Fill in the modal with your preferences",
                "- Choose method: flat (all), keyword (filtered), or general (AI-critical)",
                "",
                "**Current subscriptions**",
                "- You can have up to 3 active subscriptions",
                "- Use `!watcher subscriptions` to see your current subscriptions",
                "- Use `!watcher unsubscribe <number>` to cancel",
            ])
        elif action_name == "list_keywords":
            return "\n".join([
                "**🔍 Keywords Management**",
                "",
                "Selected: List Keywords",
                "",
                "**Your Keywords Configuration**",
                "- Keywords filter news for keyword subscriptions",
                "- Only news containing your keywords will be delivered",
                "- You can add multiple keywords per subscription",
                "",
                "**How to manage keywords**",
                "- **List**: View all your configured keywords",
                "- **Add**: Add new keywords for filtering",
                "- **Delete**: Remove keywords you no longer need",
                "",
                "**Example keywords**",
                "- Technology: AI, blockchain, machine learning, software",
                "- Finance: bitcoin, stocks, inflation, trading",
                "- Science: research, discovery, space, medicine",
                "",
                "**Current status**",
                "- Select `list` from the dropdown to see your keywords",
                "- Keywords are sent by private message for privacy",
            ])
        elif action_name == "list_premises":
            return "\n".join([
                "**🤖 AI Premises Management**",
                "",
                "Selected: List Premises",
                "",
                "**Your AI Analysis Premises**",
                "- Premises guide AI in selecting globally critical news",
                "- AI evaluates news importance based on your criteria",
                "- Only news matching your premises will be delivered",
                "",
                "**How to manage premises**",
                "- **List**: View all your configured premises",
                "- **Add**: Add new premises for AI analysis",
                "- **Delete**: Remove premises you no longer need",
                "",
                "**Example premises**",
                "- \"I care about technological advances that affect society\"",
                "- \"Focus on economic policies that impact global markets\"",
                "- \"Prioritize climate change and environmental news\"",
                "",
                "**Current status**",
                "- Select `list` from the dropdown to see your premises",
                "- Premises are sent by private message for privacy",
            ])
        else:
            return "\n".join([
                "**Interactive Selection**",
                "- Use the dropdowns below to manage your subscriptions",
                "- Method dropdown: Choose filtering approach",
                "- Subscriptions dropdown: Subscribe or view configuration",
                "- This block will update based on your selections",
                "",
                "**Available categories**",
                "- Economy, Technology, International, General, Crypto",
                "- Use interactive dropdowns to browse and subscribe",
            ])

    def _get_watcher_admin_block3_content(self, action_name: str) -> str:
        """Get dynamic content for admin block 3 based on selected action."""
        if action_name == "channel_subscribe_categories":
            return "\n".join([
                "**📂 Channel Subscription Management**",
                "",
                f"Selected: {action_name.replace('_', ' ').title()}",
                "",
                "**Channel Subscription Impact**",
                "- News will be delivered to this channel for all members",
                "- Channel subscriptions count towards server limit (max 5)",
                "- All channel members will see the news notifications",
                "",
                "**Available Categories**",
                "- 🏦 **Economy**: Financial markets, business news, economic policies",
                "- 💻 **Technology**: AI, software, hardware, tech innovations", 
                "- 🌍 **International**: Global politics, world events, diplomacy",
                "- 📰 **General**: Breaking news, general current events",
                "- 🪙 **Crypto**: Cryptocurrency, blockchain, DeFi news",
                "",
                "**Admin Subscription Process**",
                f"- Select `{action_name.replace('_', ' ').title()}` from dropdown",
                "- Choose method: flat (all), keyword (filtered), or general (AI-critical)",
                "- Specify category and optionally feed ID",
                "- News will be delivered directly to this channel",
                "",
                "**Channel vs Personal**",
                "- **Channel**: Everyone in channel sees notifications",
                "- **Personal**: Only user gets notifications via DM",
            ])
        elif action_name == "channel_view_subscriptions":
            return "\n".join([
                "**📋 Channel Subscriptions Overview**",
                "",
                "Selected: View Channel Subscriptions",
                "",
                "**Current Channel Subscriptions**",
                "- Lists all active subscriptions for this channel",
                "- Shows subscription method, category, and feed details",
                "- Displays subscription numbers for management",
                "",
                "**Management Options**",
                "- **View**: See all current channel subscriptions",
                "- **Unsubscribe**: Cancel by subscription number",
                "- **Add**: Create new channel subscriptions",
                "",
                "**Channel Subscription Limits**",
                "- Maximum 5 channel subscriptions per server",
                "- Each subscription can have different filtering method",
                "- Admin can manage all channel subscriptions",
                "",
                "**Notification Behavior**",
                "- Channel subscriptions notify in this channel",
                "- All channel members receive notifications",
                "- Uses server-wide method configuration by default",
            ])
        elif action_name == "channel_unsubscribe":
            return "\n".join([
                "**🗑️ Channel Unsubscribe Management**",
                "",
                "Selected: Channel Unsubscribe",
                "",
                "**Unsubscribe Process**",
                "- Cancel channel subscriptions by number",
                "- View current subscriptions to get numbers",
                "- Immediate cancellation - no waiting period",
                "",
                "**Steps to Unsubscribe**",
                "1. First use 'View Subscriptions' to see current list",
                "2. Note the subscription number you want to cancel",
                "3. Select 'Channel Unsubscribe' and enter the number",
                "4. Confirmation will be shown in this channel",
                "",
                "**Impact of Cancellation**",
                "- No more news notifications for that subscription",
                "- Frees up channel subscription slot",
                "- Affects all channel members equally",
                "",
                "**Admin Responsibility**",
                "- Only admins can manage channel subscriptions",
                "- Consider impact on all channel members",
                "- Can re-subscribe later if needed",
            ])
        elif action_name == "watcher_frequency":
            return "\n".join([
                "**⏰ Watcher Frequency Configuration**",
                "",
                "Selected: Set Check Frequency",
                "",
                "**Frequency Impact**",
                "- Controls how often watcher checks for new news",
                "- Affects all subscriptions server-wide",
                "- Balance between timeliness and server resources",
                "",
                "**Recommended Settings**",
                "- **1-3 hours**: Breaking news, time-sensitive topics",
                "- **6-12 hours**: Regular updates, balanced approach",
                "- **24 hours**: Daily summaries, resource-efficient",
                "",
                "**Current Server Load**",
                "- More frequent checks = more server resource usage",
                "- Consider number of active subscriptions",
                "- Adjust based on news importance and timing needs",
                "",
                "**Configuration Process**",
                "- Enter frequency in hours (1-24)",
                "- Changes apply immediately to next check",
                "- Can be adjusted anytime by admin",
                "",
                "**Default Setting**",
                "- If not configured, uses system default",
                "- Recommended starting point: 6 hours",
            ])
        elif action_name == "watcher_run_now":
            return "\n".join([
                "**▶️ Force Watcher Run**",
                "",
                "Selected: Run News Check Immediately",
                "",
                "**Immediate News Check**",
                "- Bypasses normal frequency schedule",
                "- Checks all active subscriptions now",
                "- Delays next scheduled check accordingly",
                "",
                "**When to Use Force Run**",
                "- **Breaking news**: Important events happening now",
                "- **Testing**: Verify subscriptions are working",
                "- **Schedule changes**: After adding new subscriptions",
                "- **Manual refresh**: Get latest updates immediately",
                "",
                "**Process**",
                "- Checks all user and channel subscriptions",
                "- Processes news through configured methods",
                "- Delivers notifications according to subscriptions",
                "- Updates subscription timestamps",
                "",
                "**Admin Impact**",
                "- Affects all subscriptions server-wide",
                "- May generate multiple notifications",
                "- Consider timing for channel members",
                "",
                "**Resource Usage**",
                "- Temporary increase in server activity",
                "- Normal frequency resumes after completion",
                "- Safe to use occasionally, not continuously",
            ])
        elif action_name == "watcher_run_personal":
            return "\n".join([
                "**👤 Force Personal Subscriptions**",
                "",
                "Selected: Run Personal Subscriptions Immediately",
                "",
                "**Personal Subscription Processing**",
                "- Processes all user personal subscriptions",
                "- Handles flat, keyword, and AI subscription methods",
                "- Sends notifications directly to users via DMs",
                "- Bypasses normal frequency schedule for personal subs",
                "",
                "**When to Use Personal Force Run**",
                "- **Testing**: Verify personal subscriptions are working",
                "- **New setup**: After users configure their subscriptions",
                "- **Debugging**: Troubleshoot personal notification issues",
                "- **Immediate results**: Users want news without waiting",
                "",
                "**Process**",
                "- Checks all active personal subscriptions",
                "- Processes news through each user's preferred method",
                "- Delivers notifications via user DMs",
                "- Updates personal subscription timestamps",
                "",
                "**User Impact**",
                "- Only affects personal subscriptions (not channels)",
                "- Users receive notifications in their DMs",
                "- No channel spam or public notifications",
                "- Respects each user's subscription preferences",
                "",
                "**Admin Benefits**",
                "- Helps users verify their setup works",
                "- Provides immediate feedback for troubleshooting",
                "- No disruption to channel subscriptions",
                "- Safe to use anytime for user support",
                "",
                "**Resource Usage**",
                "- Moderate server activity increase",
                "- Proportional to number of personal subscriptions",
                "- Normal frequency resumes after completion",
                "- Safe to use regularly for user support",
            ])
        else:
            return "\n".join([
                "**Admin Interactive Selection**",
                "- Use the dropdowns below to manage channel settings",
                "- Frequency control: Set how often watcher checks for news",
                "- Force run: Trigger immediate news check for channels",
                "- Force personal: Run personal subscriptions for users",
                "- This block will update based on your selections",
                "",
                "**Channel Management**",
                "- Channel subscriptions affect all users in this channel",
                "- Server method affects new subscriptions by default",
                "- Use admin controls to manage server-wide settings",
            ])
        super().__init__(timeout=600)
        self.author_id = author_id
        self.role_name = role_name
        self.admin_visible = admin_visible
        self.agent_config = agent_config
        self.current_detail = current_detail
        self.guild = guild
        self.message = message
        self.auto_response_preview = None

        current_actions = _get_canvas_behavior_action_items_for_detail(current_detail, admin_visible)
        if current_actions:
            self.add_item(CanvasBehaviorActionSelect(current_detail, admin_visible))
        self._add_behavior_buttons()
        
        # Add navigation buttons using mixin
        self.add_navigation_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True

    def _add_behavior_buttons(self):
        items = _get_canvas_behavior_detail_items(self.admin_visible)
        for label, detail_name in items:
            if detail_name != self.current_detail:
                self.add_item(CanvasBehaviorDetailButton(label=label, detail_name=detail_name))

    async def on_timeout(self) -> None:
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if self.message:
                    await self.message.delete()
                self.stop()
                return  # Success, exit the method
            except discord.NotFound:
                # Message already deleted, just stop the view
                self.stop()
                return
            except discord.Forbidden:
                for child in self.children:
                    child.disabled = True
                self.stop()
                return
            except Exception as e:
                if attempt == max_attempts - 1:  # Last attempt
                    logger.warning(f"Could not delete Canvas message on timeout after {max_attempts} attempts: {e}")
                    for child in self.children:
                        child.disabled = True
                    self.stop()
                else:
                    # Brief delay before retry
                    await asyncio.sleep(0.1)

        # Add navigation buttons using mixin
        self.add_navigation_buttons()


class CanvasBehaviorDetailButton(discord.ui.Button):
    """Button that opens one General Behavior detail view."""

    def __init__(self, label: str, detail_name: str):
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self.detail_name = detail_name

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasBehaviorView):
            await interaction.response.send_message("❌ Canvas behavior navigation is not available.", ephemeral=True)
            return

        content = _build_canvas_behavior_detail(self.detail_name, view.admin_visible, view.guild, view.agent_config)
        if not content:
            await interaction.response.send_message("❌ This behavior detail is not available.", ephemeral=True)
            return

        next_view = CanvasBehaviorView(
            author_id=view.author_id,
            sections=view.sections,
            admin_visible=view.admin_visible,
            agent_config=view.agent_config,
            current_detail=self.detail_name,
            guild=view.guild,
        )
        next_view.message = interaction.message
        behavior_embed = _build_canvas_behavior_embed(content, view.admin_visible, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=behavior_embed, view=next_view)


def _get_enabled_roles(agent_config: dict) -> list[str]:
    roles_cfg = (agent_config or {}).get("roles", {})
    enabled = []
    for role_name, cfg in roles_cfg.items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("enabled", False):
            enabled.append(role_name)
    return enabled


def _load_role_mission_prompts(role_names: list[str]) -> list[str]:
    prompts: list[str] = []
    role_prompts_cfg = PERSONALITY.get("role_system_prompts", {})

    for role_name in role_names:
        try:
            if role_name == "mc":
                from roles.mc.mc import get_mc_system_prompt
                prompts.append(get_mc_system_prompt())
                continue
            if role_name == "banker":
                from roles.banker.banker import get_banker_system_prompt
                prompts.append(get_banker_system_prompt())
                continue
            if role_name == "treasure_hunter":
                from roles.treasure_hunter.treasure_hunter import get_treasure_hunter_system_prompt
                prompts.append(get_treasure_hunter_system_prompt())
                continue
            if role_name == "trickster":
                from roles.trickster.trickster import get_trickster_system_prompt
                prompts.append(get_trickster_system_prompt())
                continue

            prompt = role_prompts_cfg.get(role_name)
            if prompt:
                prompts.append(prompt)
        except Exception as e:
            logger.warning(f"Could not load role prompt for {role_name}: {e}")
            prompt = role_prompts_cfg.get(role_name)
            if prompt:
                prompts.append(prompt)

    return [p for p in prompts if isinstance(p, str) and p.strip()]


def _build_mission_commentary_prompt(agent_config: dict, server_name: str = "default") -> str:
    """Build a comprehensive mission commentary prompt with personality, memories, and role prompts."""
    enabled_roles = _get_enabled_roles(agent_config)
    mission_prompts = _load_role_mission_prompts(enabled_roles)

    roles_text = "\n".join([f"- {r}" for r in enabled_roles]) if enabled_roles else "- none"
    missions_text = "\n\n".join(mission_prompts) if mission_prompts else "(no mission prompts found)"

    # Load general memories for context
    try:
        from agent_mind import generate_daily_memory_summary, generate_recent_memory_summary
        
        daily_memory = generate_daily_memory_summary(server_name) or ""
        recent_memory = generate_recent_memory_summary(server_name) or ""
        
        memories_section = ""
        if daily_memory and daily_memory.strip():
            memories_section += f"MEMORIA DIARIA:\n{daily_memory.strip()}\n\n"
        if recent_memory and recent_memory.strip():
            memories_section += f"RECUERDOS RECIENTES:\n{recent_memory.strip()}\n\n"
        if not memories_section:
            memories_section = "MEMORIAS: Sin recuerdos importantes recientes.\n\n"
            
    except Exception as e:
        logger.warning(f"Could not load memories for commentary: {e}")
        memories_section = "MEMORIAS: No disponibles temporalmente.\n\n"

    # Try to load custom prompt from personality JSON, fallback to default
    custom_cfg = PERSONALITY.get("prompts", {}).get("mission_commentary", {})
    if custom_cfg and isinstance(custom_cfg, dict):
        instructions = custom_cfg.get("instructions", [])
        closing = custom_cfg.get("closing", "")
        if instructions:
            rules_section = "\n".join(instructions) + "\n"
        else:
            rules_section = ""
        if closing:
            closing_section = f"\n{closing}"
        else:
            closing_section = ""
    else:
        rules_section = ""
        closing_section = ""

    return (
        f"**MISSION COMMENTARY TASK**\n\n"
        "You are the agent speaking in character. "
        "Your specific task is: **Make a comment about your active missions**. "
        "Be brief, entertaining, and don't repeat yourself. Incorporate context from your memories if relevant.\n\n"
        f"{rules_section}"
        f"ACTIVE ROLES:\n{roles_text}\n\n"
        f"MISSION CONTEXT:\n{missions_text}\n\n"
        f"{memories_section}"
        "**FINAL INSTRUCTION:** Now produce your commentary on the active missions, incorporating relevant memories if you have them."
        f"{closing_section}"
    )


class CanvasWatcherFeedsByCategoryModal(discord.ui.Modal):
    """Modal to ask for category to list feeds."""
    
    def __init__(self, view: "CanvasRoleDetailView"):
        super().__init__(title="List Feeds by Category")
        self.view = view
        
        self.category_input = discord.ui.TextInput(
            label="Category",
            placeholder="Enter category (economy, technology, gaming, crypto, international, general, patch_notes)...",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        self.add_item(self.category_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            category = str(self.category_input.value).strip().lower()
            
            # Validate category exists
            if get_news_watcher_db_instance is None or not interaction.guild:
                await interaction.response.send_message("❌ Watcher database is not available.", ephemeral=True)
                return
            
            db = get_news_watcher_db_instance(str(interaction.guild.id))
            feeds = db.get_active_feeds(category)
            
            if not feeds:
                await interaction.response.send_message(f"❌ No feeds found for category '{category}'. Available categories: economy, technology, gaming, crypto, international, general, patch_notes", ephemeral=True)
                return
            
            # Update view to show feeds for this category
            self.view.watcher_last_action = "list_feeds_by_category"
            self.view.watcher_selected_category = category  # Store category for display
            
            content = _build_canvas_role_news_watcher_detail(
                self.view.current_detail,
                self.view.admin_visible,
                self.view.guild,
                self.view.author_id,
                selected_method=self.view.watcher_selected_method,
                last_action="list_feeds_by_category",
                selected_category=category
            )
            
            next_view = CanvasRoleDetailView(
                author_id=self.view.author_id,
                role_name=self.view.role_name,
                agent_config=self.view.agent_config,
                admin_visible=self.view.admin_visible,
                sections=self.view.sections,
                current_detail=self.view.current_detail,
                guild=self.view.guild,
                watcher_selected_method=self.view.watcher_selected_method,
                watcher_last_action="list_feeds_by_category",
                watcher_selected_category=category
            )
            
            embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, self.view.current_detail, None, next_view.auto_response_preview)
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            
        except Exception as e:
            logger.exception(f"Error in feeds by category modal: {e}")
            await interaction.response.send_message("❌ Error listing feeds. Please try again.", ephemeral=True)
            

class RuneCastingModal(discord.ui.Modal):
    """Modal for rune casting questions."""
    
    def __init__(self, action_name: str, author_id: int, guild):
        reading_type = action_name.replace("runes_", "")
        title_map = {
            "runes_single": "Single Rune Casting",
            "runes_three": "Three Rune Casting", 
            "runes_cross": "Five Rune Cross Casting"
        }
        super().__init__(title=title_map.get(action_name, "Rune Casting"), timeout=300.0)  # 5 minutes timeout
        self.action_name = action_name
        self.author_id = author_id
        self.guild = guild
        self.reading_type = reading_type
        
        # Add question input field
        self.add_item(discord.ui.TextInput(
            label="Your Question",
            placeholder="What would you like to know from the runes?",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        ))
    
    async def on_submit(self, interaction: discord.Interaction):
        question = self.children[0].value.strip()
        
        if not question:
            await interaction.response.send_message("❌ Please provide a question.", ephemeral=True)
            return
        
        try:
            # Get runes commands
            if get_nordic_runes_commands_instance is None:
                await interaction.response.send_message("❌ Runes system is not available.", ephemeral=True)
                return
            
            runes_commands = get_nordic_runes_commands_instance()
            
            # Create mock message for canvas compatibility
            class MockMessage:
                def __init__(self, author, guild):
                    self.author = author
                    self.guild = guild
            
            mock_message = MockMessage(interaction.user, interaction.guild)
            
            # Perform the rune casting
            result = await runes_commands.cmd_runes_canvas_cast(
                mock_message, 
                self.reading_type, 
                question
            )
            
            # Get personality messages
            try:
                import json
                import os
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                descriptions_path = os.path.join(project_root, "personalities", "putre", "descriptions.json")
                if os.path.exists(descriptions_path):
                    with open(descriptions_path, encoding="utf-8") as f:
                        descriptions = json.load(f).get("roles_view_messages", {}).get("trickster", {}).get("nordic_runes", {})
                else:
                    descriptions = {}
            except:
                descriptions = {}
            
            # Format response with personality
            cast_title = descriptions.get(f"{self.reading_type}_cast", f"🔮 **{self.reading_type.upper()} CASTING** 🔮")
            question_label = descriptions.get("question", "Question")
            saved_msg = descriptions.get("reading_saved", "🔮 Runes have been cast! Your reading has been saved.")
            
            response = f"{cast_title}\n\n"
            response += f"**{question_label}:** {question}\n\n"
            response += result
            response += f"\n\n{saved_msg}"
            
            # Try to respond to the interaction first
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=response,
                        color=discord.Color.purple()
                    ),
                    ephemeral=True
                )
            except discord.errors.NotFound:
                # Interaction expired, send as followup message
                logger.info("Interaction expired, sending rune reading as followup message")
                try:
                    await interaction.followup.send(
                        embed=discord.Embed(
                            description=response,
                            color=discord.Color.purple()
                        ),
                        ephemeral=True
                    )
                except discord.errors.NotFound:
                    # Followup also expired, send direct message to user
                    logger.info("Followup also expired, sending direct message to user")
                    try:
                        await interaction.user.send(
                            embed=discord.Embed(
                                description="🔮 **RUNE READING COMPLETED** 🔮\n\n" + response,
                                color=discord.Color.purple()
                            )
                        )
                        logger.info(f"Successfully sent rune reading via DM to user {interaction.user.id}")
                    except Exception as e:
                        logger.error(f"Failed to send rune reading via DM: {e}")
                        # Last resort: try to send to channel if possible
                        if hasattr(interaction, 'channel') and interaction.channel:
                            try:
                                await interaction.channel.send(
                                    f"🔮 {interaction.user.mention} Your rune reading is ready!\n\n" + response
                                )
                                logger.info("Sent rune reading to channel as last resort")
                            except Exception as channel_error:
                                logger.error(f"Failed to send to channel: {channel_error}")
                        else:
                            logger.error("All delivery methods failed for rune reading")
            
        except discord.errors.NotFound as e:
            # Interaction has expired (user closed modal or timeout)
            logger.warning(f"Rune casting modal interaction expired: {e}")
            # Cannot respond to expired interaction, just log it
        except Exception as e:
            logger.exception(f"Rune casting modal failed: {e}")
            try:
                await interaction.response.send_message(
                    "❌ Failed to cast runes. Please try again.",
                    ephemeral=True
                )
            except discord.errors.NotFound:
                # Interaction already expired
                logger.warning("Cannot send error message - interaction expired")
            except Exception:
                # All response methods failed, try DM as last resort
                try:
                    await interaction.user.send("❌ Failed to cast runes. Please try again.")
                    logger.info(f"Sent error message via DM to user {interaction.user.id}")
                except Exception:
                    logger.error("All error message delivery methods failed")


async def _handle_canvas_runes_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    """Handle Nordic runes actions with dynamic content display."""
    try:
        # Import MockMessage
        class MockMessage:
            def __init__(self, author, guild):
                self.author = author
                self.guild = guild
        
        mock_message = MockMessage(interaction.user, interaction.guild)
        
        if get_nordic_runes_commands_instance is None:
            await interaction.response.send_message("❌ Runes system is not available.", ephemeral=True)
            return
        
        runes_commands = get_nordic_runes_commands_instance()
        
        # Build content parts
        content_parts = []
        
        if action_name == "runes_history":
            # Show rune reading history
            try:
                result = await runes_commands.cmd_runes_canvas_history(mock_message, 10)
                content_parts.append("🔮 **RUNES READING HISTORY** 🔮")
                content_parts.append("─" * 45)
                content_parts.append(result)
            except Exception as e:
                logger.exception(f"Canvas runes history failed: {e}")
                content_parts.extend([
                    "🔮 **RUNES READING HISTORY** 🔮",
                    "❌ **ERROR!** Could not load your rune history.",
                ])
        
        elif action_name == "runes_types":
            # Show available reading types
            try:
                result = await runes_commands.cmd_runes_types(mock_message, [])
                content_parts.append("🔮 **RUNES READING TYPES** 🔮")
                content_parts.append("─" * 45)
                content_parts.append(result)
            except Exception as e:
                logger.exception(f"Canvas runes types failed: {e}")
                content_parts.extend([
                    "🔮 **RUNES READING TYPES** 🔮",
                    "❌ **ERROR!** Could not load reading types.",
                ])
        
        elif action_name == "runes_help":
            # Show help with personality messages
            try:
                import json
                import os
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                descriptions_path = os.path.join(project_root, "personalities", "putre", "descriptions.json")
                if os.path.exists(descriptions_path):
                    with open(descriptions_path, encoding="utf-8") as f:
                        descriptions = json.load(f).get("roles_view_messages", {}).get("trickster", {}).get("nordic_runes", {})
                else:
                    descriptions = {}
                
                help_content = descriptions.get("help_content", """🔮 **NORDIC RUNES WISDOM** 🔮

**What are Nordic Runes?**
The Elder Futhark is the oldest form of the runic alphabets, used by Germanic tribes for divination and magic.

**Available Readings:**
• **Single Rune** - Quick guidance on a specific question
• **Three Rune Spread** - Past, Present, Future reading
• **Five Rune Cross** - Comprehensive situation analysis

**How to use:**
• Use Discord commands: `!runes cast [type] <question>`
• Example: `!runes cast single What should I focus on today?`

**The 24 Elder Futhark Runes:**
Fehu • Uruz • Thurisaz • Ansuz • Raidho • Kenaz • Gebo • Wunjo
Hagalaz • Nauthiz • Isa • Jera • Eiwaz • Perthro • Algiz • Sowilo
Tiwaz • Berkano • Ehwaz • Mannaz • Laguz • Ingwaz • Dagaz • Othala

Each rune carries ancient wisdom and guidance for your journey.""")
                
                content_parts.append(help_content)
            except Exception as e:
                logger.exception(f"Canvas runes help failed: {e}")
                content_parts.extend([
                    "🔮 **NORDIC RUNES HELP** 🔮",
                    "❌ **ERROR!** Could not load help content.",
                ])
        
        # Rebuild the view with dynamic content
        content = "\n".join(content_parts)
        
        # Store current embed in view for back navigation
        role_embed = _build_canvas_role_embed("trickster", content, view.admin_visible, "runes", None, f"Viewed {action_name.replace('runes_', '').title()}")
        view.current_embed = role_embed
        
        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail="runes",
            guild=view.guild,
            previous_view=view,  # Pass current view as previous_view
        )
        next_view.auto_response_preview = f"Viewed {action_name.replace('runes_', '').title()}"
        
        # Update the original Canvas message
        try:
            await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)
        except discord.InteractionResponded:
            # If interaction was already responded to, use followup
            await interaction.followup.edit_message(interaction.message.id, embed=role_embed, view=next_view)
        except discord.NotFound:
            # Message was deleted, send a new one
            try:
                await interaction.followup.send(embed=role_embed, view=next_view, ephemeral=True)
            except discord.NotFound:
                # Interaction completely expired, nothing we can do
                logger.debug("Canvas runes interaction expired completely - unable to send followup")
        except Exception as e:
            logger.exception(f"Failed to edit canvas runes message: {e}")
            try:
                await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
            except discord.NotFound:
                # Interaction expired, nothing we can do
                logger.warning("Canvas runes interaction expired during error handling")
            except Exception as followup_e:
                logger.exception(f"Failed to send error followup: {followup_e}")
    
    except Exception as e:
        logger.exception(f"Unexpected error in Canvas runes action: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)
        else:
            try:
                await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)
            except discord.NotFound:
                # Interaction expired, nothing we can do
                logger.warning("Canvas runes interaction expired during error handling")



