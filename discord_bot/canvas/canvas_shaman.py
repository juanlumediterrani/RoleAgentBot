"""Canvas Shaman content builders."""

import asyncio
import json

import discord

from discord_bot import discord_core_commands as core
from .canvas_base import CanvasModal

get_server_key = core.get_server_key

logger = core.logger
AgentDatabase = core.AgentDatabase
is_admin = core.is_admin
set_role_enabled = core.set_role_enabled

try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None

try:
    from roles.shaman.subroles.nordic_runes.nordic_runes_discord import get_nordic_runes_commands_instance
except Exception:
    get_nordic_runes_commands_instance = None


def _get_shaman_descriptions(server_id):
    """Load shaman role descriptions from personality."""
    from .content import _get_personality_descriptions
    try:
        return _get_personality_descriptions(server_id).get("role_descriptions", {}).get("shaman", {})
    except Exception:
        return {}


def get_runes_messages(guild=None) -> dict:
    """Get runes messages from personality descriptions with fallbacks."""
    try:
        from .content import _get_personality_descriptions
        server_id = get_server_key(guild) if guild else None
        descriptions = _get_personality_descriptions(server_id)
        runes = descriptions.get("role_descriptions", {}).get("shaman", {}).get("nordic_runes", {})
        if runes:
            return runes
    except Exception as e:
        logger.error(f"Error loading runes messages from shaman descriptions: {e}")

    return {
        'single_cast': "🔮 **SINGLE RUNE CASTING** 🔮",
        'three_cast': "🔮 **THREE RUNE CASTING** 🔮",
        'cross_cast': "🔮 **FIVE RUNE CROSS CASTING** 🔮",
        'runic_cross_cast': "🔮 **SEVEN RUNE RUNIC CROSS CASTING** 🔮",
        'question': 'Question for the runes',
        'types': "🔮 **RUNE CASTING TYPES** 🔮",
        'runes_list': "🔮 **ELDER FUTHARK RUNES** 🔮",
        'history': "🔮 **ANCIENT RUNES HISTORY** (Last {count}) 🔮",
        'no_question': "Please provide a question for your rune reading.",
        'reading_saved': "Your rune reading has been saved to your personal journal.",
        'error': "An error occurred while casting the runes. Please try again."
    }


def build_canvas_role_shaman(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the Shaman role overview."""
    server_id = get_server_key(guild) if guild else None
    shaman_messages = _get_shaman_descriptions(server_id)

    def _shaman_text(key: str, fallback: str) -> str:
        value = shaman_messages.get(key)
        return str(value).strip() if value else fallback

    # Load active subroles from DB, fallback to agent_config
    active_subroles = []
    try:
        if get_roles_db_instance:
            server_key = get_server_key(guild)
            roles_db = get_roles_db_instance(server_key)
            shaman_config = roles_db.get_role_config('shaman')
            if shaman_config and shaman_config.get('enabled', False):
                for subrole in ['nordic_runes']:
                    subrole_config = roles_db.get_role_config(subrole)
                    if subrole_config and subrole_config.get('enabled', False):
                        active_subroles.append(subrole)
    except Exception as e:
        logger.warning(f"Error loading shaman subroles from roles_config: {e}")
        subroles = (agent_config or {}).get("roles", {}).get("shaman", {}).get("subroles", {})
        active_subroles = [name for name, cfg in subroles.items() if isinstance(cfg, dict) and cfg.get("enabled", False)]

    subrole_descriptions = shaman_messages.get("canvas_shaman_subrole_descriptions", {})

    title = _shaman_text("title", "🔮 **Shaman**")
    description = _shaman_text("description", "Mystical guidance through ancient Nordic runes and spiritual wisdom.")

    parts = [title, description]

    if active_subroles:
        parts.append("")
        parts.append("**Available subroles**")
        for subrole in active_subroles:
            if subrole in subrole_descriptions:
                parts.append(subrole_descriptions[subrole])

    return "\n".join(parts)


def build_canvas_role_shaman_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None, agent_config: dict | None = None) -> str | None:
    """Build a detailed Shaman view."""
    if detail_name == "overview":
        return build_canvas_role_shaman(agent_config or {}, admin_visible, guild)

    server_id = get_server_key(guild) if guild else None
    shaman_messages = _get_shaman_descriptions(server_id)
    runes_messages = shaman_messages.get("nordic_runes", {})

    def _runes_text(key: str, fallback: str) -> str:
        value = runes_messages.get(key)
        return str(value).strip() if value else fallback

    if detail_name == "runes":
        title = _runes_text("title", "🔮 **Nordic Runes Ancient Wisdom** 🔮")
        description = _runes_text("description", "Ancient wisdom for modern guidance through Elder Futhark runes.")

        runes_enabled = False
        if agent_config:
            runes_enabled = agent_config.get("roles", {}).get("shaman", {}).get("subroles", {}).get("nordic_runes", {}).get("enabled", False)

        how_to_use = _runes_text("how_to_use", "**How to Use:**\n 1. Choose a reading type from the dropdown\n 2. Enter your question in the modal\n 3. Receive personalized rune interpretation\n")
        runes_title = _runes_text("runes_title", "**The 24 Elder Futhark Runes:**")

        return "\n".join([
            title,
            description,
            "-" * 45,
            how_to_use,
            "-" * 45,
            "",
            runes_title,
            "-" * 45,
            "ᚠ Fehu • ᚢ Uruz • ᚦ Thurisaz • ᚨ Ansuz • ᚱ Raidho • ᚲ Kenaz • ᚷ Gebo • ᚹ Wunjo",
            "ᚺ Hagalaz • ᚾ Nauthiz • ᛁ Isa • ᛃ Jera • ᛇ Eiwaz • ᛈ Perthro • ᛉ Algiz • ᛊ Sowilo",
            "ᛏ Tiwaz • ᛒ Berkano • ᛖ Ehwaz • ᛗ Mannaz • ᛚ Laguz • ᛜ Ingwaz • ᛞ Dagaz • ᛟ Othala",
            "",
            "-" * 45,
            f"**Status:** {'✅ Enabled' if runes_enabled else '❌ Disabled'}",
        ])

    if detail_name == "runes_admin":
        title = _runes_text("title", "🔮 **Nordic Runes Ancient Wisdom** 🔮")

        subroles = (agent_config or {}).get("roles", {}).get("shaman", {}).get("subroles", {})
        runes_enabled = subroles.get("nordic_runes", {}).get("enabled", False)

        return "\n".join([
            f"{title} Admin",
            "Configure Nordic Runes subrole settings and availability for this server.",
            f"**Status:** {'✅ Enabled' if runes_enabled else '❌ Disabled'}",
            "",
            "**Controls**",
            "- Enable or disable Nordic Runes subrole",
            "- When enabled, users can cast runes and receive interpretations",
            "- All rune readings are tracked in the database",
            "",
            "**Available Reading Types:**",
            "• Single Rune - Quick guidance and insight",
            "• Three Rune Spread - Past, Present, Future",
            "• Five Rune Cross - Comprehensive situation analysis",
            "• Seven Rune Runic Cross - Deep spiritual guidance",
            "",
            "**Features when enabled:**",
            "• Personalized rune interpretations based on user questions",
            "• Reading history tracking for each user",
            "• Contextual guidance for different life areas",
            "• Ancient Norse wisdom applied to modern situations",
            "",
            "**Routing**",
            "- Back only from here",
            "- No other subrole buttons are shown in this admin screen",
        ])

    return None


class RuneCastingModal(CanvasModal):
    """Modal for rune casting questions."""

    def __init__(self, action_name: str, author_id: int, guild):
        reading_type = action_name.replace("runes_", "")
        messages = get_runes_messages(guild)

        title_map = {
            "runes_single": messages.get('single_cast', "🔮 **SINGLE RUNE CASTING** 🔮"),
            "runes_three": messages.get('three_cast', "🔮 **THREE RUNE CASTING** 🔮"),
            "runes_cross": messages.get('cross_cast', "🔮 **FIVE RUNE CROSS CASTING** 🔮"),
            "runes_runic_cross": messages.get('runic_cross_cast', "🔮 **SEVEN RUNE RUNIC CROSS CASTING** 🔮"),
        }
        super().__init__(title=title_map.get(action_name, "Rune Casting"), timeout=300.0, author_id=author_id)
        self.action_name = action_name
        self.guild = guild
        self.reading_type = reading_type
        self.title_map = title_map

        self.add_item(discord.ui.TextInput(
            label=messages.get('question', 'Question'),
            placeholder=messages.get('question_prompt', 'What question or situation would you like guidance on?'),
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500,
        ))

    async def on_submit(self, interaction: discord.Interaction):
        question = self.children[0].value.strip()

        if not question:
            messages = get_runes_messages()
            await interaction.response.send_message(f"❌ {messages.get('no_question', 'Please provide a question for your rune reading.')}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            if get_nordic_runes_commands_instance is None:
                await interaction.followup.send("❌ Runes system is not available.", ephemeral=True)
                return

            runes_commands = get_nordic_runes_commands_instance()

            class MockMessage:
                def __init__(self, author, guild):
                    self.author = author
                    self.guild = guild

            mock_message = MockMessage(interaction.user, interaction.guild)
            result = await runes_commands.cmd_runes_cast(mock_message, self.reading_type, question)

            from .content import _get_personality_descriptions
            _rune_server_id = get_server_key(interaction.guild) if interaction.guild else None
            descriptions = _get_personality_descriptions(_rune_server_id).get("role_descriptions", {}).get("shaman", {}).get("nordic_runes", {})
            saved_msg = descriptions.get("reading_saved", "🔮 Runes have been cast! Your reading has been saved.")

            if isinstance(result, tuple) and len(result) == 2:
                main_response, interpretation_response = result
                response = main_response
                interpretation_parts = [interpretation_response]
            elif isinstance(result, tuple) and len(result) == 3:
                main_response, interpretation_part_one, interpretation_part_two = result
                response = main_response
                interpretation_parts = [interpretation_part_one, interpretation_part_two]
            else:
                response = result
                interpretation_parts = []

            embed_title = self.title_map.get(self.action_name, "🔮 Rune Reading")
            _server_id = get_server_key(interaction.guild) if interaction.guild else None

            try:
                from discord_bot.discord_utils import build_personality_embed
                personality_embed, avatar_file = await build_personality_embed(
                    interaction.client, interaction.guild, _server_id
                )

                runes_embed = discord.Embed(
                    title=embed_title,
                    description=response,
                    color=discord.Color.purple()
                )
                runes_embed.set_footer(text=f"{saved_msg}")

                if avatar_file:
                    await interaction.user.send(embeds=[personality_embed, runes_embed], file=avatar_file)
                else:
                    await interaction.user.send(embeds=[personality_embed, runes_embed])
                logger.info(f"Successfully sent rune reading via DM to user {interaction.user.id}")

                for interpretation_msg in interpretation_parts:
                    await asyncio.sleep(0.5)
                    await interaction.user.send(interpretation_msg)
                    logger.info(f"Successfully sent rune interpretation via DM to user {interaction.user.id}")

            except discord.Forbidden:
                logger.info(f"User {interaction.user.id} has DMs disabled, sending as ephemeral")
                if len(response) > 1900:
                    response = response[:1900] + "...\n\n*Message truncated due to length*"

                embed = discord.Embed(
                    title=embed_title,
                    description=response,
                    color=discord.Color.purple()
                )
                embed.set_footer(text=f"{saved_msg}")
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"DMs disabled for user {interaction.user.id}, sent as ephemeral")

                for interpretation_msg in interpretation_parts:
                    await asyncio.sleep(0.5)
                    await interaction.followup.send(interpretation_msg, ephemeral=True)

            except discord.errors.NotFound:
                logger.info("Interaction expired, attempting direct DM for rune reading")
                try:
                    from discord_bot.discord_utils import build_personality_embed
                    personality_embed, avatar_file = await build_personality_embed(
                        interaction.client, interaction.guild, _server_id
                    )

                    runes_embed = discord.Embed(
                        title=embed_title,
                        description=response,
                        color=discord.Color.purple()
                    )
                    runes_embed.set_footer(text=f"{saved_msg}")

                    if avatar_file:
                        await interaction.user.send(embeds=[personality_embed, runes_embed], file=avatar_file)
                    else:
                        await interaction.user.send(embeds=[personality_embed, runes_embed])
                    for interpretation_msg in interpretation_parts:
                        await asyncio.sleep(0.5)
                        await interaction.user.send(interpretation_msg)
                except Exception as e:
                    logger.error(f"Failed to send rune reading via DM: {e}")
                    if hasattr(interaction, "channel") and interaction.channel:
                        try:
                            embed = discord.Embed(
                                title=f"🔮 {interaction.user.mention} {embed_title.replace('🔮', '').replace('**', '').strip()}!",
                                description=response,
                                color=discord.Color.purple()
                            )
                            embed.set_footer(text=f"{saved_msg}")
                            await interaction.channel.send(embed=embed)
                            for interpretation_msg in interpretation_parts:
                                await asyncio.sleep(0.5)
                                await interaction.channel.send(interpretation_msg)
                        except Exception as channel_error:
                            logger.error(f"Failed to send to channel: {channel_error}")
                    else:
                        logger.error("All delivery methods failed for rune reading")

        except discord.errors.NotFound as e:
            logger.warning(f"Rune casting modal interaction expired: {e}")
        except Exception as e:
            logger.exception(f"Rune casting modal failed: {e}")
            try:
                await interaction.followup.send("❌ Error al lanzar las runas. Por favor intenta de nuevo.", ephemeral=True)
            except discord.errors.NotFound:
                logger.warning("Cannot send error message - interaction expired")
            except Exception:
                try:
                    await interaction.user.send("❌ Error al lanzar las runas. Por favor intenta de nuevo.")
                except Exception:
                    logger.error("All error message delivery methods failed")


async def handle_canvas_shaman_action(interaction: discord.Interaction, action_name: str, view) -> None:
    """Handle Shaman canvas actions."""
    server_key = get_server_key(interaction.guild) if interaction.guild else None
    ok = True
    current_detail = "overview"
    applied_text = None

    try:
        # --- Rune casting modals ---
        if action_name in {"runes_single", "runes_three", "runes_cross", "runes_runic_cross"}:
            if not interaction.guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return

            runes_enabled = False
            if view.agent_config:
                runes_enabled = view.agent_config.get("roles", {}).get("shaman", {}).get("subroles", {}).get("nordic_runes", {}).get("enabled", False)

            if not runes_enabled:
                await interaction.response.send_message("❌ Nordic Runes subrole is currently disabled. Contact an administrator to enable this feature.", ephemeral=True)
                return

            await interaction.response.send_modal(RuneCastingModal(action_name, view.author_id, interaction.guild))
            return

        # --- Admin: enable/disable runes ---
        if action_name in {"runes_on", "runes_off"}:
            enabled = action_name == "runes_on"
            try:
                from agent_engine import AGENT_CFG
                if "roles" not in AGENT_CFG:
                    AGENT_CFG["roles"] = {}
                if "shaman" not in AGENT_CFG["roles"]:
                    AGENT_CFG["roles"]["shaman"] = {}
                if "subroles" not in AGENT_CFG["roles"]["shaman"]:
                    AGENT_CFG["roles"]["shaman"]["subroles"] = {}
                if "nordic_runes" not in AGENT_CFG["roles"]["shaman"]["subroles"]:
                    AGENT_CFG["roles"]["shaman"]["subroles"]["nordic_runes"] = {}
                AGENT_CFG["roles"]["shaman"]["subroles"]["nordic_runes"]["enabled"] = enabled

                if get_roles_db_instance is not None:
                    db_roles = get_roles_db_instance(server_key)
                    config_data = json.dumps({"enabled": enabled})
                    ok = db_roles.save_role_config("nordic_runes", enabled, config_data)
                else:
                    ok = True

                current_detail = "runes_admin"
                applied_text = f"Nordic Runes {'enabled' if enabled else 'disabled'}."

                if view.agent_config is None:
                    view.agent_config = {}
                if "roles" not in view.agent_config:
                    view.agent_config["roles"] = {}
                if "shaman" not in view.agent_config["roles"]:
                    view.agent_config["roles"]["shaman"] = {}
                if "subroles" not in view.agent_config["roles"]["shaman"]:
                    view.agent_config["roles"]["shaman"]["subroles"] = {}
                if "nordic_runes" not in view.agent_config["roles"]["shaman"]["subroles"]:
                    view.agent_config["roles"]["shaman"]["subroles"]["nordic_runes"] = {}
                view.agent_config["roles"]["shaman"]["subroles"]["nordic_runes"]["enabled"] = enabled
            except Exception as e:
                logger.exception(f"Failed to update runes config: {e}")
                ok = False
                current_detail = "runes_admin"
                applied_text = "Failed to update runes configuration."
        elif action_name in {"runes_history", "runes_types", "runes_runes_1", "runes_runes_2", "runes_runes_3"}:
            await _handle_canvas_runes_action(interaction, action_name, view)
            return
        else:
            await interaction.response.send_message("❌ Unknown shaman action.", ephemeral=True)
            return

    except Exception as e:
        logger.exception(f"Canvas shaman action failed: {e}")
        ok = False

    # --- Re-render view ---
    try:
        from .content import _build_canvas_role_embed, _get_canvas_role_actions
        from discord_bot.canvas.ui import CanvasRoleDetailView

        detail_content = build_canvas_role_shaman_detail(current_detail, view.admin_visible, interaction.guild, view.author_id, view.agent_config)
        actions = _get_canvas_role_actions("shaman", current_detail, view.admin_visible, view.agent_config, interaction.guild)
        role_embed = _build_canvas_role_embed("shaman", detail_content, view.admin_visible, current_detail, applied_text)

        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name="shaman",
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
                logger.debug("Canvas shaman interaction expired completely")
    except Exception as e:
        logger.exception(f"Failed to re-render shaman canvas: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Error al actualizar vista.", ephemeral=True)


async def _handle_canvas_runes_action(interaction: discord.Interaction, action_name: str, view) -> None:
    """Handle Nordic runes info/history actions with dynamic content."""
    try:
        try:
            from roles.shaman.subroles.nordic_runes.nordic_runes_messages import get_message
        except ImportError as e:
            logger.error(f"Failed to import runes modules: {e}")
            await interaction.response.send_message("❌ Runes system is not available.", ephemeral=True)
            return

        guild = interaction.guild
        from .content import _get_personality_descriptions
        server_id = get_server_key(guild) if guild else None
        _runes_desc = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("shaman", {}).get("nordic_runes", {})

        class MockMessage:
            def __init__(self, author, guild):
                self.author = author
                self.guild = guild

        mock_message = MockMessage(interaction.user, guild)

        if get_nordic_runes_commands_instance is None:
            await interaction.response.send_message("❌ Runes system is not available.", ephemeral=True)
            return

        runes_commands = get_nordic_runes_commands_instance()
        content_parts = []

        if action_name == "runes_history":
            try:
                title_history = _runes_desc.get("title_history", "🌔 **RUNES READING HISTORY**🌔")
                result = await runes_commands.cmd_runes_canvas_history(mock_message, 10)
                content_parts.append("─" * 45)
                content_parts.append(result)
            except Exception as e:
                logger.exception(f"Canvas runes history failed: {e}")
                error_history = _runes_desc.get("error_history", "❌ **ERROR!** Could not load your rune history.")
                content_parts.extend([title_history, error_history, ""])
        elif action_name == "runes_runes_1":
            try:
                content_parts.append("─" * 45)
                content_parts.append(get_message("runes_list_content", 1))
            except Exception as e:
                logger.exception(f"Canvas runes list page 1 failed: {e}")
                content_parts.extend(["🔮 **ELDER FUTHARK RUNES I** 🔮", "❌ **ERROR!** Could not load runes list page 1."])
        elif action_name == "runes_runes_2":
            try:
                content_parts.append("─" * 45)
                content_parts.append(get_message("runes_list_content", 2))
            except Exception as e:
                logger.exception(f"Canvas runes list page 2 failed: {e}")
                content_parts.extend(["🔮 **ELDER FUTHARK RUNES II** 🔮", "❌ **ERROR!** Could not load runes list page 2."])
        elif action_name == "runes_runes_3":
            try:
                content_parts.append("─" * 45)
                content_parts.append(get_message("runes_list_content", 3))
            except Exception as e:
                logger.exception(f"Canvas runes list page 3 failed: {e}")
                content_parts.extend(["🔮 **ELDER FUTHARK RUNES III** 🔮", "❌ **ERROR!** Could not load runes list page 3."])
        elif action_name == "runes_runes":
            try:
                content_parts.append("─" * 45)
                content_parts.append(get_message("runes_list_content"))
            except Exception as e:
                logger.exception(f"Canvas runes list failed: {e}")
                content_parts.extend(["🔮 **ELDER FUTHARK RUNES** 🔮", "❌ **ERROR!** Could not load runes list."])
        elif action_name == "runes_types":
            try:
                title_available = _runes_desc.get("title_available_readings", "🌌**Available readings**🌌\n ")
                available = _runes_desc.get("available_readings", "-Single rune: quick guidance\n - Three runes: past, present, future\n - Five Cross runes: Comprehensive analysis\n - Seven Runic Cross: Integral spiritual insight\n")
                content_parts.append("─" * 45)
                content_parts.append(title_available)
                content_parts.append("─" * 45)
                content_parts.append(available)
            except Exception as e:
                logger.exception(f"Canvas runes types failed: {e}")
                content_parts.extend(["🔮 **RUNES READING TYPES** 🔮", "❌ **ERROR!** Could not load reading types."])

        content = "\n".join(content_parts)
        from .content import _build_canvas_role_embed
        from discord_bot.canvas.ui import CanvasRoleDetailView

        runes_title = _runes_desc.get("title", "🔮 **Nordic Runes Ancient Wisdom** 🔮")
        role_embed = _build_canvas_role_embed("shaman", content, view.admin_visible, "runes", None, f"Viewed {action_name.replace('runes_', '').title()}")
        role_embed.title = runes_title
        view.current_embed = role_embed

        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail="runes",
            guild=view.guild,
            previous_view=view,
        )
        next_view.auto_response_preview = f"Viewed {action_name.replace('runes_', '').title()}"

        try:
            await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)
        except discord.InteractionResponded:
            await interaction.followup.edit_message(interaction.message.id, embed=role_embed, view=next_view)
        except discord.NotFound:
            try:
                await interaction.followup.send(embed=role_embed, view=next_view, ephemeral=True)
            except discord.NotFound:
                logger.debug("Canvas runes interaction expired completely")
        except Exception as e:
            logger.exception(f"Failed to edit canvas runes message: {e}")
            try:
                await interaction.followup.send("❌ Error al actualizar vista. Por favor intenta de nuevo.", ephemeral=True)
            except discord.NotFound:
                logger.warning("Canvas runes interaction expired during error handling")

    except Exception as e:
        logger.exception(f"Unexpected error in Canvas shaman runes action: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)
        else:
            try:
                await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)
            except discord.NotFound:
                logger.warning("Canvas shaman interaction expired during error handling")
