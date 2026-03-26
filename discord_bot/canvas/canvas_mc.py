"""Canvas MC content and UI components."""

import asyncio

import discord

from discord_bot import discord_core_commands as core

_personality_descriptions = core._personality_descriptions
_bot_display_name = core._bot_display_name
logger = core.logger


def _build_mc_role_embed(role_name: str, content: str, admin_visible: bool, surface_name: str = "overview", user=None,
                         auto_response: str | None = None):
    from .content import _build_canvas_role_embed
    return _build_canvas_role_embed(role_name, content, admin_visible, surface_name, user, auto_response)


def _get_mc_action_items_for_detail(role_name: str, current_detail: str, admin_visible: bool):
    from .content import _get_canvas_role_action_items_for_detail
    return _get_canvas_role_action_items_for_detail(role_name, current_detail, admin_visible)


def build_canvas_role_mc(last_action=None, queue_info=None, mc_messages=None) -> str:
    """Build the MC role view with dynamic state."""
    from .content import _build_canvas_intro_block
    mc_messages_dict = {}
    try:
        mc_messages_dict = _personality_descriptions.get("roles_view_messages", {}).get("mc_messages", {})
    except Exception:
        pass

    def _mc_text(key: str, fallback: str) -> str:
        value = mc_messages_dict.get(key)
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback

    parts = [
        _build_canvas_intro_block(
            _mc_text("canvas_mc_title", f"🎵 {_bot_display_name} Canvas - MC (Master of Ceremonies)"),
            _mc_text("canvas_mc_description", "Use the dropdown below to control music playback."),
        )
    ]

    if last_action:
        parts.append("**Last action**")
        parts.append(f"- {last_action}")

    if not (last_action or queue_info or mc_messages):
        parts.append("**Voice channel required**")
        parts.append(_mc_text("canvas_mc_voice_required", "You must be in a voice channel to use MC\nBot will auto-connect to your channel"))

    if queue_info:
        parts.append("**Current queue**")
        if len(queue_info) > 0:
            for i, (title, artist, duration, _user) in enumerate(queue_info[:5], 1):
                parts.append(f"  {i}. {title}")
                if artist:
                    parts.append(f"     👤 {artist}")
                if duration and duration != "Unknown":
                    parts.append(f"     ⏱️ {duration}")
            if len(queue_info) > 5:
                parts.append(f"  ... and {len(queue_info) - 5} more songs")
        else:
            parts.append("  📭 Queue is empty")

    if mc_messages:
        parts.append("**MC status**")
        for message in mc_messages[-3:]:
            parts.append(f"  {message}")

    return "\n".join(parts)


class CanvasMCActionSelect(discord.ui.Select):
    """MC action selection dropdown."""

    def __init__(self, view):
        mc_actions = _get_mc_action_items_for_detail("mc", "overview", view.admin_visible)
        options = [
            discord.SelectOption(label=label, value=value, description=description)
            for label, value, description in mc_actions
        ]
        super().__init__(placeholder="🎵 Select MC action...", min_values=1, max_values=1, options=options[:25], row=1)
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
            await interaction.response.send_modal(CanvasMCSongModal("mc_play", view, mc_commands))
            return
        if action_name == "mc_add":
            await interaction.response.send_modal(CanvasMCSongModal("mc_add", view, mc_commands))
            return
        if action_name == "mc_volume":
            await interaction.response.send_modal(CanvasMCVolumeModal(view, mc_commands))
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
        mc_content = build_canvas_role_mc(last_action=last_action, queue_info=queue_info, mc_messages=captured_messages)
        view.auto_response_preview = last_action
        embed = _build_mc_role_embed("mc", mc_content, view.admin_visible, "overview", None, view.auto_response_preview)

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


class CanvasMCSongModal(discord.ui.Modal):
    """Modal for MC song input (play or add)."""

    def __init__(self, action_name: str, view, mc_commands):
        self.action_name = action_name
        self.view = view
        self.mc_commands = mc_commands
        title = "Play Song Now" if action_name == "mc_play" else "Add Song to Queue"
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
            mc_content = build_canvas_role_mc(last_action=result_msg, queue_info=None, mc_messages=captured_messages)
            self.view.auto_response_preview = result_msg
            embed = _build_mc_role_embed("mc", mc_content, self.view.admin_visible, "overview", None)
            try:
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self.view)
            except Exception:
                pass
        except Exception as error:
            logger.exception(f"Error in MC song modal: {error}")


class CanvasMCVolumeModal(discord.ui.Modal):
    """Modal for MC volume input."""

    def __init__(self, view, mc_commands):
        self.view = view
        self.mc_commands = mc_commands
        super().__init__(title="Set Volume", timeout=300)

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
            mc_content = build_canvas_role_mc(last_action=result_msg, queue_info=None, mc_messages=None)
            self.view.auto_response_preview = result_msg
            embed = _build_mc_role_embed("mc", mc_content, self.view.admin_visible, "overview", None)
            await interaction.response.edit_message(content=None, embed=embed, view=self.view)
        except Exception as error:
            logger.exception(f"Error in MC volume modal: {error}")
