"""Canvas Discord UI components."""

import os
import asyncio
import discord
import json
from pathlib import Path

# Import core components directly to avoid circular imports
try:
    from agent_logging import get_logger
    from agent_engine import PERSONALITY
except ImportError:
    get_logger = None
    PERSONALITY = {}

# Initialize logger early for use in import exceptions
logger = get_logger('canvas_ui') if get_logger else None

# Import Canvas-specific functions
try:
    from discord_bot.canvas.content import (
        _build_canvas_embed,
        _build_canvas_role_detail_view,
        _build_canvas_role_view,
        _build_canvas_role_embed,
        _build_canvas_home
    )
    from .canvas_behavior import (
        get_canvas_behavior_action_items_for_detail as _get_canvas_behavior_action_items_for_detail,
        get_canvas_behavior_detail_items as _get_canvas_behavior_detail_items,
        build_canvas_behavior_detail as _build_canvas_behavior_detail,
    )
    if logger:
        logger.info("✅ Canvas content functions imported successfully")
except ImportError as e:
    if logger:
        logger.error(f"❌ Failed to import Canvas content functions: {e}")
    _build_canvas_embed = None
    _build_canvas_role_detail_view = None
    _build_canvas_role_view = None
    _build_canvas_role_embed = None
    _build_canvas_home = None
    _get_canvas_behavior_action_items_for_detail = None
    _get_canvas_behavior_detail_items = None
    _build_canvas_behavior_detail = None

# Import news watcher database function
try:
    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
except ImportError:
    get_news_watcher_db_instance = None


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
            logger.info(f"Canvas interaction expired before edit: {edit_error}")
            return False
        logger.warning(f"Canvas edit failed: {edit_error}")
        return False


async def _cleanup_canvas_view_on_timeout(view, context_name: str = "Canvas") -> None:
    """Shared timeout cleanup logic for all Canvas views."""
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            # Delete the Canvas view message first
            if view.message:
                await view.message.delete()
            
            # Also delete the original command message if it exists
            if hasattr(view, 'original_command_message') and view.original_command_message:
                try:
                    await view.original_command_message.delete()
                except discord.NotFound:
                    # Original command message already deleted, that's fine
                    pass
                except discord.Forbidden:
                    logger.debug(f"Could not delete original command message due to missing permissions.")
                except discord.HTTPException as e:
                    logger.debug(f"Could not delete original command message: {e}")
            
            view.stop()
            return  # Success, exit the method
        except discord.NotFound:
            # Message already deleted, just stop the view
            view.stop()
            return
        except discord.Forbidden:
            # If we can't delete the message, at least disable the buttons
            for child in view.children:
                child.disabled = True
            view.stop()
            return
        except Exception as e:
            if attempt == max_attempts - 1:  # Last attempt
                logger.warning(f"Could not delete {context_name} message on timeout after {max_attempts} attempts: {e}")
                # Fallback: disable buttons
                for child in view.children:
                    child.disabled = True
                view.stop()
            else:
                # Brief delay before retry
                await asyncio.sleep(0.1)


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
        
        # Create a smart back button instance (unified navigation)
        button = CanvasSmartBackButton(label=button_label, row=row)
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
        
        logger.info(f"🔧 Back button clicked - view type: {type(view).__name__}")
        
        # Handle different view types
        if isinstance(view, (CanvasBehaviorView, CanvasNavigationView)):
            # For behavior views and navigation views, always go to home
            logger.info(f"🔧 Behavior/Navigation view -> home")
            await self._navigate_to_home(interaction, view)
            return
        
        if hasattr(view, 'current_detail') and hasattr(view, 'role_name'):
            logger.info(f"🔧 RoleDetailView navigation - current_detail: {view.current_detail}, role_name: {view.role_name}")
            
            # Determine navigation target based on current detail level
            if view.current_detail.endswith("_admin") or view.current_detail == "admin":
                # Level 3: Admin views -> Level 2 (parent overview)
                # Special handling for treasure_hunter admin view
                logger.info(f"🔧 Checking admin view navigation - role_name: '{view.role_name}', current_detail: '{view.current_detail}'")
                if view.role_name == "treasure_hunter":
                    # For treasure_hunter, admin should go back to main role view (which has POE2 button)
                    logger.info(f"🔧 Treasure hunter admin view -> main role view")
                    await self._navigate_to_treasure_hunter_main(interaction, view)
                    return
                else:
                    target_detail = view.current_detail.replace("_admin", "") if view.current_detail.endswith("_admin") else "overview"
                    target_function = _build_canvas_role_detail_view
                    logger.info(f"🔧 Admin view -> parent overview: {target_detail}")
                
            elif view.current_detail == "overview":
                # Level 2: Overview views -> Level 1 (roles view)
                logger.info(f"🔧 Overview view -> roles view")
                
                # Find CanvasRolesView in the previous_view chain
                current_view = view
                roles_view = None
                
                # Walk up the previous_view chain to find CanvasRolesView
                while current_view and not roles_view:
                    # CanvasRolesView should NOT have role_name or current_detail
                    # CanvasRoleDetailView always has role_name and current_detail
                    if (hasattr(current_view, 'sections') and 'roles' in current_view.sections and
                        hasattr(current_view, 'current_embed') and current_view.current_embed and
                        not hasattr(current_view, 'role_name') and  # CanvasRolesView doesn't have role_name
                        not hasattr(current_view, 'current_detail')):  # CanvasRolesView doesn't have current_detail
                        roles_view = current_view
                        break
                    
                    current_view = getattr(current_view, 'previous_view', None)
                
                if roles_view:
                    # Navigate back to the roles view
                    try:
                        if hasattr(roles_view, 'current_embed') and roles_view.current_embed:
                            await interaction.response.edit_message(embed=roles_view.current_embed, view=roles_view)
                            logger.info(f"✅ Successfully navigated to roles view")
                            return
                        else:
                            logger.warning(f"⚠️ Roles view has no current_embed, falling back to home")
                            await self._navigate_to_home(interaction, view)
                            return
                    except Exception as e:
                        logger.error(f"❌ Failed to navigate to roles view: {e}")
                        await self._navigate_to_home(interaction, view)
                        return
                else:
                    logger.warning(f"⚠️ No CanvasRolesView found in chain, falling back to home")
                    await self._navigate_to_home(interaction, view)
                    return
                
            elif view.current_detail and view.current_detail != "overview":
                # Level 2: Detail views (not overview) -> Level 1 (role overview)
                target_detail = "overview"
                target_function = _build_canvas_role_view
                logger.info(f"🔧 Detail view -> role overview")
                
            else:
                # Level 1: Role overview -> Home
                logger.info(f"🔧 Role overview -> home")
                await self._navigate_to_home(interaction, view)
                return
            
            # Execute navigation to determined target
            try:
                # Check if required functions are available
                if not target_function or not _build_canvas_role_embed:
                    logger.error(f"❌ Missing functions - target_function: {target_function}, _build_canvas_role_embed: {_build_canvas_role_embed}")
                    raise ImportError("Required Canvas functions not available")
                
                # Check which function we're calling and pass correct parameters
                if target_function == _build_canvas_role_view:
                    # _build_canvas_role_view takes: role_name, agent_config, admin_visible, guild, author_id
                    content = target_function(
                        view.role_name,
                        view.agent_config,
                        view.admin_visible,
                        view.guild,
                        view.author_id,
                    )
                    
                    CanvasRoleDetailView_class = globals().get('CanvasRoleDetailView')
                    if not CanvasRoleDetailView_class:
                        logger.error(f"❌ CanvasRoleDetailView not found in globals")
                        raise ImportError("CanvasRoleDetailView class not available")
                    
                    detail_view = CanvasRoleDetailView_class(
                        author_id=view.author_id,
                        role_name=view.role_name,
                        agent_config=view.agent_config,
                        admin_visible=view.admin_visible,
                        sections=view.sections,
                        current_detail=target_detail,
                        guild=view.guild,
                        previous_view=view,  # Pass current view to maintain correct chain
                    )
                    detail_view.message = interaction.message
                    
                    detail_embed = _build_canvas_role_embed(
                        view.role_name, 
                        content, 
                        view.admin_visible, 
                        target_detail, 
                        None, 
                        detail_view.auto_response_preview
                    )
                    
                    await interaction.response.edit_message(embed=detail_embed, view=detail_view)
                    logger.info(f"✅ Navigation completed successfully")
                    return
                else:
                    # _build_canvas_role_detail_view takes: role_name, detail_name, agent_config, admin_visible, guild, author_id
                    content = target_function(
                        view.role_name,
                        target_detail,
                        view.agent_config,
                        view.admin_visible,
                        view.guild,
                        view.author_id,
                    )
                    
                    if not content:
                        logger.error(f"❌ No content returned from target_function")
                        await _safe_send_interaction_message(interaction, "❌ This view is not available.", ephemeral=True)
                        return
                    
                    CanvasRoleDetailView_class = globals().get('CanvasRoleDetailView')
                    if not CanvasRoleDetailView_class:
                        logger.error(f"❌ CanvasRoleDetailView not found in globals")
                        raise ImportError("CanvasRoleDetailView class not available")
                    
                    detail_view = CanvasRoleDetailView_class(
                        author_id=view.author_id,
                        role_name=view.role_name,
                        agent_config=view.agent_config,
                        admin_visible=view.admin_visible,
                        sections=view.sections,
                        current_detail=target_detail,
                        guild=view.guild,
                        previous_view=view,  # Pass current view as previous_view
                    )
                    detail_view.message = interaction.message
                    
                    detail_embed = _build_canvas_role_embed(
                        view.role_name, 
                        content, 
                        view.admin_visible, 
                        target_detail, 
                        None, 
                        detail_view.auto_response_preview
                    )
                    
                    await interaction.response.edit_message(embed=detail_embed, view=detail_view)
                    logger.info(f"✅ Navigation completed successfully")
                    return
                
            except Exception as e:
                logger.error(f"❌ Navigation execution failed: {e}")
                # Fallback to previous view or home if navigation fails
                if hasattr(view, 'previous_view') and view.previous_view:
                    await self._navigate_to_previous_view(interaction, view)
                else:
                    await self._navigate_to_home(interaction, view)
                return
        
        # Fallback navigation for non-role detail views
        if hasattr(view, 'previous_view') and view.previous_view:
            await self._navigate_to_previous_view(interaction, view)
        else:
            logger.info(f"🔧 No previous view, going to home")
            await self._navigate_to_home(interaction, view)

    async def _navigate_to_treasure_hunter_main(self, interaction: discord.Interaction, view):
        """Navigate to the main treasure hunter role view (with POE2 button)."""
        try:
            # Check required functions
            if not _build_canvas_role_view or not _build_canvas_role_embed:
                raise ImportError("Role view functions not available")
            
            # Build main treasure hunter role content
            content = _build_canvas_role_view(
                "treasure_hunter",
                view.agent_config,
                view.admin_visible,
                view.guild,
                view.author_id,
            )
            
            CanvasRoleDetailView_class = globals().get('CanvasRoleDetailView')
            if not CanvasRoleDetailView_class:
                raise ImportError("CanvasRoleDetailView class not available")
            
            # Create new detail view for main treasure hunter (overview)
            main_view = CanvasRoleDetailView_class(
                author_id=view.author_id,
                role_name="treasure_hunter",
                agent_config=view.agent_config,
                admin_visible=view.admin_visible,
                sections=view.sections,
                current_detail="overview",  # This will show the main view with POE2 button
                guild=view.guild,
                previous_view=view.previous_view,  # Maintain the chain
            )
            main_view.message = interaction.message
            
            # Build embed for main view
            main_embed = _build_canvas_role_embed(
                "treasure_hunter", 
                content, 
                view.admin_visible, 
                "overview", 
                None, 
                main_view.auto_response_preview
            )
            
            await interaction.response.edit_message(embed=main_embed, view=main_view)
            logger.info(f"✅ Successfully navigated to treasure hunter main view")
        except Exception as e:
            logger.error(f"❌ Failed to navigate to treasure hunter main view: {e}")
            await self._navigate_to_home(interaction, view)

    async def _navigate_to_previous_view(self, interaction: discord.Interaction, view):
        """Navigate to the previous view if available."""
        try:
            previous_embed = view.previous_view.current_embed
            if previous_embed:
                await interaction.response.edit_message(embed=previous_embed, view=view.previous_view)
                logger.info(f"✅ Successfully navigated to previous view")
            else:
                await self._navigate_to_home(interaction, view)
        except Exception as e:
            logger.error(f"❌ Failed to navigate to previous view: {e}")
            await self._navigate_to_home(interaction, view)

    async def _navigate_to_home(self, interaction: discord.Interaction, view):
        """Navigate to the home canvas view."""
        try:
            # Check required functions
            if not _build_canvas_home or not _build_canvas_embed:
                raise ImportError("Home view functions not available")
            
            # Get correct server_id from guild
            server_id = get_server_key(view.guild) if view.guild else "default"
            
            # Build home content
            content = _build_canvas_home(
                view.agent_config,
                "Canvas",
                "No Canvas",
                "Welcome",
                "No Welcome",
                "!canvas",
                "!talk",
                view.admin_visible,
                server_id,
                view.author_id,
                view.guild,
                False
            )
            
            # Use CanvasNavigationView instead of CanvasHomeView for home navigation
            CanvasNavigationView = globals().get('CanvasNavigationView')
            if not CanvasNavigationView:
                raise ImportError("CanvasNavigationView class not available")
            
            # Build complete sections for home navigation
            from discord_bot.canvas.content import _build_canvas_sections
            complete_sections = _build_canvas_sections(
                view.agent_config, 
                "Canvas", 
                "No Canvas", 
                "Welcome", 
                "No Welcome",
                "!canvas", 
                "!talk", 
                view.admin_visible,
                server_id,
                view.author_id,
                view.guild,
                False
            )
            
            home_view = CanvasNavigationView(
                view.author_id,
                complete_sections,  # Pass complete sections for full navigation
                view.admin_visible,
                view.agent_config,
                guild=view.guild,
                message=interaction.message,
                show_dropdown=False
            )
            
            # Build embed using _build_canvas_embed
            home_embed = _build_canvas_embed("home", content, view.admin_visible)
            await interaction.response.edit_message(embed=home_embed, view=home_view)
            logger.info(f"✅ Successfully navigated to home")
        except Exception as e:
            logger.error(f"❌ Navigation to home failed: {e}")
            await _safe_send_interaction_message(interaction, "❌ Unable to navigate back.", ephemeral=True)


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
        
        # Get current guild from interaction to ensure correct server context
        guild = interaction.guild
        if not guild:
            await _safe_send_interaction_message(interaction, "❌ This command is only available in a server.", ephemeral=True)
            return
        
        # Rebuild sections with current guild context to ensure correct server data
        server_id = get_server_key(guild) if get_server_key else str(guild.id)
        author_id = view.author_id
        admin_visible = view.admin_visible
        
        # Rebuild home content with current server context
        from .content import _build_canvas_home
        home_content = _build_canvas_home(
            view.agent_config,
            "Canvas",
            "No Canvas",
            "Welcome",
            "No Welcome",
            "!canvas",
            "!talk",
            admin_visible,
            server_id,
            author_id,
            guild,
            False
        )
        
        if not home_content:
            await _safe_send_interaction_message(interaction, "❌ The Canvas home is not available.", ephemeral=True)
            return
        
        CanvasNavigationView = globals().get('CanvasNavigationView')
        if CanvasNavigationView is None:
            await _safe_send_interaction_message(interaction, "❌ Navigation not available.", ephemeral=True)
            return
        
        # Build complete sections for proper navigation
        from .content import _build_canvas_sections
        complete_sections = _build_canvas_sections(
            view.agent_config,
            "Canvas",
            "No Canvas",
            "Welcome",
            "No Welcome",
            "!canvas",
            "!talk",
            admin_visible,
            server_id,
            author_id,
            guild,
            False
        )
        
        nav_view = CanvasNavigationView(view.author_id, complete_sections, view.admin_visible, view.agent_config, guild=guild, show_dropdown=False)
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
logger = core.logger
PERSONALITY = core.PERSONALITY
AGENT_CFG = core.AGENT_CFG

try:
    from discord_bot.discord_utils import (
        set_greeting_enabled,
        is_role_enabled_check, get_server_key, set_role_enabled, is_admin
    )
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None


try:
    from roles.trickster.subroles.dice_game.dice_game import DiceGame
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
    set_greeting_enabled = None
    is_role_enabled_check = None
    get_server_key = None
    set_role_enabled = None
    get_news_watcher_db_instance = None
    get_roles_db_instance = None
    DiceGame = None
    get_behavior_db_instance = None
    
    # Core fallbacks
    _discord_cfg = {}
    _personality_name = "Unknown"
    _bot_display_name = "Bot"
    _insult_cfg = {}
    _personality_answers = {}


# Load descriptions directly if import failed
if not _personality_descriptions:
    try:
        import json
        from pathlib import Path
        import os
        
        def _get_personality_dir():
            """Get the current personality directory dynamically."""
            try:
                personality_rel = AGENT_CFG.get("personality", "personalities/putre/personality.json")
                personality_path = Path(__file__).parent.parent.parent / personality_rel
                return personality_path.parent
            except:
                # Fallback to putre if something goes wrong
                return Path(__file__).parent.parent.parent / "personalities" / "putre"
        
        descriptions_path = _get_personality_dir() / "descriptions.json"
        if descriptions_path.exists():
            with open(descriptions_path, 'r', encoding='utf-8') as f:
                _personality_descriptions = json.load(f)
    except Exception:
        _personality_descriptions = {}

try:
    from roles.trickster.subroles.dice_game.dice_game import process_play
except Exception:
    process_play = None

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
from .canvas_news_watcher import (
    build_canvas_role_news_watcher_detail as _build_canvas_role_news_watcher_detail,
    CanvasWatcherMethodSelect as _CanvasWatcherMethodSelect,
    CanvasWatcherSubscriptionSelect as _CanvasWatcherSubscriptionSelect,
    CanvasWatcherAdminMethodSelect as _CanvasWatcherAdminMethodSelect,
    CanvasWatcherAdminActionSelect as _CanvasWatcherAdminActionSelect,
    CanvasWatcherSubscribeModal as _CanvasWatcherSubscribeModal,
    CanvasWatcherAddModal as _CanvasWatcherAddModal,
    CanvasWatcherDeleteModal as _CanvasWatcherDeleteModal,
    CanvasWatcherListModal as _CanvasWatcherListModal,
    CanvasWatcherChannelSubscribeModal as _CanvasWatcherChannelSubscribeModal,
    CanvasWatcherChannelUnsubscribeModal as _CanvasWatcherChannelUnsubscribeModal,
    CanvasWatcherPersonalUnsubscribeModal as _CanvasWatcherPersonalUnsubscribeModal,
    CanvasWatcherFrequencyModal as _CanvasWatcherFrequencyModal,
    CanvasWatcherFeedsByCategoryModal as _CanvasWatcherFeedsByCategoryModal,
    handle_canvas_watcher_action as _CanvasHandleWatcherAction,
)
from .canvas_trickster import (
    build_canvas_role_trickster_detail as _build_canvas_role_trickster_detail,
    TricksterActionModal as _TricksterActionModal,
    RuneCastingModal as _RuneCastingModal,
    handle_canvas_runes_action as _HandleCanvasRunesAction,
    handle_canvas_trickster_action as _HandleCanvasTricksterAction,
)
from .canvas_treasure_hunter import (
    Poe2ItemModal as _Poe2ItemModal,
    handle_canvas_treasure_hunter_action as _HandleCanvasTreasureHunterAction,
)
from .canvas_banker import (
    BankerConfigModal as _BankerConfigModal,
    handle_canvas_banker_action as _HandleCanvasBankerAction,
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
        guild = interaction.guild or view.guild
        if guild:
            server_id = get_server_key(guild) if get_server_key else str(guild.id)
            refreshed_sections = _build_canvas_sections(
                view.agent_config,
                "Canvas",
                "No Canvas",
                "Welcome",
                "No Welcome",
                "!canvas",
                "!talk",
                view.admin_visible,
                server_id,
                view.author_id,
                guild,
                False
            )
            view.sections = refreshed_sections
            view.guild = guild
        selected = self.values[0]
        if selected == "roles":
            roles_content = view.sections.get("roles")
            if not roles_content:
                await interaction.response.send_message("❌ This Canvas section is not available.", ephemeral=True)
                return
            roles_view = CanvasRolesView(view.author_id, view.agent_config, view.admin_visible, view.sections, guild=interaction.guild)
            roles_embed = _build_canvas_embed("roles", roles_content, view.admin_visible)
            roles_view.current_embed = roles_embed  # Store embed for back navigation
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
        enabled_roles = _get_enabled_roles(view.agent_config, interaction.guild)
        
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
            guild=view.guild or interaction.guild,  # Fallback to interaction guild if view guild is None
            message=interaction.message,  # Add message reference
            watcher_selected_method=getattr(view, 'watcher_selected_method', None),
            watcher_last_action=getattr(view, 'watcher_last_action', None)
        )
        detail_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, detail_name, None, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


class CanvasRoleActionSelect(discord.ui.Select):
    def __init__(self, role_name: str, detail_name: str, admin_visible: bool, agent_config: dict | None = None):
        action_items = _get_canvas_role_action_items_for_detail(role_name, detail_name, admin_visible, agent_config)
        
        # Handle both 3-tuple and 4-tuple formats
        options = []
        for item in action_items:
            if len(item) == 4:  # (label, value, description, emoji)
                label, value, description, emoji = item
                options.append(discord.SelectOption(label=label, value=value, description=description, emoji=emoji))
            else:  # (label, value, description) - backward compatibility
                label, value, description = item
                options.append(discord.SelectOption(label=label, value=value, description=description))
        
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
            await interaction.response.send_modal(TricksterActionModal(action_name, view.author_id, interaction.guild, view.admin_visible, view))
            return
        if self.role_name == "trickster" and action_name in {"dice_play", "dice_ranking", "dice_history", "dice_help"}:
            # For dice actions, allow DM execution by using default server
            await _handle_canvas_dice_action(interaction, action_name, view)
            return
        if self.role_name == "trickster" and action_name in {"runes_single", "runes_three", "runes_cross", "runes_runic_cross"}:
            if not interaction.guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return
            
            # Check if runes subrole is enabled
            runes_enabled = False
            if view.agent_config:
                runes_enabled = view.agent_config.get("roles", {}).get("trickster", {}).get("subroles", {}).get("nordic_runes", {}).get("enabled", False)
            
            if not runes_enabled:
                await interaction.response.send_message("❌ Nordic Runes subrole is currently disabled. Contact an administrator to enable this feature.", ephemeral=True)
                return
            
            await interaction.response.send_modal(RuneCastingModal(action_name, view.author_id, interaction.guild))
            return
        if self.role_name == "trickster" and action_name.startswith("runes_"):
            # Allow runes actions in DM by using default guild
            await _handle_canvas_runes_action(interaction, action_name, view)
            return
        if self.role_name == "news_watcher" and action_name in {"method_flat", "method_keyword", "method_general", "watcher_run_now", "watcher_run_personal"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This watcher option is admin-only.", ephemeral=True)
                return
            await _handle_canvas_watcher_action(interaction, action_name, view)
            return
        if self.role_name == "trickster" and action_name in {"announcements_on", "announcements_off", "ring_on", "ring_off", "beggar_on", "beggar_off", "beggar_force_minigame", "runes_on", "runes_off"}:
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
                await interaction.response.send_message("❌ Mission commentary feature is currently disabled.", ephemeral=True)
                return
            except Exception as e:
                logger.error(f"Error in commentary action: {e}")
                await interaction.response.send_message("❌ Failed to process commentary. Check logs for details.", ephemeral=True)
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

    def __init__(self, author_id: int, sections: dict[str, str], admin_visible: bool, agent_config: dict, guild=None, message=None, show_dropdown=True):
        super().__init__(timeout=600)  # 10 minutes instead of 10
        self.author_id = author_id
        self.sections = sections
        self.admin_visible = admin_visible
        self.agent_config = agent_config
        self.guild = guild  # Store guild for role detail views
        self.message = message  # Store the message to delete it later
        if show_dropdown:
            self.add_item(CanvasSectionSelect(admin_visible))
        
        # Start the timeout timer
        self._reset_timeout()

    async def on_timeout(self) -> None:
        """Called when the view times out - delete the entire message."""
        await _cleanup_canvas_view_on_timeout(self, "Canvas sections")

    async def _show_section(self, interaction: discord.Interaction, section_name: str):
        guild = interaction.guild or self.guild
        if guild:
            server_id = get_server_key(guild) if get_server_key else str(guild.id)
            refreshed_sections = _build_canvas_sections(
                self.agent_config,
                "Canvas",
                "No Canvas",
                "Welcome",
                "No Welcome",
                "!canvas",
                "!talk",
                self.admin_visible,
                server_id,
                self.author_id,
                guild,
                False
            )
            self.sections = refreshed_sections
            self.guild = guild
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
        guild = interaction.guild or self.guild
        if guild:
            server_id = get_server_key(guild) if get_server_key else str(guild.id)
            self.sections = _build_canvas_sections(
                self.agent_config,
                "Canvas",
                "No Canvas",
                "Welcome",
                "No Welcome",
                "!canvas",
                "!talk",
                self.admin_visible,
                server_id,
                self.author_id,
                guild,
                False
            )
            self.guild = guild
        roles_content = self.sections.get("roles")
        if not roles_content:
            await _safe_send_interaction_message(interaction, "❌ This Canvas section is not available.", ephemeral=True)
            return
        roles_view = CanvasRolesView(self.author_id, self.agent_config, self.admin_visible, self.sections, guild=interaction.guild)
        roles_view.message = interaction.message
        roles_embed = _build_canvas_embed("roles", roles_content, self.admin_visible)
        roles_view.current_embed = roles_embed  # Store embed for back navigation
        await _safe_edit_interaction_message(interaction, content=None, embed=roles_embed, view=roles_view)
        # Set the message reference for timeout deletion
        roles_view.message = interaction.message

    button_behavior = _personality_descriptions.get("canvas_home_messages", {}).get("button_behavior", "Behavior")
    @discord.ui.button(label=button_behavior, style=discord.ButtonStyle.success)
    async def behavior_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild or self.guild
        if guild:
            server_id = get_server_key(guild) if get_server_key else str(guild.id)
            self.sections = _build_canvas_sections(
                self.agent_config,
                "Canvas",
                "No Canvas",
                "Welcome",
                "No Welcome",
                "!canvas",
                "!talk",
                self.admin_visible,
                server_id,
                self.author_id,
                guild,
                False
            )
            self.guild = guild
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

    def __init__(self, author_id: int, agent_config: dict, admin_visible: bool, sections: dict[str, str], message=None, guild=None):
        super().__init__(timeout=600)  # 10 minutes
        self.author_id = author_id
        self.agent_config = agent_config
        self.admin_visible = admin_visible
        self.sections = sections
        self.message = message  # Store the message to delete it later
        self.guild = guild
        self.current_embed = None  # Store current embed for back navigation
        self._add_role_buttons()
        
        # Start the timeout timer
        self._reset_timeout()

    async def on_timeout(self) -> None:
        """Called when the view times out - delete the entire message."""
        await _cleanup_canvas_view_on_timeout(self, "Canvas roles")

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
        for role_name in _get_enabled_roles(self.agent_config, getattr(self, 'guild', None)):
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
            previous_view=view  # Pass current CanvasRolesView as previous_view for back navigation
        )
        detail_view.message = interaction.message
        role_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, "overview", None, detail_view.auto_response_preview)
        detail_view.current_embed = role_embed
        await interaction.response.edit_message(content=None, embed=role_embed, view=detail_view)
        # Set the message reference for timeout deletion
        detail_view.message = interaction.message


class CanvasRoleDetailButton(discord.ui.Button):
    """Button that opens one detail view inside a role."""

    def __init__(self, label: str, role_name: str, detail_name: str):
        # Ensure detail_name is a string to prevent AttributeError
        if not isinstance(detail_name, str):
            detail_name = str(detail_name)
        
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
            previous_view=view  # Pass current view as previous_view for back navigation
        )
        next_view.message = interaction.message
        detail_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, self.detail_name, None, next_view.auto_response_preview)
        next_view.current_embed = detail_embed
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
            previous_view=view  # Pass current view as previous_view for back navigation
        )
        next_view.message = interaction.message
        detail_embed = _build_canvas_role_embed("treasure_hunter", content, view.admin_visible, detail_name, None, next_view.auto_response_preview)
        next_view.current_embed = detail_embed
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)
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


TricksterActionModal = _TricksterActionModal


async def _handle_canvas_watcher_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    return await _CanvasHandleWatcherAction(interaction, action_name, view)


async def _handle_canvas_trickster_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    return await _HandleCanvasTricksterAction(interaction, action_name, view)


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
        
        # Get the user's last server or first available as default
        try:
            from agent_db import get_user_last_server_id
            bot = interaction.client
            
            # Try to get user's last server first
            user_id = str(interaction.user.id)
            last_server_id = get_user_last_server_id(user_id)
            
            if last_server_id:
                # Find the guild object for this server ID
                guild = discord.utils.get(bot.guilds, id=int(last_server_id))
                if guild:
                    logger.info(f"Using user's last server '{guild.name}' ({guild.id}) for Canvas action from DM")
                    dm_message = messages_source.get("dm_default_server_message", "*Continuing from your last server interaction.*")
                else:
                    # Server not found in bot's guilds, fall back to first available
                    if bot.guilds:
                        guild = bot.guilds[0]
                        logger.info(f"User's last server not found, using default server '{guild.name}' for Canvas action from DM")
                        dm_message = messages_source.get("dm_default_server_message", "*Your last server is unavailable, using the first available server.*")
                    else:
                        await interaction.response.send_message("❌ No servers available.", ephemeral=True)
                        return None, []
            else:
                # No last server found, use first available
                if bot and bot.guilds:
                    guild = bot.guilds[0]
                    logger.info(f"No user history found, using default server '{guild.name}' for Canvas action from DM")
                    dm_message = messages_source.get("dm_default_server_message", "*No previous server found, using the first available server.*")
                else:
                    await interaction.response.send_message("❌ No servers available.", ephemeral=True)
                    return None, []
                
            # Add DM notification
            content_parts.extend([
                messages_source.get("dm_default_server_title", "🔔 **Using server: {server_name}**").format(server_name=guild.name),
                dm_message,
                messages_source.get("dm_default_server_separator", "─────────────────────────────────────────────"),
                ""
            ])
        except Exception as e:
            logger.error(f"Could not get server for DM Canvas action: {e}")
            error_msg = messages_source.get("dm_server_access_error", "❌ Could not access a server. Please execute actions from a server.")
            await interaction.response.send_message(error_msg, ephemeral=True)
            return None, []
    
    return guild, content_parts


async def _handle_canvas_dice_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    """Handle dice game actions with dynamic content display."""
    if get_roles_db_instance is None or get_roles_db_instance is None or DiceGame is None:
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
            db_dice = get_roles_db_instance(server_key)
            from roles.banker.banker_db import get_banker_roles_db_instance
            db_banker_roles = get_banker_roles_db_instance(server_key)
            
            # Get or create player wallet
            player_id = str(interaction.user.id)
            player_name = interaction.user.display_name
            db_banker_roles.create_wallet(player_id, player_name, 'user')
            db_banker_roles.create_wallet("dice_game_pot", "Dice Game Pot", wallet_type='system')
            
            # Check balance
            player_balance = db_banker_roles.get_balance(player_id)
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
                result = process_play(player_id, player_name, guild.name, dice_state['pot_balance'], server_key) if process_play else {"success": False, "message": "Dice game unavailable."}
                
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
                    new_player_balance = db_banker_roles.get_balance(player_id)
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
            db_dice = get_roles_db_instance(server_key)
            history = db_dice.get_dice_game_history(10)
            historytitle = descriptions.get("history", "**📜 DICE HISTORY**")
            content_parts.append(historytitle)
            content_parts.append("─" * 45)
            
            if history:
                for record in history:
                    # Parse dictionary: {'id': ..., 'user_id': ..., 'user_name': ..., 'dice': ..., 'combination': ..., 'prize': ..., 'created_at': ...}
                    user_name = record.get('user_name', 'Unknown')
                    dice = record.get('dice', '')
                    combination = record.get('combination', '')
                    prize = record.get('prize', 0)
                    
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
        # Redirect to dice_game detail view instead of showing help
        content = _build_canvas_role_detail_view(
            "trickster",
            "dice",
            view.agent_config,
            view.admin_visible,
            guild,
            view.author_id,
        )
        if not content:
            await _safe_send_interaction_message(interaction, "❌ Dice game view is not available.", ephemeral=True)
            return

        # Store current embed in view for back navigation
        role_embed = _build_canvas_role_embed("trickster", content, view.admin_visible, "dice", None, "Redirected to dice game")
        view.current_embed = role_embed
        
        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name="trickster",
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail="dice",
            guild=guild,  # Use the determined guild (default or original)
            previous_view=view,  # Pass current view as previous_view
        )
        next_view.current_embed = role_embed
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
        return
    
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
    return await _HandleCanvasTreasureHunterAction(interaction, action_name, view)


async def _handle_canvas_banker_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    return await _HandleCanvasBankerAction(interaction, action_name, view)


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
        await _cleanup_canvas_view_on_timeout(self, "Canvas behavior")


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
        # Validate guild parameter
        if guild is None or not hasattr(guild, 'id'):
            logger.warning(f"CanvasRoleDetailView: invalid guild parameter (type: {type(guild)}, value: {guild})")
            self.guild = None
        else:
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
                self.add_item(CanvasRoleActionSelect(role_name, current_detail, admin_visible, self.agent_config))
            # For other roles, create action dropdown
            else:
                self.add_item(CanvasRoleActionSelect(role_name, current_detail, admin_visible, self.agent_config))
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
        
        await _cleanup_canvas_view_on_timeout(self, "Canvas role detail")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive Canvas to its original user."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True


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


def _get_enabled_roles(agent_config: dict, guild=None) -> list[str]:
    roles_cfg = (agent_config or {}).get("roles", {})
    ordered_roles = ["news_watcher", "treasure_hunter", "trickster", "banker", "mc"]
    discovered_roles = [role_name for role_name, cfg in roles_cfg.items() if isinstance(cfg, dict) and role_name not in ordered_roles]
    enabled: list[str] = []

    for role_name in ordered_roles + discovered_roles:
        try:
            if is_role_enabled_check(role_name, agent_config, guild):
                enabled.append(role_name)
        except Exception as error:
            logger.warning(f"Could not resolve Canvas enabled state for role {role_name}: {error}")
            cfg = roles_cfg.get(role_name, {})
            if isinstance(cfg, dict) and cfg.get("enabled", False):
                enabled.append(role_name)

    return enabled


def _load_role_mission_prompts(role_names: list[str]) -> list[str]:
    prompts: list[str] = []
    role_prompts_cfg = PERSONALITY.get("roles", {})

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


CanvasWatcherMethodSelect = _CanvasWatcherMethodSelect
CanvasWatcherSubscriptionSelect = _CanvasWatcherSubscriptionSelect
CanvasWatcherAdminMethodSelect = _CanvasWatcherAdminMethodSelect
CanvasWatcherAdminActionSelect = _CanvasWatcherAdminActionSelect
CanvasWatcherSubscribeModal = _CanvasWatcherSubscribeModal
CanvasWatcherAddModal = _CanvasWatcherAddModal
CanvasWatcherDeleteModal = _CanvasWatcherDeleteModal
CanvasWatcherListModal = _CanvasWatcherListModal
CanvasWatcherChannelSubscribeModal = _CanvasWatcherChannelSubscribeModal
CanvasWatcherChannelUnsubscribeModal = _CanvasWatcherChannelUnsubscribeModal
CanvasWatcherPersonalUnsubscribeModal = _CanvasWatcherPersonalUnsubscribeModal
CanvasWatcherFrequencyModal = _CanvasWatcherFrequencyModal
CanvasWatcherFeedsByCategoryModal = _CanvasWatcherFeedsByCategoryModal
_handle_canvas_watcher_action = _CanvasHandleWatcherAction
Poe2ItemModal = _Poe2ItemModal
RuneCastingModal = _RuneCastingModal
_handle_canvas_runes_action = _HandleCanvasRunesAction
BankerConfigModal = _BankerConfigModal



