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
    from discord_bot.discord_utils import get_server_key, is_admin, sync_bot_identity_to_server_personality, update_server_identity
except ImportError:
    get_server_personality_dir = None
    copy_personality_to_server = None
    update_personality_files = None
    get_server_key = None
    is_admin = None
    sync_bot_identity_to_server_personality = None
    update_server_identity = None

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

def _get_available_personalities(language: str = None) -> list[str]:
    """Get list of available personality directories.

    If language is provided, only returns personalities that have
    a subdirectory for that language (e.g., personalities/<name>/<language>/).

    Args:
        language: IETF BCP 47 language code (e.g., "es-ES", "en-US")

    Returns:
        List of personality names that are available
    """
    try:
        base_dir = Path(__file__).parent.parent.parent
        personalities_dir = base_dir / "personalities"
        if not personalities_dir.exists():
            return []

        personalities = []
        for item in personalities_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.') and not item.name.startswith('__'):
                if language:
                    # New structure: check if language subdirectory exists with personality.json
                    lang_dir = item / language
                    if lang_dir.exists() and (lang_dir / "personality.json").exists():
                        personalities.append(item.name)
                    else:
                        # Fallback: check old structure (for backward compatibility)
                        if (item / "personality.json").exists():
                            personalities.append(item.name)
                else:
                    # No language filter - check old structure
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
        from discord_bot.canvas.content import _get_personality_descriptions as _full_get
        return _full_get(server_id)
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


def _get_current_personality_with_language(server_id: str) -> str:
    """Get the current personality name with language context for comparison."""
    try:
        # Get current personality name
        personality_name = _get_current_personality_name(server_id)

        # Get current language
        try:
            from .server_config import get_server_language
            current_language = get_server_language(server_id)
        except Exception:
            current_language = "en-US"

        # Create a unique identifier that includes both personality and language
        return f"{personality_name}:{current_language}"
    except Exception as e:
        if logger:
            logger.error(f"Error getting current personality with language: {e}")
        return f"{_personality_name}:en-US"


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
        # Note: behavior.db is now shared across personalities (no longer per-personality)
        # Note: shared_poe2 is for cross-server market data
        db_mappings = [
            (f"agent_{old_personality}.db", f"agent_{new_personality}.db"),
            (f"roles_{old_personality}.db", f"roles_{new_personality}.db"),
            # behavior.db is now shared - no longer renamed
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


def _invalidate_db_cache(import_path: str, func_name: str, db_name: str, server_id: str) -> None:
    """Safely invalidate a database cache instance for a given server."""
    try:
        module = __import__(import_path, fromlist=[func_name])
        invalidate_func = getattr(module, func_name)
        invalidate_func(server_id)
        if logger:
            logger.info(f"✅ Invalidated {db_name} db cache for server {server_id}")
    except Exception as err:
        if logger:
            logger.warning(f"Could not invalidate {db_name} db instance: {err}")


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

        # Get personality-specific labels (single call, reused below)
        server_id = get_server_key(guild) if (get_server_key and guild) else None
        personality_descriptions = _get_personality_descriptions(server_id)
        personality_msgs = personality_descriptions.get("behavior_messages", {}).get("personality", {})

        # Add dropdown with personality options
        self.add_item(CanvasPersonalitySelect(admin_visible, personality_msgs))

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
        upload_label = personality_msgs.get("option_upload", "Upload Custom Personality")
        upload_desc = personality_msgs.get("option_upload_desc", "Upload your own personality ZIP file")

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

        # Only show upload option to admins
        if admin_visible:
            options.append(
                discord.SelectOption(
                    label=upload_label,
                    value="upload_personality",
                    description=upload_desc,
                    emoji="📤"
                )
            )

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
                server_id = get_server_key(self.view.guild) if (get_server_key and self.view.guild) else None
                personality_msgs = _get_personality_descriptions(server_id).get("behavior_messages", {}).get("personality", {})
                instruction_msg = personality_msgs.get("select_personality_instruction", "Select a new personality from the dropdown below:")
                await interaction.response.send_message(
                    instruction_msg,
                    view=selection_view,
                    ephemeral=True
                )

        elif selected == "download_personality":
            await self._handle_download(interaction)

        elif selected == "upload_personality":
            await self._handle_upload(interaction)

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

            personality_msgs = _get_personality_descriptions(server_id).get("behavior_messages", {}).get("personality", {})
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

    async def _handle_upload(self, interaction: discord.Interaction):
        """Handle uploading custom personality as ZIP."""
        try:
            from discord_bot.personality_upload import (
                check_upload_cooldown,
                format_cooldown_time,
                MAX_ZIP_SIZE_BYTES,
                get_personality_descriptions,
            )

            server_id = get_server_key(self.view.guild) if (get_server_key and self.view.guild) else None
            if not server_id:
                await interaction.response.send_message("❌ Server ID not available.", ephemeral=True)
                return

            # Check rate limiting
            can_upload, cooldown_remaining = check_upload_cooldown(server_id)
            if not can_upload:
                await interaction.response.send_message(
                    f"⏱️ Debes esperar {format_cooldown_time(cooldown_remaining)} antes de subir otra personalidad.",
                    ephemeral=True
                )
                return

            # Get server language for template
            try:
                from .server_config import get_server_language
                server_language = get_server_language(server_id)
            except Exception:
                server_language = "en-US"

            # Load personality descriptions for localized messages
            personality_msgs = get_personality_descriptions(server_id)

            # Fallback to English messages
            upload_title = personality_msgs.get("upload_title", "📤 **Upload Custom Personality**")
            upload_command_instruction = personality_msgs.get("upload_command_instruction", "To upload your personality, use the `!uploadpersonality` command with a ZIP file attached.")
            upload_requirements_title = personality_msgs.get("upload_requirements_title", "📋 **ZIP Requirements:**")
            upload_max_size = personality_msgs.get("upload_max_size", f"• Max size: {MAX_ZIP_SIZE_BYTES / (1024*1024):.0f}MB")
            upload_allowed_files = personality_msgs.get("upload_allowed_files", "• Allowed files: .json, .png, .jpg, .webp, .md, .txt")
            upload_optional_files = personality_msgs.get("upload_optional_files", "• Optional files: personality.json, prompts.json, answers.json, descriptions.json")
            upload_cooldown = personality_msgs.get("upload_cooldown", "⏱️ **Cooldown:** 30 minutes between uploads")
            upload_analysis = personality_msgs.get("upload_analysis", "🔍 **Analysis:** Content will be analyzed automatically")
            upload_template_hint = personality_msgs.get("upload_template_hint", f"💡 **Need a template?** Use the button below to download the RAB personality in **{server_language}** as reference.")
            upload_example = personality_msgs.get("upload_example", "**Example:** `!uploadpersonality` (with ZIP attached)")
            upload_template_button = personality_msgs.get("upload_template_button", f"📥 Download RAB template ({server_language})")

            # Send ephemeral message with instructions and template button
            instructions = (
                f"{upload_title}\n\n"
                f"{upload_command_instruction}\n\n"
                f"{upload_requirements_title}\n"
                f"{upload_max_size}\n"
                f"{upload_allowed_files}\n"
                f"{upload_optional_files}\n\n"
                f"{upload_cooldown}\n"
                f"{upload_analysis}\n\n"
                f"{upload_template_hint}\n\n"
                f"{upload_example}"
            )

            # Create view with template download button
            view = discord.ui.View(timeout=300)
            template_button = discord.ui.Button(
                label=upload_template_button,
                style=discord.ButtonStyle.secondary,
                custom_id="download_rab_template"
            )

            async def template_callback(template_interaction: discord.Interaction):
                await template_interaction.response.defer(thinking=True, ephemeral=True)
                await self._send_rab_template(template_interaction, server_id, server_language)

            template_button.callback = template_callback
            view.add_item(template_button)

            await interaction.response.send_message(instructions, view=view, ephemeral=True)

        except Exception as e:
            if logger:
                logger.exception(f"Error initiating upload: {e}")
            await interaction.response.send_message(f"❌ Error initiating upload: {str(e)}", ephemeral=True)

    async def _send_rab_template(self, interaction: discord.Interaction, server_id: str, language: str):
        """Send RAB personality as template ZIP."""
        try:
            base_dir = Path(__file__).parent.parent.parent

            # Try language-specific path first
            rab_dir = base_dir / "personalities" / "rab" / language
            if not rab_dir.exists():
                # Fallback to default structure without language
                rab_dir = base_dir / "personalities" / "rab"
                if not rab_dir.exists():
                    await interaction.followup.send("❌ Template personality (RAB) not found.", ephemeral=True)
                    return

            if not (rab_dir / "personality.json").exists():
                await interaction.followup.send("❌ Template personality files not found.", ephemeral=True)
                return

            # Create ZIP
            zip_path = await _zip_personality(f"rab_template_{language}", rab_dir)

            if not zip_path or not zip_path.exists():
                await interaction.followup.send("❌ Failed to create template ZIP.", ephemeral=True)
                return

            # Send file
            file = discord.File(zip_path, filename=f"rab_template_{language}.zip")

            await interaction.followup.send(
                content=f"📥 **Plantilla RAB ({language})**\n\n"
                        f"Usa esta plantilla como referencia para crear tu personalidad personalizada.\n"
                        f"Incluye todos los archivos necesarios con la estructura correcta.",
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
                logger.exception(f"Error sending RAB template: {e}")
            await interaction.followup.send(f"❌ Error creating template: {str(e)}", ephemeral=True)


class CanvasPersonalitySelectView(discord.ui.View):
    """View for selecting personality with dropdown (step 1 of 2).

    Only shows personalities that are available for the server's configured language.
    """

    def __init__(self, parent_view: CanvasPersonalityView):
        super().__init__(timeout=300)
        self.parent_view = parent_view
        self.selected_personality = None
        self.old_personality = None

        # Get server's configured language
        self.server_language = self._get_server_language()

        # Get available personalities for this language
        available = _get_available_personalities(self.server_language)

        # If no personalities available for this language, show all (fallback)
        if not available:
            available = _get_available_personalities()

        # Personality selection dropdown
        if available:
            options = [
                discord.SelectOption(label=pers, value=pers)
                for pers in available
            ]
            server_id = get_server_key(self.parent_view.guild) if (get_server_key and self.parent_view.guild) else None
            personality_msgs = _get_personality_descriptions(server_id).get("behavior_messages", {}).get("personality", {})
            placeholder = personality_msgs.get("choose_personality_placeholder", "Choose a personality (language: {language})...").format(language=self.server_language)
        else:
            options = [discord.SelectOption(label="No personalities available", value="none")]
            placeholder = "No personalities available"

        self.personality_select = discord.ui.Select(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=0,
            disabled=not available
        )
        self.personality_select.callback = self._on_select
        self.add_item(self.personality_select)

        # Add Confirm and Cancel buttons (initially disabled)
        server_id = get_server_key(self.parent_view.guild) if (get_server_key and self.parent_view.guild) else None
        personality_descriptions = _get_personality_descriptions(server_id)
        general_msgs = personality_descriptions.get("general", {})
        self.confirm_button = discord.ui.Button(
            label=general_msgs.get("button_confirm", "Confirm"),
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

    def _get_server_language(self, server_id: str = None) -> str:
        """Get the configured language for the server."""
        try:
            from .server_config import get_server_language
            sid = server_id or (str(self.parent_view.guild.id) if self.parent_view.guild else None)
            if sid:
                return get_server_language(sid)
        except Exception as e:
            if logger:
                logger.debug(f"Could not get server language: {e}")
        return "en-US"

    def _truncate_to_limit(self, text: str, max_length: int = 2000) -> str:
        """Truncate text to max_length, trying to cut at paragraph or sentence boundaries."""
        if len(text) <= max_length:
            return text

        # Try to cut at paragraph boundary (double newline)
        truncated = text[:max_length]
        last_paragraph = truncated.rfind('\n\n')
        if last_paragraph > max_length * 0.7:  # Only use if we keep at least 70%
            return text[:last_paragraph].rstrip()

        # Try to cut at sentence boundary (. ! ?)
        for punctuation in ['.', '!', '?']:
            last_sentence = truncated.rfind(punctuation)
            if last_sentence > max_length * 0.7:
                return text[:last_sentence + 1].rstrip()

        # Fallback: cut at last space
        last_space = truncated.rfind(' ')
        if last_space > max_length * 0.7:
            return text[:last_space].rstrip()

        # Last resort: hard cut
        return text[:max_length].rstrip()

    def _load_personality_info(self, personality_name: str) -> str:
        """Load identity_body from personality.json for the server's language."""
        try:
            base_dir = Path(__file__).parent.parent.parent

            # Try new structure first: personalities/<name>/<language>/personality.json
            personality_file = base_dir / "personalities" / personality_name / self.server_language / "personality.json"

            # Fallback to old structure if not found
            if not personality_file.exists():
                personality_file = base_dir / "personalities" / personality_name / "personality.json"

            if personality_file.exists():
                import json
                with open(personality_file, 'r', encoding='utf-8') as f:
                    personality_data = json.load(f)

                identity_body = personality_data.get("system_prompt_template", {}).get("identity_body", [])
                if identity_body:
                    # Join the identity body lines and truncate to 2000 characters
                    full_text = "\n".join(identity_body)
                    return self._truncate_to_limit(full_text, 2000)
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

            # Get current personality with language context
            server_id = str(self.parent_view.guild.id)
            self.old_personality = _get_current_personality_name(server_id)
            current_with_language = _get_current_personality_with_language(server_id)
            new_with_language = f"{new_personality}:{self.server_language}"

            # Show confirmation if same personality but different language
            if self.old_personality == new_personality and self.server_language != self._get_server_language(server_id):
                personality_info = self._load_personality_info(new_personality)
                server_id = get_server_key(self.parent_view.guild) if (get_server_key and self.parent_view.guild) else None
                personality_descriptions = _get_personality_descriptions(server_id)
                personality_msgs = personality_descriptions.get("behavior_messages", {}).get("personality", {})
                selected_msg = personality_msgs.get("selected_personality_with_language", "**Selected Personality: {personality} (Language: {language})**").format(personality=new_personality, language=self.server_language)
                note_msg = personality_msgs.get("language_change_note", "⚠️ **Note:** Changing language for the same personality.")

                # Load personality avatar for embed thumbnail
                avatar_url = None
                avatar_file = None
                try:
                    from pathlib import Path
                    base_dir = Path(__file__).parent.parent.parent
                    avatar_path = base_dir / "personalities" / new_personality / "avatar.png"
                    if avatar_path.exists():
                        avatar_file = discord.File(avatar_path, filename="avatar.png")
                        avatar_url = "attachment://avatar.png"
                except Exception:
                    pass

                # Create embed with avatar as thumbnail
                content = f"{note_msg}\n\n{personality_info}"
                content = self._truncate_to_limit(content, 2000)
                embed = discord.Embed(title=selected_msg, description=content)
                if avatar_url:
                    embed.set_thumbnail(url=avatar_url)

                if avatar_file:
                    await interaction.response.edit_message(
                        embed=embed,
                        view=self,
                        attachments=[avatar_file]
                    )
                else:
                    await interaction.response.edit_message(
                        embed=embed,
                        view=self
                    )
                self.confirm_button.disabled = False
                return

            # Load personality info
            personality_info = self._load_personality_info(new_personality)

            # Enable confirm button
            self.confirm_button.disabled = False

            server_id = get_server_key(self.parent_view.guild) if (get_server_key and self.parent_view.guild) else None
            personality_descriptions = _get_personality_descriptions(server_id)
            personality_msgs = personality_descriptions.get("behavior_messages", {}).get("personality", {})
            selected_msg = personality_msgs.get("selected_personality", "**Selected Personality: {personality}**").format(personality=new_personality)

            # Load personality avatar for embed thumbnail
            avatar_url = None
            avatar_file = None
            try:
                from pathlib import Path
                base_dir = Path(__file__).parent.parent.parent
                avatar_path = base_dir / "personalities" / new_personality / "avatar.png"
                if avatar_path.exists():
                    avatar_file = discord.File(avatar_path, filename="avatar.png")
                    avatar_url = "attachment://avatar.png"
            except Exception:
                pass

            # Create embed with avatar as thumbnail
            content = personality_info
            embed = discord.Embed(title=selected_msg, description=content)
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)

            if avatar_file:
                await interaction.response.edit_message(
                    embed=embed,
                    view=self,
                    attachments=[avatar_file]
                )
            else:
                await interaction.response.edit_message(
                    embed=embed,
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
            server_id = get_server_key(self.parent_view.guild) if (get_server_key and self.parent_view.guild) else None
            personality_msgs = _get_personality_descriptions(server_id).get("behavior_messages", {}).get("personality", {})
            confirm_msg = personality_msgs.get("confirm_change_message", "**Confirm change to {personality}?**\nSelect your options below:").format(personality=self.selected_personality)
            await interaction.response.edit_message(
                content=confirm_msg,
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
        try:
            # Try to delete original response first (for ephemeral messages)
            await interaction.delete_original_response()
        except discord.NotFound:
            # Not an ephemeral message or already deleted, try regular delete
            try:
                await interaction.message.delete()
            except discord.NotFound:
                # Message already deleted, just stop the view
                pass
        except Exception:
            # Other errors, just stop the view
            pass
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive view to its original user."""
        if interaction.user.id != self.parent_view.author_id:
            await interaction.response.send_message("❌ This menu belongs to another user.", ephemeral=True)
            return False
        return True


class CanvasPersonalityConfirmView(discord.ui.View):
    """View for confirming personality change with boolean selectors (step 2 of 2)."""

    def __init__(self, parent_view: CanvasPersonalityView = None, new_personality: str = None, old_personality: str = None,
                 personality_name: str = None, server_id: str = None, new_language: str = None, is_language_update: bool = False):
        super().__init__(timeout=300)

        # Handle both old and new calling patterns
        if personality_name and server_id:
            # New pattern for language updates
            self.parent_view = None
            self.personality_name = personality_name
            self.server_id = server_id
            self.new_language = new_language
            self.is_language_update = is_language_update
            self.new_personality = personality_name
            self.old_personality = personality_name
            self.author_id = None  # Will be set from interaction
        else:
            # Old pattern for regular personality changes
            self.parent_view = parent_view
            self.new_personality = new_personality
            self.old_personality = old_personality
            self.personality_name = new_personality
            self.server_id = get_server_key(parent_view.guild) if (get_server_key and parent_view.guild) else None
            self.new_language = None
            self.is_language_update = False
            self.author_id = parent_view.author_id

        # Get personality messages for labels
        if self.parent_view:
            server_id = get_server_key(self.parent_view.guild) if (get_server_key and self.parent_view.guild) else None
        else:
            server_id = self.server_id
        personality_descriptions = _get_personality_descriptions(server_id)
        general_msgs = personality_descriptions.get("general", {})
        personality_msgs = personality_descriptions.get("behavior_messages", {}).get("personality", {})

        # Boolean options: Yes/No
        yes_no_options = [
            discord.SelectOption(label=general_msgs.get("option_yes", "Yes"), value="yes"),
            discord.SelectOption(label=general_msgs.get("option_no", "No"), value="no")
        ]

        # Download old personality selector
        self.download_old_select = discord.ui.Select(
            placeholder=personality_msgs.get("modal_download_label", "Download old personality?"),
            min_values=1,
            max_values=1,
            options=yes_no_options,
            row=0
        )
        self.download_old_select.callback = self._on_select_option_defer
        self.add_item(self.download_old_select)

        # Delete memory selector
        self.delete_memory_select = discord.ui.Select(
            placeholder=personality_msgs.get("modal_delete_memory_label", "Delete bot memory?"),
            min_values=1,
            max_values=1,
            options=yes_no_options,
            row=1
        )
        self.delete_memory_select.callback = self._on_select_option_defer
        self.add_item(self.delete_memory_select)

        # Download memory selector
        self.download_memory_select = discord.ui.Select(
            placeholder=personality_msgs.get("modal_download_memory_label", "Download memory first?"),
            min_values=1,
            max_values=1,
            options=yes_no_options,
            row=2
        )
        self.download_memory_select.callback = self._on_select_option_defer
        self.add_item(self.download_memory_select)

        # Confirm and Cancel buttons
        self.confirm_button = discord.ui.Button(
            label=general_msgs.get("button_confirm_changes", "Confirm Changes"),
            style=discord.ButtonStyle.green,
            row=3
        )
        self.confirm_button.callback = self._on_confirm
        self.add_item(self.confirm_button)

        self.cancel_button = discord.ui.Button(
            label=general_msgs.get("option_no", "No"),
            style=discord.ButtonStyle.red,
            row=3
        )
        self.cancel_button.callback = self._on_cancel
        self.add_item(self.cancel_button)

    async def _on_select_option_defer(self, interaction: discord.Interaction):
        """Shared callback for option selects that only need to acknowledge the interaction."""
        try:
            await interaction.response.defer()
        except Exception as e:
            if logger:
                logger.error(f"Error deferring select interaction: {e}")

    async def _on_confirm(self, interaction: discord.Interaction):
        """Handle personality change confirmation and execution."""
        try:
            # Original personality change logic (handles both regular and language updates)
            if not self.is_language_update and not self.parent_view.guild:
                await interaction.response.send_message("❌ This action is only available in a server.", ephemeral=True)
                return

            if not self.is_language_update and not self.parent_view.admin_visible:
                await interaction.response.send_message("❌ This action is admin-only.", ephemeral=True)
                return

            # Track messages for cleanup
            message1 = None  # Initial progress message
            message3 = None  # Success message

            # Determine server_id and personality names
            if self.is_language_update:
                server_id = self.server_id
                new_personality = self.personality_name
                old_personality = self.personality_name
            else:
                server_id = str(self.parent_view.guild.id)
                new_personality = self.new_personality
                old_personality = self.old_personality

            # Edit message to show progress, then send followup messages
            personality_msgs = _get_personality_descriptions(server_id).get("behavior_messages", {}).get("personality", {})
            if self.is_language_update:
                progress_text = personality_msgs.get("progress_language_update", "⏳ Updating `{personality}` to `{language}` language...").format(
                    personality=self.personality_name, language=self.new_language
                )
            else:
                progress_text = personality_msgs.get("progress_change_personality", "⏳ Changing personality from `{old}` to `{new}`...").format(
                    old=self.old_personality, new=self.new_personality
                )

            await interaction.response.edit_message(
                content=progress_text,
                view=None
            )
            # Store the original message reference
            message1 = interaction.message

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
                # Clear all memory (interactions.jsonl and state.json) from NoSQL system BEFORE deleting databases
                try:
                    from persistence.agent_state import get_agent_state
                    agent_state = get_agent_state(server_id)
                    if agent_state and agent_state._memory:
                        agent_state._memory.clear_all_memory()
                        if logger:
                            logger.info(f"✅ Cleared all NoSQL memory (interactions.jsonl and state.json) for server {server_id}")
                except Exception as e:
                    if logger:
                        logger.warning(f"⚠️ Could not clear NoSQL memory: {e}")

                # Delete ONLY the agent database (memory) of the old personality
                _delete_database(server_id, f"agent_{old_personality}.db")
                # Rename other databases from old to new personality (preserve roles, behavior, etc.)
                _rename_server_databases(server_id, old_personality, new_personality)
                # Create new agent database for new personality
                # Ensure NoSQL state directory exists for new personality
                from agent_db import get_db_instance, invalidate_db_instance
                invalidate_db_instance(server_id)
                get_db_instance(server_id)
            else:
                # Rename all databases including agent (preserve memory for new personality)
                _rename_server_databases(server_id, old_personality, new_personality)

            # Step 4: Delete old personality directory
            _delete_personality_directory(server_id, old_personality)

            # Step 5: Copy new personality files (JSON configs) to server
            # Note: .db databases are already renamed in Step 3, no conflict here
            # Use the target language for the new personality
            if self.is_language_update:
                target_language = self.new_language
            else:
                from .server_config import get_server_language
                target_language = get_server_language(server_id)

            success = False
            if copy_personality_to_server:
                success = copy_personality_to_server(server_id, new_personality, language=target_language, update_config=True)

            if not success:
                error_msg = f"❌ Failed to copy new personality `{new_personality}` to server."
                if self.is_language_update:
                    error_msg = f"❌ Failed to update `{new_personality}` to `{self.new_language}` language."
                await interaction.followup.send(error_msg, ephemeral=True)
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
                reload_personality(server_id)  # Clears personality + descriptions cache

                # IMPORTANT: Invalidate ALL cached database instances AFTER database renaming
                # This ensures new instances point to the correct personality database files
                if logger:
                    logger.info(f"🔄 Invalidating all database caches for server {server_id} after personality change")

                # Invalidate all database caches
                _invalidate_db_cache('agent_db', 'invalidate_db_instance', 'agent', server_id)
                _invalidate_db_cache('agent_roles_db', 'invalidate_roles_db_instance', 'roles', server_id)
                _invalidate_db_cache('roles.news_watcher.db_role_news_watcher', 'invalidate_news_watcher_db_instance', 'news_watcher', server_id)
                _invalidate_db_cache('roles.treasure_hunter.db_role_treasure_hunter', 'invalidate_poe_db_instance', 'POE', server_id)

                # Invalidate beggar config cache
                try:
                    from roles.banker.subroles.beggar.beggar_db import invalidate_beggar_config_cache
                    invalidate_beggar_config_cache(server_id)
                    if logger:
                        logger.info(f"✅ Invalidated beggar config cache for server {server_id}")
                except Exception as err:
                    if logger:
                        logger.warning(f"Could not invalidate beggar config cache: {err}")

                # Step 7: Initialize memory synthesis for the NEW personality (skip for language-only updates)
                # This creates initial daily memory and schedules the next task
                if self.is_language_update:
                    if logger:
                        logger.info(f"⏭️ Skipping memory synthesis for language-only update")
                else:
                    try:
                        from agent_mind import generate_daily_memory_summary
                        personality_msgs = _get_personality_descriptions(server_id).get("behavior_messages", {}).get("personality", {})
                        memory_msg = personality_msgs.get("generating_memory_synthesis", "🧠 Generating initial memory synthesis for new personality...")
                        await interaction.followup.send(
                            memory_msg,
                            ephemeral=True
                        )
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

            # Step 10: Sync bot identity (nickname + avatar) to new personality
            # This updates the bot's visual identity in the Discord server
            try:
                if sync_bot_identity_to_server_personality and interaction.guild:
                    if logger:
                        logger.info(f"🔄 Syncing bot identity for server {server_id} after personality change")

                    identity_result = await sync_bot_identity_to_server_personality(interaction.guild)

                    if identity_result.get('success'):
                        changes = []
                        if identity_result.get('nickname_changed'):
                            changes.append("nickname")
                        if identity_result.get('avatar_changed'):
                            changes.append("avatar")

                        if changes:
                            if logger:
                                logger.info(f"✅ Bot identity synced: {', '.join(changes)} updated")
                        else:
                            if logger:
                                logger.info(f"✅ Bot identity already correct for new personality")
                    else:
                        errors = identity_result.get('errors', ['Unknown error'])
                        if logger:
                            logger.warning(f"⚠️ Could not sync bot identity: {', '.join(errors)}")
                        # Send a non-blocking warning to the user
                        try:
                            await interaction.followup.send(
                                f"⚠️ Personality changed successfully, but identity sync failed: {', '.join(errors)}\n"
                                f"The bot's nickname/avatar may need manual adjustment with `!setnickname`.",
                                ephemeral=True
                            )
                        except:
                            pass
            except Exception as identity_error:
                if logger:
                    logger.warning(f"Could not sync bot identity: {identity_error}")
                # Non-critical error, don't block the personality change

            # Step 11: Update bot presence message to new personality's message
            # This updates the "Listening to..." status with the new personality's message
            try:
                from discord_bot.agent_discord import set_bot_presence_message
                if interaction.guild and interaction.client:
                    if logger:
                        logger.info(f"🔄 Updating bot presence message for server {server_id} after personality change")

                    await set_bot_presence_message(interaction.guild, bot_instance=interaction.client)

                    if logger:
                        logger.info(f"✅ Bot presence message updated to new personality")
            except Exception as presence_error:
                if logger:
                    logger.warning(f"Could not update bot presence message: {presence_error}")
                # Non-critical error, don't block the personality change

            # Get success message
            personality_msgs = _get_personality_descriptions(server_id).get("behavior_messages", {}).get("personality", {})

            if self.is_language_update:
                success_msg = personality_msgs.get(
                    "language_update_success",
                    "✅ Personality `{personality}` updated to `{language}` language! The new language version is now active."
                )
                success_content = success_msg.format(personality=new_personality, language=self.new_language)
            else:
                success_msg = personality_msgs.get(
                    "change_success",
                    "✅ Personality changed from `{old}` to `{new}`! The new personality is now active."
                )
                success_content = success_msg.format(old=old_personality, new=new_personality)

            # Delete message1 (initial progress) when sending message3 (success)
            try:
                if message1:
                    await message1.delete()
            except:
                pass

            # Send message3 (success message)
            await interaction.followup.send(success_content, ephemeral=True)
            self.stop()

        except Exception as e:
            if logger:
                logger.exception(f"Error in personality change confirmation view: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
            except:
                pass
            self.stop()

    async def _on_cancel(self, interaction: discord.Interaction):
        """Handle cancel button - dismiss the message."""
        try:
            await interaction.response.defer()
        except Exception:
            pass
        try:
            # Try to delete original response first (for ephemeral messages)
            await interaction.delete_original_response()
        except discord.NotFound:
            # Not an ephemeral message or already deleted, try regular delete
            try:
                await interaction.message.delete()
            except discord.NotFound:
                # Message already deleted, just stop the view
                pass
        except Exception:
            # Other errors, just stop the view
            pass
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive view to its original user."""
        # For language updates, set author_id from first interaction
        if self.is_language_update and self.author_id is None:
            self.author_id = interaction.user.id
            return True

        # Check if user is authorized
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This menu belongs to another user.", ephemeral=True)
            return False
        return True


# ============================================================================
# Server Onboarding Views (New Server Setup)
# ============================================================================

class ServerWelcomeView(discord.ui.View):
    """View shown when bot joins a new server with a configuration button."""

    def __init__(self, guild, server_id: str, detected_lang: str):
        super().__init__(timeout=None)  # No timeout for welcome message
        self.guild = guild
        self.server_id = server_id
        self.detected_lang = detected_lang

        # Add configuration button
        config_button = discord.ui.Button(
            label="⚙️ Configure Language & Personality",
            style=discord.ButtonStyle.primary,
            emoji="⚙️",
            row=0
        )
        config_button.callback = self._on_config_click
        self.add_item(config_button)

    async def _on_config_click(self, interaction: discord.Interaction):
        """Handle configuration button click - open language selection view."""
        try:
            # Check if user is admin
            if is_admin and not is_admin(interaction, guild=self.guild):
                await interaction.response.send_message("❌ This action is admin-only.", ephemeral=True)
                return

            # Open language selection view (step 1)
            language_view = OnboardingLanguageSelectView(self.guild, self.server_id, self.detected_lang)
            server_id = get_server_key(self.guild) if (get_server_key and self.guild) else None
            personality_descriptions = _get_personality_descriptions(server_id)
            general_msgs = personality_descriptions.get("general", {})
            welcome_msg = general_msgs.get("onboarding_welcome", "Welcome! Let's configure your bot language.")

            await interaction.response.send_message(
                welcome_msg,
                view=language_view,
                ephemeral=True
            )
        except Exception as e:
            if logger:
                logger.exception(f"Error in config button click: {e}")
            await interaction.response.send_message(
                "❌ Error opening configuration. Please try again.",
                ephemeral=True
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Allow all users to see the welcome, but only admins can configure."""
        return True


class OnboardingLanguageSelectView(discord.ui.View):
    """Step 1: Language selection view for server onboarding - reuses LanguageSelect logic."""

    def __init__(self, guild, server_id: str, detected_lang: str):
        super().__init__(timeout=300)
        self.guild = guild
        self.server_id = server_id
        self.detected_lang = detected_lang
        self.selected_language = None
        self.author_id = None

        # Reuse LanguageSelect dropdown logic
        from .server_config import get_available_languages, get_server_language
        current_lang = get_server_language(server_id) if server_id else detected_lang

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

        self.language_select = discord.ui.Select(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=0,
            custom_id="language_select"
        )
        self.language_select.callback = self._on_language_select
        self.add_item(self.language_select)

        # Confirm and Cancel buttons
        general_msgs = descriptions.get("general", {})
        self.confirm_button = discord.ui.Button(
            label=general_msgs.get("button_confirm", "Confirm"),
            style=discord.ButtonStyle.green,
            disabled=True,
            row=1
        )
        self.confirm_button.callback = self._on_confirm
        self.add_item(self.confirm_button)

        self.cancel_button = discord.ui.Button(
            label=general_msgs.get("option_no", "Cancel"),
            style=discord.ButtonStyle.red,
            row=1
        )
        self.cancel_button.callback = self._on_cancel
        self.add_item(self.cancel_button)

    async def _on_language_select(self, interaction: discord.Interaction):
        """Handle language selection - reuses LanguageSelect callback logic."""
        try:
            from .server_config import set_server_language, get_server_language
            from .canvas_personality import _get_current_personality_name, _get_available_personalities

            selected_language = self.language_select.values[0]
            self.selected_language = selected_language
            server_id = str(self.guild.id) if self.guild else "0"

            # Get current personality before language change
            current_personality = _get_current_personality_name(server_id)
            old_language = get_server_language(server_id)

            # Save the language
            success = set_server_language(server_id, selected_language)

            if success:
                # Update dropdown to show selected language as default
                from .server_config import get_available_languages
                lang_options = []
                for lang_code, lang_name in get_available_languages().items():
                    lang_options.append(discord.SelectOption(
                        label=lang_name,
                        value=lang_code,
                        emoji="🌐",
                        default=lang_code == selected_language
                    ))

                for item in self.children:
                    if hasattr(item, 'custom_id') and item.custom_id == "language_select":
                        item.options = lang_options
                        break

                self.confirm_button.disabled = False
                await interaction.response.edit_message(view=self)
            else:
                await interaction.response.send_message(
                    "❌ Failed to update language setting.",
                    ephemeral=True
                )
        except Exception as e:
            if logger:
                logger.exception(f"Error in language select: {e}")
            await interaction.response.send_message(
                "❌ Error updating language. Please try again.",
                ephemeral=True
            )

    async def _on_confirm(self, interaction: discord.Interaction):
        """Handle confirm button - move to personality selection."""
        try:
            if not self.selected_language:
                await interaction.response.send_message("❌ Please select a language.", ephemeral=True)
                return

            # Open personality selection view (step 2)
            personality_view = OnboardingPersonalitySelectView(self.guild, self.server_id, self.selected_language)
            server_id = get_server_key(self.guild) if (get_server_key and self.guild) else None
            personality_descriptions = _get_personality_descriptions(server_id)
            general_msgs = personality_descriptions.get("general", {})
            personality_msg = general_msgs.get("onboarding_personality", "Now select a personality:")

            await interaction.response.edit_message(
                content=personality_msg,
                view=personality_view
            )
            self.stop()
        except Exception as e:
            if logger:
                logger.exception(f"Error in confirm callback: {e}")
            await interaction.response.send_message(
                "❌ Error preparing personality selection. Please try again.",
                ephemeral=True
            )

    async def _on_cancel(self, interaction: discord.Interaction):
        """Handle cancel button - dismiss the message."""
        try:
            await interaction.delete_original_response()
        except discord.NotFound:
            pass
        except Exception:
            pass
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive view to its original user."""
        if self.author_id is None:
            self.author_id = interaction.user.id
        elif interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This menu belongs to another user.", ephemeral=True)
            return False
        return True


class OnboardingPersonalitySelectView(discord.ui.View):
    """Step 2: Personality selection view for server onboarding - reuses CanvasPersonalitySelectView logic."""

    def __init__(self, guild, server_id: str, selected_language: str):
        super().__init__(timeout=300)
        self.guild = guild
        self.server_id = server_id
        self.selected_language = selected_language
        self.selected_personality = None
        self.old_personality = None
        self.author_id = None

        # Get available personalities for selected language
        self.available_personalities = _get_available_personalities(selected_language)
        if not self.available_personalities:
            self.available_personalities = _get_available_personalities()

        # Get personality descriptions
        server_id = get_server_key(guild) if (get_server_key and guild) else None
        personality_descriptions = _get_personality_descriptions(server_id)
        personality_msgs = personality_descriptions.get("behavior_messages", {}).get("personality", {})
        general_msgs = personality_descriptions.get("general", {})

        # Personality dropdown - reuses CanvasPersonalitySelectView logic
        if self.available_personalities:
            options = [
                discord.SelectOption(label=pers, value=pers)
                for pers in self.available_personalities
            ]
            placeholder = personality_msgs.get("choose_personality_placeholder", "Choose a personality (language: {language})...").format(language=selected_language)
        else:
            options = [discord.SelectOption(label="No personalities available", value="none")]
            placeholder = "No personalities available"

        self.personality_select = discord.ui.Select(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=0,
            disabled=not self.available_personalities,
            custom_id="personality_select"
        )
        self.personality_select.callback = self._on_select
        self.add_item(self.personality_select)

        # Confirm and Cancel buttons (initially disabled)
        self.confirm_button = discord.ui.Button(
            label=general_msgs.get("button_confirm", "Confirm"),
            style=discord.ButtonStyle.green,
            disabled=True,
            row=1
        )
        self.confirm_button.callback = self._on_confirm
        self.add_item(self.confirm_button)

        self.cancel_button = discord.ui.Button(
            label=general_msgs.get("option_no", "Cancel"),
            style=discord.ButtonStyle.red,
            row=1
        )
        self.cancel_button.callback = self._on_cancel
        self.add_item(self.cancel_button)

    def _truncate_to_limit(self, text: str, max_length: int = 2000) -> str:
        """Truncate text to max_length - reused from CanvasPersonalitySelectView."""
        if len(text) <= max_length:
            return text

        # Try to cut at paragraph boundary (double newline)
        truncated = text[:max_length]
        last_paragraph = truncated.rfind('\n\n')
        if last_paragraph > max_length * 0.7:
            return text[:last_paragraph].rstrip()

        # Try to cut at sentence boundary (. ! ?)
        for punctuation in ['.', '!', '?']:
            last_sentence = truncated.rfind(punctuation)
            if last_sentence > max_length * 0.7:
                return text[:last_sentence + 1].rstrip()

        # Fallback: cut at last space
        last_space = truncated.rfind(' ')
        if last_space > max_length * 0.7:
            return text[:last_space].rstrip()

        # Last resort: hard cut
        return text[:max_length].rstrip()

    def _load_personality_info(self, personality_name: str) -> str:
        """Load identity_body from personality.json - reused from CanvasPersonalitySelectView."""
        try:
            base_dir = Path(__file__).parent.parent.parent

            # Try new structure first: personalities/<name>/<language>/personality.json
            personality_file = base_dir / "personalities" / personality_name / self.selected_language / "personality.json"

            # Fallback to old structure if not found
            if not personality_file.exists():
                personality_file = base_dir / "personalities" / personality_name / "personality.json"

            if personality_file.exists():
                import json
                with open(personality_file, 'r', encoding='utf-8') as f:
                    personality_data = json.load(f)

                identity_body = personality_data.get("system_prompt_template", {}).get("identity_body", [])
                if identity_body:
                    # Join the identity body lines and truncate to 2000 characters
                    full_text = "\n".join(identity_body)
                    return self._truncate_to_limit(full_text, 2000)
            return "No personality description available."
        except Exception as e:
            if logger:
                logger.warning(f"Could not load personality info for {personality_name}: {e}")
            return "Could not load personality description."

    async def _on_select(self, interaction: discord.Interaction):
        """Handle personality selection - reuses CanvasPersonalitySelectView._on_select logic with avatar."""
        try:
            if not self.guild:
                await interaction.response.send_message("❌ This action is only available in a server.", ephemeral=True)
                return

            new_personality = self.personality_select.values[0]
            self.selected_personality = new_personality
            self.old_personality = _get_current_personality_name(str(self.guild.id))

            if new_personality == "none":
                self.confirm_button.disabled = True
                await interaction.response.edit_message(view=self)
                return

            # Update dropdown to show selected personality as default
            if self.available_personalities:
                options = [
                    discord.SelectOption(label=pers, value=pers, default=pers == new_personality)
                    for pers in self.available_personalities
                ]
                for item in self.children:
                    if hasattr(item, 'custom_id') and item.custom_id == "personality_select":
                        item.options = options
                        break

            # Load personality info
            personality_info = self._load_personality_info(new_personality)

            # Enable confirm button
            self.confirm_button.disabled = False

            server_id = get_server_key(self.guild) if (get_server_key and self.guild) else None
            personality_descriptions = _get_personality_descriptions(server_id)
            personality_msgs = personality_descriptions.get("behavior_messages", {}).get("personality", {})
            selected_msg = personality_msgs.get("selected_personality", "**Selected Personality: {personality}**").format(personality=new_personality)

            # Load personality avatar for embed thumbnail - from CanvasPersonalitySelectView
            avatar_url = None
            avatar_file = None
            try:
                from pathlib import Path
                base_dir = Path(__file__).parent.parent.parent
                avatar_path = base_dir / "personalities" / new_personality / "avatar.png"
                if avatar_path.exists():
                    avatar_file = discord.File(avatar_path, filename="avatar.png")
                    avatar_url = "attachment://avatar.png"
            except Exception:
                pass

            # Create embed with avatar as thumbnail - from CanvasPersonalitySelectView
            content = personality_info
            embed = discord.Embed(title=selected_msg, description=content)
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)

            if avatar_file:
                await interaction.response.edit_message(
                    embed=embed,
                    view=self,
                    attachments=[avatar_file]
                )
            else:
                await interaction.response.edit_message(
                    embed=embed,
                    view=self
                )

        except Exception as e:
            if logger:
                logger.exception(f"Error in personality selection view: {e}")
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            self.stop()

    async def _on_confirm(self, interaction: discord.Interaction):
        """Handle confirm button - apply personality change directly."""
        try:
            if not self.selected_personality:
                await interaction.response.send_message("❌ No personality selected.", ephemeral=True)
                return

            server_id = str(self.guild.id)

            # Show progress - remove embed and show only text
            personality_msgs = _get_personality_descriptions(server_id).get("behavior_messages", {}).get("personality", {})
            progress_text = personality_msgs.get("onboarding_progress", "⏳ Setting up personality `{personality}` (language: {language})...").format(
                personality=self.selected_personality,
                language=self.selected_language
            )

            await interaction.response.edit_message(
                content=progress_text,
                embed=None,
                view=None
            )

            # Copy personality files to server
            base_dir = Path(__file__).parent.parent.parent
            success = False
            if copy_personality_to_server:
                success = copy_personality_to_server(
                    server_id,
                    self.selected_personality,
                    language=self.selected_language,
                    update_config=True
                )

            if not success:
                error_msg = f"❌ Failed to copy personality `{self.selected_personality}` to server."
                try:
                    await interaction.edit_original_response(content=error_msg)
                except:
                    pass
                self.stop()
                return

            # Update personality files
            if update_personality_files:
                files_updated = update_personality_files(server_id, self.selected_personality)
                if logger:
                    if files_updated:
                        logger.info(f"✅ Updated personality files for {self.selected_personality}")
                    else:
                        logger.warning(f"⚠️ Could not update personality files for {self.selected_personality}")

            # Save server config with active personality
            try:
                import json
                server_config_dir = base_dir / "databases" / server_id
                server_config_dir.mkdir(parents=True, exist_ok=True)
                server_config_path = server_config_dir / "server_config.json"

                server_config = {}
                if server_config_path.exists():
                    with open(server_config_path, 'r', encoding='utf-8') as f:
                        server_config = json.load(f)

                server_config['active_personality'] = self.selected_personality
                server_config['language'] = self.selected_language
                with open(server_config_path, 'w', encoding='utf-8') as f:
                    json.dump(server_config, f, indent=2, ensure_ascii=False)

                if logger:
                    logger.info(f"Saved server config with active personality: {self.selected_personality}, language: {self.selected_language}")
            except Exception as config_error:
                if logger:
                    logger.warning(f"Could not save server config: {config_error}")

            # Reload personality
            try:
                from agent_engine import reload_personality
                reload_personality(server_id)

                # Invalidate ALL database caches - from CanvasPersonalityConfirmView
                if logger:
                    logger.info(f"🔄 Invalidating all database caches for server {server_id} after personality change")

                # Invalidate all database caches
                _invalidate_db_cache('agent_db', 'invalidate_db_instance', 'agent', server_id)
                _invalidate_db_cache('agent_roles_db', 'invalidate_roles_db_instance', 'roles', server_id)
                _invalidate_db_cache('roles.news_watcher.db_role_news_watcher', 'invalidate_news_watcher_db_instance', 'news_watcher', server_id)
                _invalidate_db_cache('roles.treasure_hunter.db_role_treasure_hunter', 'invalidate_poe_db_instance', 'POE', server_id)

                # Invalidate beggar config cache
                try:
                    from roles.banker.subroles.beggar.beggar_db import invalidate_beggar_config_cache
                    invalidate_beggar_config_cache(server_id)
                    if logger:
                        logger.info(f"✅ Invalidated beggar config cache for server {server_id}")
                except Exception as err:
                    if logger:
                        logger.warning(f"Could not invalidate beggar config cache: {err}")

                # Generate initial memory synthesis for new personality (non-blocking background task)
                try:
                    from agent_mind import generate_daily_memory_summary
                    # Run in background without blocking the user
                    import asyncio
                    asyncio.create_task(asyncio.to_thread(generate_daily_memory_summary, server_id))
                    if logger:
                        logger.info(f"🧠 Started background memory synthesis task for server {server_id}")
                except Exception as memory_error:
                    if logger:
                        logger.warning(f"Could not start background memory synthesis: {memory_error}")
            except Exception as reload_error:
                if logger:
                    logger.warning(f"Could not reload personality: {reload_error}")

            # Sync bot identity (nickname + avatar) to server personality - from setpersonality command
            try:
                from discord_bot.discord_utils import sync_bot_identity_to_server_personality
                if logger:
                    logger.info(f"🔄 Syncing bot identity for server {server_id} after personality change")

                # Force avatar update by passing force_avatar=True parameter
                identity_result = await sync_bot_identity_to_server_personality(self.guild, force_avatar=True)

                if identity_result.get('success'):
                    changes = []
                    if identity_result.get('nickname_changed'):
                        changes.append("nickname")
                    if identity_result.get('avatar_changed'):
                        changes.append("avatar")

                    if changes:
                        if logger:
                            logger.info(f"✅ Bot identity synced: {', '.join(changes)} updated")
                    else:
                        if logger:
                            logger.info(f"✅ Bot identity already correct for new personality")
                else:
                    errors = identity_result.get('errors', ['Unknown error'])
                    if logger:
                        logger.warning(f"⚠️ Could not sync bot identity: {', '.join(errors)}")
            except Exception as identity_error:
                if logger:
                    logger.warning(f"Could not sync bot identity: {identity_error}")

            # Success message
            success_msg = personality_msgs.get("onboarding_success", "✅ Configuration complete! Personality: `{personality}`, Language: `{language}`").format(
                personality=self.selected_personality,
                language=self.selected_language
            )
            try:
                await interaction.edit_original_response(content=success_msg)
            except:
                pass

            self.stop()

        except Exception as e:
            if logger:
                logger.exception(f"Error in confirm callback: {e}")
            error_msg = f"❌ Error applying configuration: {str(e)}"
            try:
                await interaction.edit_original_response(content=error_msg)
            except:
                pass
            self.stop()

    async def _on_cancel(self, interaction: discord.Interaction):
        """Handle cancel button - dismiss the message."""
        try:
            await interaction.delete_original_response()
        except discord.NotFound:
            pass
        except Exception:
            pass
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive view to its original user."""
        if self.author_id is None:
            self.author_id = interaction.user.id
        elif interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This menu belongs to another user.", ephemeral=True)
            return False
        return True


async def send_server_welcome_message(guild, server_id: str, detected_lang: str):
    """Send a welcome message with configuration button when bot joins a new server.

    Args:
        guild: Discord guild object
        server_id: Server ID string
        detected_lang: Detected language code (e.g., "es-ES", "en-US")
    """
    try:
        from behavior.welcome import get_welcome_channel_info
        from agent_engine import _get_personality, _build_system_prompt
        from agent_mind import call_llm_async

        # Get welcome channel
        discord_cfg = _get_personality(server_id).get("discord", {})
        welcome_info = await get_welcome_channel_info(guild, discord_cfg)

        if not welcome_info:
            # Fallback to system channel
            if guild.system_channel:
                welcome_channel = guild.system_channel
                logger.info(f"Using system channel as welcome channel: {welcome_channel.name}")
            else:
                logger.warning(f"No welcome channel or system channel found for guild {guild.name}")
                return
        else:
            welcome_channel = welcome_info["channel"]

        # Generate welcome message using LLM
        personality = _get_personality(server_id)
        system_instruction = _build_system_prompt(personality, server_id)

        # Build simple welcome prompt
        welcome_prompt = f"""You have just been invited to a new Discord server called "{guild.name}".
Introduce yourself briefly and warmly in the personality's style.
Mention that the server administrator can configure the language and personality using the button below.
Keep it concise (1-2 sentences)."""

        welcome_message = await call_llm_async(
            system_instruction=system_instruction,
            prompt=welcome_prompt,
            background=False,
            call_type="think",
            critical=True,
            logger=logger,
        )

        # Send welcome message with configuration button
        view = ServerWelcomeView(guild, server_id, detected_lang)
        await welcome_channel.send(welcome_message, view=view)

        logger.info(f"Welcome message sent to {guild.name} in channel {welcome_channel.name}")

    except Exception as e:
        logger.error(f"Error sending server welcome message to {guild.name}: {e}")


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

    # Get available personalities filtered by server language
    try:
        from .server_config import get_server_language
        server_language = get_server_language(server_id) if server_id else None
    except Exception:
        server_language = None
    available = _get_available_personalities(server_language) or _get_available_personalities()
    available_list = "\n".join([f"• `{p}`" for p in available]) if available else "No personalities found"

    title = personality_msgs.get("title", "🎭 Personality Management")
    description = personality_msgs.get("description", "Change or download the bot's personality for this server.")

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
