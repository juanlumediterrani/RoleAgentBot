"""Canvas MC content and UI components."""

import asyncio
import json
import os

import discord

from discord_bot import discord_core_commands as core
from .canvas_base import CanvasModal

logger = core.logger


def _load_mc_descriptions(server_id: str = None) -> dict:
    """
    Load MC descriptions from server-specific mc.json file, with fallback to personality.
    
    Args:
        server_id: Discord server ID for server-specific descriptions
        
    Returns:
        dict: MC descriptions loaded from mc.json or empty dict if not found
    """
    if not server_id:
        return {}
    
    try:
        # First try server-specific mc.json
        # Path: databases/{server_id}/rab/descriptions/mc.json
        from agent_db import DB_DIR
        mc_json_path = DB_DIR / server_id / "rab" / "descriptions" / "mc.json"
        
        if mc_json_path.exists():
            with open(mc_json_path, encoding="utf-8") as f:
                return json.load(f)
        
        # Fallback to personality mc.json
        from agent_runtime import get_personality_directory
        personality_dir = get_personality_directory(server_id)
        personality_mc_path = personality_dir / "descriptions" / "mc.json"
        
        if personality_mc_path.exists():
            with open(personality_mc_path, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load mc.json for server {server_id}: {e}")
    
    return {}


def build_canvas_role_mc(last_action=None, queue_info=None, mc_messages=None, guild=None) -> str:
    """Build the MC role view with dynamic state."""
    from .content import _get_personality_descriptions
    server_id = core.get_server_key(guild) if guild else None
    mc_messages_fallback = core._personality_answers.get("mc_messages", {})
    mc_descriptions = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("mc", {})
    mc_json_data = _load_mc_descriptions(server_id)

    def _mc_text(key: str, fallback: str) -> str:
        # First try mc.json (server-specific), then descriptions.json, then fallback
        value = mc_json_data.get(key, mc_descriptions.get(key, mc_messages_fallback.get(key)))
        return str(value).strip() if value else fallback

    parts = [
        _mc_text("title", "🎵 Canvas - MC Music"),
        _mc_text("canvas_mc_description", "Use the dropdown below to control music playback."),
    ]

    if last_action:
        parts.append(_mc_text("last_action_title", "**Last action**"))
        parts.append(f"- {last_action}")

    if not (last_action or queue_info or mc_messages):
        parts.append(_mc_text("voice_channel_required_title", "**Voice channel required**"))
        parts.append(_mc_text("canvas_mc_voice_required", "You must be in a voice channel to use MC\nBot will auto-connect to your channel"))

    if queue_info:
        parts.append(_mc_text("current_queue_title", "**Current queue**"))
        if len(queue_info) > 0:
            for i, (title, artist, duration, _user) in enumerate(queue_info[:5], 1):
                parts.append(f"  {i}. {title}")
                if artist:
                    parts.append(f"     👤 {artist}")
                if duration and duration != "Unknown":
                    parts.append(f"     ⏱️ {duration}")
            if len(queue_info) > 5:
                more_count = len(queue_info) - 5
                parts.append(f"  {_mc_text('and_more_songs', f'... and {more_count} more songs').format(count=more_count)}")
        else:
            parts.append(f"  {_mc_text('queue_empty', '📭 Queue is empty')}")

    if mc_messages:
        parts.append(_mc_text("mc_status", "**MC status**"))
        parts.append(f"  {mc_messages[-1]}")

    return "\n".join(parts)


class CanvasMCActionSelect(discord.ui.Select):
    """MC action selection dropdown."""

    def __init__(self, view):
        from .content import _get_personality_descriptions, _get_canvas_role_action_items_for_detail
        server_id = core.get_server_key(view.guild) if view.guild else None
        mc_messages_fallback = core._personality_answers.get("mc_messages", {})
        mc_descriptions = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("mc", {})
        mc_json_data = _load_mc_descriptions(server_id)

        def _mc_text(key: str, fallback: str) -> str:
            # First try mc.json (server-specific), then descriptions.json, then fallback
            value = mc_json_data.get(key, mc_descriptions.get(key, mc_messages_fallback.get(key)))
            return str(value).strip() if value else fallback

        mc_actions = _get_canvas_role_action_items_for_detail("mc", "overview", view.admin_visible, view.agent_config, server_id)
        options = [
            discord.SelectOption(label=label, value=value, description=description, emoji=emoji)
            for label, value, description, emoji in mc_actions
        ]
        super().__init__(placeholder=_mc_text("select_mc_action", "🎵 Select MC action..."), min_values=1, max_values=1, options=options[:25], row=1)
        self.canvas_view = view

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        view = self.canvas_view
        if not interaction.guild:
            await interaction.response.send_message("❌ MC actions are only available in a server.", ephemeral=True)
            return
        # Handle modal actions (play, add, volume) separately
        if action_name in {"mc_play", "mc_add"}:
            from roles.mc.mc_discord import get_mc_commands_instance
            mc_commands = get_mc_commands_instance()
            if not mc_commands:
                await interaction.response.send_message("❌ MC commands are not initialized.", ephemeral=True)
                return
            await interaction.response.send_modal(CanvasMCSongModal(action_name, view, mc_commands, view.author_id))
            return
        if action_name == "mc_volume":
            from roles.mc.mc_discord import get_mc_commands_instance
            mc_commands = get_mc_commands_instance()
            if not mc_commands:
                await interaction.response.send_message("❌ MC commands are not initialized.", ephemeral=True)
                return
            await interaction.response.send_modal(CanvasMCVolumeModal(view, mc_commands, view.author_id))
            return
        # Handle direct actions (skip, pause, resume, stop, queue, clear, history)
        await _handle_canvas_mc_action(interaction, action_name, view)


async def _handle_canvas_mc_action(interaction: discord.Interaction, action_name: str, view) -> None:
    """Handle MC canvas actions."""
    logger.info(f"MC canvas action received: {action_name}")
    try:
        from roles.mc.mc_discord import get_mc_commands_instance
        from roles.mc.db_role_mc import get_mc_db_instance
        from agent_engine import get_mc_feature
        from .content import _get_personality_descriptions

        # Load translations
        server_id = core.get_server_key(view.guild) if view.guild else None
        mc_descriptions = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("mc", {})
        mc_messages_fallback = core._personality_answers.get("mc_messages", {})
        mc_json_data = _load_mc_descriptions(server_id)

        def _mc_text(key: str, fallback: str) -> str:
            # First try mc.json (server-specific), then descriptions.json, then fallback
            value = mc_json_data.get(key, mc_descriptions.get(key, mc_messages_fallback.get(key)))
            return str(value).strip() if value else fallback

        mc_commands = get_mc_commands_instance()
        if not mc_commands:
            await interaction.response.send_message("❌ MC commands are not initialized.", ephemeral=True)
            return

        mc_enabled = get_mc_feature("voice_commands") if get_mc_feature else False
        if not mc_enabled:
            await interaction.response.send_message("❌ MC voice commands are not enabled.", ephemeral=True)
            return

        class MockMessage:
            def __init__(self, channel, author, guild):
                self.channel = channel
                self.author = author
                self.guild = guild

        mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)

        captured_messages = []
        last_action = None
        queue_info = None

        async def message_callback(content, **kwargs):
            captured_messages.append(content)

        original_callback = mc_commands._message_callback
        mc_commands.set_message_callback(message_callback)

        if not hasattr(view, "_mc_callbacks"):
            view._mc_callbacks = []
        view._mc_callbacks.append((mc_commands, original_callback))

        if action_name == "mc_skip":
            await mc_commands.cmd_skip(mock_message, [])
            last_action = _mc_text("song_skipped", "⏭️ Song skipped")
        elif action_name == "mc_pause":
            await mc_commands.cmd_pause(mock_message, [])
            last_action = _mc_text("playback_paused", "⏸️ Playback paused")
        elif action_name == "mc_resume":
            await mc_commands.cmd_resume(mock_message, [])
            last_action = _mc_text("playback_resumed", "▶️ Playback resumed")
        elif action_name == "mc_stop":
            await mc_commands.cmd_stop(mock_message, [])
            last_action = _mc_text("playback_stopped", "⏹️ Playback stopped and queue cleared")
        elif action_name == "mc_queue":
            await mc_commands.cmd_queue(mock_message, [])
            last_action = _mc_text("queue_displayed", "📋 Queue displayed")
            try:
                db_mc = get_mc_db_instance(str(interaction.guild.id))
                queue_data = db_mc.get_queue(str(interaction.guild.id), str(interaction.channel.id))
                queue_info = [(title, artist, duration, user_id) for _pos, title, _url, duration, artist, user_id, _fecha in queue_data]
            except Exception:
                pass
        elif action_name == "mc_clear":
            await mc_commands.cmd_clear(mock_message, [])
            last_action = _mc_text("queue_cleared", "🗑️ Queue cleared")

        # Fetch updated queue info after actions that modify the queue
        if action_name in ["mc_skip", "mc_pause", "mc_resume", "mc_stop", "mc_clear"]:
            try:
                db_mc = get_mc_db_instance(str(interaction.guild.id))
                queue_data = db_mc.get_queue(str(interaction.guild.id), str(interaction.channel.id))
                queue_info = [(title, artist, duration, user_id) for _pos, title, _url, duration, artist, user_id, _fecha in queue_data]
            except Exception:
                pass
        elif action_name == "mc_history":
            await mc_commands.cmd_history(mock_message, [])
            last_action = _mc_text("history_displayed", "📜 History displayed")
        else:
            logger.warning(f"Unknown MC action received: {action_name}")
            await interaction.response.send_message(f"❌ Unknown MC action: {action_name}", ephemeral=True)
            return

        await asyncio.sleep(0.5)
        from .content import _build_canvas_role_embed
        mc_content = build_canvas_role_mc(last_action=last_action, queue_info=queue_info, mc_messages=captured_messages, guild=view.guild)
        view.auto_response_preview = last_action
        server_id = core.get_server_key(view.guild) if view.guild else None
        embed = _build_canvas_role_embed("mc", mc_content, view.admin_visible, "overview", None, view.auto_response_preview, server_id=server_id)

        try:
            await interaction.response.edit_message(content=None, embed=embed, view=view)
        except discord.InteractionResponded:
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
        except Exception as error:
            logger.exception(f"Failed to edit canvas MC message: {error}")

    except ImportError:
        await interaction.response.send_message("❌ MC commands are not available. Install yt-dlp and PyNaCl.", ephemeral=True)
    except Exception as error:
        logger.exception(f"Error handling MC canvas action {action_name}: {error}")


class CanvasMCSongModal(CanvasModal):
    """Modal for MC song input (play or add)."""

    def __init__(self, action_name: str, view, mc_commands, author_id: int):
        self.action_name = action_name
        self.view = view
        self.mc_commands = mc_commands
        
        from .content import _get_personality_descriptions
        server_id = core.get_server_key(view.guild) if view.guild else None
        mc_descriptions = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("mc", {})
        mc_messages_fallback = core._personality_answers.get("mc_messages", {})
        mc_json_data = _load_mc_descriptions(server_id)

        def _mc_text(key: str, fallback: str) -> str:
            # First try mc.json (server-specific), then descriptions.json, then fallback
            value = mc_json_data.get(key, mc_descriptions.get(key, mc_messages_fallback.get(key)))
            return str(value).strip() if value else fallback

        self._mc_text = _mc_text

        title = _mc_text("play_song_title", "Play Song Now") if action_name == "mc_play" else _mc_text("add_song_title", "Add Song to Queue")
        super().__init__(title=title, timeout=300, author_id=author_id)

        self.song_input = discord.ui.TextInput(
            label=_mc_text("song_name_label", "Song Name or URL"),
            placeholder=_mc_text("song_name_placeholder", "Enter song name, YouTube URL, or search query..."),
            style=discord.TextStyle.long,
            required=True,
            max_length=200,
        )
        self.add_item(self.song_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message(self._mc_text("processing_song", "🎵 Processing song request..."), ephemeral=True, delete_after=5)

            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild

            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)

            captured_messages = []

            async def message_callback(content, **kwargs):
                captured_messages.append(content)

            original_callback = self.mc_commands._message_callback
            self.mc_commands.set_message_callback(message_callback)

            if not hasattr(self.view, "_mc_callbacks"):
                self.view._mc_callbacks = []
            self.view._mc_callbacks.append((self.mc_commands, original_callback))

            song_query = str(self.song_input.value).strip()
            args = song_query.split()

            if self.action_name == "mc_play":
                await self.mc_commands.cmd_play(mock_message, args)
                result_msg = self._mc_text("song_playing_result", "🎵 Now playing: {song}").format(song=song_query)
            else:
                await self.mc_commands.cmd_add(mock_message, args)
                result_msg = self._mc_text("song_added_result", "🎵 Added to queue: {song}").format(song=song_query)

            # Fetch updated queue info after adding/playing song
            queue_info = None
            try:
                from roles.mc.db_role_mc import get_mc_db_instance
                server_id = core.get_server_key(self.view.guild) if self.view.guild else None
                if server_id and self.view.guild:
                    db_mc = get_mc_db_instance(server_id)
                    queue_data = db_mc.get_queue(server_id, str(self.view.guild.id))
                    queue_info = [(title, artist, duration, user_id) for _pos, title, _url, duration, artist, user_id, _fecha in queue_data]
            except Exception:
                pass

            await asyncio.sleep(0.5)
            from .content import _build_canvas_role_embed
            mc_content = build_canvas_role_mc(last_action=result_msg, queue_info=queue_info, mc_messages=captured_messages, guild=self.view.guild)
            self.view.auto_response_preview = result_msg
            server_id = core.get_server_key(self.view.guild) if self.view.guild else None
            embed = _build_canvas_role_embed("mc", mc_content, self.view.admin_visible, "overview", None, server_id=server_id)
            try:
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self.view)
            except Exception:
                pass
        except Exception as error:
            logger.exception(f"Error in MC song modal: {error}")


class CanvasMCVolumeModal(CanvasModal):
    """Modal for MC volume input."""

    def __init__(self, view, mc_commands, author_id: int):
        self.view = view
        self.mc_commands = mc_commands

        from .content import _get_personality_descriptions
        server_id = core.get_server_key(view.guild) if view.guild else None
        mc_descriptions = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("mc", {})
        mc_messages_fallback = core._personality_answers.get("mc_messages", {})
        mc_json_data = _load_mc_descriptions(server_id)

        def _mc_text(key: str, fallback: str) -> str:
            # First try mc.json (server-specific), then descriptions.json, then fallback
            value = mc_json_data.get(key, mc_descriptions.get(key, mc_messages_fallback.get(key)))
            return str(value).strip() if value else fallback

        self._mc_text = _mc_text

        super().__init__(author_id=author_id, title=_mc_text("set_volume_title", "Set Volume"), timeout=300)

        self.volume_input = discord.ui.TextInput(
            label=_mc_text("volume_label", "Volume (0-100)"),
            placeholder=_mc_text("volume_placeholder", "Enter volume level between 0 and 100..."),
            style=discord.TextStyle.short,
            required=True,
            max_length=3,
        )
        self.add_item(self.volume_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild

            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            volume_str = str(self.volume_input.value).strip()
            await self.mc_commands.cmd_volume(mock_message, [volume_str])

            result_msg = self._mc_text("volume_set_result", "🔊 Volume set to {volume}%").format(volume=volume_str)

            # Fetch updated queue info after volume change
            queue_info = None
            try:
                from roles.mc.db_role_mc import get_mc_db_instance
                server_id = core.get_server_key(self.view.guild) if self.view.guild else None
                if server_id and self.view.guild:
                    db_mc = get_mc_db_instance(server_id)
                    queue_data = db_mc.get_queue(server_id, str(self.view.guild.id))
                    queue_info = [(title, artist, duration, user_id) for _pos, title, _url, duration, artist, user_id, _fecha in queue_data]
            except Exception:
                pass

            mc_content = build_canvas_role_mc(last_action=result_msg, queue_info=queue_info, mc_messages=None, guild=self.view.guild)
            self.view.auto_response_preview = result_msg
            from .content import _build_canvas_role_embed
            embed = _build_canvas_role_embed("mc", mc_content, self.view.admin_visible, "overview", None)
            await interaction.response.edit_message(content=None, embed=embed, view=self.view)
        except Exception as error:
            logger.exception(f"Error in MC volume modal: {error}")
