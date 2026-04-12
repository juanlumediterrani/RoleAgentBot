"""Canvas Personality Management - Change and download personalities from Discord UI.

This module provides Canvas UI components for managing server personalities:
- Change personality: Migrate to a new personality with database management
- Download personality: Export current personality as ZIP
"""

import os
import shutil
import zipfile
import discord
import asyncio
from pathlib import Path
from datetime import datetime, date

# Import core components
try:
    from agent_logging import get_logger
    logger = get_logger('canvas_personality')
except ImportError:
    logger = None

try:
    from discord_bot.db_init import get_server_personality_dir, copy_personality_to_server, update_personality_files
    from discord_bot.discord_utils import get_server_key, is_admin
except ImportError:
    get_server_personality_dir = None
    copy_personality_to_server = None
    update_personality_files = None
    get_server_key = None
    is_admin = None

try:
    from discord_bot import discord_core_commands as core
    _personality_name = core._personality_name
    AGENT_CFG = core.AGENT_CFG
except ImportError:
    _personality_name = "default"
    AGENT_CFG = {}


# ============================================================================
# Helper Functions
# ============================================================================

def _get_available_personalities() -> list[str]:
    """Get list of available personality directories."""
    try:
        base_dir = Path(__file__).parent.parent.parent
        personalities_dir = base_dir / "personalities"
        if not personalities_dir.exists():
            return []
        
        personalities = []
        for item in personalities_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.') and not item.name.startswith('__'):
                # Check if it has a personality.json file
                if (item / "personality.json").exists():
                    personalities.append(item.name)
        return sorted(personalities)
    except Exception as e:
        if logger:
            logger.error(f"Error getting available personalities: {e}")
        return []


def _get_personality_descriptions(server_id: str = None) -> dict:
    """Get personality descriptions from server-specific or global directory."""
    try:
        import json
        from pathlib import Path
        from discord_bot.db_init import get_server_personality_dir
        
        server_dir = get_server_personality_dir(server_id) if get_server_personality_dir else None
        if server_dir:
            server_path = Path(server_dir)
            descriptions_path = server_path / "descriptions.json"
            if descriptions_path.exists():
                with open(descriptions_path, 'r', encoding='utf-8') as f:
                    data = json.load(f).get("discord", {})
                return data
    except Exception as e:
        if logger:
            logger.debug(f"Could not load descriptions for server {server_id}: {e}")
    return {}


def _get_current_personality_name(server_id: str) -> str:
    """Get the current personality name for a server."""
    try:
        server_dir = get_server_personality_dir(server_id) if get_server_personality_dir else None
        if server_dir:
            return Path(server_dir).name
    except Exception as e:
        if logger:
            logger.error(f"Error getting current personality name: {e}")
    return _personality_name


async def _zip_personality(personality_name: str, source_dir: Path) -> Path | None:
    """Create a ZIP archive of a personality directory."""
    try:
        # Create temp directory for ZIP
        temp_dir = Path(__file__).parent.parent.parent / "temp"
        temp_dir.mkdir(exist_ok=True)
        
        zip_path = temp_dir / f"{personality_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(source_dir):
                # Skip __pycache__ directories
                dirs[:] = [d for d in dirs if not d.startswith('__')]
                
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(source_dir)
                    zf.write(file_path, arcname)
        
        return zip_path
    except Exception as e:
        if logger:
            logger.error(f"Error creating ZIP: {e}")
        return None


def _rename_server_databases(server_id: str, old_personality: str, new_personality: str) -> bool:
    """Rename ALL personality-specific databases to match new personality name."""
    try:
        base_dir = Path(__file__).parent.parent.parent
        db_dir = base_dir / "databases" / server_id
        
        if not db_dir.exists():
            return True
        
        # ALL personality-specific database files to rename
        # Note: taboo lives inside behavior_*.db, shared_poe2 is for cross-server market data
        db_mappings = [
            (f"agent_{old_personality}.db", f"agent_{new_personality}.db"),
            (f"roles_{old_personality}.db", f"roles_{new_personality}.db"),
            (f"behavior_{old_personality}.db", f"behavior_{new_personality}.db"),
            (f"watcher_{old_personality}.db", f"watcher_{new_personality}.db"),
            (f"fatigue_{old_personality}.db", f"fatigue_{new_personality}.db"),
        ]
        
        for old_name, new_name in db_mappings:
            old_path = db_dir / old_name
            new_path = db_dir / new_name
            
            if old_path.exists():
                # If new file exists, remove it first
                if new_path.exists():
                    new_path.unlink()
                
                # Rename the file
                old_path.rename(new_path)
                if logger:
                    logger.info(f"Renamed {old_name} -> {new_name}")
        
        
        return True
    except Exception as e:
        if logger:
            logger.error(f"Error renaming databases: {e}")
        return False


def _delete_database(server_id: str, db_name: str) -> bool:
    """Delete a specific database file."""
    try:
        base_dir = Path(__file__).parent.parent.parent
        db_path = base_dir / "databases" / server_id / db_name
        
        if db_path.exists():
            db_path.unlink()
            if logger:
                logger.info(f"Deleted database: {db_name}")
            return True
        return False
    except Exception as e:
        if logger:
            logger.error(f"Error deleting database {db_name}: {e}")
        return False


def _delete_personality_directory(server_id: str, personality_name: str) -> bool:
    """Delete a personality directory from server."""
    try:
        base_dir = Path(__file__).parent.parent.parent
        personality_dir = base_dir / "databases" / server_id / personality_name
        
        if personality_dir.exists():
            shutil.rmtree(personality_dir)
            if logger:
                logger.info(f"Deleted personality directory: {personality_dir}")
            return True
        return False
    except Exception as e:
        if logger:
            logger.error(f"Error deleting personality directory: {e}")
        return False


# ============================================================================
# Canvas Views
# ============================================================================

class CanvasPersonalityView(discord.ui.View):
    """View for personality management with dropdown options."""
    
    def __init__(self, author_id: int, admin_visible: bool, guild=None, message=None):
        super().__init__(timeout=900)  # 15 minutes
        self.author_id = author_id
        self.admin_visible = admin_visible
        self.guild = guild
        self.message = message
        
        # Get personality-specific labels
        server_id = get_server_key(guild) if (get_server_key and guild) else None
        personality_msgs = _get_personality_descriptions(server_id).get("personality_messages", {})
        
        # Add dropdown with personality options
        self.add_item(CanvasPersonalitySelect(admin_visible, personality_msgs))
        
        # Add navigation buttons
        server_id = get_server_key(guild) if (get_server_key and guild) else None
        personality_descriptions = _get_personality_descriptions(server_id)
        
        # Back button
        back_label = personality_descriptions.get("canvas_home_messages", {}).get("button_back", "← Back")
        from .ui import CanvasSmartBackButton
        self.add_item(CanvasSmartBackButton(label=back_label, row=4))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive Canvas to its original user."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True
    
    async def on_timeout(self) -> None:
        """Called when the view times out."""
        try:
            if self.message:
                await self.message.delete()
        except:
            pass
        self.stop()


class CanvasPersonalitySelect(discord.ui.Select):
    """Dropdown for personality management options."""
    
    def __init__(self, admin_visible: bool, personality_msgs: dict):
        self.personality_msgs = personality_msgs
        
        # Get labels from descriptions or use defaults
        change_label = personality_msgs.get("option_change", "Change Personality")
        change_desc = personality_msgs.get("option_change_desc", "Switch to a different bot personality")
        download_label = personality_msgs.get("option_download", "Download Current")
        download_desc = personality_msgs.get("option_download_desc", "Export current personality as ZIP")
        
        options = [
            discord.SelectOption(
                label=change_label, 
                value="change_personality", 
                description=change_desc,
                emoji="🔄"
            ),
            discord.SelectOption(
                label=download_label, 
                value="download_personality", 
                description=download_desc,
                emoji="📦"
            ),
        ]
        
        placeholder = personality_msgs.get("placeholder", "Choose a personality action...")
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, row=1)
    
    async def callback(self, interaction: discord.Interaction):
        """Handle selection from dropdown."""
        # Check if view is valid (either CanvasPersonalityView or CanvasBehaviorView)
        if not hasattr(self.view, 'guild') or not hasattr(self.view, 'admin_visible'):
            await interaction.response.send_message("❌ Personality management not available.", ephemeral=True)
            return
        
        selected = self.values[0]
        
        if selected == "change_personality":
            # Open selection view (step 1 of 2)
            from .ui import CanvasBehaviorView
            modal_view = self.view if isinstance(self.view, CanvasPersonalityView) else None
            if modal_view is None and isinstance(self.view, CanvasBehaviorView):
                # Create a temporary personality view for the selection
                modal_view = CanvasPersonalityView(
                    author_id=self.view.author_id,
                    admin_visible=self.view.admin_visible,
                    guild=self.view.guild,
                    message=self.view.message
                )
            if modal_view:
                selection_view = CanvasPersonalitySelectView(modal_view)
                await interaction.response.send_message(
                    "Select a new personality from the dropdown below:",
                    view=selection_view,
                    ephemeral=True
                )
        
        elif selected == "download_personality":
            await self._handle_download(interaction)
    
    async def _handle_download(self, interaction: discord.Interaction):
        """Handle downloading current personality as ZIP."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        try:
            server_id = get_server_key(self.view.guild) if (get_server_key and self.view.guild) else None
            if not server_id:
                await interaction.followup.send("❌ Server ID not available.", ephemeral=True)
                return
            
            # Get current personality directory
            current_personality = _get_current_personality_name(server_id)
            base_dir = Path(__file__).parent.parent.parent
            personality_dir = base_dir / "databases" / server_id / current_personality
            
            # Fallback to global personality if server-specific doesn't exist
            if not personality_dir.exists():
                personality_dir = base_dir / "personalities" / current_personality
            
            if not personality_dir.exists():
                await interaction.followup.send(f"❌ Personality directory not found: {current_personality}", ephemeral=True)
                return
            
            # Create ZIP
            zip_path = await _zip_personality(current_personality, personality_dir)
            
            if not zip_path or not zip_path.exists():
                await interaction.followup.send("❌ Failed to create ZIP archive.", ephemeral=True)
                return
            
            # Send file
            file = discord.File(zip_path, filename=f"{current_personality}.zip")
            
            personality_msgs = _get_personality_descriptions(server_id).get("personality_messages", {})
            success_msg = personality_msgs.get("download_success", "✅ Personality `{personality}` exported successfully!")
            
            await interaction.followup.send(
                content=success_msg.format(personality=current_personality),
                file=file,
                ephemeral=True
            )
            
            # Clean up temp file
            try:
                zip_path.unlink()
            except:
                pass
                
        except Exception as e:
            if logger:
                logger.exception(f"Error downloading personality: {e}")
            await interaction.followup.send(f"❌ Error downloading personality: {str(e)}", ephemeral=True)


class CanvasPersonalitySelectView(discord.ui.View):
    """View for selecting personality with dropdown (step 1 of 2)."""
    
    def __init__(self, parent_view: CanvasPersonalityView):
        super().__init__(timeout=300)
        self.parent_view = parent_view
        self.selected_personality = None
        self.old_personality = None
        
        # Get available personalities
        available = _get_available_personalities()
        
        # Personality selection dropdown
        options = [
            discord.SelectOption(label=pers, value=pers)
            for pers in available
        ]
        
        self.personality_select = discord.ui.Select(
            placeholder="Choose a personality...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )
        self.personality_select.callback = self._on_select
        self.add_item(self.personality_select)
        
        # Add Confirm and Cancel buttons (initially disabled)
        self.confirm_button = discord.ui.Button(
            label="Confirm",
            style=discord.ButtonStyle.green,
            disabled=True,
            row=1
        )
        self.confirm_button.callback = self._on_confirm
        self.add_item(self.confirm_button)
        
        self.cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.red,
            row=1
        )
        self.cancel_button.callback = self._on_cancel
        self.add_item(self.cancel_button)
    
    def _load_personality_info(self, personality_name: str) -> str:
        """Load identity_body from personality.json."""
        try:
            base_dir = Path(__file__).parent.parent.parent
            personality_file = base_dir / "personalities" / personality_name / "personality.json"
            
            if personality_file.exists():
                import json
                with open(personality_file, 'r', encoding='utf-8') as f:
                    personality_data = json.load(f)
                
                identity_body = personality_data.get("system_prompt_template", {}).get("identity_body", [])
                if identity_body:
                    # Join the identity body lines
                    return "\n".join(identity_body)
            return "No personality description available."
        except Exception as e:
            if logger:
                logger.warning(f"Could not load personality info for {personality_name}: {e}")
            return "Could not load personality description."
    
    async def _on_select(self, interaction: discord.Interaction):
        """Handle personality selection and show personality info."""
        try:
            if not self.parent_view.guild:
                await interaction.response.send_message("❌ This action is only available in a server.", ephemeral=True)
                return
            
            if not self.parent_view.admin_visible:
                await interaction.response.send_message("❌ This action is admin-only.", ephemeral=True)
                return
            
            new_personality = self.personality_select.values[0]
            self.selected_personality = new_personality
            
            # Get current personality
            server_id = str(self.parent_view.guild.id)
            self.old_personality = _get_current_personality_name(server_id)
            
            if self.old_personality == new_personality:
                await interaction.response.send_message(
                    f"❌ The bot is already using the `{new_personality}` personality.",
                    ephemeral=True
                )
                self.stop()
                return
            
            # Load personality info
            personality_info = self._load_personality_info(new_personality)
            
            # Enable confirm button and update message
            self.confirm_button.disabled = False
            
            await interaction.response.edit_message(
                content=f"**Selected Personality: {new_personality}**\n\n{personality_info}",
                view=self
            )
                
        except Exception as e:
            if logger:
                logger.exception(f"Error in personality selection view: {e}")
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            self.stop()
    
    async def _on_confirm(self, interaction: discord.Interaction):
        """Handle confirm button - open confirmation view."""
        try:
            if not self.selected_personality:
                await interaction.response.send_message("❌ No personality selected.", ephemeral=True)
                return

            # Edit the current message to show confirmation view instead of deleting
            confirm_view = CanvasPersonalityConfirmView(self.parent_view, self.selected_personality, self.old_personality)
            await interaction.response.edit_message(
                content=f"**Confirm change to {self.selected_personality}?**\nSelect your options below:",
                view=confirm_view
            )
            self.stop()

        except Exception as e:
            if logger:
                logger.exception(f"Error in confirm callback: {e}")
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            self.stop()

    async def _on_cancel(self, interaction: discord.Interaction):
        """Handle cancel button - dismiss the message."""
        await interaction.message.delete()
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive view to its original user."""
        if interaction.user.id != self.parent_view.author_id:
            await interaction.response.send_message("❌ This menu belongs to another user.", ephemeral=True)
            return False
        return True


class CanvasPersonalityConfirmView(discord.ui.View):
    """View for confirming personality change with boolean selectors (step 2 of 2)."""
    
    def __init__(self, parent_view: CanvasPersonalityView, new_personality: str, old_personality: str):
        super().__init__(timeout=300)
        self.parent_view = parent_view
        self.new_personality = new_personality
        self.old_personality = old_personality
        
        # Get personality messages for labels
        server_id = get_server_key(parent_view.guild) if (get_server_key and parent_view.guild) else None
        personality_msgs = _get_personality_descriptions(server_id).get("personality_messages", {})
        
        # Boolean options: Yes/No
        yes_no_options = [
            discord.SelectOption(label="Yes", value="yes"),
            discord.SelectOption(label="No", value="no")
        ]
        
        # Download old personality selector
        self.download_old_select = discord.ui.Select(
            placeholder=personality_msgs.get("modal_download_label", "Download old personality?"),
            min_values=1,
            max_values=1,
            options=yes_no_options,
            row=0
        )
        self.download_old_select.callback = self._dummy_callback
        self.add_item(self.download_old_select)
        
        # Delete memory selector
        self.delete_memory_select = discord.ui.Select(
            placeholder=personality_msgs.get("modal_delete_memory_label", "Delete bot memory?"),
            min_values=1,
            max_values=1,
            options=yes_no_options,
            row=1
        )
        self.delete_memory_select.callback = self._dummy_callback
        self.add_item(self.delete_memory_select)
        
        # Download memory selector
        self.download_memory_select = discord.ui.Select(
            placeholder=personality_msgs.get("modal_download_memory_label", "Download memory first?"),
            min_values=1,
            max_values=1,
            options=yes_no_options,
            row=2
        )
        self.download_memory_select.callback = self._dummy_callback
        self.add_item(self.download_memory_select)
        
        # Confirm and Cancel buttons
        self.confirm_button = discord.ui.Button(
            label="Confirm Change",
            style=discord.ButtonStyle.green,
            row=3
        )
        self.confirm_button.callback = self._on_confirm
        self.add_item(self.confirm_button)
        
        self.cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.red,
            row=3
        )
        self.cancel_button.callback = self._on_cancel
        self.add_item(self.cancel_button)
    
    async def _dummy_callback(self, interaction: discord.Interaction):
        """Dummy callback for Select dropdowns - just acknowledge selection."""
        await interaction.response.defer()
    
    async def _on_confirm(self, interaction: discord.Interaction):
        """Handle personality change confirmation and execution."""
        try:
            if not self.parent_view.guild:
                await interaction.response.send_message("❌ This action is only available in a server.", ephemeral=True)
                return

            if not self.parent_view.admin_visible:
                await interaction.response.send_message("❌ This action is admin-only.", ephemeral=True)
                return

            # Track messages for cleanup
            message1 = None  # Initial progress message
            message2 = None  # Memory synthesis message
            message3 = None  # Success message

            # Edit message to show progress, then send followup messages
            await interaction.response.edit_message(
                content=f"⏳ Changing personality from `{self.old_personality}` to `{self.new_personality}`...",
                view=None
            )
            # Store the original message reference
            message1 = interaction.message

            server_id = str(self.parent_view.guild.id)
            new_personality = self.new_personality
            old_personality = self.old_personality
            download_old = self.download_old_select.values[0] == "yes"
            delete_memory = self.delete_memory_select.values[0] == "yes"
            download_memory = self.download_memory_select.values[0] == "yes"

            base_dir = Path(__file__).parent.parent.parent
            server_db_dir = base_dir / "databases" / server_id

            # Step 1: Download old personality if requested
            if download_old:
                old_personality_dir = base_dir / "databases" / server_id / old_personality
                if not old_personality_dir.exists():
                    old_personality_dir = base_dir / "personalities" / old_personality

                if old_personality_dir.exists():
                    zip_path = await _zip_personality(old_personality, old_personality_dir)
                    if zip_path and zip_path.exists():
                        file = discord.File(zip_path, filename=f"{old_personality}_backup.zip")
                        await interaction.followup.send(
                            content=f"📦 Backup of `{old_personality}` created. Proceeding with migration...",
                            file=file,
                            ephemeral=True
                        )
                        try:
                            zip_path.unlink()
                        except:
                            pass
                    else:
                        await interaction.followup.send(
                            "⚠️ Could not create backup. Proceeding with migration anyway...",
                            ephemeral=True
                        )
                else:
                    await interaction.followup.send(
                        f"⚠️ Old personality directory not found. Proceeding with migration...",
                        ephemeral=True
                    )

            # Step 2: Download memory if requested (before any deletion/rename)
            if download_memory:
                agent_db_path = server_db_dir / f"agent_{old_personality}.db"
                if agent_db_path.exists():
                    file = discord.File(agent_db_path, filename=f"agent_{old_personality}_memory_backup.db")
                    await interaction.followup.send(
                        content=f"📦 Memory database backup attached.",
                        file=file,
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"⚠️ Memory database not found at {agent_db_path}",
                        ephemeral=True
                    )
            
            # Step 3: Handle databases FIRST (before copying new personality)
            # This ensures we preserve/transfer memory before new personality overwrites files
            if delete_memory:
                # Delete agent database (memory) and rename others
                _delete_database(server_id, f"agent_{old_personality}.db")
                _rename_server_databases(server_id, old_personality, new_personality)
                # Create new agent database for new personality
                new_agent_db = server_db_dir / f"agent_{new_personality}.db"
                if not new_agent_db.exists():
                    from agent_db import AgentDatabase
                    AgentDatabase(server_id)  # This will create the database
            else:
                # Rename all databases including agent (preserve memory for new personality)
                _rename_server_databases(server_id, old_personality, new_personality)
                # Also rename agent database specifically
                old_agent = server_db_dir / f"agent_{old_personality}.db"
                new_agent = server_db_dir / f"agent_{new_personality}.db"
                if old_agent.exists():
                    if new_agent.exists():
                        new_agent.unlink()
                    old_agent.rename(new_agent)
            
            # Step 4: Delete old personality directory
            _delete_personality_directory(server_id, old_personality)
            
            # Step 5: Copy new personality files (JSON configs) to server
            # Note: .db databases are already renamed in Step 3, no conflict here
            success = False
            if copy_personality_to_server:
                success = copy_personality_to_server(server_id, new_personality)

            if not success:
                await interaction.followup.send(
                    f"❌ Failed to copy new personality `{new_personality}` to server.",
                    ephemeral=True
                )
                return

            # Step 5b: Always update JSON config files to ensure descriptions are current
            # This is crucial when switching personalities to get correct Canvas paragraphs
            if update_personality_files:
                files_updated = update_personality_files(server_id, new_personality)
                if logger:
                    if files_updated:
                        logger.info(f"✅ Updated personality files for {new_personality}")
                    else:
                        logger.warning(f"⚠️ Could not update personality files for {new_personality}")
            
            # Step 6: Save server-specific config with active personality
            try:
                import json
                server_config_dir = base_dir / "databases" / server_id
                server_config_dir.mkdir(parents=True, exist_ok=True)
                server_config_path = server_config_dir / "server_config.json"
                
                server_config = {}
                if server_config_path.exists():
                    with open(server_config_path, 'r', encoding='utf-8') as f:
                        server_config = json.load(f)
                
                # Update active personality for this server
                server_config['active_personality'] = new_personality
                with open(server_config_path, 'w', encoding='utf-8') as f:
                    json.dump(server_config, f, indent=2, ensure_ascii=False)
                
                if logger:
                    logger.info(f"Saved server config with active personality: {new_personality}")
            except Exception as config_error:
                if logger:
                    logger.warning(f"Could not save server config: {config_error}")
            
            # Reload personality in memory
            try:
                from agent_engine import reload_personality
                reload_personality(server_id)  # Pass server_id to clear specific cache
                # Also reload descriptions cache
                global _personality_descriptions_cache, _personality_descriptions_cache_server_id
                _personality_descriptions_cache = {}
                _personality_descriptions_cache_server_id = None
                
                # IMPORTANT: Invalidate ALL cached database instances AFTER database renaming
                # This ensures new instances point to the correct personality database files
                if logger:
                    logger.info(f"🔄 Invalidating all database caches for server {server_id} after personality change")
                
                # Helper function to safely invalidate database caches
                def _invalidate_cache(import_path, func_name, db_name):
                    """Safely invalidate a database cache with error handling."""
                    try:
                        module = __import__(import_path, fromlist=[func_name])
                        invalidate_func = getattr(module, func_name)
                        invalidate_func(server_id)
                        if logger:
                            logger.info(f"✅ Invalidated {db_name} db cache for server {server_id}")
                    except Exception as err:
                        if logger:
                            logger.warning(f"Could not invalidate {db_name} db instance: {err}")
                
                # Invalidate all database caches
                _invalidate_cache('agent_db', 'invalidate_db_instance', 'agent')
                _invalidate_cache('agent_roles_db', 'invalidate_roles_db_instance', 'roles')
                _invalidate_cache('behavior.db_behavior', 'invalidate_behavior_db_instance', 'behavior')
                _invalidate_cache('roles.news_watcher.db_role_news_watcher', 'invalidate_news_watcher_db_instance', 'news_watcher')
                _invalidate_cache('roles.treasure_hunter.db_role_treasure_hunter', 'invalidate_poe_db_instance', 'POE')
                
                # Invalidate beggar config cache
                try:
                    from roles.trickster.subroles.beggar.beggar_config import invalidate_beggar_config_cache
                    invalidate_beggar_config_cache(server_id)
                    if logger:
                        logger.info(f"✅ Invalidated beggar config cache for server {server_id}")
                except Exception as err:
                    if logger:
                        logger.warning(f"Could not invalidate beggar config cache: {err}")
                
                # Step 7: Initialize memory synthesis for the NEW personality (always)
                # This creates initial daily memory and schedules the next task
                try:
                    from agent_mind import generate_daily_memory_summary
                    msg2 = await interaction.followup.send(
                        "🧠 Generating initial memory synthesis for new personality...",
                        ephemeral=True
                    )
                    message2 = msg2
                    # Force personality reload to ensure we use the correct one
                    from agent_engine import _get_personality
                    _get_personality(server_id)  # Pass server_id to load correct personality
                    
                    memory_summary = generate_daily_memory_summary(server_id=server_id)
                    if memory_summary:
                        if logger:
                            logger.info(f"✅ Initial memory synthesis generated for {new_personality}")
                    else:
                        if logger:
                            logger.warning(f"⚠️ No memory summary generated (may be normal for new personality)")
                    
                    # Step 8: Initialize recent memory with fallback
                    try:
                        from agent_mind import _get_recent_memory_fallback
                        from agent_db import get_db_instance
                        db_instance = get_db_instance(server_id)
                        recent_fallback = _get_recent_memory_fallback(server_id)
                        if recent_fallback:
                            db_instance.upsert_recent_memory(
                                summary=recent_fallback,
                                memory_date=date.today().isoformat(),
                                metadata={"source": "personality_change_fallback"}
                            )
                            if logger:
                                logger.info(f"✅ Recent memory initialized with fallback for {new_personality}")
                    except Exception as recent_error:
                        if logger:
                            logger.warning(f"Could not initialize recent memory: {recent_error}")
                    
                    # Step 9: Initialize relationship memory with fallback (for generic user)
                    try:
                        from agent_mind import _get_relationship_memory_fallback
                        relationship_fallback = _get_relationship_memory_fallback("default_user", server_id)
                        if relationship_fallback:
                            db_instance.upsert_user_relationship_memory(
                                user_id="default",
                                summary=relationship_fallback,
                                last_interaction_at=datetime.now().isoformat(),
                                metadata={"source": "personality_change_fallback"}
                            )
                            if logger:
                                logger.info(f"✅ Relationship memory initialized with fallback for {new_personality}")
                    except Exception as relationship_error:
                        if logger:
                            logger.warning(f"Could not initialize relationship memory: {relationship_error}")
                except Exception as synthesis_error:
                    if logger:
                        logger.warning(f"Could not generate initial memory synthesis: {synthesis_error}")
                    # Non-critical error, don't block the personality change
            except Exception as reload_error:
                if logger:
                    logger.warning(f"Could not reload personality in memory: {reload_error}")

            # Get success message
            personality_msgs = _get_personality_descriptions(server_id).get("personality_messages", {})
            success_msg = personality_msgs.get(
                "change_success",
                "✅ Personality changed from `{old}` to `{new}`! The new personality is now active."
            )

            # Delete message1 (initial progress) when sending message3 (success)
            try:
                if message1:
                    await message1.delete()
            except:
                pass

            # Send message3 (success message)
            await interaction.followup.send(
                success_msg.format(old=old_personality, new=new_personality),
                ephemeral=True
            )
            self.stop()

        except Exception as e:
            if logger:
                logger.exception(f"Error in personality change confirmation view: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
            self.stop()

    async def _on_cancel(self, interaction: discord.Interaction):
        """Handle cancel button - dismiss the message."""
        await interaction.message.delete()
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive view to its original user."""
        if interaction.user.id != self.parent_view.author_id:
            await interaction.response.send_message("❌ This menu belongs to another user.", ephemeral=True)
            return False
        return True


# ============================================================================
# Public API
# ============================================================================

def build_canvas_personality_content(admin_visible: bool, guild=None) -> tuple[str, str, str]:
    """Build the personality management view content.
    
    Returns:
        tuple: (title, description, content)
    """
    server_id = get_server_key(guild) if (get_server_key and guild) else None
    personality_msgs = _get_personality_descriptions(server_id).get("personality_messages", {})
    
    current_personality = _get_current_personality_name(server_id) if server_id else _personality_name
    
    # Get available personalities
    available = _get_available_personalities()
    available_list = "\n".join([f"• `{p}`" for p in available]) if available else "No personalities found"
    
    title = personality_msgs.get("view_title", "🎭 Personality Management")
    description = personality_msgs.get("view_description", "Change or download the bot's personality for this server.")
    
    content = f"""
**Current Personality:** `{current_personality}`

**Available Personalities:**
{available_list}

**⚠️ Important Notes:**
• Changing personality will migrate all configuration files
• You can choose to preserve or delete the bot's memory
• Database files will be renamed to match the new personality
• The bot may need a restart to fully apply changes
"""
    
    return title, description, content


async def handle_canvas_personality_action(interaction: discord.Interaction, action_name: str, view) -> None:
    """Handle personality-related Canvas actions."""
    # This function is a placeholder for future expansion
    # Currently, all actions are handled within the modal classes
    pass
