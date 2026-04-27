"""Canvas Discord UI components."""

import os
import asyncio
import discord
import json
import random
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
    from discord_bot.discord_utils import translate_dice_combination
    from .canvas_behavior import (
        get_canvas_behavior_action_items_for_detail as _get_canvas_behavior_action_items_for_detail,
        get_canvas_behavior_detail_items as _get_canvas_behavior_detail_items,
        build_canvas_behavior_detail as _build_canvas_behavior_detail,
    )
    if logger:
        logger.debug("✅ Canvas content functions imported successfully")
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

# Import Canvas base classes
from .canvas_base import CanvasModal


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
        server_id = get_server_key(self.guild) if self.guild else None
        personality_descriptions = _get_personality_descriptions(server_id)
        button_label = label or personality_descriptions.get("canvas_home_messages", {}).get("button_back", "Back")
        
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
        server_id = get_server_key(self.guild) if self.guild else None
        personality_descriptions = _get_personality_descriptions(server_id)
        button_label = label or personality_descriptions.get("canvas_home_messages", {}).get("button_back", "Back")
        
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
        
        # Handle CanvasBehaviorView with personality detail - go back to conversation
        if isinstance(view, CanvasBehaviorView) and view.current_detail == "personality":
            logger.info(f"🔧 Behavior personality view -> conversation")
            from .canvas_behavior import build_canvas_behavior_detail
            from .content import _build_canvas_behavior_embed
            title, description, content = build_canvas_behavior_detail("conversation", view.admin_visible, view.guild, view.agent_config, author_id=str(view.author_id)) or (None, None, "")
            if content:
                behavior_view = CanvasBehaviorView(
                    author_id=view.author_id,
                    sections=view.sections,
                    admin_visible=view.admin_visible,
                    agent_config=view.agent_config,
                    current_detail="conversation",
                    guild=view.guild,
                )
                behavior_embed = _build_canvas_behavior_embed(content, view.admin_visible, None, title, description)
                await interaction.response.edit_message(content=None, embed=behavior_embed, view=behavior_view)
                behavior_view.message = interaction.message
            else:
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
                        detail_view.auto_response_preview,
                        server_id=get_server_key(view.guild) if view.guild else None
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
                        detail_view.auto_response_preview,
                        server_id=get_server_key(view.guild) if view.guild else None
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
                main_view.auto_response_preview,
                server_id=get_server_key(interaction.guild) if interaction.guild else None
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

            # Get correct server_id from guild or active server
            from agent_db import get_server_id
            server_id = get_server_key(view.guild) if view.guild else get_server_id()

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
            
            # Build embed using _build_canvas_embed (server_id already resolved above)
            home_embed = _build_canvas_embed("home", content, view.admin_visible, server_id=server_id)
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
        server_id = get_server_key(self.guild) if self.guild else None
        personality_descriptions = _get_personality_descriptions(server_id)
        button_label = label or personality_descriptions.get("canvas_home_messages", {}).get("button_home", "Home")
        
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
        
        home_embed = _build_canvas_embed("home", home_content, view.admin_visible, server_id=server_id)
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
    
    # Get variables from core
    _discord_cfg = core._discord_cfg
    _personality_name = core._personality_name
    _insult_cfg = core._insult_cfg
    _personality_answers = core._personality_answers
    from agent_engine import _personality_descriptions
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
    
    # Core fallbacks
    _discord_cfg = {}
    _personality_name = "Unknown"
    _insult_cfg = {}
    _personality_answers = {}


# Dynamic descriptions loading function
def _get_personality_descriptions(server_id: str = None) -> dict:
    """
    Get personality descriptions from server-specific or global directory.
    
    Args:
        server_id: Discord server ID for server-specific descriptions
        
    Returns:
        dict: Personality descriptions loaded from descriptions.json
    """
    if not server_id:
        return {}
    try:
        import json
        from pathlib import Path
        from discord_bot.db_init import get_server_personality_dir
        server_dir = get_server_personality_dir(server_id)
        if server_dir:
            server_path = Path(server_dir)
            descriptions_path = server_path / "descriptions.json"
            if descriptions_path.exists():
                with open(descriptions_path, 'r', encoding='utf-8') as f:
                    data = json.load(f).get("discord", {})
                sub_dir = server_path / "descriptions"
                if sub_dir.exists():
                    if "role_descriptions" not in data:
                        data["role_descriptions"] = {}
                    for sub_file in sub_dir.glob("*.json"):
                        role_key = sub_file.stem
                        try:
                            with open(sub_file, 'r', encoding='utf-8') as f:
                                sub_data = json.load(f)
                            data["role_descriptions"][role_key] = sub_data
                        except Exception:
                            pass
                return data
    except Exception as e:
        if logger:
            logger.debug(f"Could not load descriptions for server {server_id}: {e}")
    return {}

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
from .canvas_juggler import JugglerActionModal
from .canvas_news_watcher import (
    build_canvas_role_news_watcher_detail as _build_canvas_role_news_watcher_detail,
    CanvasWatcherSubscriptionSelect as _CanvasWatcherSubscriptionSelect,
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
    handle_canvas_trickster_action as _HandleCanvasTricksterAction,
)
from .canvas_shaman import (
    RuneCastingModal as _RuneCastingModal,
    handle_canvas_shaman_action as _HandleCanvasShamanAction,
)
from .canvas_scholar import (
    handle_canvas_scholar_action as _HandleCanvasScholarAction,
)
from .canvas_treasure_hunter import (
    Poe2ItemModal as _Poe2ItemModal,
    Poe2PurchaseLiquidateView as _Poe2PurchaseLiquidateView,
    Poe2PurchaseItemSelectView as _Poe2PurchaseItemSelectView,
    handle_canvas_treasure_hunter_action as _HandleCanvasTreasureHunterAction,
)
from .canvas_banker import (
    BankerConfigModal as _BankerConfigModal,
    BeggarFrequencyModal as _BeggarFrequencyModal,
    handle_canvas_banker_action as _HandleCanvasBankerAction,
)
from .canvas_personality import (
    CanvasPersonalityView,
    build_canvas_personality_content,
)

class CanvasSectionSelect(discord.ui.Select):
    def __init__(self, admin_visible: bool, server_id: str = None):
        # Get personalized labels from descriptions.json (server-specific if available)
        personality_descriptions = _get_personality_descriptions(server_id)
        canvas_home = personality_descriptions.get("canvas_home_messages", {})
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
            roles_view = CanvasRolesView(view.author_id, view.agent_config, view.admin_visible, view.sections, guild=guild, current_page=1, roles_per_page=5)
            server_id = get_server_key(guild) if guild else None
            roles_embed = _build_canvas_embed("roles", roles_content, view.admin_visible, server_id=server_id)
            roles_view.current_embed = roles_embed  # Store embed for back navigation
            await interaction.response.edit_message(content=None, embed=roles_embed, view=roles_view)
            # Set the message reference for timeout deletion
            roles_view.message = interaction.message
            return
        if selected == "behavior":
            guild = interaction.guild or view.guild
            result = _build_canvas_behavior_detail("conversation", view.admin_visible, guild, view.agent_config, author_id=str(view.author_id))
            if not result:
                await interaction.response.send_message("❌ This Canvas section is not available.", ephemeral=True)
                return
            b_title, b_description, b_content = result
            behavior_view = CanvasBehaviorView(view.author_id, view.sections, view.admin_visible, view.agent_config, current_detail="conversation", guild=guild)
            behavior_embed = _build_canvas_behavior_embed(b_content, view.admin_visible, title=b_title, description=b_description)
            await interaction.response.edit_message(content=None, embed=behavior_embed, view=behavior_view)
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
            "shaman": ("Shaman", "Nordic runes and mystical guidance"),
            "mc": ("MC", "Music and queue controls"),
            "scholar": ("Scholar", "Knowledge and archives"),
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
        role_embed = _build_canvas_role_embed(role_name, content, view.admin_visible, "overview", interaction.user, detail_view.auto_response_preview, server_id=get_server_key(interaction.guild) if interaction.guild else None)
        await interaction.response.edit_message(content=None, embed=role_embed, view=detail_view)
        # Set the message reference for timeout deletion
        detail_view.message = interaction.message

    async def _handle_list_option(self, interaction: discord.Interaction, view):
        """Handle the 'list' option to show all available roles."""
        # Filter roles that are enabled in agent_config globally
        # Roles disabled in agent_config should not appear at all (like they don't exist)
        # Also filter out subroles (beggar is a subrole of banker)
        roles_cfg = (view.agent_config or {}).get("roles", {})
        all_roles = [
            role for role in ["news_watcher", "treasure_hunter", "trickster", "banker", "shaman", "mc", "scholar"]
            if roles_cfg.get(role, {}).get("enabled", False)
        ]
        enabled_roles = _get_enabled_roles(view.agent_config, interaction.guild)
        
        role_labels = {
            "news_watcher": ("Watcher", "Alerts and subscriptions"),
            "treasure_hunter": ("Treasure Hunter", "Tracked item opportunities"),
            "trickster": ("Trickster", "Subroles and player surfaces"),
            "banker": ("Banker", "Wallet and economy"),
            "shaman": ("Shaman", "Nordic runes and mystical guidance"),
            "mc": ("MC", "Music and queue controls"),
            "scholar": ("Scholar", "Knowledge and archives"),
        }
        
        embed = discord.Embed(
            title="📋 All Available Roles",
            description="Complete list of available roles and their status",
            color=discord.Color.blue()
        )

        # Get localized labels
        server_id = get_server_key(interaction.guild) if interaction.guild else None
        general = _get_personality_descriptions(server_id).get("general", {})
        action_labels = general.get("action_labels", {})
        label_enabled = action_labels.get("enabled", "Enabled")
        label_disabled = action_labels.get("disabled", "Disabled")

        for role_name in all_roles:
            label, description = role_labels.get(role_name, (role_name.replace("_", " ").title(), "Role surface"))
            status = f"✅ {label_enabled}" if role_name in enabled_roles else f"❌ {label_disabled}"
            embed.add_field(
                name=f"{label} {status}",
                value=description,
                inline=False
            )
        
        await interaction.response.edit_message(embed=embed, view=view)


class CanvasRoleDetailSelect(discord.ui.Select):
    def __init__(self, role_name: str, admin_visible: bool, server_id: str = None, agent_config: dict = None):
        options = [
            discord.SelectOption(label=label, value=detail_name, description=f"Focus on {label.lower()} tasks")
            for label, detail_name in _get_canvas_role_detail_items(role_name, None, admin_visible, role_name, server_id, agent_config)
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
        detail_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, detail_name, None, next_view.auto_response_preview, server_id=get_server_key(interaction.guild) if interaction.guild else None)
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


class CanvasRoleActionSelect(discord.ui.Select):
    def __init__(self, role_name: str, detail_name: str, admin_visible: bool, agent_config: dict | None = None, guild=None):
        # Use server-specific descriptions if guild is provided
        server_id = get_server_key(guild) if guild else None
        action_items = _get_canvas_role_action_items_for_detail(role_name, detail_name, admin_visible, agent_config, server_id)

        # Handle both 3-tuple and 4-tuple formats
        options = []
        for item in action_items:
            if len(item) == 4:  # (label, value, description, emoji)
                label, value, description, emoji = item
                options.append(discord.SelectOption(label=label, value=value, description=description, emoji=emoji))
            else:  # (label, value, description) - backward compatibility
                label, value, description = item
                options.append(discord.SelectOption(label=label, value=value, description=description))
        generic_option_label = _get_personality_descriptions(server_id).get("canvas_home_messages", {}).get("generic_option_label", "Choose a concrete option...")
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
        # Effective guild: use interaction guild when in-server, fall back to the
        # view's resolved guild (e.g. user's last server) when in DM.
        eff_guild = interaction.guild or getattr(view, 'guild', None)
        if self.role_name == "banker" and action_name in {"config_tae", "config_bonus"}:
            if not view.admin_visible:
                await interaction.response.send_message("❌ This banker option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(BankerConfigModal(action_name, view.author_id, eff_guild))
            return
        if self.role_name == "banker" and action_name == "beggar_donate":
            if not eff_guild:
                await interaction.response.send_message("❌ Donations are only available in a server.", ephemeral=True)
                return
            # Open donation modal
            from .canvas_banker import BeggarDonationModal as _BeggarDonationModal
            await interaction.response.send_modal(_BeggarDonationModal(eff_guild, view.author_id, view))
            return
        if action_name == "watcher_frequency":
            if not view.admin_visible:
                await interaction.response.send_message("❌ This role option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(RoleFrequencyModal(self.role_name, action_name, view.agent_config, view, view.author_id))
            return
        if self.role_name == "treasure_hunter" and action_name in {"poe2_item_add", "poe2_item_remove"}:
            # Check if treasure_hunter is enabled globally in agent_config
            th_global_enabled = (view.agent_config or {}).get("roles", {}).get("treasure_hunter", {}).get("enabled", False)
            if not th_global_enabled:
                from .content import _get_personality_descriptions
                server_id = str(interaction.guild.id) if interaction.guild else None
                descriptions = _get_personality_descriptions(server_id)
                treasure_translations = descriptions.get("treasure_hunter", {}).get("poe2", {})
                error_message = treasure_translations.get("poe2_not_enabled_globally", "❌ Treasure Hunter is not enabled globally.")
                await interaction.response.send_message(error_message, ephemeral=True)
                return
            # Allow POE2 item operations in DM (use view's resolved guild as fallback)
            await interaction.response.send_modal(Poe2ItemModal(action_name, view.author_id, eff_guild, view))
            return
        if self.role_name == "treasure_hunter" and action_name in {"poe2_purchase_add", "poe2_purchase_remove"}:
            # Check if treasure_hunter is enabled globally in agent_config
            th_global_enabled = (view.agent_config or {}).get("roles", {}).get("treasure_hunter", {}).get("enabled", False)
            if not th_global_enabled:
                from .content import _get_personality_descriptions
                server_id = str(interaction.guild.id) if interaction.guild else None
                descriptions = _get_personality_descriptions(server_id)
                treasure_translations = descriptions.get("treasure_hunter", {}).get("poe2", {})
                error_message = treasure_translations.get("poe2_not_enabled_globally", "❌ Treasure Hunter is not enabled globally.")
                await interaction.response.send_message(error_message, ephemeral=True)
                return
            # Allow POE2 purchase operations in DM (use view's resolved guild as fallback)
            guild = eff_guild
            if action_name == "poe2_purchase_add":
                # Get tracked items and prices for the Select view
                from roles.treasure_hunter.poe2.poe2_subrole_manager import get_poe2_manager
                manager = get_poe2_manager()
                if manager is None:
                    from .content import _get_personality_descriptions
                    server_id = str(interaction.guild.id) if interaction.guild else None
                    descriptions = _get_personality_descriptions(server_id)
                    treasure_translations = descriptions.get("treasure_hunter", {}).get("poe2", {})
                    error_message = treasure_translations.get("poe2_manager_not_available", "❌ POE2 manager is not available.")
                    await interaction.response.send_message(error_message, ephemeral=True)
                    return
                
                server_id = "" if guild is None else str(guild.id)
                user_id = str(view.author_id)
                league = manager.get_user_league(user_id, server_id)

                # Get tracked items from user's subscription for this server (not from global objectives)
                roles_db = manager._get_roles_db(server_id)
                subscription = roles_db.get_poe2_subscription(user_id, server_id)
                tracked_items = subscription.get('tracked_items', []) if subscription else []
                
                # Get current prices from POE2 manager's global price database
                current_prices = {}
                for item in tracked_items:
                    item_name = item.get('item_name', '')
                    item_id = item.get('item_id')
                    try:
                        # Get current price using new per-item table method
                        if item_id:
                            price_data = manager.get_latest_price_for_item(league, item_id)
                            if price_data:
                                current_price = price_data.get('price')
                                logger.info(f"Current price for {item_name} in {league}: {current_price}")
                                current_prices[item_name] = current_price
                            else:
                                logger.info(f"No price data found for {item_name} in {league}")
                        else:
                            logger.warning(f"Item ID not found for {item_name}")
                    except Exception as e:
                        logger.exception(f"Error getting price for {item_name}: {e}")
                logger.info(f"Final current_prices dict: {current_prices}")
                
                if tracked_items:
                    # Get translations for the message
                    from .content import _get_personality_descriptions
                    server_id = str(guild.id) if guild else None
                    descriptions = _get_personality_descriptions(server_id)
                    treasure_translations = descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("poe2", {})
                    select_message = treasure_translations.get("select_purchase_item_message", "Select an item to register a purchase:")
                    
                    await interaction.response.send_message(
                        select_message,
                        view=_Poe2PurchaseItemSelectView(view.author_id, guild, view, tracked_items, current_prices),
                        ephemeral=True
                    )
                else:
                    from .content import _get_personality_descriptions
                    server_id = str(guild.id) if guild else None
                    descriptions = _get_personality_descriptions(server_id)
                    treasure_translations = descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("poe2", {})
                    error_message = treasure_translations.get("no_tracked_items_error", "❌ No tracked items found. Add items to your tracking list first.")
                    await interaction.response.send_message(error_message, ephemeral=True)
            else:
                # Get purchases from user's subscription
                server_id = "" if guild is None else str(guild.id)
                user_id = str(view.author_id)
                from agent_roles_db import get_roles_db_instance
                roles_db = get_roles_db_instance(server_id)
                subscription = roles_db.get_poe2_subscription(user_id, server_id)
                purchases = subscription.get("purchases", []) if subscription else []

                if purchases:
                    from .content import _get_personality_descriptions
                    server_id_str = str(guild.id) if guild else None
                    descriptions = _get_personality_descriptions(server_id_str)
                    treasure_translations = descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("poe2", {})
                    select_message = treasure_translations.get("select_purchase_item_message", "Select a purchase to liquidate:")

                    await interaction.response.send_message(
                        select_message,
                        view=_Poe2PurchaseLiquidateView(view.author_id, guild, view, purchases),
                        ephemeral=True
                    )
                else:
                    from .content import _get_personality_descriptions
                    server_id_str = str(guild.id) if guild else None
                    descriptions = _get_personality_descriptions(server_id_str)
                    treasure_translations = descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("poe2", {})
                    error_message = treasure_translations.get("no_purchases", "❌ No purchases found.")
                    await interaction.response.send_message(error_message, ephemeral=True)
            return
        if self.role_name == "treasure_hunter" and action_name in {"league_standard", "league_fate_of_the_vaal", "league_hardcore"}:
            # Check if treasure_hunter is enabled globally in agent_config
            th_global_enabled = (view.agent_config or {}).get("roles", {}).get("treasure_hunter", {}).get("enabled", False)
            if not th_global_enabled:
                from .content import _get_personality_descriptions
                server_id = str(interaction.guild.id) if interaction.guild else None
                descriptions = _get_personality_descriptions(server_id)
                treasure_translations = descriptions.get("treasure_hunter", {}).get("poe2", {})
                error_message = treasure_translations.get("poe2_not_enabled_globally", "❌ Treasure Hunter is not enabled globally.")
                await interaction.response.send_message(error_message, ephemeral=True)
                return
            # Allow league changes in DM (user-specific setting)
            guild = interaction.guild  # Will be None in DM
            await _handle_canvas_treasure_hunter_action(interaction, action_name, view)
            return
        if self.role_name == "treasure_hunter" and action_name in {"poe2_on", "poe2_off"}:
            # Check if treasure_hunter is enabled globally in agent_config
            th_global_enabled = (view.agent_config or {}).get("roles", {}).get("treasure_hunter", {}).get("enabled", False)
            if not th_global_enabled:
                from .content import _get_personality_descriptions
                server_id = str(interaction.guild.id) if interaction.guild else None
                descriptions = _get_personality_descriptions(server_id)
                treasure_translations = descriptions.get("treasure_hunter", {}).get("poe2", {})
                error_message = treasure_translations.get("poe2_not_enabled_globally", "❌ Treasure Hunter is not enabled globally.")
                await interaction.response.send_message(error_message, ephemeral=True)
                return
            # Keep admin restrictions for activation/deactivation
            if not view.admin_visible:
                await interaction.response.send_message("❌ This option is admin-only and requires a server.", ephemeral=True)
                return
            await _handle_canvas_treasure_hunter_action(interaction, action_name, view)
            return
        if self.role_name == "trickster" and action_name in {"dice_fixed_bet", "dice_pot_value"}:
            if not eff_guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return
            await interaction.response.send_modal(TricksterActionModal(action_name, view.author_id, eff_guild, view.admin_visible, view))
            return
        if self.role_name == "trickster" and action_name in {"dice_play", "dice_ranking", "dice_history", "dice_help"}:
            # For dice actions, allow DM execution by using default server
            await _handle_canvas_dice_action(interaction, action_name, view)
            return
        if self.role_name == "shaman":
            await _HandleCanvasShamanAction(interaction, action_name, view)
            return
        if self.role_name == "scholar":
            await _HandleCanvasScholarAction(interaction, action_name, view)
            return
        if self.role_name == "juggler":
            from .canvas_juggler import handle_canvas_juggler_modal_submit
            # Handle ring actions that need modal input
            if action_name in {"ring_accuse", "ring_frequency"}:
                await interaction.response.send_modal(JugglerActionModal(action_name, view.author_id, eff_guild, view.admin_visible, view))
                return
            # Handle ring toggle actions
            if action_name in {"ring_on", "ring_off"}:
                if not view.admin_visible:
                    await interaction.response.send_message("❌ This juggler option is admin-only.", ephemeral=True)
                    return
                await handle_canvas_juggler_modal_submit(interaction, action_name, "", eff_guild, view.author_id, view.admin_visible, view)
                return
        if self.role_name == "news_watcher" and action_name in {"method_flat", "method_keyword", "method_general", "watcher_run_now", "watcher_run_personal"}:
            if not view.admin_visible:
                await interaction.response.send_message("❌ This watcher option is admin-only.", ephemeral=True)
                return
            await _handle_canvas_watcher_action(interaction, action_name, view)
            return
        if self.role_name == "trickster" and action_name in {"announcements_on", "announcements_off"}:
            if not view.admin_visible:
                await interaction.response.send_message("❌ This trickster option is admin-only.", ephemeral=True)
                return
            await _handle_canvas_trickster_action(interaction, action_name, view)
            return
        if self.role_name == "banker" and action_name in {"beggar_on", "beggar_off", "beggar_frequency", "beggar_force_minigame"}:
            if not view.admin_visible:
                await interaction.response.send_message("❌ This banker option is admin-only.", ephemeral=True)
                return
            await _handle_canvas_banker_action(interaction, action_name, view)
            return
        if self.role_name == "mc":
            if not interaction.guild:
                await interaction.response.send_message("❌ MC actions are only available in a server.", ephemeral=True)
                return
            # Handle modal actions (play, add, volume) separately
            if action_name in {"mc_play", "mc_add"}:
                from .canvas_mc import CanvasMCSongModal
                from roles.mc.mc_discord import get_mc_commands_instance
                mc_commands = get_mc_commands_instance()
                if not mc_commands:
                    await interaction.response.send_message("❌ MC commands are not initialized.", ephemeral=True)
                    return
                await interaction.response.send_modal(CanvasMCSongModal(action_name, view, mc_commands, view.author_id))
                return
            if action_name == "mc_volume":
                from .canvas_mc import CanvasMCVolumeModal
                from roles.mc.mc_discord import get_mc_commands_instance
                mc_commands = get_mc_commands_instance()
                if not mc_commands:
                    await interaction.response.send_message("❌ MC commands are not initialized.", ephemeral=True)
                    return
                await interaction.response.send_modal(CanvasMCVolumeModal(view, mc_commands, view.author_id))
                return
            # Handle direct actions (skip, pause, resume, stop, queue, clear, history)
            await _handle_canvas_mc_action(interaction, action_name, view)
            return
        # This should never be reached as all roles have specific handlers
        await interaction.response.send_message("❌ This role option is not available.", ephemeral=True)
        return


class CanvasConversationActionSelect(discord.ui.Select):
    """Dropdown for conversation view with only GDPR forget_me option."""
    
    def __init__(self, admin_visible: bool, guild=None):
        from .content import _get_personality_descriptions
        server_id = get_server_key(guild) if guild else None
        descriptions = _get_personality_descriptions(server_id)
        general = descriptions.get("general", {})
        
        label_forget_me = general.get("forget_me_label", "🧹 Forget me (erase my data)")
        desc_forget_me = general.get(
            "forget_me_description",
            "Erase your personal data from every server this bot knows (GDPR Art. 17)",
        )
        generic_option_label = descriptions.get("canvas_home_messages", {}).get("generic_option_label", "Choose a concrete option...")
        
        options = [
            discord.SelectOption(label=label_forget_me, value="forget_me", description=desc_forget_me)
        ]
        
        super().__init__(placeholder=generic_option_label, min_values=1, max_values=1, options=options, row=2)
    
    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasBehaviorView):
            from agent_runtime import get_personality_message
            server_id = get_server_key(interaction.guild) if interaction.guild else None
            error_msg = get_personality_message("answers.json", ["general", "error_selection_unavailable"], server_id, "❌ Canvas behavior action selection is not available.")
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        action_name = self.values[0]
        if action_name == "forget_me":
            from discord_bot.gdpr import send_forget_me_prompt
            await send_forget_me_prompt(interaction)
            return


class MemoryTypeSelect(discord.ui.Select):
    """Dropdown selector for memory type (long, recent, relationship)."""
    def __init__(self, admin_visible: bool, guild=None, agent_config=None):
        server_id = get_server_key(guild) if guild else None
        descriptions = _get_personality_descriptions(server_id)
        
        # Get memory dropdown configuration from behavior_messages
        behavior_messages = descriptions.get("behavior_messages", {})
        memory_config = behavior_messages.get("memory", {}).get("dropdown", {})
        
        # Get current selection from agent_config
        selected_memory_type = (agent_config or {}).get("selected_memory_type", "long") if agent_config else "long"
        
        long_config = memory_config.get("long", {})
        recent_config = memory_config.get("recent", {})
        relationship_config = memory_config.get("relationship", {})
        
        label_long = long_config.get("label", "Long Memory")
        emoji_long = long_config.get("emoji", "🗺️")
        desc_long = long_config.get("description", "Memoria")
        
        label_recent = recent_config.get("label", "Recent Memory")
        emoji_recent = recent_config.get("emoji", "🧐")
        desc_recent = recent_config.get("description", "Sucesos recientes")
        
        label_relationship = relationship_config.get("label", "Relationship Memory")
        emoji_relationship = relationship_config.get("emoji", "👞")
        desc_relationship = relationship_config.get("description", "Relación personal")
        
        options = [
            discord.SelectOption(
                label=label_long,
                value="memory_long",
                description=desc_long,
                emoji=emoji_long
            ),
            discord.SelectOption(
                label=label_recent,
                value="memory_recent",
                description=desc_recent,
                emoji=emoji_recent
            ),
            discord.SelectOption(
                label=label_relationship,
                value="memory_relationship",
                description=desc_relationship,
                emoji=emoji_relationship
            ),
        ]
        
        generic_option_label = descriptions.get("canvas_home_messages", {}).get("generic_option_label", "Choose a concrete option...")
        super().__init__(placeholder=generic_option_label, min_values=1, max_values=1, options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasBehaviorView):
            from agent_runtime import get_personality_message
            server_id = get_server_key(interaction.guild) if interaction.guild else None
            error_msg = get_personality_message("answers.json", ["general", "error_selection_unavailable"], server_id, "❌ Canvas memory type selection is not available.")
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        action_name = self.values[0]
        # Update agent_config with selected memory type
        if view.agent_config is None:
            view.agent_config = {}
        view.agent_config["selected_memory_type"] = action_name.replace("memory_", "")
        
        # Rebuild the view with updated memory type
        title, description, content = _build_canvas_behavior_detail("memory", view.admin_visible, view.guild, view.agent_config, author_id=str(view.author_id)) or (None, None, "")
        behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview, title, description)
        
        # Update the view with new MemoryTypeSelect that has the updated agent_config
        next_view = CanvasBehaviorView(
            author_id=view.author_id,
            sections=view.sections,
            admin_visible=view.admin_visible,
            agent_config=view.agent_config,
            current_detail="memory",
            guild=view.guild,
            message=interaction.message
        )
        await interaction.response.edit_message(content=None, embed=behavior_embed, view=next_view)


class CanvasBehaviorActionSelect(discord.ui.Select):
    def __init__(self, detail_name: str, admin_visible: bool, guild=None):
        options = [
            discord.SelectOption(label=label, value=value, description=description)
            for label, value, description in _get_canvas_behavior_action_items_for_detail(detail_name, admin_visible, guild)
        ]
        server_id = get_server_key(guild) if guild else None
        generic_option_label = _get_personality_descriptions(server_id).get("canvas_home_messages", {}).get("generic_option_label", "Choose a concrete option...")
        
        super().__init__(placeholder=generic_option_label, min_values=1, max_values=1, options=options[:25], row=2)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasBehaviorView):
            # Get error message from answers
            from agent_runtime import get_personality_message
            server_id = get_server_key(interaction.guild) if interaction.guild else None
            error_msg = get_personality_message("answers.json", ["general", "error_selection_unavailable"], server_id, "❌ Canvas behavior action selection is not available.")
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        action_name = self.values[0]
        view.auto_response_preview = _get_canvas_auto_response_preview(action_name=action_name)

        # Effective guild: support DM by falling back to the view's resolved guild.
        eff_guild = interaction.guild or getattr(view, 'guild', None)

        # Load answers.json for general messages
        from agent_runtime import get_personality_message
        server_id = get_server_key(eff_guild) if eff_guild else None
        general_answers = get_personality_message("answers.json", ["general"], server_id, {})
        
        if action_name == "forget_me":
            # GDPR self-service — scoped to the interacting user only.
            from discord_bot.gdpr import send_forget_me_prompt
            await send_forget_me_prompt(interaction)
            return

        if action_name in {"memory_long", "memory_recent", "memory_relationship"}:
            # Handle memory type selection via dropdown
            if not view.admin_visible:
                error_behavior_admin_only = general_answers.get("error_behavior_admin_only", "❌ This behavior option is admin-only.")
                await interaction.response.send_message(error_behavior_admin_only, ephemeral=True)
                return
            # Store selected memory type in view for dropdown
            view.selected_memory_type = action_name.replace("memory_", "")
            title, description, content = _build_canvas_behavior_detail("memory", view.admin_visible, view.guild, view.agent_config, author_id=str(view.author_id)) or (None, None, "")
            behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview, title, description)
            await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
            return
        if action_name in {"taboo_add", "taboo_del"}:
            if not view.admin_visible or not eff_guild:
                error_behavior_admin_only = general_answers.get("error_behavior_admin_only", "❌ This behavior option is admin-only.")
                await interaction.response.send_message(error_behavior_admin_only, ephemeral=True)
                return
            await interaction.response.send_modal(TabooKeywordModal(action_name, int(eff_guild.id), view))
            return
        if action_name == "language_settings":
            if not view.admin_visible:
                error_settings_admin_only = general_answers.get("error_settings_admin_only", "❌ This settings option is admin-only.")
                await interaction.response.send_message(error_settings_admin_only, ephemeral=True)
                return
            
            # Get modal title from descriptions
            descriptions = _get_personality_descriptions(server_id)
            lang_select = descriptions.get("behavior_messages", {}).get("settings", {}).get("language_select", {})
            modal_title = lang_select.get("modal_title", "🌐 **Select Server Language**")
            
            await interaction.response.send_message(
                modal_title,
                view=LanguageSelectView(view),
                ephemeral=True
            )
            return
        if action_name == "role_control":
            if not view.admin_visible:
                error_settings_admin_only = general_answers.get("error_settings_admin_only", "❌ This settings option is admin-only.")
                await interaction.response.send_message(error_settings_admin_only, ephemeral=True)
                return
            # Send ephemeral message with dropdown instead of modal
            role_view = RoleManagementView(view)
            await interaction.response.send_message("🎛️ **Gestión de Roles** - Selecciona un rol para activar/desactivar:", view=role_view, ephemeral=True)
            return
        if action_name in {"taboo_on", "taboo_off"}:
            if not view.admin_visible or not eff_guild:
                error_behavior_admin_only = general_answers.get("error_behavior_admin_only", "❌ This behavior option is admin-only.")
                await interaction.response.send_message(error_behavior_admin_only, ephemeral=True)
                return
            guild_id = int(eff_guild.id)
            enabled = action_name == "taboo_on"
            if update_taboo_state(guild_id, enabled=enabled):
                title, description, content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config, author_id=str(view.author_id)) or (None, None, "")
                
                # Get success message from answers
                success_taboo_state = general_answers.get("success_taboo_state", "Taboo {enabled_disabled} for this server.")
                state_enabled = general_answers.get("state_enabled", "enabled")
                state_disabled = general_answers.get("state_disabled", "disabled")
                enabled_disabled = state_enabled if enabled else state_disabled
                
                view.auto_response_preview = success_taboo_state.format(enabled_disabled=enabled_disabled)
                behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview, title, description)
                await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
            else:
                await interaction.response.send_message("❌ Failed to update taboo state. Check logs for details.", ephemeral=True)
            return
        
        # Handle greetings toggle
        if action_name in {"greetings_on", "greetings_off"}:
            if not view.admin_visible or not eff_guild:
                error_behavior_admin_only = general_answers.get("error_behavior_admin_only", "❌ This behavior option is admin-only.")
                await interaction.response.send_message(error_behavior_admin_only, ephemeral=True)
                return
            enabled = action_name == "greetings_on"
            try:
                from discord_bot.discord_utils import set_greeting_enabled
                set_greeting_enabled(eff_guild, enabled)
                title, description, content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config, author_id=str(view.author_id)) or (None, None, "")
                
                # Get success message from answers
                success_greetings_state = general_answers.get("success_greetings_state", "Greetings {enabled_disabled} for this server.")
                state_enabled = general_answers.get("state_enabled", "enabled")
                state_disabled = general_answers.get("state_disabled", "disabled")
                enabled_disabled = state_enabled if enabled else state_disabled
                
                view.auto_response_preview = success_greetings_state.format(enabled_disabled=enabled_disabled)
                behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview, title, description)
                await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
            except Exception as e:
                logger.error(f"Error updating greetings state: {e}")
                await interaction.response.send_message("❌ Failed to update greetings state. Check logs for details.", ephemeral=True)
            return
        
        # Handle welcome toggle
        if action_name in {"welcome_on", "welcome_off"}:
            if not view.admin_visible or not eff_guild:
                error_behavior_admin_only = general_answers.get("error_behavior_admin_only", "❌ This behavior option is admin-only.")
                await interaction.response.send_message(error_behavior_admin_only, ephemeral=True)
                return
            enabled = action_name == "welcome_on"
            try:
                # Update in-memory config
                greeting_cfg = _discord_cfg.get("member_greeting", {})
                greeting_cfg["enabled"] = enabled

                # Save to server_config.json
                try:
                    from discord_bot.canvas.server_config import set_welcome_enabled
                    guild_id = str(eff_guild.id)
                    set_welcome_enabled(guild_id, enabled, f"{interaction.user.name}")
                except Exception as e:
                    logger.error(f"Failed to save welcome state to server_config: {e}")
                
                title, description, content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config, author_id=str(view.author_id)) or (None, None, "")
                
                # Get success message from answers
                success_welcome_state = general_answers.get("success_welcome_state", "Welcome messages {enabled_disabled} for this server.")
                state_enabled = general_answers.get("state_enabled", "enabled")
                state_disabled = general_answers.get("state_disabled", "disabled")
                enabled_disabled = state_enabled if enabled else state_disabled
                
                view.auto_response_preview = success_welcome_state.format(enabled_disabled=enabled_disabled)
                behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview, title, description)
                await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
            except Exception as e:
                logger.error(f"Error updating welcome state: {e}")
                await interaction.response.send_message("❌ Failed to update welcome state. Check logs for details.", ephemeral=True)
            return
        
        # Fallback for other behavior actions
        content = _build_canvas_behavior_action_view(action_name, view.admin_visible)
        if not content:
            await interaction.response.send_message("❌ This behavior option is not available.", ephemeral=True)
            return
        behavior_embed = _build_canvas_behavior_embed(content, view.admin_visible, view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)


class CanvasNavRolesButton(discord.ui.Button):
    """Dynamic Roles button for Canvas home - loads label from server-specific descriptions."""

    def __init__(self, label: str = "Roles"):
        super().__init__(label=label, style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        guild = interaction.guild or view.guild
        if guild:
            server_id = get_server_key(guild) if get_server_key else str(guild.id)
            view.sections = _build_canvas_sections(
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
            view.guild = guild
        roles_content = view.sections.get("roles")
        if not roles_content:
            await _safe_send_interaction_message(interaction, "❌ This Canvas section is not available.", ephemeral=True)
            return
        roles_view = CanvasRolesView(view.author_id, view.agent_config, view.admin_visible, view.sections, guild=guild, current_page=1, roles_per_page=5)
        roles_view.message = interaction.message
        server_id = get_server_key(guild) if guild else None
        roles_embed = _build_canvas_embed("roles", roles_content, view.admin_visible, server_id=server_id)
        roles_view.current_embed = roles_embed  # Store embed for back navigation
        await _safe_edit_interaction_message(interaction, content=None, embed=roles_embed, view=roles_view)
        roles_view.message = interaction.message


class CanvasNavBehaviorButton(discord.ui.Button):
    """Dynamic Behavior button for Canvas home - loads label from server-specific descriptions."""

    def __init__(self, label: str = "Behavior"):
        super().__init__(label=label, style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        guild = interaction.guild or view.guild
        if guild:
            server_id = get_server_key(guild) if get_server_key else str(guild.id)
            view.sections = _build_canvas_sections(
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
            view.guild = guild
        guild = interaction.guild or view.guild
        result = _build_canvas_behavior_detail("conversation", view.admin_visible, guild, view.agent_config, author_id=str(view.author_id))
        if not result:
            await _safe_send_interaction_message(interaction, "❌ This Canvas section is not available.", ephemeral=True)
            return
        b_title, b_description, b_content = result
        behavior_view = CanvasBehaviorView(view.author_id, view.sections, view.admin_visible, view.agent_config, current_detail="conversation", guild=guild)
        behavior_embed = _build_canvas_behavior_embed(b_content, view.admin_visible, title=b_title, description=b_description)
        await _safe_edit_interaction_message(interaction, content=None, embed=behavior_embed, view=behavior_view)
        behavior_view.message = interaction.message


class CanvasNavHelpButton(discord.ui.Button):
    """Dynamic Help button for Canvas home - loads label from server-specific descriptions."""

    def __init__(self, label: str = "Help"):
        super().__init__(label=label, style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        await view._show_section(interaction, "help")


class CanvasNavigationView(TimeoutResetMixin, BackButtonMixin, HomeButtonMixin, discord.ui.View):
    """Interactive button-based Canvas navigation for top-level sections."""

    def __init__(self, author_id: int, sections: dict[str, str], admin_visible: bool, agent_config: dict, guild=None, message=None, show_dropdown=True):
        super().__init__(timeout=900)  # 15 minutes
        self.author_id = author_id
        self.sections = sections
        self.admin_visible = admin_visible
        self.agent_config = agent_config
        self.guild = guild  # Store guild for role detail views
        self.message = message  # Store the message to delete it later
        server_id = get_server_key(guild) if guild else None
        if show_dropdown:
            self.add_item(CanvasSectionSelect(admin_visible, server_id))
        # Dynamically add nav buttons with server-specific labels (same pattern as CanvasRolesView)
        self._add_nav_buttons()
        # Start the timeout timer
        self._reset_timeout()

    def _add_nav_buttons(self):
        """Add navigation buttons with labels from server-specific descriptions.json."""
        server_id = get_server_key(self.guild) if self.guild else None
        _desc = _get_personality_descriptions(server_id).get("canvas_home_messages", {})
        roles_label = _desc.get("button_roles", "Roles")
        behavior_label = _desc.get("button_behavior", "Behavior")
        help_label = _desc.get("button_help", "Help")
        self.add_item(CanvasNavRolesButton(label=roles_label))
        self.add_item(CanvasNavBehaviorButton(label=behavior_label))
        self.add_item(CanvasNavHelpButton(label=help_label))

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
        title = self.sections.get("behavior_title") if section_name == "behavior" else None
        description = self.sections.get("behavior_description") if section_name == "behavior" else None
        embed = _build_canvas_embed(section_name, content, self.admin_visible, title, description, server_id=server_id if guild else None)
        await _safe_edit_interaction_message(interaction, content=None, embed=embed, view=self)

    async def _check_user_permission(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive Canvas to its original user."""
        if interaction.user.id != self.author_id:
            await _safe_send_interaction_message(interaction, "❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True

    def update_visibility(self):
        """Hide or disable admin-only controls according to current permissions."""
        if not self.admin_visible:
            for child in self.children:
                if getattr(child, "label", "") == "Setup":
                    child.disabled = True
                    break


class CanvasRolesView(TimeoutResetMixin, SmartBackButtonMixin, HomeButtonMixin, discord.ui.View):
    """Interactive role navigation for enabled roles with pagination."""

    def __init__(self, author_id: int, agent_config: dict, admin_visible: bool, sections: dict[str, str], message=None, guild=None, current_page: int = 1, roles_per_page: int = 5):
        super().__init__(timeout=900)  # 15 minutes
        self.author_id = author_id
        self.agent_config = agent_config
        self.admin_visible = admin_visible
        self.sections = sections
        self.message = message  # Store the message to delete it later
        self.guild = guild
        self.current_embed = None  # Store current embed for back navigation
        self.current_page = current_page
        self.roles_per_page = roles_per_page
        self._add_role_buttons()
        self._add_pagination_buttons()
        
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
        """Add buttons for enabled roles on current page (max 5 per page)."""
        server_id = get_server_key(self.guild) if self.guild else None
        _roles_desc = _get_personality_descriptions(server_id).get("role_descriptions", {})
        button_watcher = _roles_desc.get("news_watcher", {}).get("button", "Watcher")
        button_trickster = _roles_desc.get("trickster", {}).get("button", "Trickster")
        button_treasure_hunter = _roles_desc.get("treasure_hunter", {}).get("button", "Hunter")
        button_banker = _roles_desc.get("banker", {}).get("button", "Banker")
        button_shaman = _roles_desc.get("shaman", {}).get("button", "Shaman")
        button_mc = _roles_desc.get("mc", {}).get("button", "MC")
        button_juggler = _roles_desc.get("juggler", {}).get("button", "Juggler")

        role_labels = {
            "news_watcher": button_watcher,
            "treasure_hunter": button_treasure_hunter,
            "trickster": button_trickster,
            "banker": button_banker,
            "shaman": button_shaman,
            "mc": button_mc,
            "juggler": button_juggler,
        }
        
        # Get all enabled roles
        all_enabled_roles = _get_enabled_roles(self.agent_config, getattr(self, 'guild', None))
        
        # Calculate pagination
        total_roles = len(all_enabled_roles)
        total_pages = (total_roles + self.roles_per_page - 1) // self.roles_per_page if total_roles > 0 else 1
        self.current_page = max(1, min(self.current_page, total_pages))
        
        # Get roles for current page
        start_idx = (self.current_page - 1) * self.roles_per_page
        end_idx = start_idx + self.roles_per_page
        page_roles = all_enabled_roles[start_idx:end_idx]
        
        # Add buttons for roles on current page
        for role_name in page_roles:
            label = role_labels.get(role_name, role_name.replace("_", " ").title())
            self.add_item(CanvasRoleButton(label=label, role_name=role_name))

    def _add_pagination_buttons(self):
        """Add pagination buttons (previous/next) if there are multiple pages."""
        # Get all enabled roles to calculate total pages
        all_enabled_roles = _get_enabled_roles(self.agent_config, getattr(self, 'guild', None))
        total_roles = len(all_enabled_roles)
        total_pages = (total_roles + self.roles_per_page - 1) // self.roles_per_page if total_roles > 0 else 1
        
        # Only add pagination buttons if there are multiple pages
        if total_pages > 1:
            # Add previous button if not on first page
            if self.current_page > 1:
                self.add_item(CanvasRolesPageButton(label_key="button_previous", page_offset=-1, row=2, guild=self.guild))
            
            # Add next button if not on last page
            if self.current_page < total_pages:
                self.add_item(CanvasRolesPageButton(label_key="button_next", page_offset=1, row=2, guild=self.guild))
        
        # Add navigation buttons using mixins
        self.add_smart_back_button()
        self.add_home_button()


class CanvasRolesPageButton(discord.ui.Button):
    """Button that navigates to previous or next page of roles."""

    def __init__(self, label_key: str, page_offset: int, row: int = 2, guild=None):
        # Get label from personality descriptions
        server_id = get_server_key(guild) if guild else None
        _roles_desc = _get_personality_descriptions(server_id).get("roles_view_messages", {})
        label = _roles_desc.get(label_key, label_key.replace("button_", "").title())
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=row)
        self.page_offset = page_offset

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRolesView):
            await interaction.response.send_message("❌ Canvas role navigation is not available.", ephemeral=True)
            return

        # Calculate new page
        new_page = view.current_page + self.page_offset
        if new_page < 1:
            new_page = 1

        # Rebuild roles content with new page
        from .content import _build_canvas_roles
        roles_content = _build_canvas_roles(
            view.agent_config,
            view.admin_visible,
            view.guild,
            page=new_page,
            roles_per_page=view.roles_per_page
        )

        # Update sections with new roles content
        view.sections["roles"] = roles_content

        # Create new view with updated page
        new_view = CanvasRolesView(
            author_id=view.author_id,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            message=interaction.message,
            guild=view.guild,
            current_page=new_page,
            roles_per_page=view.roles_per_page
        )
        server_id = get_server_key(view.guild) if view.guild else None
        new_view.current_embed = _build_canvas_embed("roles", roles_content, view.admin_visible, server_id=server_id)

        # Update message with new view
        await interaction.response.edit_message(embed=new_view.current_embed, view=new_view)
        new_view.message = interaction.message


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

        eff_guild = interaction.guild or getattr(view, 'guild', None)
        content = _build_canvas_role_view(
            self.role_name,
            view.agent_config,
            view.admin_visible,
            eff_guild,
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
            guild=eff_guild,
            previous_view=view  # Pass current CanvasRolesView as previous_view for back navigation
        )
        detail_view.message = interaction.message
        role_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, "overview", None, detail_view.auto_response_preview, server_id=get_server_key(eff_guild) if eff_guild else None)
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
        detail_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, self.detail_name, None, next_view.auto_response_preview, server_id=get_server_key(view.guild) if view.guild else None)
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

        # Navigate to the POE2 overview view
        detail_name = "poe2"
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
        detail_embed = _build_canvas_role_embed("treasure_hunter", content, view.admin_visible, detail_name, None, next_view.auto_response_preview, server_id=get_server_key(interaction.guild) if interaction.guild else None)
        next_view.current_embed = detail_embed
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


class CanvasTricksterDicePlayButton(discord.ui.Button):
    """Button that executes the dice_play action for Trickster."""

    def __init__(self, label: str = "🎲 Play", style=discord.ButtonStyle.success):
        super().__init__(label=label, style=style)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRoleDetailView):
            await interaction.response.send_message("❌ Canvas role detail navigation is not available.", ephemeral=True)
            return

        # Execute dice_play action
        await _handle_canvas_dice_action(interaction, "dice_play", view)
class RoleFrequencyModal(CanvasModal):
    """Modal for setting Watcher frequency - Hunter frequency is controlled from agent_config.json only."""
    def __init__(self, role_name: str, action_name: str, agent_config: dict, view, author_id: int):
        # Only watcher_frequency is supported now
        super().__init__(title="Watcher Frequency", author_id=author_id)
        self.role_name = role_name
        self.action_name = action_name
        self.agent_config = agent_config
        self.view = view
        self.value_input = discord.ui.TextInput(label="Hours", placeholder="1-24 hours", required=True, max_length=10)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        eff_guild = interaction.guild or getattr(self.view, 'guild', None)
        if not eff_guild:
            await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
            return
        if not is_admin(interaction, guild=eff_guild):
            await interaction.response.send_message("❌ This option is admin-only.", ephemeral=True)
            return
        try:
            hours = int(str(self.value_input.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number of hours.", ephemeral=True)
            return

        # Only handle watcher_frequency (hunter_frequency is controlled from agent_config.json only)
        if hours < 1 or hours > 24:
            await interaction.response.send_message("❌ Watcher frequency must be between 1 and 24 hours.", ephemeral=True)
            return
        if get_news_watcher_db_instance is None:
            await interaction.response.send_message("❌ Watcher database is not available.", ephemeral=True)
            return
        try:
            db_watcher = get_news_watcher_db_instance(str(eff_guild.id))
            ok = db_watcher.set_frequency_setting(hours)
        except Exception as e:
            logger.exception(f"Canvas watcher frequency update failed: {e}")
            ok = False
        if not ok:
            await interaction.response.send_message("❌ Could not update watcher frequency.", ephemeral=True)
            return
        current_method = _get_canvas_watcher_method_label(str(eff_guild.id))
        applied_text = f"Watcher frequency updated to `{hours}` hours.\nCurrent method: {current_method}"

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
        role_embed = _build_canvas_role_embed(self.role_name, content, self.view.admin_visible, "admin", None, next_view.auto_response_preview, server_id=get_server_key(eff_guild) if eff_guild else None)
        await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)


class TabooKeywordModal(CanvasModal):
    def __init__(self, action_name: str, guild_id: int, view, author_id: int):
        # Get modal messages from descriptions
        server_id = get_server_key(view.guild) if view.guild else None
        descriptions = _get_personality_descriptions(server_id)
        modal_messages = descriptions.get("behavior_messages", {}).get("taboo", {}).get("modal", {})
        
        title = modal_messages.get("title", "Taboo Keyword")
        label_keyword = modal_messages.get("label_keyword", "Keyword")
        placeholder_keyword = modal_messages.get("placeholder_keyword", "forbidden word")
        
        super().__init__(title=title, author_id=author_id)
        self.action_name = action_name
        self.guild_id = guild_id
        self.view = view
        self.value_input = discord.ui.TextInput(label=label_keyword, placeholder=placeholder_keyword, required=True, max_length=80)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Get modal messages from descriptions
        server_id = get_server_key(interaction.guild) if interaction.guild else None
        descriptions = _get_personality_descriptions(server_id)
        modal_messages = descriptions.get("behavior_messages", {}).get("taboo", {}).get("modal", {})
        
        error_invalid_keyword = modal_messages.get("error_invalid_keyword", "❌ Enter a valid keyword.")
        success_added = modal_messages.get("success_added", "Added taboo keyword `{keyword}`.")
        error_add_failed = modal_messages.get("error_add_failed", "Failed to add keyword `{keyword}`. Check logs for details.")
        info_already_exists = modal_messages.get("info_already_exists", "Keyword `{keyword}` was already in the list.")
        success_removed = modal_messages.get("success_removed", "Removed taboo keyword `{keyword}`.")
        error_remove_failed = modal_messages.get("error_remove_failed", "Failed to remove keyword `{keyword}`. Check logs for details.")
        info_not_exists = modal_messages.get("info_not_exists", "Keyword `{keyword}` was not in the list.")
        
        keyword = str(self.value_input.value).strip().lower()
        if not keyword:
            await interaction.response.send_message(error_invalid_keyword, ephemeral=True)
            return
        
        # Get current keywords from database
        state = get_taboo_state(self.guild_id)
        current_keywords = state.get("keywords", [])
        
        applied_text = ""
        success = False
        
        if self.action_name == "taboo_add":
            if keyword not in current_keywords:
                if update_taboo_state(self.guild_id, keywords=current_keywords + [keyword]):
                    applied_text = success_added.format(keyword=keyword)
                    success = True
                else:
                    applied_text = error_add_failed.format(keyword=keyword)
            else:
                applied_text = info_already_exists.format(keyword=keyword)
                success = True
        else:  # taboo_del
            if keyword in current_keywords:
                new_keywords = [kw for kw in current_keywords if kw != keyword]
                if update_taboo_state(self.guild_id, keywords=new_keywords):
                    applied_text = success_removed.format(keyword=keyword)
                    success = True
                else:
                    applied_text = error_remove_failed.format(keyword=keyword)
            else:
                applied_text = info_not_exists.format(keyword=keyword)
                success = True
        
        # Rebuild the Canvas behavior view with updated state
        title, description, content = _build_canvas_behavior_detail(self.view.current_detail, self.view.admin_visible, self.view.guild, self.view.agent_config, author_id=str(self.view.author_id)) or (None, None, "")
        next_view = CanvasBehaviorView(
            author_id=self.view.author_id,
            sections=self.view.sections,
            admin_visible=self.view.admin_visible,
            agent_config=self.view.agent_config,
            current_detail=self.view.current_detail,
            guild=self.view.guild,
        )
        next_view.auto_response_preview = applied_text
        behavior_embed = _build_canvas_behavior_embed(content or "", self.view.admin_visible, next_view.auto_response_preview, title, description)
        
        if success:
            await interaction.response.edit_message(content=None, embed=behavior_embed, view=next_view)
        else:
            await interaction.response.send_message(applied_text, ephemeral=True)


class RoleManagementView(discord.ui.View):
    """View for role management dropdown."""
    
    def __init__(self, canvas_view: "CanvasBehaviorView"):
        super().__init__(timeout=300)
        self.canvas_view = canvas_view
        self.add_item(RoleManagementDropdown(canvas_view))


class RoleManagementDropdown(discord.ui.Select):
    """Dropdown for role management with toggle functionality."""
    
    def __init__(self, view: "CanvasBehaviorView"):
        self.canvas_view = view
        server_id = get_server_key(view.guild) if view.guild else None
        
        # Get descriptions
        descriptions = _get_personality_descriptions(server_id)
        role_descriptions = descriptions.get("role_descriptions", {})
        general = descriptions.get("general", {})
        
        # Role configuration with display names and internal names
        # MC is always enabled (cannot be toggled)
        roles_config = [
            {"internal": "news_watcher", "display": role_descriptions.get("news_watcher", {}).get("title", "🎯 Vigia de Noticias").replace("**", "").strip(), "always_enabled": False},
            {"internal": "treasure_hunter", "display": role_descriptions.get("treasure_hunter", {}).get("title", "💎 Putre Cazador de Tesoros").replace("**", "").strip(), "always_enabled": False},
            {"internal": "trickster", "display": role_descriptions.get("trickster", {}).get("title", "🎭Trilero Putre").replace("**", "").strip(), "always_enabled": False},
            {"internal": "banker", "display": role_descriptions.get("banker", {}).get("title", "💰 El Gran Kofre de Putre").replace("**", "").strip(), "always_enabled": False},
            {"internal": "mc", "display": role_descriptions.get("mc", {}).get("title", "🥁 Putre Tamborilero!").replace("**", "").strip(), "always_enabled": True},
            {"internal": "juggler", "display": role_descriptions.get("juggler", {}).get("title", "🤹 El Juglah Putre").replace("**", "").strip(), "always_enabled": False},
            {"internal": "shaman", "display": role_descriptions.get("shaman", {}).get("title", "🐺 Chamán Putre").replace("**", "").strip(), "always_enabled": False},
        ]
        
        # Get current state for each role
        agent_config = view.agent_config
        options = []
        
        for role in roles_config:
            role_name = role["internal"]
            display_name = role["display"]
            always_enabled = role["always_enabled"]
            
            # Check if role is enabled
            if always_enabled:
                status = general.get("always_enabled", "Siempre activado")
                status_emoji = "✅"
            else:
                is_enabled = is_role_enabled_check(role_name, agent_config, view.guild)
                status = general.get("state_enabled" if is_enabled else "state_disabled", "Activado" if is_enabled else "Desactivado")
                status_emoji = "✅" if is_enabled else "❌"
            
            label = f"{display_name}: {status_emoji} {status}"
            
            options.append(discord.SelectOption(
                label=label[:100],  # Discord limit for select option labels
                value=role_name,
                description=f"Click para {general.get('action_labels', {}).get('off', 'Desactivar') if not always_enabled and is_enabled else general.get('action_labels', {}).get('on', 'Activar')}" if not always_enabled else "No se puede modificar"
            ))
        
        placeholder = general.get("action_labels", {}).get("role_management", "🎛️ Gestión de Roles")
        
        super().__init__(
            placeholder=placeholder[:100],
            options=options,
            custom_id="role_management_dropdown",
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle role selection and toggle."""
        role_name = self.values[0]
        
        # Get descriptions
        server_id = get_server_key(interaction.guild) if interaction.guild else None
        descriptions = _get_personality_descriptions(server_id)
        general = descriptions.get("general", {})
        
        # Check if role is always enabled (MC)
        if role_name == "mc":
            await interaction.response.send_message(
                f"❌ {general.get('action_labels', {}).get('role_management', 'Gestión de Roles')}: Este rol siempre está activado.",
                ephemeral=True
            )
            return
        
        # Get current state
        agent_config = self.canvas_view.agent_config
        is_enabled = is_role_enabled_check(role_name, agent_config, interaction.guild)
        new_state = not is_enabled
        
        # Import role toggle function
        from discord_bot.discord_core_commands import _cmd_role_toggle
        
        # Create mock context for the role toggle function
        class MockContext:
            def __init__(self, interaction, enabled_state):
                self.guild = interaction.guild
                self.author = interaction.user
                self.enabled_state = enabled_state
            
            async def send(self, content):
                pass
        
        # Execute role toggle
        mock_ctx = MockContext(interaction, new_state)
        await _cmd_role_toggle(mock_ctx, role_name, new_state)
        
        # Build success message
        state_text = general.get("state_enabled", "Activado") if new_state else general.get("state_disabled", "Desactivado")
        role_display_map = {
            "news_watcher": descriptions.get("role_descriptions", {}).get("news_watcher", {}).get("title", "🎯 Vigia de Noticias").replace("**", "").strip(),
            "treasure_hunter": descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("title", "💎 Putre Cazador de Tesoros").replace("**", "").strip(),
            "trickster": descriptions.get("role_descriptions", {}).get("trickster", {}).get("title", "🎭Trilero Putre").replace("**", "").strip(),
            "banker": descriptions.get("role_descriptions", {}).get("banker", {}).get("title", "💰 El Gran Kofre de Putre").replace("**", "").strip(),
            "juggler": descriptions.get("role_descriptions", {}).get("juggler", {}).get("title", "🤹 El Juglah Putre").replace("**", "").strip(),
            "shaman": descriptions.get("role_descriptions", {}).get("shaman", {}).get("title", "🐺 Chamán Putre").replace("**", "").strip(),
        }
        role_display = role_display_map.get(role_name, role_name)
        
        success_msg = f"✅ {role_display}: {state_text}"
        
        # Update the dropdown with new states
        new_options = []
        roles_config = [
            {"internal": "news_watcher", "display": descriptions.get("role_descriptions", {}).get("news_watcher", {}).get("title", "🎯 Vigia de Noticias").replace("**", "").strip(), "always_enabled": False},
            {"internal": "treasure_hunter", "display": descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("title", "💎 Putre Cazador de Tesoros").replace("**", "").strip(), "always_enabled": False},
            {"internal": "trickster", "display": descriptions.get("role_descriptions", {}).get("trickster", {}).get("title", "🎭Trilero Putre").replace("**", "").strip(), "always_enabled": False},
            {"internal": "banker", "display": descriptions.get("role_descriptions", {}).get("banker", {}).get("title", "💰 El Gran Kofre de Putre").replace("**", "").strip(), "always_enabled": False},
            {"internal": "mc", "display": descriptions.get("role_descriptions", {}).get("mc", {}).get("title", "🥁 Putre Tamborilero!").replace("**", "").strip(), "always_enabled": True},
            {"internal": "juggler", "display": descriptions.get("role_descriptions", {}).get("juggler", {}).get("title", "🤹 El Juglah Putre").replace("**", "").strip(), "always_enabled": False},
            {"internal": "shaman", "display": descriptions.get("role_descriptions", {}).get("shaman", {}).get("title", "🐺 Chamán Putre").replace("**", "").strip(), "always_enabled": False},
        ]
        
        for role in roles_config:
            r_name = role["internal"]
            display_name = role["display"]
            always_enabled = role["always_enabled"]
            
            if always_enabled:
                status = general.get("always_enabled", "Siempre activado")
                status_emoji = "✅"
            else:
                r_enabled = is_role_enabled_check(r_name, agent_config, interaction.guild)
                status = general.get("state_enabled" if r_enabled else "state_disabled", "Activado" if r_enabled else "Desactivado")
                status_emoji = "✅" if r_enabled else "❌"
            
            label = f"{display_name}: {status_emoji} {status}"
            
            new_options.append(discord.SelectOption(
                label=label[:100],
                value=r_name,
                description=f"Click para {general.get('action_labels', {}).get('off', 'Desactivar') if not always_enabled and r_enabled else general.get('action_labels', {}).get('on', 'Activar')}" if not always_enabled else "No se puede modificar"
            ))
        
        self.options = new_options
        
        # Update the view
        title, description, content = _build_canvas_behavior_detail(self.canvas_view.current_detail, self.canvas_view.admin_visible, self.canvas_view.guild, self.canvas_view.agent_config, author_id=str(self.canvas_view.author_id)) or (None, None, "")
        self.canvas_view.auto_response_preview = success_msg
        behavior_embed = _build_canvas_behavior_embed(content or "", self.canvas_view.admin_visible, self.canvas_view.auto_response_preview, title, description)
        
        # Rebuild the view with updated dropdown
        view = self.canvas_view
        await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)


class LanguageSelect(discord.ui.Select):
    """Dropdown for selecting server language."""
    
    def __init__(self, view: "CanvasBehaviorView"):
        from .server_config import get_available_languages, get_server_language
        
        self.canvas_view = view
        server_id = str(view.guild.id) if view.guild else "0"
        current_lang = get_server_language(server_id)
        
        # Get language select messages from descriptions
        descriptions = _get_personality_descriptions(server_id)
        lang_select = descriptions.get("behavior_messages", {}).get("settings", {}).get("language_select", {})
        
        placeholder = lang_select.get("placeholder", "🌐 Select server language...")
        description_template = lang_select.get("description", "Set server language to {lang_name}")
        
        options = []
        for lang_code, lang_name in get_available_languages().items():
            options.append(discord.SelectOption(
                label=lang_name,
                value=lang_code,
                description=description_template.format(lang_name=lang_name),
                emoji="🌐",
                default=lang_code == current_lang
            ))
        
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            custom_id="language_select"
        )
    
    async def callback(self, interaction: discord.Interaction):
        try:
            from .server_config import set_server_language, get_server_language
            from .canvas_personality import _get_current_personality_name, CanvasPersonalitySelectView
            
            selected_language = self.values[0]
            server_id = str(interaction.guild.id) if interaction.guild else "0"
            
            # Get current personality before language change
            current_personality = _get_current_personality_name(server_id)
            old_language = get_server_language(server_id)
            
            # Save the language
            success = set_server_language(server_id, selected_language)
            
            if success:
                # Check if personality exists for new language
                from .canvas_personality import _get_available_personalities
                available_personalities = _get_available_personalities(selected_language)
                
                if current_personality in available_personalities:
                    # Personality exists for new language - offer to update it
                    await self._offer_personality_language_update(
                        interaction, current_personality, old_language, selected_language, server_id
                    )
                else:
                    # Personality doesn't exist for new language - just update language
                    await self._update_language_only(interaction, selected_language)
            else:
                await interaction.response.send_message(
                    "❌ Failed to update language setting.", 
                    ephemeral=True
                )
        except Exception as e:
            logger.exception(f"Error in language select: {e}")
            await interaction.response.send_message(
                "❌ Error updating language. Please try again.", 
                ephemeral=True
            )
    
    async def _offer_personality_language_update(self, interaction, personality_name, old_language, new_language, server_id):
        """Offer to update personality to new language version via ephemeral Yes/No prompt."""
        try:
            canvas_view = self.canvas_view
            
            view = _LanguagePersonalityPromptView(
                personality_name=personality_name,
                old_language=old_language,
                new_language=new_language,
                server_id=server_id,
                canvas_view=canvas_view,
            )
            
            await interaction.response.send_message(
                f"Language Updated: {old_language} → {new_language}\n\n"
                f"The current personality `{personality_name}` is also available in `{new_language}`.\n"
                f"Would you also like to change the personality to its `{new_language}` version?",
                view=view,
                ephemeral=True
            )
        except Exception as e:
            logger.exception(f"Error offering personality language update: {e}")
            await interaction.response.send_message(
                "❌ Error preparing personality update. Please try again.", 
                ephemeral=True
            )
    
    async def _update_language_only(self, interaction, selected_language):
        """Update language only without personality change."""
        try:
            # Update the parent view
            title, description, content = _build_canvas_behavior_detail(
                self.canvas_view.current_detail, 
                self.canvas_view.admin_visible, 
                self.canvas_view.guild, 
                self.canvas_view.agent_config,
                author_id=str(self.canvas_view.author_id)
            ) or (None, None, "")
            
            self.canvas_view.auto_response_preview = f"✅ Server language set to: {selected_language}"
            behavior_embed = _build_canvas_behavior_embed(
                content or "", 
                self.canvas_view.admin_visible, 
                self.canvas_view.auto_response_preview, 
                title, 
                description
            )
            
            await interaction.response.edit_message(
                content=None, 
                embed=behavior_embed, 
                view=self.canvas_view
            )
        except Exception as e:
            logger.exception(f"Error updating language only: {e}")
            await interaction.response.send_message(
                "❌ Error updating view. Please try again.", 
                ephemeral=True
            )


class _LanguagePersonalityPromptView(discord.ui.View):
    """Ephemeral Yes/No prompt shown after a language change when the current personality
    also supports the new language.  
    - Yes: opens the personality selection flow (with the language already updated)  
    - No: confirms language-only change and edits this message
    """

    def __init__(self, personality_name: str, old_language: str, new_language: str,
                 server_id: str, canvas_view):
        super().__init__(timeout=180)
        self.personality_name = personality_name
        self.old_language = old_language
        self.new_language = new_language
        self.server_id = server_id
        self.canvas_view = canvas_view

        from .canvas_personality import _get_personality_descriptions
        personality_descriptions = _get_personality_descriptions(server_id)
        general_msgs = personality_descriptions.get("general", {})

        yes_button = discord.ui.Button(label=general_msgs.get("option_yes", "Yes"), style=discord.ButtonStyle.green, row=0)
        yes_button.callback = self._on_yes
        self.add_item(yes_button)

        no_button = discord.ui.Button(label=general_msgs.get("option_no", "No"), style=discord.ButtonStyle.red, row=0)
        no_button.callback = self._on_no
        self.add_item(no_button)

    async def _on_yes(self, interaction: discord.Interaction):
        """Open the personality selection dropdown (language already saved)."""
        try:
            from .canvas_personality import CanvasPersonalityView, CanvasPersonalitySelectView

            # Build a minimal parent view so CanvasPersonalitySelectView can work
            parent_view = CanvasPersonalityView(
                author_id=interaction.user.id,
                admin_visible=self.canvas_view.admin_visible,
                guild=interaction.guild,
                message=None,
            )
            selection_view = CanvasPersonalitySelectView(parent_view)
            server_id = get_server_key(interaction.guild) if (get_server_key and interaction.guild) else None
            from .canvas_personality import _get_personality_descriptions
            personality_msgs = _get_personality_descriptions(server_id).get("behavior_messages", {}).get("personality", {})
            instruction_msg = personality_msgs.get("select_personality_instruction", "Select a new personality from the dropdown below:")
            await interaction.response.edit_message(
                content=instruction_msg,
                view=selection_view,
            )
        except Exception as e:
            logger.exception(f"Error opening personality select from language prompt: {e}")
            await interaction.response.edit_message(
                content=f"❌ Error: {str(e)}",
                view=None,
            )
        self.stop()

    async def _on_no(self, interaction: discord.Interaction):
        """Confirm language-only change and edit this ephemeral message."""
        try:
            await interaction.response.edit_message(
                content=f"Language Updated: {self.old_language} → {self.new_language}\n"
                        f"Personality unchanged.",
                view=None,
            )
        except Exception as e:
            logger.exception(f"Error confirming language-only change: {e}")
        self.stop()



class LanguageSelectView(discord.ui.View):
    """View containing only the language select dropdown."""
    
    def __init__(self, view: "CanvasBehaviorView"):
        super().__init__(timeout=300)
        self.add_item(LanguageSelect(view))
        self.canvas_view = view


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
            messages_source = _get_personality_descriptions(None).get("canvas_home_messages", {})
        
        # Load answers.json for DM messages
        from agent_runtime import get_personality_message
        server_id = None
        dm_messages = get_personality_message("answers.json", ["dm_messages"], server_id, {})
        
        # Merge dm_messages into messages_source (dm_messages takes precedence)
        messages_source = {**messages_source, **dm_messages}
        
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
    _g = getattr(interaction, 'guild', None)
    messages_source = _get_personality_descriptions(get_server_key(_g) if _g else None).get("role_descriptions", {}).get("trickster", {}).get("dice_game", {})
    guild, dm_notification_parts = await _get_default_guild_for_dm(interaction, messages_source)
    if guild is None:
        return  # Error already handled by utility function

    server_key = get_server_key(guild)
    server_id = str(guild.id)
    server_name = guild.name
    
    # Get current dice state and personality messages
    dice_state = _get_canvas_dice_state(guild)
    from agent_runtime import get_personality_message
    answers = get_personality_message("answers.json", ["roles", "trickster", "dice_game"], server_key, {})
    descriptions = _get_personality_descriptions(get_server_key(guild) if guild else None).get("role_descriptions", {}).get("trickster", {}).get("dice_game", {})
    trickster_messages = _get_personality_descriptions(get_server_key(guild) if guild else None).get("role_descriptions", {}).get("trickster", {})
    
    # Build the base content with pot balance (title is handled by embed)
    pot_title = descriptions.get("current_balance", "💎 **CURRENT POT:**")
    fixed_bet = descriptions.get("fixed_bet", "💎 **FIXED BET:**")
    content_parts = [
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
                    # Translate combination from English fallback to personality-specific text
                    translated_combination = translate_dice_combination(combination, trickster_messages)
                    content_parts.extend([
                        #"**🎲 DICE PLAY RESULT**",
                        f"{roll_title}\n **{dice_display}**",
                        f"{result_title} **{translated_combination}**",
                        "",
                    ])
                    if prize == dice_state['pot_balance']:
                        pot_winner_msgs = answers.get("pot_winner", ["🎉 **POT WINNER!!!**"])
                        pot_winner_msg = random.choice(pot_winner_msgs) if isinstance(pot_winner_msgs, list) else pot_winner_msgs
                        content_parts.append(f"{prize_title} **{prize:,}** :coin:")
                        content_parts.append(f"\n{pot_winner_msg}\n")
                    elif prize > 0:
                        winner_msgs = answers.get("youwin", ["🎉 **WINNER!!!**"])
                        winner_msg = random.choice(winner_msgs) if isinstance(winner_msgs, list) else winner_msgs
                        content_parts.append(f"{prize_title} **{prize:,}** :coin:")
                        content_parts.append(f"\n{winner_msg}\n")
                    else:
                        loser_msgs = answers.get("youlose", ["😢 **LOSER!**"])
                        loser_msg = random.choice(loser_msgs) if isinstance(loser_msgs, list) else loser_msgs
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
                    # Translate combination from English fallback to personality-specific text
                    translated_combination = translate_dice_combination(combination, trickster_messages)
                    prize_emoji = "💰" if prize > 0 else "💸"
                    
                    content_parts.append(
                        f"👤 {user_name} | {dice_display} → {translated_combination} | {prize_emoji} {prize:,}"
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
        role_embed = _build_canvas_role_embed("trickster", content, view.admin_visible, "dice", None, "Redirected to dice game", server_id=get_server_key(interaction.guild) if interaction.guild else None)
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
    role_embed = _build_canvas_role_embed("trickster", content, view.admin_visible, "dice", None, f"Executed {action_name.replace('_', ' ').title()}", server_id=get_server_key(interaction.guild) if interaction.guild else None)
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
        super().__init__(timeout=900)  # 15 minutes
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
        if current_detail == "personality":
            # Personality view uses its own custom dropdown
            from .canvas_personality import CanvasPersonalitySelect, _get_personality_descriptions as _get_pers_desc
            personality_msgs = _get_pers_desc(get_server_key(guild) if guild else None).get("behavior_messages", {}).get("personality", {})
            self.add_item(CanvasPersonalitySelect(admin_visible, personality_msgs))
        elif current_detail == "conversation":
            self.add_item(CanvasConversationActionSelect(admin_visible, guild))
        elif current_detail == "memory":
            # Add memory type dropdown selector
            memory_dropdown = MemoryTypeSelect(admin_visible, guild, agent_config)
            self.add_item(memory_dropdown)
        elif current_detail in ["greetings", "welcome", "taboo", "settings", "role_control"]:
            self.add_item(CanvasBehaviorActionSelect(current_detail, admin_visible, guild))
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
        detail_items = _get_canvas_behavior_detail_items(self.admin_visible, self.current_detail, self.guild)
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
        super().__init__(timeout=900)  # 15 minutes
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
        
        server_id = get_server_key(guild) if guild else None
        role_details = _get_canvas_role_detail_items(role_name, current_detail, admin_visible, role_name, server_id, self.agent_config)
        current_actions = _get_canvas_role_action_items_for_detail(role_name, current_detail, admin_visible, self.agent_config, server_id)
        if current_actions:
            # For News Watcher, create dynamic dropdowns
            if role_name == "news_watcher" and current_detail in {"personal", "overview"}:
                self.add_item(CanvasWatcherSubscriptionSelect(self))
            elif role_name == "news_watcher" and current_detail == "admin":
                self.add_item(CanvasWatcherAdminActionSelect(self))
            # For MC, create action dropdown
            elif role_name == "mc" and current_detail == "overview":
                self.add_item(CanvasMCActionSelect(self))
            # For Banker, only create dropdown for admin (overview/wallet are info-only)
            elif role_name == "banker" and current_detail == "admin":
                self.add_item(CanvasRoleActionSelect(role_name, current_detail, admin_visible, self.agent_config, self.guild))
            # For other roles, create action dropdown
            else:
                self.add_item(CanvasRoleActionSelect(role_name, current_detail, admin_visible, self.agent_config, self.guild))
        for label, detail_name in role_details:
            self.add_item(CanvasRoleDetailButton(label=label, role_name=role_name, detail_name=detail_name))
            # Add dice_play button after personal button for trickster dice view
            if role_name == "trickster" and current_detail == "dice" and detail_name == "dice":
                server_id = get_server_key(guild) if guild else None
                button_label = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("trickster", {}).get("dice_game", {}).get("dice_play_button", "🎲 Play")
                self.add_item(CanvasTricksterDicePlayButton(label=button_label, style=discord.ButtonStyle.success))
        self._add_role_buttons()
        
        # Add navigation buttons using mixins
        self.add_smart_back_button()
        self.add_home_button()
        
        # Start the timeout timer
        self._reset_timeout()

    def _add_role_buttons(self):
        """Add role-specific buttons."""
        # Add POE2 button only for treasure_hunter main overview (not subrol views)
        # AND only if treasure_hunter is enabled globally in agent_config
        if self.role_name == "treasure_hunter" and self.current_detail == "overview":
            th_global_enabled = (self.agent_config or {}).get("roles", {}).get("treasure_hunter", {}).get("enabled", False)
            if th_global_enabled:
                server_id = get_server_key(self.guild) if self.guild else None
                button_poe2 = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("treasure_hunter", {}).get("button_poe2", "👺 POE2")
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

        title, description, content = _build_canvas_behavior_detail(self.detail_name, view.admin_visible, view.guild, view.agent_config, author_id=str(view.author_id)) or (None, None, "")
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
        behavior_embed = _build_canvas_behavior_embed(content, view.admin_visible, next_view.auto_response_preview, title, description)
        await interaction.response.edit_message(content=None, embed=behavior_embed, view=next_view)


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


CanvasWatcherSubscriptionSelect = _CanvasWatcherSubscriptionSelect
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
BankerConfigModal = _BankerConfigModal



