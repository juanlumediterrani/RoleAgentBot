"""Canvas Shaman content builders."""

import asyncio
import json
from datetime import datetime

import discord

from discord_bot import discord_core_commands as core
from .canvas_base import CanvasModal
from .server_config import get_role_config_value

get_server_key = core.get_server_key

logger = core.logger
AgentDatabase = core.AgentDatabase
is_admin = core.is_admin
set_role_enabled = core.set_role_enabled
_personality_answers = core._personality_answers

try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None

try:
    from roles.shaman.api import get_nordic_runes_commands_instance, Astrology
except Exception:
    get_nordic_runes_commands_instance = None
    Astrology = None


def get_moon_phase():
    """Calculate current moon phase using a simple algorithm.

    Returns a tuple of (phase_name, emoji) where phase_name is one of:
    'new_moon', 'waxing_crescent', 'first_quarter', 'waxing_gibbous',
    'full_moon', 'waning_gibbous', 'last_quarter', 'waning_crescent'
    """
    # Known new moon date (January 6, 2000)
    known_new_moon = datetime(2000, 1, 6, 18, 14)
    current_date = datetime.utcnow()

    # Calculate days since known new moon
    days_since = (current_date - known_new_moon).total_seconds() / 86400

    # Lunar cycle is approximately 29.53 days
    lunar_cycle = 29.53
    cycle_position = days_since % lunar_cycle

    # Determine phase based on position in cycle
    if cycle_position < 1.85:
        return "new_moon", "🌑"
    elif cycle_position < 7.38:
        return "waxing_crescent", "🌒"
    elif cycle_position < 9.23:
        return "first_quarter", "🌓"
    elif cycle_position < 13.77:
        return "waxing_gibbous", "🌔"
    elif cycle_position < 16.69:
        return "full_moon", "🌕"
    elif cycle_position < 21.23:
        return "waning_gibbous", "🌖"
    elif cycle_position < 23.08:
        return "last_quarter", "🌗"
    else:
        return "waning_crescent", "🌘"


def _get_shaman_descriptions(server_id):
    """Load shaman role descriptions from personality."""
    from .content import _get_personality_descriptions
    try:
        return _get_personality_descriptions(server_id).get("role_descriptions", {}).get("shaman", {})
    except Exception:
        return {}


def _get_personality_answers(server_id):
    """Load personality answers from server-specific or global directory."""
    if not server_id:
        return _personality_answers
    try:
        import json
        from pathlib import Path
        from discord_bot.db_init import get_server_personality_dir
        server_dir = get_server_personality_dir(server_id)
        if server_dir:
            server_path = Path(server_dir)
            answers_path = server_path / "answers.json"
            if answers_path.exists():
                with open(answers_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
    except Exception as e:
        logger.debug(f"Could not load answers for server {server_id}: {e}")
    return _personality_answers


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

    # Get general messages
    general_messages = {}
    try:
        from .content import _get_personality_descriptions
        personality_descriptions = _get_personality_descriptions(server_id)
        general_messages = personality_descriptions.get("general", {})
    except Exception:
        pass

    def _shaman_text(key: str, fallback: str) -> str:
        value = shaman_messages.get(key)
        return str(value).strip() if value else fallback

    def _general_text(key: str, fallback: str) -> str:
        """Get text from general messages."""
        value = general_messages.get(key)
        return str(value).strip() if value else fallback

    # Load active subroles from server_config.json, fallback to agent_config
    active_subroles = []
    try:
        server_id = str(guild.id) if guild else None
        if server_id:
            from .server_config import is_role_enabled

            # Check shaman role is enabled
            shaman_enabled = is_role_enabled(server_id, "shaman", default_enabled=False)
            if shaman_enabled:
                for subrole in ['nordic_runes', 'astrology']:
                    subrole_enabled = get_role_config_value(server_id, "shaman", f"config.subroles.{subrole}.enabled", False)
                    if subrole_enabled:
                        active_subroles.append(subrole)
    except Exception as e:
        logger.warning(f"Error loading shaman subroles from server_config: {e}")
        subroles = (agent_config or {}).get("roles", {}).get("shaman", {}).get("subroles", {})
        active_subroles = [name for name, cfg in subroles.items() if isinstance(cfg, dict) and cfg.get("enabled", False)]

    subrole_descriptions = shaman_messages.get("canvas_shaman_subrole_descriptions", {})

    description = _shaman_text("description", "Mystical guidance through ancient Nordic runes and spiritual wisdom.")

    parts = [description]

    # Add moon phase after description - combine title from descriptions with message from answers.json
    moon_phase_name, moon_emoji = get_moon_phase()

    # Get moon phase title from descriptions (emoji + phase name)
    moon_title = shaman_messages.get("moon_phases", {}).get(moon_phase_name, f"{moon_emoji} {moon_phase_name.replace('_', ' ').title()}")

    # Get moon phase message from answers.json
    personality_answers = _get_personality_answers(server_id)
    moon_phase_messages = personality_answers.get("roles", {}).get("shaman", {}).get("moon_phases", {})
    moon_message_list = moon_phase_messages.get(moon_phase_name, [])
    moon_message = moon_message_list[0] if moon_message_list else ""

    # Combine title and message
    if moon_message:
        parts.append(f"**{moon_title}** - {moon_message}")
    else:
        parts.append(moon_title)

    if active_subroles:
        parts.append(f"**{_general_text('available_subroles', 'Available subroles')}**")
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

        # Get localized labels
        general = shaman_messages.get("general", {})
        action_labels = general.get("action_labels", {})
        label_enabled = action_labels.get("enabled", "Enabled")
        label_disabled = action_labels.get("disabled", "Disabled")

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
            f"**Status:** {'✅ ' + label_enabled if runes_enabled else '❌ ' + label_disabled}",
        ])

    if detail_name == "runes_admin":

        subroles = (agent_config or {}).get("roles", {}).get("shaman", {}).get("subroles", {})
        runes_enabled = subroles.get("nordic_runes", {}).get("enabled", False)

        # Get localized labels
        general = shaman_messages.get("general", {})
        action_labels = general.get("action_labels", {})
        label_enabled = action_labels.get("enabled", "Enabled")
        label_disabled = action_labels.get("disabled", "Disabled")

        return "\n".join([
            "Configure Nordic Runes subrole settings and availability for this server.",
            f"**Status:** {'✅ ' + label_enabled if runes_enabled else '❌ ' + label_disabled}",
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

    if detail_name == "astrology":
        astrology_messages = shaman_messages.get("astrology", {})

        title = astrology_messages.get("welcome", "✨ Welcome to Sefer Yetzirah Astrology! ✨")
        description = astrology_messages.get("help_content", "The Sefer Yetzirah system reveals the 32 paths of wisdom through 22 Hebrew letters (3 Mothers, 7 Doubles, 12 Simples).")

        astrology_enabled = False
        if agent_config:
            astrology_enabled = agent_config.get("roles", {}).get("shaman", {}).get("subroles", {}).get("astrology", {}).get("enabled", False)

        how_to_use = "**How to Use:**\n 1. Choose a reading type from the dropdown\n 2. Enter your question in the modal\n 3. Receive personalized Hebrew letter interpretation\n"
        letters_title = astrology_messages.get("letters_title", "**The 22 Hebrew Letters:**")

        # Get localized labels
        general = shaman_messages.get("general", {})
        action_labels = general.get("action_labels", {})
        label_enabled = action_labels.get("enabled", "Enabled")
        label_disabled = action_labels.get("disabled", "Disabled")

        return "\n".join([
            title,
            description,
            "-" * 45,
            how_to_use,
            "-" * 45,
            "",
            letters_title,
            "-" * 45,
            "**Mother Letters (3):** Alef (Air) • Mem (Water) • Shin (Fire)",
            "**Double Letters (7):** Bet • Gimel • Dalet • Kaf • Pe • Resh • Tav",
            "**Simple Letters (12):** He • Vav • Zayin • Jet • Tet • Yod • Lamed • Nun • Samej • Ayin • Tzadi • Kof",
            "",
            "-" * 45,
            f"**Status:** {'✅ ' + label_enabled if astrology_enabled else '❌ ' + label_disabled}",
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
            label=messages.get('labels', {}).get('question', 'Question'),
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

            runes_commands = get_nordic_runes_commands_instance(interaction.guild)

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


class AstrologyReadingModal(CanvasModal):
    """Modal for astrology reading questions."""

    def __init__(self, action_name: str, author_id: int, guild):
        reading_type = action_name.replace("astrology_", "")
        server_id = get_server_key(guild) if guild else None
        shaman_messages = _get_shaman_descriptions(server_id)
        astrology_messages = shaman_messages.get("astrology", {})

        title_map = {
            "astrology_birth": astrology_messages.get("birth_title", "🌟 BIRTH CHART 🌟"),
            "astrology_moment": astrology_messages.get("moment_title", "⏰ MOMENT READING ⏰"),
            "astrology_year": astrology_messages.get("year_title", "📅 PERSONAL YEAR 📅"),
            "astrology_integrated": astrology_messages.get("integrated_title", "🔮 INTEGRATED READING 🔮"),
        }

        super().__init__(title=title_map.get(action_name, "Astrology Reading"), timeout=300.0, author_id=author_id)
        self.action_name = action_name
        self.guild = guild
        self.reading_type = reading_type
        self.title_map = title_map

        # Add question input
        self.add_item(discord.ui.TextInput(
            label=astrology_messages.get("labels", {}).get("question", "Question"),
            placeholder="What question or situation would you like guidance on?",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500,
        ))

        # Add birth date input for birth chart
        if reading_type == "birth":
            self.add_item(discord.ui.TextInput(
                label="Birth Date (YYYY-MM-DD)",
                placeholder="1990-05-15",
                style=discord.TextStyle.short,
                required=True,
                max_length=10,
            ))
            self.add_item(discord.ui.TextInput(
                label="Birth Time (HH:MM, optional)",
                placeholder="14:30",
                style=discord.TextStyle.short,
                required=False,
                max_length=5,
            ))

        # Add birth year input for year reading
        if reading_type == "year":
            self.add_item(discord.ui.TextInput(
                label="Birth Year",
                placeholder="1990",
                style=discord.TextStyle.short,
                required=True,
                max_length=4,
            ))

    async def on_submit(self, interaction: discord.Interaction):
        question = self.children[0].value.strip()

        if not question:
            server_id = get_server_key(interaction.guild) if interaction.guild else None
            shaman_messages = _get_shaman_descriptions(server_id)
            astrology_messages = shaman_messages.get("astrology", {})
            await interaction.response.send_message(f"❌ {astrology_messages.get('no_question', 'Please provide a question.')}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            if Astrology is None:
                await interaction.followup.send("❌ Astrology system is not available.", ephemeral=True)
                return

            from roles.shaman.subroles.astrology.astrology_db import get_astrology_db_instance
            db = get_astrology_db_instance()
            astrology = Astrology(db)
            from datetime import datetime, time

            result_data = None
            if self.reading_type == "birth":
                birth_date_str = self.children[1].value.strip()
                birth_time_str = self.children[2].value.strip() if len(self.children) > 2 else None
                try:
                    birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
                    birth_time = datetime.strptime(birth_time_str, "%H:%M").time() if birth_time_str else None
                    result_data = astrology.calculate_birth_chart(birth_date, birth_time)
                    # Save birth data
                    user_id = str(interaction.user.id)
                    db.save_astrology_birth_data(user_id, birth_date_str, birth_time_str)
                except ValueError:
                    await interaction.followup.send("❌ Invalid date format. Use YYYY-MM-DD for dates and HH:MM for times.", ephemeral=True)
                    return
            elif self.reading_type == "moment":
                result_data = astrology.calculate_moment_reading(datetime.now())
            elif self.reading_type == "year":
                birth_year_str = self.children[1].value.strip()
                try:
                    birth_year = int(birth_year_str)
                    result_data = astrology.calculate_personal_year(birth_year)
                except ValueError:
                    await interaction.followup.send("❌ Invalid year format. Please use a 4-digit year.", ephemeral=True)
                    return
            elif self.reading_type == "integrated":
                # Get user's birth data
                user_id = str(interaction.user.id)
                birth_data = db.get_astrology_birth_data(user_id)
                if not birth_data:
                    await interaction.followup.send("❌ Please save your birth data first using 'Save Birth Data'.", ephemeral=True)
                    return
                birth_date_str = birth_data.get("birth_date")
                try:
                    birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
                    birth_year = birth_date.year
                    result_data = astrology.calculate_integrated_reading(birth_date, birth_year, datetime.now())
                except ValueError:
                    await interaction.followup.send("❌ Invalid birth data format.", ephemeral=True)
                    return

            # Format the result
            from roles.shaman.subroles.astrology.astrology_messages import get_letter_translations, get_position_translation
            server_id = get_server_key(interaction.guild) if interaction.guild else None
            letter_translations = get_letter_translations(server_id)
            position_translations = get_position_translation(server_id)

            response_parts = []
            for layer_name, layer_data in result_data.items():
                letter_name = layer_data["letter"]["name"]
                letter_info = letter_translations.get(letter_name, {})
                pos_key = layer_data["letter"]["category"] + "_" + layer_name
                pos_name = position_translations.get(pos_key, layer_name.title())

                response_parts.append(f"**{pos_name}**: {letter_info.get('meaning', letter_name)}")
                response_parts.append(f"  Keywords: {letter_info.get('keywords', '')}")
                response_parts.append(f"  {letter_info.get('interpretation', '')}")
                response_parts.append("")

            response = "\n".join(response_parts)

            # Save reading
            db.save_astrology_reading(
                str(interaction.user.id),
                self.reading_type,
                result_data,
                response,
                question
            )

            server_id = get_server_key(interaction.guild) if interaction.guild else None
            shaman_messages = _get_shaman_descriptions(server_id)
            astrology_messages = shaman_messages.get("astrology", {})
            saved_msg = astrology_messages.get("birth_data_saved", "✨ Your astrology reading has been saved!")

            embed_title = self.title_map.get(self.action_name, "🌟 Astrology Reading")
            _server_id = get_server_key(interaction.guild) if interaction.guild else None

            try:
                from discord_bot.discord_utils import build_personality_embed
                personality_embed, avatar_file = await build_personality_embed(
                    interaction.client, interaction.guild, _server_id
                )

                astrology_embed = discord.Embed(
                    title=embed_title,
                    description=response,
                    color=discord.Color.gold()
                )
                astrology_embed.set_footer(text=f"{saved_msg}")

                if avatar_file:
                    await interaction.user.send(embeds=[personality_embed, astrology_embed], file=avatar_file)
                else:
                    await interaction.user.send(embeds=[personality_embed, astrology_embed])
                logger.info(f"Successfully sent astrology reading via DM to user {interaction.user.id}")

            except discord.Forbidden:
                logger.info(f"User {interaction.user.id} has DMs disabled, sending as ephemeral")
                if len(response) > 1900:
                    response = response[:1900] + "...\n\n*Message truncated due to length*"

                embed = discord.Embed(
                    title=embed_title,
                    description=response,
                    color=discord.Color.gold()
                )
                embed.set_footer(text=f"{saved_msg}")
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"DMs disabled for user {interaction.user.id}, sent as ephemeral")

            except discord.errors.NotFound:
                logger.info("Interaction expired, attempting direct DM for astrology reading")
                try:
                    from discord_bot.discord_utils import build_personality_embed
                    personality_embed, avatar_file = await build_personality_embed(
                        interaction.client, interaction.guild, _server_id
                    )

                    astrology_embed = discord.Embed(
                        title=embed_title,
                        description=response,
                        color=discord.Color.gold()
                    )
                    astrology_embed.set_footer(text=f"{saved_msg}")

                    if avatar_file:
                        await interaction.user.send(embeds=[personality_embed, astrology_embed], file=avatar_file)
                    else:
                        await interaction.user.send(embeds=[personality_embed, astrology_embed])
                except Exception as e:
                    logger.error(f"Failed to send astrology reading via DM: {e}")
                    if hasattr(interaction, "channel") and interaction.channel:
                        try:
                            embed = discord.Embed(
                                title=f"🌟 {interaction.user.mention} {embed_title.replace('🌟', '').replace('**', '').strip()}!",
                                description=response,
                                color=discord.Color.gold()
                            )
                            embed.set_footer(text=f"{saved_msg}")
                            await interaction.channel.send(embed=embed)
                        except Exception as channel_error:
                            logger.error(f"Failed to send to channel: {channel_error}")
                    else:
                        logger.error("All delivery methods failed for astrology reading")

        except discord.errors.NotFound as e:
            logger.warning(f"Astrology modal interaction expired: {e}")
        except Exception as e:
            logger.exception(f"Astrology modal failed: {e}")
            try:
                await interaction.followup.send("❌ Error processing astrology reading. Please try again.", ephemeral=True)
            except discord.errors.NotFound:
                logger.warning("Cannot send error message - interaction expired")
            except Exception:
                try:
                    await interaction.user.send("❌ Error processing astrology reading. Please try again.")
                except Exception:
                    logger.error("All error message delivery methods failed")


async def handle_canvas_shaman_action(interaction: discord.Interaction, action_name: str, view) -> None:
    """Handle Shaman canvas actions."""
    # Effective guild: fall back to the view's resolved guild in DM.
    eff_guild = interaction.guild or getattr(view, 'guild', None)
    server_key = get_server_key(eff_guild) if eff_guild else None
    ok = True
    current_detail = "overview"
    applied_text = None

    try:
        # --- Rune casting modals ---
        if action_name in {"runes_single", "runes_three", "runes_cross", "runes_runic_cross"}:
            if not eff_guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return

            runes_enabled = False
            if view.agent_config:
                runes_enabled = view.agent_config.get("roles", {}).get("shaman", {}).get("subroles", {}).get("nordic_runes", {}).get("enabled", False)

            if not runes_enabled:
                await interaction.response.send_message("❌ Nordic Runes subrole is currently disabled. Contact an administrator to enable this feature.", ephemeral=True)
                return

            await interaction.response.send_modal(RuneCastingModal(action_name, view.author_id, eff_guild))
            return

        # --- Astrology reading modals ---
        if action_name in {"astrology_birth", "astrology_moment", "astrology_year", "astrology_integrated"}:
            if not eff_guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return

            astrology_enabled = False
            if view.agent_config:
                astrology_enabled = view.agent_config.get("roles", {}).get("shaman", {}).get("subroles", {}).get("astrology", {}).get("enabled", False)

            if not astrology_enabled:
                await interaction.response.send_message("❌ Astrology subrole is currently disabled. Contact an administrator to enable this feature.", ephemeral=True)
                return

            await interaction.response.send_modal(AstrologyReadingModal(action_name, view.author_id, eff_guild))
            return

        # --- Astrology save birth data modal ---
        if action_name == "astrology_save_birth":
            if not eff_guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return

            astrology_enabled = False
            if view.agent_config:
                astrology_enabled = view.agent_config.get("roles", {}).get("shaman", {}).get("subroles", {}).get("astrology", {}).get("enabled", False)

            if not astrology_enabled:
                await interaction.response.send_message("❌ Astrology subrole is currently disabled. Contact an administrator to enable this feature.", ephemeral=True)
                return

            # Send a simple modal for saving birth data
            from .canvas_base import CanvasModal
            class SaveBirthDataModal(CanvasModal):
                def __init__(self, author_id):
                    super().__init__(title="Save Birth Data", timeout=300.0, author_id=author_id)
                    self.add_item(discord.ui.TextInput(
                        label="Birth Date (YYYY-MM-DD)",
                        placeholder="1990-05-15",
                        style=discord.TextStyle.short,
                        required=True,
                        max_length=10,
                    ))
                    self.add_item(discord.ui.TextInput(
                        label="Birth Time (HH:MM, optional)",
                        placeholder="14:30",
                        style=discord.TextStyle.short,
                        required=False,
                        max_length=5,
                    ))

                async def on_submit(self, interaction: discord.Interaction):
                    birth_date_str = self.children[0].value.strip()
                    birth_time_str = self.children[1].value.strip() if len(self.children) > 1 else None

                    try:
                        from datetime import datetime
                        datetime.strptime(birth_date_str, "%Y-%m-%d")
                        if birth_time_str:
                            datetime.strptime(birth_time_str, "%H:%M")
                    except ValueError:
                        await interaction.response.send_message("❌ Invalid date format. Use YYYY-MM-DD for dates and HH:MM for times.", ephemeral=True)
                        return

                    from roles.shaman.subroles.astrology.astrology_db import get_astrology_db_instance
                    db = get_astrology_db_instance()
                    user_id = str(interaction.user.id)
                    db.save_astrology_birth_data(user_id, birth_date_str, birth_time_str)

                    server_id = get_server_key(interaction.guild) if interaction.guild else None
                    shaman_messages = _get_shaman_descriptions(server_id)
                    astrology_messages = shaman_messages.get("astrology", {})
                    saved_msg = astrology_messages.get("birth_data_saved", "✨ Your birth data has been saved successfully!")

                    await interaction.response.send_message(saved_msg, ephemeral=True)

            await interaction.response.send_modal(SaveBirthDataModal(view.author_id))
            return

        # --- Astrology info actions ---
        if action_name in {"astrology_history", "astrology_letters"}:
            await _handle_canvas_astrology_action(interaction, action_name, view)
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

                try:
                    from .server_config import set_role_config
                    ok = set_role_config(server_key, "nordic_runes", enabled, role_config_dict={"enabled": enabled})
                except Exception as e:
                    logger.error(f"Failed to update nordic_runes config in server_config: {e}")
                    ok = False

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

        detail_content = build_canvas_role_shaman_detail(current_detail, view.admin_visible, eff_guild, view.author_id, view.agent_config)
        actions = _get_canvas_role_actions("shaman", current_detail, view.admin_visible, view.agent_config, eff_guild)
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


class RuneDetailButton(discord.ui.Button):
    """Button representing one rune; clicking shows an ephemeral detail card."""

    def __init__(self, rune_data: dict, row: int):
        label = f"{rune_data['symbol']} {rune_data['name']}"
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=f"rune_detail_{rune_data['key']}",
            row=row,
        )
        self.rune_data = rune_data

    async def callback(self, interaction: discord.Interaction):
        r = self.rune_data
        labels = r.get('labels', {})
        title_interpretation = labels.get("interpretation", "Interpretación")

        # Format keywords as comma-separated string
        keywords = r.get('keywords', [])
        if isinstance(keywords, list):
            keywords_str = ', '.join(keywords)
        else:
            keywords_str = str(keywords)

        content = (
            f"{'-'*45}\n **{r['symbol']} {r['name']}**: {keywords_str}\n{'-'*45}\n"
            f"{title_interpretation} {r['interpretation']}"
        )
        await interaction.response.send_message(content, ephemeral=True)


class RunesPageActionSelect(discord.ui.Select):
    """Custom select for runes page that uses parent view's context."""

    def __init__(self, parent_view):
        # Copy options from parent's CanvasRoleActionSelect
        from .ui import CanvasRoleActionSelect
        for item in parent_view.children:
            if isinstance(item, CanvasRoleActionSelect):
                options = item.options
                placeholder = item.placeholder
                self._role_name = item.role_name
                self._detail_name = item.detail_name
                break
        else:
            options = []
            placeholder = "Choose an option..."
            self._role_name = "shaman"
            self._detail_name = "runes"

        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, row=2)
        self._parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        # Adapted logic from CanvasRoleActionSelect callback, using parent_view
        from .ui import _get_canvas_auto_response_preview
        from discord_bot.canvas.canvas_banker import BankerConfigModal, BeggarDonationModal
        from discord_bot.canvas.ui import RoleFrequencyModal

        action_name = self.values[0]
        self._parent_view.auto_response_preview = _get_canvas_auto_response_preview(self._role_name, action_name)

        eff_guild = interaction.guild or getattr(self._parent_view, 'guild', None)

        if self._role_name == "banker" and action_name in {"config_tae", "config_bonus"}:
            if not self._parent_view.admin_visible:
                await interaction.response.send_message("❌ This banker option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(BankerConfigModal(action_name, self._parent_view.author_id, eff_guild))
            return

        if self._role_name == "banker" and action_name == "beggar_donate":
            if not eff_guild:
                await interaction.response.send_message("❌ Donations are only available in a server.", ephemeral=True)
                return
            await interaction.response.send_modal(BeggarDonationModal(eff_guild, self._parent_view.author_id, self._parent_view))
            return

        if action_name == "watcher_frequency":
            if not self._parent_view.admin_visible:
                await interaction.response.send_message("❌ This role option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(RoleFrequencyModal(self._role_name, action_name, self._parent_view.agent_config, self._parent_view, self._parent_view.author_id))
            return

        if self._role_name == "treasure_hunter" and action_name in {"poe2_item_add", "poe2_item_remove"}:
            # Allow POE2 item operations in DM
            from discord_bot.canvas.canvas_treasure_hunter import handle_canvas_treasure_action
            await handle_canvas_treasure_action(interaction, self._parent_view, action_name)
            return

        if self._role_name == "shaman" and action_name.startswith("runes_"):
            from discord_bot.canvas.canvas_shaman import _handle_canvas_runes_action
            await _handle_canvas_runes_action(interaction, action_name, self._parent_view)
            return

        # Default handler for other actions
        from discord_bot.canvas.content import _build_canvas_role_embed
        from discord_bot.canvas.ui import CanvasRoleDetailView

        role_embed = _build_canvas_role_embed(
            self._role_name,
            action_name,
            self._parent_view.admin_visible,
            self._detail_name,
            self._parent_view.agent_config,
            f"Selected {action_name}"
        )

        base_view = CanvasRoleDetailView(
            author_id=self._parent_view.author_id,
            role_name=self._role_name,
            agent_config=self._parent_view.agent_config,
            admin_visible=self._parent_view.admin_visible,
            sections=self._parent_view.sections,
            current_detail=self._detail_name,
            guild=self._parent_view.guild,
            previous_view=self._parent_view,
        )
        base_view.auto_response_preview = self._parent_view.auto_response_preview

        try:
            await interaction.response.edit_message(content=None, embed=role_embed, view=base_view)
        except discord.InteractionResponded:
            await interaction.followup.edit_message(interaction.message.id, embed=role_embed, view=base_view)
        except discord.NotFound:
            try:
                await interaction.followup.send(embed=role_embed, view=base_view, ephemeral=True)
            except discord.NotFound:
                pass


class RunesPageNavButton(discord.ui.Button):
    """Button for navigating between runes pages."""

    def __init__(self, target_page: int, label: str, row: int):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=row)
        self.target_page = target_page

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        parent_view = view._parent

        # Get runes page data for the target page
        try:
            from roles.shaman.api import get_runes_page_data, get_message
            server_id = get_server_key(parent_view.guild) if parent_view.guild else None

            runes_page_data = get_runes_page_data(self.target_page, server_id)
            content = get_message("runes_list_content", self.target_page, server_id)

            from .content import _build_canvas_role_embed
            from discord_bot.canvas.ui import CanvasRoleDetailView

            role_embed = _build_canvas_role_embed("shaman", content, parent_view.admin_visible, "runes", None, f"Viewed runes page {self.target_page}")
            role_embed.title = ""  # Force empty title since content already includes the page title

            # Create new base view with target page
            base_view = CanvasRoleDetailView(
                author_id=parent_view.author_id,
                role_name=parent_view.role_name,
                agent_config=parent_view.agent_config,
                admin_visible=parent_view.admin_visible,
                sections=parent_view.sections,
                current_detail="runes",
                guild=parent_view.guild,
                previous_view=parent_view.previous_view,
            )
            base_view.auto_response_preview = f"Viewed runes page {self.target_page}"

            # Wrap with RunesPageView for the target page
            next_view = RunesPageView(base_view, runes_page_data, self.target_page)

            await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)
            logger.info(f"✅ RunesPageNavButton navigated to runes page {self.target_page}")
        except Exception as e:
            logger.exception(f"RunesPageNavButton failed: {e}")
            await interaction.response.send_message("❌ Error al navegar a la página de runas.", ephemeral=True)


class RunesPageBackButton(discord.ui.Button):
    """Custom back button for runes pages that navigates to runes overview instead of shaman overview."""

    def __init__(self, row=4, label="Back"):
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=row)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        parent_view = view._parent

        # Navigate to runes overview using the standard canvas navigation
        # This rebuilds the runes detail view (overview) for the shaman role
        from .ui import _build_canvas_role_detail_view
        from .content import _build_canvas_role_embed

        try:
            content = _build_canvas_role_detail_view(
                parent_view.role_name,
                "runes",
                parent_view.agent_config,
                parent_view.admin_visible,
                parent_view.guild,
                parent_view.author_id,
            )
            role_embed = _build_canvas_role_embed(
                parent_view.role_name,
                content,
                parent_view.admin_visible,
                "runes",
                None,
                "Viewed runes overview"
            )
            # Force empty title to avoid extra "shaman //" title
            role_embed.title = ""

            # Create a new CanvasRoleDetailView for runes overview
            from .ui import CanvasRoleDetailView
            next_view = CanvasRoleDetailView(
                author_id=parent_view.author_id,
                role_name=parent_view.role_name,
                agent_config=parent_view.agent_config,
                admin_visible=parent_view.admin_visible,
                sections=parent_view.sections,
                current_detail="runes",
                guild=parent_view.guild,
                previous_view=parent_view.previous_view,
            )
            next_view.current_embed = role_embed

            await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)
            logger.info("✅ RunesPageBackButton navigated to runes overview")
        except Exception as e:
            logger.exception(f"RunesPageBackButton failed: {e}")
            await interaction.response.send_message("❌ Error al navegar al overview de runes.", ephemeral=True)


class RunesPageView(discord.ui.View):
    """A View that wraps a CanvasRoleDetailView and adds one button per rune on the page."""

    def __init__(self, parent_view, runes_page_data: list, page: int = 1):
        super().__init__(timeout=parent_view.timeout if hasattr(parent_view, 'timeout') else 600)
        self._parent = parent_view
        self.page = page

        # Load navigation labels from server-specific shaman.json with fallback
        try:
            from roles.shaman.api import get_message, ENGLISH_MESSAGES
            server_id = get_server_key(parent_view.guild) if parent_view.guild else None

            nav_page = get_message('nav_page', server_id=server_id) or ENGLISH_MESSAGES.get('nav_page', "Page")
        except Exception:
            # Fallback to English if loading fails
            nav_page = "Page"

        # Add rune buttons in rows 0-1 (max 5 per row)
        num_runes = min(len(runes_page_data), 10)
        for idx, rune_data in enumerate(runes_page_data[:10]):  # max 10 buttons
            self.add_item(RuneDetailButton(rune_data, row=idx // 5))

        # Add page navigation buttons at the end of row 1 (after rune buttons)
        # Calculate position based on how many rune buttons are in row 1
        row_1_rune_count = max(0, num_runes - 5)  # runes in row 1 (after first 5)
        if row_1_rune_count < 5:  # Only add if there's space
            if page == 1:
                self.add_item(RunesPageNavButton(2, f"{nav_page} 2 ▶", row=1))
            elif page == 2:
                if row_1_rune_count <= 3:  # Need space for 2 buttons
                    self.add_item(RunesPageNavButton(1, f"◀ {nav_page} 1", row=1))
                    self.add_item(RunesPageNavButton(3, f"{nav_page} 3 ▶", row=1))
            elif page == 3:
                self.add_item(RunesPageNavButton(2, f"◀ {nav_page} 2", row=1))

        # Add action dropdown that delegates to parent view (row 2)
        self.add_item(RunesPageActionSelect(parent_view))

        # Copy navigation items from parent view, but replace back button with custom one
        from .ui import CanvasSmartBackButton
        for item in parent_view.children:
            # Skip the standard back button and add our custom one
            if hasattr(item, 'row') and item.row is not None and item.row >= 3:
                if isinstance(item, CanvasSmartBackButton):
                    # Replace with custom back button
                    self.add_item(RunesPageBackButton(row=item.row, label=item.label))
                else:
                    self.add_item(item)

    # Delegate attribute access for author_id, guild, etc. to the parent view
    def __getattr__(self, name):
        return getattr(self._parent, name)


async def _handle_canvas_runes_action(interaction: discord.Interaction, action_name: str, view) -> None:
    """Handle Nordic runes info/history actions with dynamic content."""
    try:
        try:
            from roles.shaman.api import get_message
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
        runes_page_data = []  # structured data for rune detail buttons

        _PAGE_ACTIONS = {
            "runes_runes_1": 1,
            "runes_runes_2": 2,
            "runes_runes_3": 3,
            "runes_runes":   1,
        }

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
        elif action_name in _PAGE_ACTIONS:
            page = _PAGE_ACTIONS[action_name]
            try:
                from roles.shaman.api import get_runes_page_data
                content_parts.append(get_message("runes_list_content", page, server_id))
                runes_page_data = get_runes_page_data(page, server_id)
            except Exception as e:
                logger.exception(f"Canvas runes list page {page} failed: {e}")
                content_parts.extend([f"🔮 **ELDER FUTHARK RUNES {page}** 🔮", f"❌ **ERROR!** Could not load runes list page {page}."])
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

        # Page-specific title for runes list pages and types (content already includes title)
        if action_name in _PAGE_ACTIONS or action_name == "runes_types":
            runes_title = None
        else:
            runes_title = _runes_desc.get("title", "🔮 **Nordic Runes Ancient Wisdom** 🔮")

        role_embed = _build_canvas_role_embed("shaman", content, view.admin_visible, "runes", None, f"Viewed {action_name.replace('runes_', '').title()}")
        # For runes pages, force empty title since content already includes the page title
        if action_name in _PAGE_ACTIONS:
            role_embed.title = ""
        elif runes_title:
            role_embed.title = runes_title
        view.current_embed = role_embed

        base_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail="runes",
            guild=view.guild,
            previous_view=view,
        )
        base_view.auto_response_preview = f"Viewed {action_name.replace('runes_', '').title()}"

        # Wrap with rune buttons only for list pages
        if runes_page_data:
            next_view = RunesPageView(base_view, runes_page_data, page)
        else:
            next_view = base_view

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


async def _handle_canvas_astrology_action(interaction: discord.Interaction, action_name: str, view) -> None:
    """Handle astrology info/history actions with dynamic content."""
    try:
        guild = interaction.guild
        from .content import _get_personality_descriptions
        server_id = get_server_key(guild) if guild else None
        _astrology_desc = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("shaman", {}).get("astrology", {})

        from roles.shaman.subroles.astrology.astrology_db import get_astrology_db_instance
        db = get_astrology_db_instance()

        content_parts = []

        if action_name == "astrology_history":
            try:
                title_history = _astrology_desc.get("history", "📓 **ASTROLOGY READING HISTORY** 📓")
                user_id = str(interaction.user.id)
                readings = db.get_astrology_readings(user_id, limit=10)
                stats = db.get_astrology_stats(user_id)

                if not readings:
                    content_parts.append(title_history)
                    content_parts.append(_astrology_desc.get("history_empty", "No previous readings."))
                else:
                    content_parts.append(title_history)
                    content_parts.append("-" * 45)
                    for reading in readings:
                        content_parts.append(f"**ID {reading.get('created_at', '')[:10]}** - {reading.get('reading_type', 'Unknown')}")
                        content_parts.append(f"Question: {reading.get('question', 'N/A')}")
                        content_parts.append("")
                    content_parts.append(stats)
            except Exception as e:
                logger.exception(f"Canvas astrology history failed: {e}")
                content_parts.extend(["📓 **ASTROLOGY READING HISTORY**", "❌ **ERROR!** Could not load your astrology history."])
        elif action_name == "astrology_letters":
            try:
                from roles.shaman.subroles.astrology.astrology_messages import get_letter_translations
                letter_translations = get_letter_translations(server_id)
                title_letters = _astrology_desc.get("letters_title", "📜 THE 22 HEBREW LETTERS 📜")
                content_parts.append(title_letters)
                content_parts.append("-" * 45)

                # Mother letters
                content_parts.append("**Mother Letters (3):**")
                for letter in ["alef", "mem", "shin"]:
                    info = letter_translations.get(letter, {})
                    content_parts.append(f"• {letter.title()}: {info.get('meaning', letter)}")

                # Double letters
                content_parts.append("\n**Double Letters (7):**")
                for letter in ["bet", "gimel", "dalet", "kaf", "pe", "resh", "tav"]:
                    info = letter_translations.get(letter, {})
                    content_parts.append(f"• {letter.title()}: {info.get('meaning', letter)}")

                # Simple letters
                content_parts.append("\n**Simple Letters (12):**")
                for letter in ["he", "vav", "zayin", "jet", "tet", "yod", "lamed", "nun", "samej", "ayin", "tzadi", "kof"]:
                    info = letter_translations.get(letter, {})
                    content_parts.append(f"• {letter.title()}: {info.get('meaning', letter)}")

            except Exception as e:
                logger.exception(f"Canvas astrology letters failed: {e}")
                content_parts.extend(["📜 **THE 22 HEBREW LETTERS**", "❌ **ERROR!** Could not load letters list."])

        content = "\n".join(content_parts)
        from .content import _build_canvas_role_embed
        from discord_bot.canvas.ui import CanvasRoleDetailView

        role_embed = _build_canvas_role_embed("shaman", content, view.admin_visible, "astrology", None, f"Viewed {action_name.replace('astrology_', '').title()}")
        view.current_embed = role_embed

        base_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail="astrology",
            guild=view.guild,
            previous_view=view,
        )
        base_view.auto_response_preview = f"Viewed {action_name.replace('astrology_', '').title()}"

        try:
            await interaction.response.edit_message(content=None, embed=role_embed, view=base_view)
        except discord.InteractionResponded:
            await interaction.followup.edit_message(interaction.message.id, embed=role_embed, view=base_view)
        except discord.NotFound:
            try:
                await interaction.followup.send(embed=role_embed, view=base_view, ephemeral=True)
            except discord.NotFound:
                logger.debug("Canvas astrology interaction expired completely")
        except Exception as e:
            logger.exception(f"Failed to edit canvas astrology message: {e}")
            try:
                await interaction.followup.send("❌ Error al actualizar vista. Por favor intenta de nuevo.", ephemeral=True)
            except discord.NotFound:
                logger.warning("Canvas astrology interaction expired during error handling")

    except Exception as e:
        logger.exception(f"Unexpected error in Canvas shaman astrology action: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)
        else:
            try:
                await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)
            except discord.NotFound:
                logger.warning("Canvas shaman interaction expired during error handling")
