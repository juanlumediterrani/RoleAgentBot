"""Canvas content builders and render helpers."""

from discord_bot import discord_core_commands as core
from roles import news_watcher
from .canvas_news_watcher import _get_nw_descriptions

# Dynamic descriptions loading function
def _get_personality_descriptions(server_id: str = None) -> dict:
    """
    Get personality descriptions from server-specific or global directory.
    
    Args:
        server_id: Discord server ID for server-specific descriptions
        
    Returns:
        dict: Personality descriptions loaded from descriptions.json and subdirectory
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
            data = {}
            # Load descriptions.json if it exists
            descriptions_path = server_path / "descriptions.json"
            if descriptions_path.exists():
                with open(descriptions_path, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    # Load from "discord" key, but also check for direct structure
                    if "discord" in loaded_data:
                        data = loaded_data["discord"]
                    else:
                        # If no "discord" key, use the whole data
                        data = loaded_data
            # Always merge sub-role description files from descriptions/ subdirectory
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
                    except Exception as e:
                        logger.error(f"Failed to load {sub_file}: {e}")
            return data
    except Exception as e:
        if logger:
            logger.debug(f"Could not load descriptions for server {server_id}: {e}")
    return {}

def _get_server_personality_name(server_id: str = None) -> str:
    """Get the personality name for a specific server."""
    if not server_id:
        return "bot"
    try:
        from agent_engine import _get_personality
        return _get_personality(server_id).get("name", "bot")
    except Exception:
        return "bot"

os = core.os
asyncio = core.asyncio
discord = core.discord
Path = core.Path
AgentDatabase = core.AgentDatabase
logger = core.logger
PERSONALITY = core.PERSONALITY
from agent_mind import call_llm
AGENT_CFG = core.AGENT_CFG

from discord_bot.discord_utils import (
    get_db_for_server,
    send_dm_or_channel, send_embed_dm_or_channel,
    is_admin, 
    get_greeting_enabled, set_greeting_enabled,
    check_chat_rate_limit, is_already_initialized, mark_as_initialized,
    acquire_connection_lock, acquire_process_lock,
    get_server_key, set_role_enabled, is_role_enabled_check,
)
get_news_watcher_db_instance = core.get_news_watcher_db_instance if hasattr(core, 'get_news_watcher_db_instance') and core.get_news_watcher_db_instance is not None else None

try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None
get_poe2_manager = core.get_poe2_manager
get_banker_db_instance = None  # Now using roles_db directly
_discord_cfg = core._discord_cfg
_personality_name = core._personality_name
_insult_cfg = core._insult_cfg
_personality_answers = core._personality_answers
_talk_state_by_guild_id = core._talk_state_by_guild_id
_taboo_state_by_guild_id = core._taboo_state_by_guild_id
get_taboo_state = core.get_taboo_state
update_taboo_state = core.update_taboo_state
is_taboo_triggered = core.is_taboo_triggered

from .state import (
    _get_canvas_watcher_method_label,
    _get_canvas_watcher_frequency_hours,
    _get_canvas_dice_state,
    _get_canvas_dice_ranking,
    _get_canvas_dice_history,
    _get_canvas_beggar_state,
    _get_canvas_poe2_state,
    _get_enabled_roles,
    _load_role_mission_prompts,
)
from .canvas_news_watcher import (
    build_canvas_role_news_watcher,
    build_canvas_role_news_watcher_detail,
)
from .canvas_treasure_hunter import (
    build_canvas_role_treasure_hunter,
    build_canvas_role_treasure_hunter_detail,
    handle_canvas_treasure_hunter_action,
)
from .canvas_banker import (
    build_canvas_role_banker,
    build_canvas_role_banker_detail,
)
from .canvas_mc import build_canvas_role_mc
from .canvas_trickster import (
    build_canvas_role_trickster,
    build_canvas_role_trickster_detail,
)
from .canvas_shaman import (
    build_canvas_role_shaman,
    build_canvas_role_shaman_detail,
    get_moon_phase,
)
from .canvas_juggler import (
    build_canvas_role_juggler,
    build_canvas_role_juggler_detail,
)
from .canvas_scholar import (
    build_canvas_role_scholar,
    build_canvas_role_scholar_detail,
)
from .canvas_behavior import (
    build_canvas_behavior,
)


def _build_canvas_setup_not_available() -> str:
    """Build message for when setup is only available to administrators."""
    return "❌ This setup is only available to administrators."

def _build_canvas_sections(agent_config: dict, greet_name: str, nogreet_name: str, welcome_name: str, nowelcome_name: str,
                           role_cmd_name: str, talk_cmd_name: str, admin_visible: bool, server_id: str = "default",
                           author_id: int = 0, guild=None, is_dm: bool = False) -> dict[str, str]:
    """Build the top-level Canvas sections for the current user context."""
    # Get behavior tuple and store separately for title/description handling
    behavior_title, behavior_description, behavior_content = build_canvas_behavior(
        greet_name, nogreet_name, welcome_name, nowelcome_name, role_cmd_name, talk_cmd_name, admin_visible, guild
    )
    
    return {
        "home": _build_canvas_home(
            agent_config, greet_name, nogreet_name, welcome_name, nowelcome_name, role_cmd_name, talk_cmd_name,
            admin_visible, server_id, author_id, guild, is_dm
        ),
        "behavior": behavior_content,
        "behavior_title": behavior_title,
        "behavior_description": behavior_description,
        "roles": _build_canvas_roles(agent_config, admin_visible, guild, page=1, roles_per_page=5),
        "personal": _build_canvas_personal(),
        "help": _build_canvas_help(guild),
    }


def _build_canvas_embed(section_name: str, content: str, admin_visible: bool, title: str | None = None, description: str | None = None, server_id: str = None) -> discord.Embed:
    # Get title from personality descriptions for consistency
    personality_descriptions = _get_personality_descriptions(server_id)

    help_title = personality_descriptions.get("help_menu", {}).get("title", "📚 Canvas - Help & Troubleshooting")

    if section_name == "behavior":
        # Use provided title/description or fall back to personality descriptions
        if title is None:
            behavior_descriptions = personality_descriptions.get("behavior_messages", {})
            behavior_title = behavior_descriptions.get("canvas_conversation_title", "💬 General Behavior")
        else:
            behavior_title = title

        # Get home title from descriptions.json
        canvas_home_messages = personality_descriptions.get("canvas_home_messages", {})
        home_title = canvas_home_messages.get("title", "🧭 Canvas Hub")

        titles = {
            "home": home_title,
            "behavior": behavior_title,
            "roles": None,  # Will be set from content
            "personal": "👤 Canvas - Personal Space",
            "help": help_title,
        }
    else:
        # Get home title from descriptions.json
        canvas_home_messages = personality_descriptions.get("canvas_home_messages", {})
        home_title = canvas_home_messages.get("title", "🧭 Canvas Hub")

        titles = {
            "home": home_title,
            "behavior": "⚙️ Canvas - General Behavior",
            "roles": None,  # Will be set from content
            "personal": "👤 Canvas - Personal Space",
            "help": help_title,
        }
    
    # Replace placeholders in all titles
    for key in titles:
        if titles[key]:
            pass  # Placeholder replacement removed
    colors = {
        "home": discord.Color.blurple(),
        "behavior": discord.Color.orange(),
        "roles": discord.Color.purple(),
        "personal": discord.Color.teal(),
        "help": discord.Color.gold(),
    }
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    description = ""
    
    # Extract title from content for roles section
    if section_name == "roles" and lines:
        # The first line should be the title from _build_canvas_roles
        first_line = lines[0]
        if first_line and not first_line.startswith("**"):
            titles["roles"] = first_line

    home_description_text = ""
    roles_description_text = ""
    if section_name == "home":
        home_description_text = lines[0] if lines else ""
        description = home_description_text
    elif section_name == "home_status":
        personality_line = next((line for line in lines if line.startswith("**Personality:**")), "")
        roles_line = next((line for line in lines if line.startswith("**Active roles:**")), "")
        description_parts = [part for part in [personality_line, roles_line] if part]
        description = "\n".join(description_parts)
    elif section_name == "roles":
        roles_description_text = lines[1] if len(lines) > 1 else ""
        description = roles_description_text

    elif section_name == "personal":
        description = "Focus on private or user-specific workflows that continue naturally in DM."
    elif section_name == "help":
        description = personality_descriptions.get("help_menu", {}).get("description", "Find command entry points, troubleshooting hints, and the fastest recovery paths.")
    elif section_name == "behavior":
        description = description or "Shared bot behavior that sits above any individual role."

    # Fallback title if none was extracted
    if titles.get(section_name) is None:
        titles[section_name] = "Canvas"
        titles[section_name] = titles[section_name]
    # Get final title with placeholder replacement
    final_title = titles.get(section_name, "Canvas")
    final_title = final_title
    embed = discord.Embed(
        title=final_title,
        description=description[:4096],
        color=colors.get(section_name, discord.Color.blurple()),
    )
    blocks = _split_canvas_blocks(content)
    # Discord allows up to 25 fields per embed; keep a safe margin
    visible_blocks = blocks[:20]
    last_block_index = len(visible_blocks) - 1
    
    for index, (block_title, block_lines) in enumerate(visible_blocks):
        filtered_lines = [
            line for line in block_lines
            if not (section_name in {"home", "home_status"} and (line.startswith("**Personality:**") or line.startswith("**Active roles:**")))
            and not (section_name == "roles" and index == 0 and block_lines and line == titles.get("roles"))
            and not (section_name == "roles" and index == 0 and line == roles_description_text)  # Filter out description that's now in embed.description
            and not (section_name == "home" and index == 0 and line == home_description_text)  # Filter out home description to prevent duplication
        ]
        value = "\n".join(filtered_lines)[:1024]
        if not value:
            continue
        # If the block has no title on home/roles/help, merge it into the embed description
        # to avoid Discord rendering a phantom blank line from the zero-width field name.
        if not block_title and section_name in {"home", "roles", "help"}:
            merged = (embed.description + "\n" + value) if embed.description else value
            embed.description = merged[:4096]
            continue
        # Use block_title as field name, not as part of the value
        field_name = block_title if block_title and block_title != "\u200b" else "\u200b"
        embed.add_field(name=field_name, value=value, inline=False)
    # Remove footer to prevent truncation issues
    return embed


def _split_canvas_blocks(content: str) -> list[tuple[str, list[str]]]:
    """Split Canvas plain text into titled blocks for embed rendering."""
    blocks: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("**") and line.endswith("**") and len(line) > 4:
            if current_lines:
                blocks.append((current_title, current_lines))
            # Only strip leading/trailing **, not internal ones
            current_title = line[2:-2]
            current_lines = []
            continue
        current_lines.append(line)

    if current_lines:
        blocks.append((current_title, current_lines))
    return blocks



def _build_canvas_role_embed(role_name: str, content: str, admin_visible: bool, surface_name: str = "overview", user=None,
                             auto_response: str | None = None, server_id: str = None) -> discord.Embed:
    """Render a role/detail Canvas screen with a role-specific embed layout."""
    personality_descriptions = _get_personality_descriptions(server_id)
    role_descriptions = personality_descriptions.get("role_descriptions", {})

    def _get_embed_role_title(role_key: str, detail_key: str = None) -> str:
        """Get role title from merged role_descriptions or fallback to key.
        If detail_key is provided, tries to get subrole title first."""
        try:
            # Try to get subrole title first if detail_key provided
            if detail_key:
                subrole_title = role_descriptions.get(role_key, {}).get(detail_key, {}).get("title", "")
                if subrole_title:
                    return subrole_title.strip()
            # Fall back to main role title
            title = role_descriptions.get(role_key, {}).get("title", "")
            return title.strip() if title else role_key
        except Exception:
            return role_key
    
    # Use surface_name as detail_key for subrole titles
    # For admin views like "beggar_admin", use the base subrole key "beggar"
    # Map canvas surface names to JSON keys where they differ
    _surface_to_json_key = {
        "dice": "dice_game",
        "dice_admin": "dice_game",
        "runes": "nordic_runes",
        "runes_admin": "nordic_runes",
        "league": "poe2",
        "poe2": "poe2",
        "items": "poe2",
        "personal": "poe2",
    }
    # For treasure_hunter, admin view should use main title, not a subrole title
    # For shaman runes detail, use None to prevent title duplication with content
    if surface_name == "admin" and role_name == "treasure_hunter":
        detail_key = None
    elif role_name == "shaman" and surface_name == "runes":
        detail_key = None
    elif surface_name and surface_name not in {"overview", "admin"}:
        base = surface_name.replace("_admin", "")
        detail_key = _surface_to_json_key.get(surface_name, _surface_to_json_key.get(base, base))
    else:
        detail_key = None
    
    role_titles = {
        "news_watcher": _get_embed_role_title("news_watcher", detail_key),
        "treasure_hunter": _get_embed_role_title("treasure_hunter", detail_key),
        "trickster": _get_embed_role_title("trickster", detail_key),
        "banker": _get_embed_role_title("banker", detail_key),
        "mc": _get_embed_role_title("mc", detail_key),
        "shaman": _get_embed_role_title("shaman", detail_key),
        "juggler": _get_embed_role_title("juggler", detail_key),
        "scholar": _get_embed_role_title("scholar", detail_key),
    }
    title = role_titles.get(role_name, "Canvas")
    # Override title for shaman runes detail to prevent parent title from appearing
    if role_name == "shaman" and surface_name == "runes":
        title = ""
    blocks = _split_canvas_blocks(content)
    role_colors = {
        "news_watcher": discord.Color.blue(),
        "treasure_hunter": discord.Color.dark_gold(),
        "trickster": discord.Color.magenta(),
        "banker": discord.Color.green(),
        "mc": discord.Color.purple(),
        "shaman": discord.Color.dark_purple(),
        "juggler": discord.Color.orange(),
        "scholar": discord.Color.teal(),
    }
     
    # Extract first block's content as description to avoid extra space between title and fields
    description = ""
    blocks_to_process = blocks[:4]
    # Skip description extraction for shaman runes to prevent title duplication
    if not (role_name == "shaman" and surface_name == "runes"):
        if blocks_to_process and blocks_to_process[0][1]:
            # Use the first line of the first block's content as description
            first_block_lines = blocks_to_process[0][1]
            if first_block_lines:
                description = first_block_lines[0]
                # Remove it from the block to avoid duplication
                blocks_to_process[0] = (blocks_to_process[0][0], first_block_lines[1:])

    embed = discord.Embed(
        title=title,
        description=description,
        color=role_colors.get(role_name, discord.Color.blurple()),
    )

    last_block_index = len(blocks_to_process) - 1
    for index, (block_title, block_lines) in enumerate(blocks_to_process):
        value = _merge_canvas_block_with_auto_response(block_lines, auto_response, role_name, surface_name) if index == last_block_index else _truncate_canvas_field_value("\n".join(block_lines))
        if value:
            embed.add_field(name=block_title, value=value, inline=False)

    footer_title = role_titles.get(role_name, role_name)
    embed.set_footer(text=f"{footer_title} • {'admin' if admin_visible else 'user'} view")
    
    # Add user thumbnail for banker role (like !banker balance)
    if role_name == "banker" and user and hasattr(user, 'display_avatar'):
        embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)
    
    return embed


def _truncate_canvas_field_value(value: str, limit: int = 1024) -> str:
    value = (value or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _merge_canvas_block_with_auto_response(block_lines: list[str], auto_response: str | None, role_name: str | None = None, surface_name: str | None = None) -> str:
    base_value = "\n".join(block_lines).strip()
    response_value = (auto_response or "").strip()
    if not response_value:
        return _truncate_canvas_field_value(base_value)
    
    # Skip Automatic Response header for shaman runes pages
    if role_name == "shaman" and surface_name and surface_name.startswith("runes_page"):
        merged = "\n".join([
            base_value,
            "",
            response_value,
        ]).strip()
    else:
        merged = "\n".join([
            base_value,
            "",
            "**Automatic Response**",
            response_value,
        ]).strip()
    return _truncate_canvas_field_value(merged)

#Default english fallback for modals
def _get_canvas_auto_response_preview(role_name: str | None = None, action_name: str | None = None) -> str | None:
    if not action_name:
        return None

    role_action_map: dict[str, dict[str, str]] = {
        "news_watcher": {
            "method_flat": "Watcher method set to `flat`.",
            "method_keyword": "Watcher method set to `keyword`.",
            "method_general": "Watcher method set to `general`.",
            "list_categories": "Showing the available watcher categories.",
            "list_feeds": "Showing the available watcher feeds.",
            "list_keywords": "Showing your configured watcher keywords.",
            "list_premises": "Showing your configured watcher premises.",
            "subscribe_categories": "The bot will ask for category details and create the watcher subscription after you confirm the modal.",
            "add_keywords": "The bot will ask for the keyword text and append it to your watcher filters.",
            "delete_keywords": "The bot will ask which keyword to remove from your watcher filters.",
            "add_premises": "The bot will ask for the premise text and store it for AI-based watcher filtering.",
            "delete_premises": "The bot will ask which premise to remove from your watcher configuration.",
            "channel_subscribe_categories": "The bot will ask for channel subscription details and publish future watcher alerts in this channel.",
            "channel_view_subscriptions": "Showing the current watcher channel subscriptions for this server.",
            "channel_unsubscribe": "The bot will ask for the subscription number to remove from this channel.",
            "watcher_frequency": "The bot will ask for the watcher frequency in hours and apply it server-wide.",
            "watcher_run_now": "The watcher will run immediately and publish any matching notifications.",
            "watcher_run_personal": "The watcher will run immediately for personal subscriptions and send notifications to users.",
        },
        "treasure_hunter": {
            "poe2_item_add": "The bot will ask for an item name and add it to your tracked POE2 objectives.",
            "poe2_item_remove": "The bot will ask for an item name or visible number and remove it from your tracked objectives.",
            "league_standard": "League updated to `Standard`.",
            "league_fate_of_the_vaal": "League updated to `Fate of the Vaal`.",
            "league_hardcore": "League updated to `Hardcore`.",
            "poe2_on": "POE2 subrole enabled for this server.",
            "poe2_off": "POE2 subrole disabled for this server.",
        },
        "trickster": {
            "dice_play": "The bot will roll the dice for you and post the result.",
            "dice_ranking": "Showing the current dice ranking for this server.",
            "dice_history": "Showing the most recent dice results.",
            "dice_help": "Showing the dice help and rules.",
            "runes_single": "Cast a single rune for quick guidance on your question.",
            "runes_three": "Cast three runes for past, present, and future guidance.",
            "runes_cross": "Cast five runes in a cross pattern for comprehensive insight.",
            "runes_runic_cross": "Cast seven runes in a runic cross pattern for spiritual guidance.",
            "runes_history": "Show your recent rune casting history.",
            "runes_types": "Show available rune reading types and descriptions.",
            "runes_runes_1": "Show all runes with descriptions - Page 1 (Fehu to Gebo)",
            "runes_runes_2": "Show all runes with descriptions - Page 2 (Wunjo to Perthro)",
            "runes_runes_3": "Show all runes with descriptions - Page 3 (Algiz to Othala)",
            "announcements_on": "Dice announcements enabled for this server.",
            "announcements_off": "Dice announcements disabled for this server.",
            "dice_fixed_bet": "The bot will ask for the fixed bet amount and update the dice game configuration.",
            "dice_pot_value": "The bot will ask for the new pot value and update the dice game balance.",
            "beggar_donate": "The bot will ask for the donation amount and transfer gold from your wallet.",
            "beggar_on": "Beggar enabled for this server.",
            "beggar_off": "Beggar disabled for this server.",
            "beggar_frequency": "The bot will ask for the beggar frequency in hours and update the schedule.",
            "runes_on": "Nordic Runes subrole enabled for this server.",
            "runes_off": "Nordic Runes subrole disabled for this server.",
        },
        "banker": {
            "config_tae": "The bot will ask for the daily TAE value and update the banker configuration.",
            "config_bonus": "The bot will ask for the opening bonus value and update the banker configuration.",
        },
        "mc": {
            "mc_play": "The bot will ask for a song or query and start playback.",
            "mc_add": "The bot will ask for a song or query and add it to the queue.",
            "mc_skip": "The bot will skip the current song.",
            "mc_pause": "Playback paused.",
            "mc_resume": "Playback resumed.",
            "mc_stop": "Playback stopped and the queue cleared.",
            "mc_queue": "Showing the current queue.",
            "mc_remove_last": "Remove the last song added to the queue.",
            "mc_clear": "Queue cleared.",
            "mc_history": "Showing recent playback history.",
            "mc_volume": "The bot will ask for a new volume value.",
        },
        "scholar": {
            "scholar_on": "Scholar role enabled for this server.",
            "scholar_off": "Scholar role disabled for this server.",
        },
    }
    behavior_action_map = {
        "greetings_on": "Presence greetings enabled for this server.",
        "greetings_off": "Presence greetings disabled for this server.",
        "welcome_on": "Welcome messages enabled for this server.",
        "welcome_off": "Welcome messages disabled for this server.",
        "memory_long": "Showing long-term memory (daily analysis).",
        "memory_recent": "Showing recent short-term memory.",
        "memory_relationship": "Showing relationship memory with users.",
        "taboo_on": "Taboo enabled for this server.",
        "taboo_off": "Taboo disabled for this server.",
        "taboo_add": "The bot will ask for a keyword and add it to the taboo list.",
        "taboo_del": "The bot will ask for a keyword and remove it from the taboo list.",
        "settings_open": "The bot will open server settings to manage language and role activation.",
        "personality_open": "The bot will open the personality management interface.",
    }

    if role_name:
        return role_action_map.get(role_name, {}).get(action_name)
    return behavior_action_map.get(action_name)


def _build_canvas_behavior_embed(content: str, admin_visible: bool, auto_response: str | None = None, title: str | None = None, description: str | None = None) -> discord.Embed:
    """Render a General Behavior Canvas screen with a specific embed layout."""
    # Use provided title/description or fall back to extracting from content
    if title is None:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        title_line = lines[0] if lines else "Canvas - General Behavior"
        title = title_line
    else:
        title = title

    embed = discord.Embed(
        title=title,
        description=description or "",
        color=discord.Color.orange() if admin_visible else discord.Color.dark_orange(),
    )
    blocks = _split_canvas_blocks(content)
    # Discord allows up to 25 fields per embed; keep a safe margin
    visible_blocks = blocks[:20]
    last_block_index = len(visible_blocks) - 1
    for index, (block_title, block_lines) in enumerate(visible_blocks):
        value = _merge_canvas_block_with_auto_response(block_lines, auto_response, None, None) if index == last_block_index else _truncate_canvas_field_value("\n".join(block_lines))
        if value:
            embed.add_field(name=block_title, value=value, inline=False)
    embed.set_footer(text=f"General Behavior • {'admin' if admin_visible else 'user'} view")
    return embed

def _get_canvas_role_detail_items(role_name: str, current_detail: str | None, admin_visible: bool, label: str, server_id: str = None, agent_config: dict = None) -> list[tuple[str, str]]:
    trickster_personal_map = {
        "dice": "dice",
        "dice_admin": "dice",
    }
    trickster_admin_map = {
        "dice": "dice_admin",
        "dice_admin": "dice_admin",
    }
    personality_descriptions = _get_personality_descriptions(server_id)
    general = personality_descriptions.get("general", {})
    
    # Helper function to resolve general.button references
    def _resolve_button_label(label_text: str) -> str:
        if label_text and label_text.startswith("general.button_"):
            parts = label_text.split(".", 2)
            key = parts[2] if len(parts) >= 3 else label_text
            return general.get(f"button_{key}", label_text)
        return label_text
    
    # Get button labels from general section
    button_personal = general.get("button_personal", "👤 Personal")
    button_admin = general.get("button_admin", "🔧 Admin")
    
    # Check if treasure_hunter is enabled globally in agent_config
    th_global_enabled = (agent_config or {}).get("roles", {}).get("treasure_hunter", {}).get("enabled", False)
    
    items_map: dict[str, list[tuple[str, str]]] = {
        "news_watcher": [
            (button_personal, "overview"),
        ] + ([(_resolve_button_label(general.get("button_admin", "Admin")), "admin")] if admin_visible else []),
        "treasure_hunter": [],  # POE2 button added separately with emoticon only if th_global_enabled
        "trickster": (
            # Regular subrole views
            [(button_personal, trickster_personal_map.get(current_detail or "dice", "dice"))]
            + ([(_resolve_button_label(general.get("button_admin", "Admin")), trickster_admin_map.get(current_detail or "dice", "dice_admin"))] if admin_visible else [])
        ) if current_detail in {"dice"} else (
            # Admin views
            [(button_personal, trickster_personal_map.get(current_detail or "dice", "dice"))]
            + ([(_resolve_button_label(general.get("button_admin", "Admin")), trickster_admin_map.get(current_detail or "dice", "dice_admin"))] if admin_visible else [])
        ) if current_detail in {"dice_admin"} else [
            # Main trickster overview - show all subroles
            (personality_descriptions.get("role_descriptions", {}).get("trickster", {}).get("subrole_buttons", {}).get("dice", "Dice"), "dice"),
        ] if current_detail not in {"dice", "dice_admin"} else [],
        "banker": [
            # Main banker overview - always show subrole buttons
            (personality_descriptions.get("role_descriptions", {}).get("banker", {}).get("subrole_buttons", {}).get("overview", "Overview"), "overview"),
            (personality_descriptions.get("role_descriptions", {}).get("banker", {}).get("subrole_buttons", {}).get("beggar", "Beggar"), "beggar"),
        ] + ([(_resolve_button_label(general.get("button_admin", "Admin")), "admin")] if admin_visible else []),
        "mc": [
            (personality_descriptions.get("role_descriptions", {}).get("mc", {}).get("subrole_buttons", {}).get("overview", button_personal), "overview"),
        ],
        "shaman": (
            [(button_personal, "runes")]
            + ([(_resolve_button_label(general.get("button_admin", "Admin")), "runes_admin")] if admin_visible else [])
        ) if current_detail in {"runes", "runes_admin"} else [
            (personality_descriptions.get("role_descriptions", {}).get("shaman", {}).get("subrole_buttons", {}).get("runes", "🔮 Runes"), "runes"),
        ] if current_detail not in {"runes", "runes_admin"} else [],
        "juggler": (
            [(button_personal, "ring")]
            + ([(_resolve_button_label(general.get("button_admin", "Admin")), "ring_admin")] if admin_visible else [])
        ) if current_detail in {"ring", "ring_admin"} else [
            (personality_descriptions.get("role_descriptions", {}).get("juggler", {}).get("subrole_buttons", {}).get("overview", "🤹 Vista"), "overview"),
            (personality_descriptions.get("role_descriptions", {}).get("juggler", {}).get("subrole_buttons", {}).get("ring", "👁️ Ring"), "ring"),
        ] if current_detail not in {"ring", "ring_admin"} else [],
        "scholar": (
            [(button_personal, "personal")]
            + ([(_resolve_button_label(general.get("button_admin", "Admin")), "admin")] if admin_visible else [])
        ) if current_detail in {"personal", "admin"} else [
            (button_personal, "personal"),
        ] + ([(_resolve_button_label(general.get("button_admin", "Admin")), "admin")] if admin_visible else []),
    }
    
    # Special handling for treasure_hunter POE2 views
    # Only show POE2 buttons if treasure_hunter is enabled globally in agent_config
    if role_name == "treasure_hunter" and current_detail in {"poe2", "league", "admin"}:
        if not th_global_enabled:
            return []  # POE2 not available if treasure_hunter disabled globally
        poe2_buttons = [
            (personality_descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("subrole_buttons", {}).get("items", "Items"), "poe2"),
            (personality_descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("subrole_buttons", {}).get("league", "League"), "league"),
        ]
        if admin_visible:
            admin_button = personality_descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("subrole_buttons", {}).get("admin", "Admin")
            poe2_buttons.append(
                (_resolve_button_label(admin_button), "admin")
            )
        return poe2_buttons
    
    # Special handling for treasure_hunter overview - return empty list (POE2 button added separately with emoticon in ui.py)
    # Only if treasure_hunter is enabled globally
    if role_name == "treasure_hunter":
        return []
    
    # Special handling for banker beggar views - show Personal/Admin navigation
    if role_name == "banker":
        if current_detail == "beggar":
            return [
                (button_personal, "beggar"),
                (_resolve_button_label(general.get("button_admin", "Admin")), "beggar_admin"),
            ]
        if current_detail == "beggar_admin":
            return [
                (button_personal, "beggar"),
                (_resolve_button_label(general.get("button_admin", "Admin")), "beggar_admin"),
            ]
        if current_detail in {"overview", "admin"}:
            return items_map.get(role_name, [])
    
    return items_map.get(role_name, [])


def _get_canvas_role_action_items_for_detail(role_name: str, detail_name: str, admin_visible: bool, agent_config: dict | None = None, server_id: str = None) -> list[tuple[str, str, str]]:
    if role_name == "news_watcher":
        # Get news_watcher descriptions for action items with robust fallbacks
        _personality_descriptions = _get_personality_descriptions(server_id)
        
        # Safe nested access with fallbacks
        roles_view = _personality_descriptions.get("role_descriptions", {})
        news_watcher = roles_view.get("news_watcher", {})
        
        # Now dropdown is directly in news_watcher, not nested under canvas
        news_descriptions = news_watcher.get("dropdown", {}) if isinstance(news_watcher, dict) else {}
        
        # Ensure news_descriptions is a dict
        if not isinstance(news_descriptions, dict):
            news_descriptions = {}
        
        def _news_text(key: str, fallback: str) -> str:
            value = news_descriptions.get(key)
            if value:
                value = str(value)
            return str(value).strip() if value else fallback
        
        if detail_name in {"personal", "overview"}:  # Same view for both
            return [
                (_news_text("method_flat", "Method: Flat"), "method_flat", _news_text("method_flat_description", "Set subscription method to flat"), "📰"),
                (_news_text("method_keyword", "Method: Keyword"), "method_keyword", _news_text("method_keyword_description", "Set subscription method to keyword"), "🔍"),
                (_news_text("method_general", "Method: General"), "method_general", _news_text("method_general_description", "Set subscription method to general"), "🤖"),
                (_news_text("list_premises", "List: Premises"), "list_premises", _news_text("list_premises_description", "View your configured premises"), "🤖"),
            ]
        if detail_name == "admin" and admin_visible:
            return [
                (_news_text("watcher_frequency", "Watcher: Frequency"), "watcher_frequency", _news_text("watcher_frequency_description", "Number input target"), "⏰"),
                (_news_text("watcher_run_now", "Watcher: Run Now"), "watcher_run_now", _news_text("watcher_run_now_description", "Action"), "🏃"),
            ]
        return []

    if role_name == "treasure_hunter":
        # Get treasure_hunter descriptions for action items with robust fallbacks
        _personality_descriptions = _get_personality_descriptions(server_id)
        
        # Safe nested access with fallbacks
        roles_view = _personality_descriptions.get("role_descriptions", {})
        treasure_hunter = roles_view.get("treasure_hunter", {})
        poe2 = treasure_hunter.get("poe2", {})
        
        # Use poe2.dropdown for the dropdown options
        hunter_descriptions = poe2.get("dropdown", {})
        
        # Ensure hunter_descriptions is a dict
        if not isinstance(hunter_descriptions, dict):
            hunter_descriptions = {}
        
        def _hunter_text(key: str, fallback: str) -> str:
            value = hunter_descriptions.get(key)
            if value:
                value = str(value)
            return str(value).strip() if value else fallback
        
        if detail_name == "league":
            return [
                (_hunter_text("league_standard", "League: Standard"), "league_standard", _hunter_text("league_standard_description", "Choose POE2 league"), "🏆"),
                (_hunter_text("league_fate_of_the_vaal", "League: Fate of the Vaal"), "league_fate_of_the_vaal", _hunter_text("league_fate_of_the_vaal_description", "Choose POE2 league"), "⚡"),
                (_hunter_text("league_hardcore", "League: Hardcore"), "league_hardcore", _hunter_text("league_hardcore_description", "Choose POE2 league"), "💀"),
            ]
        if detail_name in {"personal", "poe2", "items"}:
            return [
                (_hunter_text("poe2_item_add", "Items: Add"), "poe2_item_add", _hunter_text("poe2_item_add_description", "Add a new POE2 item"), "➕"),
                (_hunter_text("poe2_item_remove", "Items: Remove"), "poe2_item_remove", _hunter_text("poe2_item_remove_description", "Remove a tracked POE2 item"), "➖"),
                (_hunter_text("poe2_purchase_add", "Purchases: Record"), "poe2_purchase_add", _hunter_text("poe2_purchase_add_description", "Record a purchase for a tracked item"), "📝"),
                (_hunter_text("poe2_purchase_remove", "Purchases: Liquidate"), "poe2_purchase_remove", _hunter_text("poe2_purchase_remove_description", "Liquidate a recorded purchase"), "💰"),
            ]
        if detail_name == "admin" and admin_visible:
            # Admin only sees POE2 toggle (frequency is controlled from agent_config.json only)
            return [
                (_hunter_text("poe2_on", "POE2: On"), "poe2_on", _hunter_text("poe2_on_description", "Activate POE2 subrole"), "✅"),
                (_hunter_text("poe2_off", "POE2: Off"), "poe2_off", _hunter_text("poe2_off_description", "Deactivate POE2 subrole"), "❌"),
            ]
        # If no specific detail matched, return empty list for treasure_hunter
        return []

    if role_name == "trickster":
        # Get trickster descriptions for action items with robust fallbacks
        _personality_descriptions = _get_personality_descriptions(server_id)
        
        # Safe nested access with fallbacks
        roles_view = _personality_descriptions.get("role_descriptions", {})
        trickster = roles_view.get("trickster", {})
        
        # Initialize empty dropdown descriptions
        trickster_descriptions = {}
        
        # Collect dropdown items from relevant subroles based on detail_name
        if detail_name in {"dice", "game"}:
            dice_dropdown = trickster.get("dice_game", {}).get("dropdown", {})
            if isinstance(dice_dropdown, dict):
                trickster_descriptions.update(dice_dropdown)
        elif detail_name in {"beggar", "beggar_admin"}:
            # Beggar is now under banker, load from banker descriptions
            banker = role_descriptions.get("banker", {})
            beggar_dropdown = banker.get("beggar", {}).get("dropdown", {})
            if isinstance(beggar_dropdown, dict):
                trickster_descriptions.update(beggar_dropdown)
        elif detail_name in {"runes", "runes_admin"}:
            shaman = roles_view.get("shaman", {})
            runes_dropdown = shaman.get("nordic_runes", {}).get("dropdown", {})
            if isinstance(runes_dropdown, dict):
                trickster_descriptions.update(runes_dropdown)
        
        # Ensure trickster_descriptions is a dict
        if not isinstance(trickster_descriptions, dict):
            trickster_descriptions = {}
        
        def _trickster_text(key: str, fallback: str) -> str:
            value = trickster_descriptions.get(key)
            if value:
                value = str(value)
            return str(value).strip() if value else fallback
        
        if detail_name == "overview":
            # Overview shows navigation to subroles, no specific actions
            return []
        if detail_name == "dice":
            # Get dice_game descriptions for action items
            dice_descriptions = _personality_descriptions.get("role_descriptions", {}).get("trickster", {}).get("dice_game", {})
            
            def _dice_text(key: str, fallback: str) -> str:
                value = dice_descriptions.get(key)
                if value:
                    value = str(value)
                return str(value).strip() if value else fallback
            
            return [
                (_dice_text("dice_play", "Dice: Play"), "dice_play", _dice_text("dice_play_description", "Play action"), "🎲"),
                (_dice_text("dice_ranking", "Dice: Ranking"), "dice_ranking", _dice_text("dice_ranking_description", "Ranking action"), "🏆"),
                (_dice_text("dice_history", "Dice: History"), "dice_history", _dice_text("dice_history_description", "History action"), "📜"),
                (_dice_text("dice_stats", "Dice: Stats"), "dice_help", _dice_text("dice_stats_description", "Stats action"), "📊"),
            ]
        if detail_name == "runes":
            # Check if runes subrole is enabled
            runes_enabled = True  # Temporarily force enabled for testing
            if agent_config:
                runes_enabled = agent_config.get("roles", {}).get("shaman", {}).get("subroles", {}).get("nordic_runes", {}).get("enabled", False)
            
            if not runes_enabled:
                # Runes disabled - only show info actions
                return [
                    ("Runes: Types", "runes_types", "Action"),
                ]
            
            # Runes enabled - show all casting actions
            # Get personality messages for dropdown labels
            roles_messages = _personality_descriptions.get("role_descriptions", {})
            nordic_runes_messages = roles_messages.get("shaman", {}).get("nordic_runes", {})
            canvas_labels = nordic_runes_messages.get("dropdown", {})
            
            def _runes_text(key: str, fallback: str) -> str:
                value = canvas_labels.get(key)
                if value:
                    value = str(value)
                return str(value).strip() if value else fallback
            
            # English fallbacks
            english_fallbacks = {
                "runes_single": "Runes: Single Cast",
                "runes_three": "Runes: Three Cast", 
                "runes_cross": "Runes: Cross Cast",
                "runes_runic_cross": "Runes: Runic Cross Cast",
                "runes_history": "Runes: History",
                "runes_types": "Runes: Types",
                "runes_runes_1": "Runes: All Runes I",
                "runes_runes_2": "Runes: All Runes II",
                "runes_runes_3": "Runes: All Runes III"
            }
            
            return [
                (canvas_labels.get("runes_single", english_fallbacks["runes_single"]), "runes_single", _runes_text("runes_single_description", "Text input target"), "🦅"),
                (canvas_labels.get("runes_three", english_fallbacks["runes_three"]), "runes_three", _runes_text("runes_three_description", "Text input target"), "🐾"),
                (canvas_labels.get("runes_cross", english_fallbacks["runes_cross"]), "runes_cross", _runes_text("runes_cross_description", "Text input target"), "🌍"),
                (canvas_labels.get("runes_runic_cross", english_fallbacks["runes_runic_cross"]), "runes_runic_cross", _runes_text("runes_runic_cross_description", "Text input target"), "🌌"),
                (canvas_labels.get("runes_history", english_fallbacks["runes_history"]), "runes_history", _runes_text("runes_history_description", "Action"), "📓"),
                (canvas_labels.get("runes_types", english_fallbacks["runes_types"]), "runes_types", _runes_text("runes_types_description", "Action"), "🌔"),
                (canvas_labels.get("runes_runes_1", english_fallbacks["runes_runes_1"]), "runes_runes_1", _runes_text("runes_runes_1_description", "Action"), "🗻"),
                (canvas_labels.get("runes_runes_2", english_fallbacks["runes_runes_2"]), "runes_runes_2", _runes_text("runes_runes_2_description", "Action"), "🗻"),
                (canvas_labels.get("runes_runes_3", english_fallbacks["runes_runes_3"]), "runes_runes_3", _runes_text("runes_runes_3_description", "Action"), "🗻"),
            ]
        if detail_name == "dice_admin" and admin_visible:
            # Get dice_game descriptions for action items with robust fallbacks
            _personality_descriptions = _get_personality_descriptions(server_id)
            
            # Safe nested access with fallbacks
            roles_view = _personality_descriptions.get("role_descriptions", {})
            
            # Check if dice_game data is directly in roles_view (trickster.json format)
            dice_game = roles_view.get("dice_game", {})
            
            # Ensure dice_descriptions is a dict
            if not isinstance(dice_game, dict):
                dice_descriptions = {}
            else:
                dice_descriptions = dice_game
            
            def _dice_text(key: str, fallback: str) -> str:
                value = dice_descriptions.get(key)
                if value:
                    value = str(value)
                return str(value).strip() if value else fallback
            
            return [
                (_dice_text("announcements_on", "Announcements: On"), "announcements_on", _dice_text("announcements_on_description", "Dice config"), "📢"),
                (_dice_text("announcements_off", "Announcements: Off"), "announcements_off", _dice_text("announcements_off_description", "Dice config"), "🔇"),
                (_dice_text("dice_fixed_bet", "Dice: Fixed Bet"), "dice_fixed_bet", _dice_text("dice_fixed_bet_description", "Number input target"), "🎲"),
                (_dice_text("dice_pot_value", "Dice: Pot Value"), "dice_pot_value", _dice_text("dice_pot_value_description", "Number input target"), "💰"),
            ]
        if detail_name == "runes_admin" and admin_visible:
            return [
                (_trickster_text("runes_on", "Runes: On"), "runes_on", _trickster_text("runes_on_description", "Boolean toggle"), "✅"),
                (_trickster_text("runes_off", "Runes: Off"), "runes_off", _trickster_text("runes_off_description", "Boolean toggle"), "❌"),
            ]
        return []

    if role_name == "shaman":
        _personality_descriptions = _get_personality_descriptions(server_id)
        canvas_labels = (_personality_descriptions
                         .get("role_descriptions", {})
                         .get("shaman", {})
                         .get("nordic_runes", {})
                         .get("dropdown", {}))

        def _runes_text(key: str, fallback: str) -> str:
            value = canvas_labels.get(key)
            return str(value).strip() if value else fallback

        if detail_name == "runes":
            runes_enabled = True
            if agent_config:
                runes_enabled = (agent_config.get("roles", {})
                                 .get("shaman", {})
                                 .get("subroles", {})
                                 .get("nordic_runes", {})
                                 .get("enabled", False))
            if not runes_enabled:
                return [
                    (_runes_text("runes_types", "Runes: Types"), "runes_types", _runes_text("runes_types_description", "Action"), "🌔"),
                ]
            return [
                (_runes_text("runes_single",      "Runes: Single Cast"),       "runes_single",      _runes_text("runes_single_description",      "Text input target"), "🦅"),
                (_runes_text("runes_three",       "Runes: Three Cast"),        "runes_three",       _runes_text("runes_three_description",       "Text input target"), "🐾"),
                (_runes_text("runes_cross",       "Runes: Cross Cast"),        "runes_cross",       _runes_text("runes_cross_description",       "Text input target"), "🌍"),
                (_runes_text("runes_runic_cross", "Runes: Runic Cross Cast"),  "runes_runic_cross", _runes_text("runes_runic_cross_description",  "Text input target"), "🌌"),
                (_runes_text("runes_history",     "Runes: History"),           "runes_history",     _runes_text("runes_history_description",     "Action"),            "📓"),
                (_runes_text("runes_types",       "Runes: Types"),             "runes_types",       _runes_text("runes_types_description",       "Action"),            "🌔"),
                (_runes_text("runes_runes_1",     "Runes: All Runes I"),       "runes_runes_1",     _runes_text("runes_runes_1_description",     "Action"),            "🗻"),
                (_runes_text("runes_runes_2",     "Runes: All Runes II"),      "runes_runes_2",     _runes_text("runes_runes_2_description",     "Action"),            "🗻"),
                (_runes_text("runes_runes_3",     "Runes: All Runes III"),     "runes_runes_3",     _runes_text("runes_runes_3_description",     "Action"),            "🗻"),
            ]
        if detail_name == "runes_admin" and admin_visible:
            return [
                (_runes_text("runes_on",  "Runes: On"),  "runes_on",  _runes_text("runes_on_description",  "Boolean toggle"), "✅"),
                (_runes_text("runes_off", "Runes: Off"), "runes_off", _runes_text("runes_off_description", "Boolean toggle"), "❌"),
            ]
        return []

    if role_name == "juggler":
        _personality_descriptions = _get_personality_descriptions(server_id)
        canvas_labels = (_personality_descriptions
                         .get("role_descriptions", {})
                         .get("juggler", {})
                         .get("ring", {})
                         .get("dropdown", {}))

        def _ring_text(key: str, fallback: str) -> str:
            value = canvas_labels.get(key)
            return str(value).strip() if value else fallback

        if detail_name == "ring":
            ring_enabled = True
            if agent_config:
                ring_enabled = (agent_config.get("roles", {})
                                 .get("juggler", {})
                                 .get("subroles", {})
                                 .get("ring", {})
                                 .get("enabled", False))
            if not ring_enabled:
                return []
            return [
                (_ring_text("ring_accuse", "Ring: Accuse"), "ring_accuse", _ring_text("ring_accuse_description", "Accuse a user of carrying the One Ring"), "👁️"),
            ]
        if detail_name == "ring_admin" and admin_visible:
            return [
                (_ring_text("ring_on", "Hunt: On"), "ring_on", _ring_text("ring_on_description", "Start the One Ring hunt"), "✅"),
                (_ring_text("ring_off", "Hunt: Off"), "ring_off", _ring_text("ring_off_description", "Stop the One Ring hunt"), "❌"),
                (_ring_text("ring_frequency", "Hunt: Frequency"), "ring_frequency", _ring_text("ring_frequency_description", "Configure the round frequency"), "⏰"),
            ]
        return []

    if role_name == "banker":
        # Import banker messages function
        try:
            from roles.banker.banker_messages import get_messages
        except ImportError:
            get_messages = None
        
        # Get server_db_path for banker messages
        server_db_path = None
        if server_id:
            try:
                from discord_bot.db_init import get_server_personality_dir
                server_dir = get_server_personality_dir(server_id)
                if server_dir:
                    server_db_path = server_dir
            except Exception:
                pass
        
        def _banker_text(key: str) -> str:
            # Use get_messages from banker_messages.py if available
            if get_messages and server_db_path:
                return get_messages(server_db_path, key)
            # Fallback to personality descriptions
            _personality_descriptions = _get_personality_descriptions(server_id)
            roles_view = _personality_descriptions.get("role_descriptions", {})
            banker = roles_view.get("banker", {})
            
            # Handle dot notation for nested keys (e.g., "beggar.title")
            if "." in key:
                keys = key.split(".")
                value = banker
                for k in keys:
                    if isinstance(value, dict) and k in value:
                        value = value[k]
                    else:
                        value = None
                        break
            else:
                value = banker.get(key)
            if value:
                value = str(value)
            return str(value).strip() if value else key
        
        def _banker_emoji(key: str):
            """Get emoji string from JSON."""
            emoji_str = _banker_text(key)
            # Return None if the key was returned (emoji not found)
            if emoji_str == key:
                return None
            return emoji_str
        
        if detail_name == "overview":
            # Overview shows wallet info, no specific actions
            return []
        if detail_name == "beggar":
            return [
                (_banker_text("beggar.dropdown.beggar_donate"), "beggar_donate", _banker_text("beggar.dropdown.beggar_donate_description"), _banker_emoji("beggar.dropdown.beggar_donate_emoji")),
            ]
        if detail_name == "beggar_admin" and admin_visible:
            return [
                (_banker_text("beggar.dropdown.beggar_on"), "beggar_on", _banker_text("beggar.dropdown.beggar_on_description"), _banker_emoji("beggar.dropdown.beggar_on_emoji")),
                (_banker_text("beggar.dropdown.beggar_off"), "beggar_off", _banker_text("beggar.dropdown.beggar_off_description"), _banker_emoji("beggar.dropdown.beggar_off_emoji")),
                (_banker_text("beggar.dropdown.beggar_frequency"), "beggar_frequency", _banker_text("beggar.dropdown.beggar_frequency_description"), _banker_emoji("beggar.dropdown.beggar_frequency_emoji")),
                (_banker_text("beggar.dropdown.beggar_force_minigame"), "beggar_force_minigame", _banker_text("beggar.dropdown.beggar_force_minigame_description"), _banker_emoji("beggar.dropdown.beggar_force_minigame_emoji")),
            ]
        if detail_name == "admin" and admin_visible:
            return [
                (_banker_text("config_tae"), "config_tae", _banker_text("config_tae_description"), _banker_emoji("config_tae_emoji")),
                (_banker_text("config_bonus"), "config_bonus", _banker_text("config_bonus_description"), _banker_emoji("config_bonus_emoji")),
            ]
    
    if role_name == "mc":
        # Get MC descriptions for action items with robust fallbacks
        _personality_descriptions = _get_personality_descriptions(server_id)
        
        # Safe nested access with fallbacks
        roles_view = _personality_descriptions.get("role_descriptions", {})
        mc = roles_view.get("mc", {})
        
        # Ensure mc_descriptions is a dict
        if not isinstance(mc, dict):
            mc_descriptions = {}
        else:
            mc_descriptions = mc
        
        # Get dropdown section if available, otherwise use root level
        dropdown_section = mc_descriptions.get("dropdown", mc_descriptions)
        
        def _mc_text(key: str, fallback: str) -> str:
            value = dropdown_section.get(key)
            if value:
                value = str(value)
            return str(value).strip() if value else fallback
        
        return [
            (_mc_text("mc_play", "Play Now"), "mc_play", _mc_text("mc_play_description", "Text input target"), "🎵"),
            (_mc_text("mc_add", "Add to Queue"), "mc_add", _mc_text("mc_add_description", "Text input target"), "➕"),
            (_mc_text("mc_skip", "Skip Song"), "mc_skip", _mc_text("mc_skip_description", "Action"), "⏭️"),
            (_mc_text("mc_pause", "Pause"), "mc_pause", _mc_text("mc_pause_description", "Action"), "⏸️"),
            (_mc_text("mc_resume", "Resume"), "mc_resume", _mc_text("mc_resume_description", "Action"), "▶️"),
            (_mc_text("mc_stop", "Stop"), "mc_stop", _mc_text("mc_stop_description", "Action"), "⏹️"),
            (_mc_text("mc_queue", "View Queue"), "mc_queue", _mc_text("mc_queue_description", "Action"), "📋"),
            (_mc_text("mc_remove_last", "Remove Last"), "mc_remove_last", _mc_text("mc_remove_last_description", "Action"), "🔙"),
            (_mc_text("mc_clear", "Clear Queue"), "mc_clear", _mc_text("mc_clear_description", "Action"), "🗑️"),
            (_mc_text("mc_history", "Show History"), "mc_history", _mc_text("mc_history_description", "Action"), "📜"),
            (_mc_text("mc_volume", "Set Volume"), "mc_volume", _mc_text("mc_volume_description", "Number input"), "🔊"),
        ]

    if role_name == "scholar":
        # Get scholar descriptions for action items with robust fallbacks
        _personality_descriptions = _get_personality_descriptions(server_id)
        
        # Safe nested access with fallbacks
        roles_view = _personality_descriptions.get("role_descriptions", {})
        scholar = roles_view.get("scholar", {})
        general = _personality_descriptions.get("general", {})
        
        # Use dropdown section if available
        scholar_descriptions = scholar.get("dropdown", {})
        
        # Ensure scholar_descriptions is a dict
        if not isinstance(scholar_descriptions, dict):
            scholar_descriptions = {}
        
        # Get action descriptions from general (to avoid redundancy)
        action_descriptions = general.get("action_descriptions", {}).get("boolean_toggle", "Toggle activation/deactivation")
        
        def _scholar_text(key: str, fallback: str) -> str:
            value = scholar_descriptions.get(key)
            if value:
                value = str(value)
            return str(value).strip() if value else fallback
        
        if detail_name == "admin" and admin_visible:
            return [
                (_scholar_text("toggle_on", "Enable Scholar"), "scholar_on", action_descriptions, "✅"),
                (_scholar_text("toggle_off", "Disable Scholar"), "scholar_off", action_descriptions, "❌"),
            ]
        # Personal view has no actions
        return []

    return []


def _get_canvas_role_action_items(role_name: str, admin_visible: bool, agent_config: dict | None = None, server_id: str = None) -> list[tuple[str, str, str]]:
    actions: list[tuple[str, str, str]] = []
    for _label, detail_name in _get_canvas_role_detail_items(role_name, None, admin_visible, role_name, server_id, agent_config):
        actions.extend(_get_canvas_role_action_items_for_detail(role_name, detail_name, admin_visible, agent_config, server_id))
    return actions


def _build_canvas_behavior_action_view(action_name: str, admin_visible: bool) -> str | None:
    if not admin_visible:
        return None
    action_map = {
        "greetings_on": ("Presence greetings", "On", f"`!greet{_personality_name}`", "Boolean toggle"),
        "greetings_off": ("Presence greetings", "Off", f"`!nogreet{_personality_name}`", "Boolean toggle"),
        "welcome_on": ("Welcome messages", "On", f"`!welcome{_personality_name}`", "Boolean toggle"),
        "welcome_off": ("Welcome messages", "Off", f"`!nowelcome{_personality_name}`", "Boolean toggle"),
        "memory_long": ("Memory", "Long memory", "View long-term daily memory analysis", "Dropdown selection"),
        "memory_recent": ("Memory", "Recent memory", "View recent short-term memory", "Dropdown selection"),
        "memory_relationship": ("Memory", "Relationship memory", "View relationship memory with users", "Dropdown selection"),
        "taboo_on": ("Taboo", "On", "`!taboo on`", "Boolean toggle"),
        "taboo_off": ("Taboo", "Off", "`!taboo off`", "Boolean toggle"),
        "taboo_add": ("Taboo", "Add keyword", "`!taboo add <keyword>`", "Text input"),
        "taboo_del": ("Taboo", "Remove keyword", "`!taboo del <keyword>`", "Text input"),
        "settings_open": ("Settings", "Manage language and roles", f"`!settings` or `!language`", "Select menu for server configuration"),
    }
    selected = action_map.get(action_name)
    if not selected:
        return None
    surface, state, command_name, input_type = selected
    return "\n".join([
        "⚙️ Canvas - General Behavior Action Choice\n",
        "**Selected option**",
        f"- Surface: {surface}",
        f"- State or action: {state}",
        f"- Command: {command_name}",
        "",
        "**GUI input model**",
        f"- Input type: {input_type}",
        "",
        "**Next step**",
        "- Apply the change only if you want to affect the whole server behavior",
    ])

def _get_last_saved_memory_fallback(database, memory_type: str, author_id: int = None, user_name: str = None, server_id: str = None) -> str:
    """Try to get the last saved memory paragraph as fallback before using defaults."""
    import sqlite3
    
    try:
        with database._lock:
            conn = sqlite3.connect(database.db_path)
            cursor = conn.cursor()
            
            if memory_type == "daily":
                # Get the most recent daily memory (excluding today's empty record and errors)
                cursor.execute("""
                    SELECT summary, updated_at FROM daily_memory 
                    WHERE summary IS NOT NULL AND summary != '' AND summary != '[Error in internal task]'
                    ORDER BY updated_at DESC LIMIT 5
                """)
                records = cursor.fetchall()
                if records:
                    for summary, updated_at in records:
                        summary = summary.strip()
                        if summary and len(summary) > 20:  # Valid content
                            conn.close()
                            return summary
                        
            elif memory_type == "recent":
                # Get the most recent recent memory (excluding today's empty record and errors)
                cursor.execute("""
                    SELECT summary, updated_at FROM recent_memory 
                    WHERE summary IS NOT NULL AND summary != '' AND summary != '[Error in internal task]'
                    ORDER BY updated_at DESC LIMIT 5
                """)
                records = cursor.fetchall()
                if records:
                    for summary, updated_at in records:
                        summary = summary.strip()
                        if summary and len(summary) > 20:  # Valid content
                            conn.close()
                            return summary
                        
            elif memory_type == "relationship" and author_id:
                # Get the most recent relationship memory for this user
                cursor.execute("""
                    SELECT summary, memory_date FROM user_relationship_daily_memory 
                    WHERE usuario_id = ? AND summary IS NOT NULL AND summary != '' AND summary != '[Error in internal task]'
                    ORDER BY memory_date DESC LIMIT 5
                """, (author_id,))
                records = cursor.fetchall()
                if records:
                    for summary, memory_date in records:
                        summary = summary.strip()
                        if summary and len(summary) > 20:  # Valid content
                            conn.close()
                            return summary
            
            conn.close()
    except Exception as e:
        logger.debug(f"Could not retrieve saved memory fallback for {memory_type}: {e}")
    
    # If no saved records found, use the default fallback with server_id
    from agent_mind import _get_daily_memory_fallback, _get_recent_memory_fallback, _get_relationship_memory_fallback
    
    if memory_type == "daily":
        return _get_daily_memory_fallback(server_id)
    elif memory_type == "recent":
        return _get_recent_memory_fallback(server_id)
    elif memory_type == "relationship":
        return _get_relationship_memory_fallback(user_name or "este umano", server_id)
    
    return ""


def _get_news_watcher_subscriptions_info(server_id: str, author_id: int, guild=None, news_title: str = "📰 News Watcher") -> str:
    """Get mini description of active news watcher subscriptions for user/channel."""
    try:
        db = get_news_watcher_db_instance(server_id)
        if not db:
            return ""
        
        # Import to get feed names
        from roles.news_watcher.global_feed_health import get_healthy_feeds
        
        # Get healthy feeds to map feed_id to feed name
        healthy_feeds = get_healthy_feeds()
        feed_map = {fid: name for fid, name, url, cat in healthy_feeds}
        
        subscriptions_lines = []
        
        # Get channel subscriptions (if in guild)
        if guild:
            unified_subs = db.get_all_active_subscriptions()
            for subscription_id, user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by in unified_subs:
                # Only include channel subscriptions
                if not channel_id:
                    continue
                
                # Get feed name
                if feed_id:
                    feed_name = feed_map.get(feed_id, f"Feed #{feed_id}")
                else:
                    feed_name = "all feeds"
                
                subscriptions_lines.append(f"🔍 {category} ({feed_name}) - {method}")
        
        # Get user subscriptions (DM)
        user_subs = db.get_user_subscriptions(str(author_id))
        if user_subs:
            for sub in user_subs[:3]:  # Limit to 3
                subscription_id = sub[0] if len(sub) > 0 else 0
                user_id = sub[1] if len(sub) > 1 else ""
                channel_id = sub[2] if len(sub) > 2 else None
                category = sub[3] if len(sub) > 3 else "general"
                feed_id = sub[4] if len(sub) > 4 else None
                premises = sub[5] if len(sub) > 5 else ""
                keywords = sub[6] if len(sub) > 6 else ""
                method = sub[7] if len(sub) > 7 else "general"
                
                # Get feed name
                if feed_id:
                    feed_name = feed_map.get(feed_id, f"Feed #{feed_id}")
                else:
                    feed_name = "all feeds"
                
                subscriptions_lines.append(f"🔍 {category} ({feed_name}) - {method}")
        
        if subscriptions_lines:
            return "\n".join(subscriptions_lines[:5])  # Limit to 5
        return ""
    except Exception as e:
        logger.warning(f"Error getting news watcher subscriptions: {e}")
        return ""

def _get_poe2_purchases_info(server_id: str, author_id: int, poe2_title: str = "💎 POE2") -> str:
    """Get items registered as purchase in POE2."""
    try:
        if not get_roles_db_instance or not get_poe2_manager:
            return ""
        
        # Use fixed title format: 👺 PoE2:
        poe2_title = "👺 PoE2:"
        
        roles_db = get_roles_db_instance(server_id)
        subscription = roles_db.get_poe2_subscription(str(author_id), server_id)
        
        if subscription and subscription.get('purchases'):
            purchases = subscription['purchases']
            league = subscription.get('league', 'Standard')
            
            # Get POE2 manager to fetch current prices
            manager = get_poe2_manager()
            
            items_with_prices = []
            for purchase in purchases[:3]:  # Limit to 3 items
                if isinstance(purchase, dict):
                    item_name = purchase.get('item_name')
                    buy_price = purchase.get('buy_price')
                    item_id = purchase.get('item_id')
                    
                    if not item_name:
                        continue
                    
                    # Get current price from global database
                    current_price = None
                    if item_id:
                        try:
                            price_data = manager.get_latest_price_for_item(league, item_id)
                            if price_data:
                                current_price = price_data.get('price')
                        except Exception:
                            pass
                    
                    if current_price is not None:
                        # Emoji based on buy price vs current price
                        # Lower buy price = price went up (📈), Higher buy price = price went down (📉)
                        if buy_price < current_price:
                            emoji = "📈"  # Bought at lower price (price went up - good investment)
                        elif buy_price > current_price:
                            emoji = "📉"  # Bought at higher price (price went down - bad investment)
                        else:
                            emoji = "➡️"  # Same price
                        items_with_prices.append(f"{item_name} {current_price:.2f} divs {emoji}")
                    else:
                        items_with_prices.append(f"{item_name}")
                else:
                    # Handle old string format
                    items_with_prices.append(str(purchase))
            
            if items_with_prices:
                return f"{poe2_title}\n" + "\n".join(f"-{item}" for item in items_with_prices)
        return ""
    except Exception as e:
        logger.warning(f"Error getting POE2 purchases: {e}")
        return ""

def _get_dice_game_pot_info(server_id: str, coin_emoji: str = "🪙", dice_title: str = "🎲 Dice Game") -> str:
    """Get current dice game pot."""
    try:
        from roles.banker.banker_db import get_banker_roles_db_instance
        logger.debug(f"Attempting to get dice game pot for server {server_id}")
        
        banker_db = get_banker_roles_db_instance(server_id)
        # Create wallet if it doesn't exist
        banker_db.create_wallet("dice_game_pot", "Dice Game Pot", wallet_type='system')
        pot_balance = banker_db.get_balance("dice_game_pot")
        logger.debug(f"Dice game pot balance: {pot_balance}")
        return f"{dice_title}: {pot_balance} {coin_emoji}"
    except Exception as e:
        logger.warning(f"Error getting dice game pot: {e}")
        return ""

def _get_mc_last_song_info(server_id: str, mc_title: str = "🎵 MC") -> str:
    """Get last song played in the server."""
    try:
        from roles.mc.db_role_mc import get_mc_db_instance
        mc_db = get_mc_db_instance(server_id)
        
        # Get history from any channel in the server using NoSQL
        from roles.role_configs_nosql import get_role_configs_nosql
        nosql = get_role_configs_nosql(server_id)
        
        # Access history store directly to get most recent entry across all channels
        all_entries = list(nosql._mc_history.iter_records())
        filtered = [
            e for e in all_entries
            if e.get("server_id") == server_id
        ]
        if filtered:
            # Sort by played_at descending and get the most recent
            filtered.sort(key=lambda e: e.get("played_at", ""), reverse=True)
            most_recent = filtered[0]
            title = most_recent.get("title")
            artist = most_recent.get("artist")
            if artist:
                return f"{mc_title}: {title} by {artist}"
            return f"{mc_title}: {title}"
        return ""
    except Exception as e:
        logger.warning(f"Error getting MC last song: {e}")
        return ""

def _get_banker_wallet_info(server_id: str, author_id: int, coin_emoji: str = "🪙", banker_title: str = "💰 Banker") -> str:
    """Get gold amount of banker wallet for the user."""
    try:
        from roles.banker.banker_db import get_banker_roles_db_instance
        
        banker_db = get_banker_roles_db_instance(server_id)
        balance = banker_db.get_balance(str(author_id))
        return f"{banker_title}: {balance} {coin_emoji}"
    except Exception as e:
        logger.warning(f"Error getting banker wallet: {e}")
        return ""

def _get_ring_accused_info(server_id: str, guild=None, ring_title: str = "⚖️ Ring") -> str:
    """Get current accused user in ring subrole."""
    try:
        from roles.juggler.subroles.ring.ring_db import get_ring_db_instance
        ring_db = get_ring_db_instance(server_id)
        config = ring_db.get_config()
        
        # Get accused_label from personality descriptions
        from .content import _get_personality_descriptions
        personality_descriptions = _get_personality_descriptions(server_id)
        juggler_messages = personality_descriptions.get("role_descriptions", {}).get("juggler", {})
        ring_messages = juggler_messages.get("ring", {})
        accused_label = ring_messages.get("accused_label", "Accused:")
        
        accused_user_id = config.get('accused_user_id')
        if accused_user_id and guild:
            try:
                member = guild.get_member(int(accused_user_id))
                if member:
                    return f"{ring_title}: {accused_label} {member.display_name}"
            except:
                return f"{ring_title}: {accused_label} {accused_user_id}"
        return ""
    except Exception as e:
        logger.warning(f"Error getting ring accused: {e}")
        return ""

def _get_moon_phase_info(server_id: str = "default", shaman_title: str = "🐺 Shaman") -> str:
    """Get current moon phase with emoji and phase name."""
    try:
        # Get moon phase name and emoji
        moon_phase_name, moon_emoji = get_moon_phase()
        
        # Get moon phase title from personality descriptions (for display in home)
        personality_descriptions = _get_personality_descriptions(server_id)
        shaman_messages = personality_descriptions.get("role_descriptions", {}).get("shaman", {})
        moon_messages = shaman_messages.get("moon_phases", {})
        moon_title = moon_messages.get(moon_phase_name, f"{moon_emoji} Current moon phase")
        
        return f"{shaman_title}: {moon_title}"
    except Exception as e:
        logger.warning(f"Error getting moon phase: {e}")
        return ""

def _build_canvas_home(agent_config: dict, greet_name: str, nogreet_name: str, welcome_name: str, nowelcome_name: str,
                       role_cmd_name: str, talk_cmd_name: str, admin_visible: bool, server_id: str = "default",
                       author_id: int = 0, guild=None, is_dm: bool = False) -> str:
    """Build the main Canvas hub view with status information."""
    enabled_roles = _get_enabled_roles(agent_config, guild)
    roles_text = ", ".join(enabled_roles) if enabled_roles else "none"
    
    # Get home messages from personality with fallback (dynamic per server)
    personality_descriptions = _get_personality_descriptions(server_id)
    home_messages = personality_descriptions.get("canvas_home_messages", {})
    
    def _home_text(key: str, fallback: str) -> str:
        value = home_messages.get(key)
        if value:
            value = str(value)
        return str(value).strip() if value else fallback
    
    personalitystatus = _home_text("personalitystatus", "Personality:" )
    homedescription = _home_text("description", "Interact with all of the bot feautures from this panel." )
    recentsynthesistitle = _home_text("recentsynthesistitle", "Recent synthesis" )
    personalsynthesistitle = _home_text("personalsynthesistitle", "Personal synthesis with you" )
    interestingthings = _home_text("interestingthings", "Interesting things - " )
    pilgrimdatatitle = _home_text("pilgrimdatatitle", "Pilgrim Data:" )
    
    # Get coin emoji and role titles from descriptions
    coin_emoji = "🪙"  # Default fallback
    dice_title = "🎲 Dice Game"  # Default fallback
    banker_title = "💰 Banker"  # Default fallback
    news_title = "📰 News Watcher"  # Default fallback
    poe2_title = "💎 POE2"  # Default fallback
    mc_title = "🎵 MC"  # Default fallback
    ring_title = "⚖️ Ring"  # Default fallback
    shaman_title = "🐺 Shaman"  # Default fallback
    try:
        role_descriptions = personality_descriptions.get("role_descriptions", {})
        
        # Get coin emoji from banker
        banker_desc = role_descriptions.get("banker", {})
        if banker_desc and "coin" in banker_desc:
            coin_emoji = banker_desc["coin"]
        if banker_desc and "title" in banker_desc:
            banker_title = banker_desc["title"]
        
        # Get dice game title from trickster
        trickster_desc = role_descriptions.get("trickster", {})
        if trickster_desc and "dice_game" in trickster_desc:
            dice_game_desc = trickster_desc["dice_game"]
            if isinstance(dice_game_desc, dict) and "title" in dice_game_desc:
                dice_title = dice_game_desc["title"]
        
        # Get news watcher title
        news_desc = role_descriptions.get("news_watcher", {})
        if news_desc and "title" in news_desc:
            news_title = news_desc["title"]
        
        # Get POE2 title from treasure_hunter
        th_desc = role_descriptions.get("treasure_hunter", {})
        if th_desc and "poe2" in th_desc:
            poe2_desc = th_desc["poe2"]
            if isinstance(poe2_desc, dict) and "title" in poe2_desc:
                poe2_title = poe2_desc["title"]
        
        # Get MC title
        mc_desc = role_descriptions.get("mc", {})
        if mc_desc and "title" in mc_desc:
            mc_title = mc_desc["title"]
        
        # Get Ring title from juggler
        juggler_desc = role_descriptions.get("juggler", {})
        if juggler_desc and "ring" in juggler_desc:
            ring_desc = juggler_desc["ring"]
            if isinstance(ring_desc, dict) and "title" in ring_desc:
                ring_title = ring_desc["title"]
        
        # Get Shaman title
        shaman_desc = role_descriptions.get("shaman", {})
        if shaman_desc and "title" in shaman_desc:
            shaman_title = shaman_desc["title"]
    except Exception as e:
        logger.debug(f"Could not get role titles from descriptions: {e}")
    
    # Build status content
    status_lines: list[str] = []
    
    # Add DM notification if applicable
    if is_dm and guild:
        status_lines.extend([
            home_messages.get("dm_default_server_separator", "─────────────────────────────────────────────"),
            home_messages.get("dm_default_server_title", "🔔 **Using default server: {server_name}**").format(server_name=guild.name),
            home_messages.get("dm_default_server_message", "*You're navigating from DM, using the first available server.*"),
            home_messages.get("dm_default_server_separator", "─────────────────────────────────────────────"),
            "",
        ])
    
    # Title and description
    status_lines.extend([
        f"{homedescription}",
        "─" * 45,
    ])
    
    # Section: Cosas interesantes (Interesting things)
    status_lines.extend([
        interestingthings,
        ""
    ])
    
    # Check which roles are enabled from agent_config
    roles_config = agent_config.get('roles', {})
    
    # 1. News Watcher - Active subscriptions
    if roles_config.get('news_watcher', {}).get('enabled'):
        news_info = _get_news_watcher_subscriptions_info(server_id, author_id, guild, news_title)
        if news_info:
            # Append subscription lines directly
            for line in news_info.split('\n'):
                status_lines.append(line)
    
    # 2. POE2 - Items registered as purchase
    if roles_config.get('treasure_hunter', {}).get('enabled'):
        poe2_info = _get_poe2_purchases_info(server_id, author_id, poe2_title)
        if poe2_info:
            status_lines.append(poe2_info)
    
    # 3. Dice Game - Current pot
    dice_game_enabled = roles_config.get('trickster', {}).get('subroles', {}).get('dice_game', {}).get('enabled')
    logger.debug(f"Dice game enabled check: {dice_game_enabled}, roles_config: {roles_config.get('trickster', {})}")
    if dice_game_enabled:
        dice_info = _get_dice_game_pot_info(server_id, coin_emoji, dice_title)
        logger.debug(f"Dice info returned: {dice_info}")
        if dice_info:
            status_lines.append(dice_info)
    
    # 4. MC - Last song played
    if roles_config.get('mc', {}).get('enabled'):
        mc_info = _get_mc_last_song_info(server_id, mc_title)
        if mc_info:
            status_lines.append(mc_info)
    
    # 5. Banker - User's wallet balance (moved to Pilgrim Data section)
    
    # 6. Ring - Current accused user
    if roles_config.get('juggler', {}).get('subroles', {}).get('ring', {}).get('enabled'):
        ring_info = _get_ring_accused_info(server_id, guild, ring_title)
        if ring_info:
            status_lines.append(ring_info)
    
    # 7. Shaman - Current moon phase
    if roles_config.get('shaman', {}).get('enabled'):
        moon_info = _get_moon_phase_info(server_id, shaman_title)
        if moon_info:
            status_lines.append(moon_info)
    
    status_lines.extend([
        "",
        "─" * 45,
    ])
    
    # Section: Recent Memory
    # Initialize records as None
    recent_record = None
    relationship_record = {"summary": "", "updated_at": None, "last_interaction_at": None, "metadata": {}}
    daily_record = None
    
    # Try to get database and records
    database = None
    try:
        from agent_db import get_db_instance
        database = get_db_instance(server_id)
        recent_record = database.get_most_recent_memory_record()
        relationship_record = database.get_user_relationship_memory(author_id)
        daily_record = database.get_most_recent_daily_memory_record()
    except Exception as e:
        logger.warning(f"Canvas status could not load memory data for server={server_id}: {e}")
        # Database error, but we still have the records (might be None)
        # Don't set fallbacks here - let the logic below handle it
    
    recent_summary = (recent_record or {}).get("summary", "").strip()
    relationship_summary = (relationship_record or {}).get("summary", "").strip()
    daily_summary = (daily_record or {}).get("summary", "").strip()
    
    # Exclude error messages from summaries
    if daily_summary == "[Error in internal task]":
        daily_summary = ""
    if recent_summary == "[Error in internal task]":
        recent_summary = ""
    if relationship_summary == "[Error in internal task]":
        relationship_summary = ""
    
    # Use fallback content if summaries are empty (e.g., due to token errors or no today's record)
    if not recent_summary:
        if database:
            recent_summary = _get_last_saved_memory_fallback(database, "recent", server_id=server_id)
        else:
            from agent_mind import _get_recent_memory_fallback
            recent_summary = _get_recent_memory_fallback(server_id)
    
    if not daily_summary:
        if database:
            daily_summary = _get_last_saved_memory_fallback(database, "daily", server_id=server_id)
        else:
            from agent_mind import _get_daily_memory_fallback
            daily_summary = _get_daily_memory_fallback(server_id)
    
    if not relationship_summary:
        user_name = None
        if guild and author_id:
            try:
                member = guild.get_member(author_id)
                if member and member.display_name:
                    user_name = member.display_name
            except:
                pass
        if not user_name:
            user_name = "unknown user"
            
        if database:
            relationship_summary = _get_last_saved_memory_fallback(database, "relationship", author_id, user_name, server_id)
        else:
            from agent_mind import _get_relationship_memory_fallback
            relationship_summary = _get_relationship_memory_fallback(user_name, server_id)
    
    # Only show recent synthesis (relationship section removed as requested)
    if recent_summary:
        status_lines.extend([
            f"{recentsynthesistitle}",
            f"- {recent_summary[:1000]}",
        ])
    
    status_lines.extend([
        "",
        "─" * 45,
    ])
    
    # Section: Pilgrim Data
    if roles_config.get('banker', {}).get('enabled'):
        banker_info = _get_banker_wallet_info(server_id, author_id, coin_emoji, banker_title)
        if banker_info:
            status_lines.append(banker_info)
    
    # Add final separator
    status_lines.extend([
        "─" * 45,
        f"{personalitystatus} `{_get_server_personality_name(server_id)}`"
    ])
    
    return "\n".join(status_lines)


def _build_canvas_roles(agent_config: dict, admin_visible: bool, guild=None, page: int = 1, roles_per_page: int = 5) -> str:
    """Build the role navigation Canvas view - now uses database as primary source with pagination."""
    # Note: Roles initialization happens once at server startup via server_config.json
    
    # Get roles view messages from personality with fallback
    server_id = core.get_server_key(guild) if guild else None
    _personality_descriptions = _get_personality_descriptions(server_id)
    roles_messages = _personality_descriptions.get("roles_view_messages", {})
    
    # Title and description from descriptions.json with fallback
    title = roles_messages.get("title", f"🎭 ROLE MANAGER - {server_id} 🎭").strip()
    description = roles_messages.get("description", "🌟 The role manager oversees all aspects of the clan. Each role has unique abilities to serve the tribe. Explore different specializations and choose your path.").strip()
    separator = roles_messages.get("role_categories", "──────────────────────────────").strip()
    
    # Helper messages
    enabled_status = roles_messages.get("enabled_status", "ACTIVE")
    # Resolve general.active reference if present
    if enabled_status and enabled_status.startswith("general."):
        general = _personality_descriptions.get("general", {})
        key = enabled_status.split(".", 1)[1]
        enabled_status = general.get(key, enabled_status)
    interval_info = roles_messages.get("interval_info", "⏰ Every {interval}h")
    inactive_status = roles_messages.get("inactive_status", "❌ INACTIVE")
    
    parts = [
        title,
        description,
        separator,
    ]
    
    # Track active and inactive roles
    active_roles = []
    inactive_roles = []
    
    role_descriptions = _personality_descriptions.get("role_descriptions", {})

    def get_role_info(role_key):
        role_data = role_descriptions.get(role_key, {})
        title = str(role_data.get("title", "")).strip()
        if not title:
            title = role_key.replace("_", " ").title()
        description = str(role_data.get("description", "")).strip()
        return {"title": title, "description": description}
    
    # Define all possible roles with their intervals (must match order in ui.py)
    role_configs = [
        ("news_watcher", 1),
        ("treasure_hunter", 1),
        ("trickster", None),
        ("banker", 24),
        ("mc", None),
        ("juggler", None),
        ("shaman", None),
        ("scholar", None),
    ]
    
    # Collect all active roles first - use same order as ui.py
    for role_name, interval in role_configs:
        if is_role_enabled_check(role_name, None, guild):
            active_roles.append((role_name, interval))
    
    # Check for inactive roles
    all_possible_roles = [r[0] for r in role_configs]
    for role in all_possible_roles:
        if role not in [r[0] for r in active_roles]:
            inactive_roles.append(role)
    
    # Calculate pagination
    total_roles = len(active_roles)
    total_pages = (total_roles + roles_per_page - 1) // roles_per_page if total_roles > 0 else 1
    page = max(1, min(page, total_pages))  # Ensure page is within valid range
    
    # Get roles for current page
    start_idx = (page - 1) * roles_per_page
    end_idx = start_idx + roles_per_page
    page_roles = active_roles[start_idx:end_idx]
    
    # Add roles for current page
    for role_name, interval in page_roles:
        role_info = get_role_info(role_name)
        parts.append(role_info['title'])
        if role_info['description']:
            parts.append(role_info['description'])
        parts.append(separator)
    
    # Add page indicator if there are multiple pages
    if total_pages > 1:
        page_indicator = roles_messages.get("page_indicator", "**Page {page}/{total_pages}**")
        parts.append(page_indicator.format(page=page, total_pages=total_pages))
    
    # Add inactive roles section if any exist
    if inactive_roles:
        parts.append("**DEACTIVATE ROLES:**")
        
        for role in inactive_roles:
            role_info = get_role_info(role)
            role_icons = {
                "news_watcher": "📡",
                "treasure_hunter": "💎", 
                "trickster": "🎭",
                "banker": "💰",
                "mc": "🎵",
                "juggler": "🤹",
                "shaman": "🔮"
            }
            icon = role_icons.get(role, "📋")
            parts.append(f"{icon} {role_info['title']}")
    
    # If no roles are active, show helpful message
    if not active_roles:
        no_roles_msg = roles_messages.get("no_roles_active",
            "🌫️ **NO ACTIVE ROLES**\n\nNo specialized roles are currently active. Ask an administrator to activate some roles using `!canvas setup`.\n\n**Available roles to activate:**\n• 📡 News Watcher - News monitoring\n• 💎 Treasure Hunter - Treasure hunting\n• 🎭 Trickster - Games and tricks\n• 💰 Banker - Clan economy\n• 🎵 MC - Music and entertainment"
        )
        parts.append(no_roles_msg)

    return "\n".join(parts)


def _build_canvas_personal() -> str:
    """Build the personal/DM-oriented Canvas view."""
    return (
        "👤 Canvas - Personal Space\n\n"
        "**Personal workflows**\n"
        "- News Watcher personal subscriptions: `!watcherhelp`\n"
        "- POE2 objectives and league: `!hunter poe2 help`\n"
        "- Wallet and recent transactions: `!banker balance` (unified in Canvas)\n"
        "- Dice game stats and balance: `!dice stats`, `!dice balance`\n\n"
        "**DM-oriented flows**\n"
        "- Some Watcher responses are delivered by private message\n"
        "- POE2 personal management is DM-only for some commands\n"
        "- Banker balance is designed to answer privately\n\n"
        "**Concrete choices**\n"
        "- Text input: tracked item names, watcher keywords, watcher premises\n"
        "- Select menu: league choices such as `Standard` or `Fate of the Vaal`\n"
        "- Boolean toggle: critical watcher alerts on/off\n\n"
        "**Fast path**\n"
        "- `!watchernotify` - Subscribe to critical watcher alerts\n"
        "- `!hunter poe2 list` - Show tracked POE2 objectives\n"
        "- `!banker balance` - Show your wallet (unified in Canvas)\n"
        "- `!dice ranking` - View the current ranking"
    )


def _build_canvas_help(guild=None) -> str:
    """Build the help and troubleshooting Canvas view."""
    #2nd block for this view
    server_id = get_server_key(guild) if guild else None
    help_messages = _get_personality_descriptions(server_id).get("help_menu", {})
    separator = help_messages.get("separator", "-" * 45)
    roles = help_messages.get("roles_section", "**Roles**\nThe Roles modules are some capabilities for the bot to give some services to the users.")
    behavior = help_messages.get("behavior_section", "**Behavior**\nIn this section you'll configurate some interactuable behaviors of the bot. Only for Admins")
    tips = help_messages.get("tips_section", "**Some tips**\n-You can ask to the bot how works a command like: 'how works the command dice?'\n-The most jouicy parts of the bots its inside of each role")
    
    return (
        f"{separator}\n"
        f"{roles}\n"
        f"{behavior}\n"
        f"{separator}\n"
        f"{tips}"   
    )


def _build_canvas_role_view(role_name: str, agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Build a role-specific Canvas view."""
    if role_name == "news_watcher" and is_role_enabled_check("news_watcher", agent_config, guild):
        return build_canvas_role_news_watcher(agent_config, admin_visible, guild, author_id or 0)
    if role_name == "treasure_hunter" and is_role_enabled_check("treasure_hunter", agent_config, guild):
        return build_canvas_role_treasure_hunter(agent_config, admin_visible, guild, author_id)
    if role_name == "trickster" and is_role_enabled_check("trickster", agent_config, guild):
        return build_canvas_role_trickster(agent_config, admin_visible, guild)
    if role_name == "banker" and is_role_enabled_check("banker", agent_config, guild):
        return build_canvas_role_banker(agent_config, admin_visible, guild, author_id)
    if role_name == "shaman" and is_role_enabled_check("shaman", agent_config, guild):
        return build_canvas_role_shaman(agent_config, admin_visible, guild)
    if role_name == "juggler" and is_role_enabled_check("juggler", agent_config, guild):
        return build_canvas_role_juggler(agent_config, admin_visible, guild)
    if role_name == "mc" and is_role_enabled_check("mc", agent_config, guild):
        queue_info = None
        try:
            from roles.mc.db_role_mc import get_mc_db_instance
            server_id = core.get_server_key(guild) if guild else None
            if server_id and guild:
                db_mc = get_mc_db_instance(server_id)
                queue_data = db_mc.get_queue(server_id, str(guild.id))
                queue_info = [(title, artist, duration, user_id) for _pos, title, _url, duration, artist, user_id, _fecha in queue_data]
        except Exception as e:
            logger.warning(f"Failed to load MC queue for overview: {e}")
        return build_canvas_role_mc(queue_info=queue_info, guild=guild)
    if role_name == "scholar" and is_role_enabled_check("scholar", agent_config, guild):
        return build_canvas_role_scholar(agent_config, admin_visible, guild)
    return None


def _build_canvas_role_detail_view(role_name: str, detail_name: str, agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Build a role detail Canvas view."""
    if role_name == "news_watcher" and is_role_enabled_check("news_watcher", agent_config, guild):
        return build_canvas_role_news_watcher_detail(
            detail_name=detail_name,
            admin_visible=admin_visible,
            guild=guild,
            author_id=author_id or 0,
            selected_method=None,
            last_action=None,
            selected_category=None,
            setup_not_available_builder=_build_canvas_setup_not_available,
        )
    if role_name == "treasure_hunter" and is_role_enabled_check("treasure_hunter", agent_config, guild):
        return build_canvas_role_treasure_hunter_detail(
            detail_name,
            admin_visible,
            guild,
            author_id,
            setup_not_available_builder=_build_canvas_setup_not_available,
        )
    if role_name == "trickster" and is_role_enabled_check("trickster", agent_config, guild):
        return build_canvas_role_trickster_detail(detail_name, admin_visible, guild, author_id, agent_config)
    if role_name == "banker" and is_role_enabled_check("banker", agent_config, guild):
        return build_canvas_role_banker_detail(detail_name, admin_visible, guild, author_id)
    if role_name == "shaman" and is_role_enabled_check("shaman", agent_config, guild):
        return build_canvas_role_shaman_detail(detail_name, admin_visible, guild, author_id, agent_config)
    if role_name == "juggler" and is_role_enabled_check("juggler", agent_config, guild):
        return build_canvas_role_juggler_detail(detail_name, admin_visible, guild)
    if role_name == "scholar" and is_role_enabled_check("scholar", agent_config, guild):
        return build_canvas_role_scholar_detail(detail_name, admin_visible, guild, author_id, agent_config)
    if role_name == "mc" and is_role_enabled_check("mc", agent_config, guild):
        queue_info = None
        try:
            from roles.mc.db_role_mc import get_mc_db_instance
            server_id = core.get_server_key(guild) if guild else None
            if server_id and guild:
                db_mc = get_mc_db_instance(server_id)
                # Get the most recent channel_id from the queue for this server
                queue_data_all = db_mc.get_queue_all_channels(server_id)
                if queue_data_all:
                    # Use the channel_id from the most recent entry
                    channel_id = queue_data_all[0][7]  # channel_id is at index 7
                    queue_data = db_mc.get_queue(server_id, channel_id)
                    queue_info = [(title, artist, duration, user_id) for _pos, title, _url, duration, artist, user_id, _fecha in queue_data]
        except Exception as e:
            logger.warning(f"Failed to load MC queue for detail view: {e}")
        return build_canvas_role_mc(queue_info=queue_info, guild=guild)
    return None
