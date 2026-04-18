"""Canvas MC content and UI components."""

import asyncio

import discord

from discord_bot import discord_core_commands as core
from .canvas_base import CanvasModal

logger = core.logger


def build_canvas_role_mc(last_action=None, queue_info=None, mc_messages=None, guild=None) -> str:
    """Build the MC role view with dynamic state."""
    from .content import _get_personality_descriptions
    server_id = core.get_server_key(guild) if guild else None
    mc_messages_fallback = core._personality_answers.get("mc_messages", {})
    mc_descriptions = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("mc", {})

    def _mc_text(key: str, fallback: str) -> str:
        value = mc_descriptions.get(key, mc_messages_fallback.get(key))
        return str(value).strip() if value else fallback

    parts = [
        _mc_text("title", "🎵 Canvas - MC (Master of Ceremonies)"),
        _mc_text("description", "Use the dropdown below to control music playback."),
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
        parts.append("**MC status**")
        for message in mc_messages[-3:]:
            parts.append(f"  {message}")

    return "\n".join(parts)


class CanvasMCActionSelect(discord.ui.Select):
    """MC action selection dropdown."""

    def __init__(self, view):
        from .content import _get_personality_descriptions, _get_canvas_role_action_items_for_detail
        server_id = core.get_server_key(view.guild) if view.guild else None
        mc_messages_fallback = core._personality_answers.get("mc_messages", {})
        mc_descriptions = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("mc", {})

        def _mc_text(key: str, fallback: str) -> str:
            value = mc_descriptions.get(key, mc_messages_fallback.get(key))
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
        await _handle_canvas_mc_action(interaction, action_name, view)


async def _handle_canvas_mc_action(interaction: discord.Interaction, action_name: str, view) -> None:
    """Handle MC canvas actions."""
    try:
        from roles.mc.mc_discord import get_mc_commands_instance
        from roles.mc.db_role_mc import get_mc_db_instance
        from agent_engine import get_mc_feature

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

        if action_name == "mc_play":
            await interaction.response.send_modal(CanvasMCSongModal("mc_play", view, mc_commands, view.author_id))
            return
        if action_name == "mc_add":
            await interaction.response.send_modal(CanvasMCSongModal("mc_add", view, mc_commands, view.author_id))
            return
        if action_name == "mc_volume":
            await interaction.response.send_modal(CanvasMCVolumeModal(view, mc_commands, view.author_id))
            return

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
            last_action = "⏭️ Song skipped"
        elif action_name == "mc_pause":
            await mc_commands.cmd_pause(mock_message, [])
            last_action = "⏸️ Playback paused"
        elif action_name == "mc_resume":
            await mc_commands.cmd_resume(mock_message, [])
            last_action = "▶️ Playback resumed"
        elif action_name == "mc_stop":
            await mc_commands.cmd_stop(mock_message, [])
            last_action = "⏹️ Playback stopped and queue cleared"
        elif action_name == "mc_queue":
            await mc_commands.cmd_queue(mock_message, [])
            last_action = "📋 Queue displayed"
            try:
                db_mc = get_mc_db_instance(str(interaction.guild.id))
                queue_data = db_mc.obtener_queue(str(interaction.guild.id), str(interaction.channel.id))
                queue_info = [(title, artist, duration, user_id) for _pos, title, _url, duration, artist, user_id, _fecha in queue_data]
            except Exception:
                pass
        elif action_name == "mc_clear":
            await mc_commands.cmd_clear(mock_message, [])
            last_action = "🗑️ Queue cleared"
        elif action_name == "mc_history":
            await mc_commands.cmd_history(mock_message, [])
            last_action = "📜 History displayed"
        else:
            await interaction.response.send_message("❌ Unknown MC action.", ephemeral=True)
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

        def _mc_text(key: str, fallback: str) -> str:
            value = mc_descriptions.get(key, mc_messages_fallback.get(key))
            return str(value).strip() if value else fallback

        title = _mc_text("play_song_title", "Play Song Now") if action_name == "mc_play" else _mc_text("add_song_title", "Add Song to Queue")
        super().__init__(title=title, timeout=300)

        self.song_input = discord.ui.TextInput(
            label="Song Name or URL",
            placeholder="Enter song name, YouTube URL, or search query...",
            style=discord.TextStyle.long,
            required=True,
            max_length=200,
        )
        self.add_item(self.song_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message("🎵 Processing song request...", ephemeral=True, delete_after=5)

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
                result_msg = f"🎵 Now playing: {song_query}"
            else:
                await self.mc_commands.cmd_add(mock_message, args)
                result_msg = f"🎵 Added to queue: {song_query}"

            await asyncio.sleep(0.5)
            from .content import _build_canvas_role_embed
            mc_content = build_canvas_role_mc(last_action=result_msg, queue_info=None, mc_messages=captured_messages, guild=self.view.guild)
            self.view.auto_response_preview = result_msg
            server_id = core.get_server_key(self.view.guild) if self.view.guild else None
            embed = _build_canvas_role_embed("mc", mc_content, self.view.admin_visible, "overview", None, server_id=server_id)
            try:
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self.view)
            except Exception:
                pass
        except Exception as error:
            logger.exception(f"Error in MC song modal: {error}")


class CanvasMCVolumeModal(discord.ui.Modal):
    """Modal for MC volume input."""

    def __init__(self, view, mc_commands, author_id: int):
        self.view = view
        self.mc_commands = mc_commands
        self.author_id = author_id
        
        from .content import _get_personality_descriptions
        server_id = core.get_server_key(view.guild) if view.guild else None
        mc_descriptions = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("mc", {})
        mc_messages_fallback = core._personality_answers.get("mc_messages", {})

        def _mc_text(key: str, fallback: str) -> str:
            value = mc_descriptions.get(key, mc_messages_fallback.get(key))
            return str(value).strip() if value else fallback

        super().__init__(title=_mc_text("set_volume_title", "Set Volume"), timeout=300, author_id=author_id)

        self.volume_input = discord.ui.TextInput(
            label="Volume (0-100)",
            placeholder="Enter volume level between 0 and 100...",
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

            result_msg = f"🔊 Volume set to {volume_str}%"
            mc_content = build_canvas_role_mc(last_action=result_msg, queue_info=None, mc_messages=None, guild=self.view.guild)
            self.view.auto_response_preview = result_msg
            from .content import _build_canvas_role_embed
            embed = _build_canvas_role_embed("mc", mc_content, self.view.admin_visible, "overview", None)
            await interaction.response.edit_message(content=None, embed=embed, view=self.view)
        except Exception as error:
            logger.exception(f"Error in MC volume modal: {error}")
