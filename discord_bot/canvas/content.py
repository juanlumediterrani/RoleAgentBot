"""Canvas content builders and render helpers."""

from discord_bot import discord_core_commands as core
from roles import news_watcher

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
                # Merge sub-role description files from descriptions/ subdirectory
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
get_news_watcher_db_instance = core.get_news_watcher_db_instance

try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None
get_poe2_manager = core.get_poe2_manager
get_banker_db_instance = None  # Now using roles_db directly
get_behavior_db_instance = core.get_behavior_db_instance
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
    _get_canvas_ring_state,
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
)
from .canvas_behavior import (
    build_canvas_behavior,
)


def _build_canvas_setup_not_available() -> str:
    """Build message for when setup is only available to administrators."""
    return "❌ This setup is only available to administrators."

def _get_behavior_db_for_guild(guild):
    """Get behavior database instance for a guild."""
    try:
        from discord_bot.discord_utils import get_behaviors_db_instance, get_server_key
        if get_behaviors_db_instance is None:
            return None
        # Handle None guild case - use default server
        if guild is None:
            return get_behaviors_db_instance(None)
        return get_behaviors_db_instance(get_server_key(guild))
    except Exception as e:
        logger.error(f"Error getting behavior database for guild: {e}")
        return None


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
        "roles": _build_canvas_roles(agent_config, admin_visible, guild),
        "personal": _build_canvas_personal(),
        "help": _build_canvas_help(guild),
    }


def _build_canvas_embed(section_name: str, content: str, admin_visible: bool, title: str | None = None, description: str | None = None, server_id: str = None) -> discord.Embed:
    # Get title from personality descriptions for consistency
    personality_descriptions = _get_personality_descriptions(server_id)

    help_title = personality_descriptions.get("help_menu", {}).get("title", "📚 Canvas - Help & Troubleshooting")
    help_title = help_title.replace("**", "")

    if section_name == "behavior":
        # Use provided title/description or fall back to personality descriptions
        if title is None:
            behavior_descriptions = personality_descriptions.get("behavior_messages", {})
            behavior_title = behavior_descriptions.get("canvas_conversation_title", "💬 General Behavior")
            # Remove ** for embed title
            behavior_title = behavior_title.replace("**", "")
        else:
            behavior_title = title.replace("**", "")

        # Get home title from descriptions.json
        canvas_home_messages = personality_descriptions.get("canvas_home_messages", {})
        home_title = canvas_home_messages.get("title", "🧭 Canvas Hub")
        # Remove ** for embed title
        home_title = home_title.replace("**", "")

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
        # Remove ** for embed title
        home_title = home_title.replace("**", "")

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

    if section_name == "home":
        personality_line = next((line for line in lines if line.startswith("**Personality:**")), "")
        roles_line = next((line for line in lines if line.startswith("**Active roles:**")), "")
        description_parts = [part for part in [personality_line.replace("**", ""), roles_line.replace("**", "")] if part]
        description = "".join(description_parts)
    elif section_name == "home_status":
        personality_line = next((line for line in lines if line.startswith("**Personality:**")), "")
        roles_line = next((line for line in lines if line.startswith("**Active roles:**")), "")
        description_parts = [part for part in [personality_line.replace("**", ""), roles_line.replace("**", "")] if part]
        description = "\n".join(description_parts)
    elif section_name == "roles":
        description = ""  # Empty description - title will be the main content
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
    visible_blocks = blocks[:4]
    last_block_index = len(visible_blocks) - 1
    for index, (block_title, block_lines) in enumerate(visible_blocks):
        filtered_lines = [
            line for line in block_lines
            if not (section_name in {"home", "home_status"} and (line.startswith("**Personality:**") or line.startswith("**Active roles:**")))
            and not (section_name == "roles" and index == 0 and block_lines and line == titles.get("roles"))
        ]
        value = "\n".join(filtered_lines)[:1024]
        # Use block_title as field name, not as part of the value
        field_name = block_title if block_title and block_title != "\u200b" else "\u200b"
        if value:
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
            current_title = line.strip("*")
            current_lines = []
            continue
        current_lines.append(line)

    if current_lines:
        blocks.append((current_title, current_lines))
    return blocks


def _normalize_canvas_title(title: str) -> str:
    return str(title or "").replace("**", "").strip()



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
                    return subrole_title.replace("**", "").strip()
            # Fall back to main role title
            title = role_descriptions.get(role_key, {}).get("title", "")
            return title.replace("**", "").strip() if title else role_key
        except Exception:
            return role_key
    
    # Use surface_name as detail_key for subrole titles
    # For admin views like "beggar_admin", use the base subrole key "beggar"
    # Map canvas surface names to JSON keys where they differ
    _surface_to_json_key = {"runes": "nordic_runes", "runes_admin": "nordic_runes"}
    if surface_name and surface_name not in {"overview", "admin"}:
        base = surface_name.replace("_admin", "")
        detail_key = _surface_to_json_key.get(surface_name, _surface_to_json_key.get(base, base))
    else:
        detail_key = None
    
    role_titles = {
        "news_watcher": _normalize_canvas_title(_get_embed_role_title("news_watcher", detail_key)),
        "treasure_hunter": _normalize_canvas_title(_get_embed_role_title("treasure_hunter", detail_key)),
        "trickster": _normalize_canvas_title(_get_embed_role_title("trickster", detail_key)),
        "banker": _normalize_canvas_title(_get_embed_role_title("banker", detail_key)),
        "mc": _normalize_canvas_title(_get_embed_role_title("mc", detail_key)),
        "shaman": _normalize_canvas_title(_get_embed_role_title("shaman", detail_key)),
    }
    title = role_titles.get(role_name, "Canvas")
    content_lines = content.splitlines()
    if content_lines and content_lines[0].strip().replace("**", "").strip() == title:
        content = "\n".join(content_lines[1:])
    blocks = _split_canvas_blocks(content)
    role_colors = {
        "news_watcher": discord.Color.blue(),
        "treasure_hunter": discord.Color.dark_gold(),
        "trickster": discord.Color.magenta(),
        "banker": discord.Color.green(),
        "mc": discord.Color.purple(),
        "shaman": discord.Color.dark_purple(),
    }
     
    description = ""
    blocks_to_process = blocks[:4]

    embed = discord.Embed(
        title=_normalize_canvas_title(title),
        description=description,
        color=role_colors.get(role_name, discord.Color.blurple()),
    )

    last_block_index = len(blocks_to_process) - 1
    for index, (block_title, block_lines) in enumerate(blocks_to_process):
        value = _merge_canvas_block_with_auto_response(block_lines, auto_response) if index == last_block_index else _truncate_canvas_field_value("\n".join(block_lines))
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


def _merge_canvas_block_with_auto_response(block_lines: list[str], auto_response: str | None) -> str:
    base_value = "\n".join(block_lines).strip()
    response_value = (auto_response or "").strip()
    if not response_value:
        return _truncate_canvas_field_value(base_value)
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
            "hunter_frequency": "The bot will ask for the hunter execution frequency in hours and update the scheduler.",
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
            "ring_accuse": "The bot will ask for a target user and generate a public ring accusation.",
            "ring_on": "Ring enabled for this server.",
            "ring_off": "Ring disabled for this server.",
            "ring_frequency": "The bot will ask for the ring frequency in hours and update the schedule.",
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
            "mc_clear": "Queue cleared.",
            "mc_history": "Showing recent playback history.",
            "mc_volume": "The bot will ask for a new volume value.",
        },
    }
    behavior_action_map = {
        "greetings_on": "Presence greetings enabled for this server.",
        "greetings_off": "Presence greetings disabled for this server.",
        "welcome_on": "Welcome messages enabled for this server.",
        "welcome_off": "Welcome messages disabled for this server.",
        "commentary_on": "Mission commentary enabled for this server.",
        "commentary_off": "Mission commentary disabled for this server.",
        "commentary_now": "The bot will generate and post commentary immediately.",
        "commentary_frequency": "The bot will ask for the commentary interval in minutes and update the schedule.",
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
        title = title_line.replace("**", "")
    else:
        title = title.replace("**", "")

    embed = discord.Embed(
        title=title,
        description=description or "",
        color=discord.Color.orange() if admin_visible else discord.Color.dark_orange(),
    )
    blocks = _split_canvas_blocks(content)
    visible_blocks = blocks[:4]
    last_block_index = len(visible_blocks) - 1
    for index, (block_title, block_lines) in enumerate(visible_blocks):
        value = _merge_canvas_block_with_auto_response(block_lines, auto_response) if index == last_block_index else _truncate_canvas_field_value("\n".join(block_lines))
        if value:
            embed.add_field(name=block_title, value=value, inline=False)
    embed.set_footer(text=f"General Behavior • {'admin' if admin_visible else 'user'} view")
    return embed

def _get_canvas_role_detail_items(role_name: str, current_detail: str | None, admin_visible: bool, label: str, server_id: str = None) -> list[tuple[str, str]]:
    trickster_personal_map = {
        "dice": "dice",
        "dice_admin": "dice",
        "ring": "ring",
        "ring_admin": "ring",
    }
    trickster_admin_map = {
        "dice": "dice_admin",
        "dice_admin": "dice_admin",
        "ring": "ring_admin",
        "ring_admin": "ring_admin",
    }
    personality_descriptions = _get_personality_descriptions(server_id)
    
    items_map: dict[str, list[tuple[str, str]]] = {
        "news_watcher": [
            ("Personal", "overview"),
        ] + ([("Admin", "admin")] if admin_visible else []),
        "treasure_hunter": [],  # POE2 button added separately with emoticon
        "trickster": (
            # Regular subrole views
            [("Personal", trickster_personal_map.get(current_detail or "dice", "dice"))]
            + ([("Admin", trickster_admin_map.get(current_detail or "dice", "dice_admin"))] if admin_visible else [])
        ) if current_detail in {"dice", "ring"} else (
            # Admin views
            [("Personal", trickster_personal_map.get(current_detail or "dice", "dice"))]
            + ([("Admin", trickster_admin_map.get(current_detail or "dice", "dice_admin"))] if admin_visible else [])
        ) if current_detail in {"dice_admin", "ring_admin"} else [
            # Main trickster overview - show all subroles
            (personality_descriptions.get("role_descriptions", {}).get("trickster", {}).get("subrole_buttons", {}).get("dice", "Dice"), "dice"),
            (personality_descriptions.get("role_descriptions", {}).get("trickster", {}).get("subrole_buttons", {}).get("ring", "Ring"), "ring"),
        ] if current_detail not in {"dice", "ring", "dice_admin", "ring_admin"} else [],
        "banker": [
            # Main banker overview - always show subrole buttons
            (personality_descriptions.get("role_descriptions", {}).get("banker", {}).get("subrole_buttons", {}).get("overview", "Overview"), "overview"),
            (personality_descriptions.get("role_descriptions", {}).get("banker", {}).get("subrole_buttons", {}).get("beggar", "Beggar"), "beggar"),
        ] + ([("Admin", "admin")] if admin_visible else []),
        "mc": [
            ("Personal", "overview"),
        ],
        "shaman": (
            [("Personal", "runes")]
            + ([("Admin", "runes_admin")] if admin_visible else [])
        ) if current_detail in {"runes", "runes_admin"} else [
            (personality_descriptions.get("role_descriptions", {}).get("shaman", {}).get("subrole_buttons", {}).get("runes", "🔮 Runes"), "runes"),
        ] if current_detail not in {"runes", "runes_admin"} else [],
    }
    
    # Special handling for treasure_hunter POE2 views
    if role_name == "treasure_hunter" and current_detail in {"poe2", "league", "admin"}:
        poe2_buttons = [
            (personality_descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("subrole_buttons", {}).get("items", "Items"), "poe2"),
            (personality_descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("subrole_buttons", {}).get("league", "League"), "league"),
        ]
        if admin_visible:
            poe2_buttons.append(
                (personality_descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("subrole_buttons", {}).get("admin", "Admin"), "admin")
            )
        return poe2_buttons
    
    # Special handling for treasure_hunter overview - return empty list (POE2 button added separately with emoticon in ui.py)
    if role_name == "treasure_hunter":
        return []
    
    # Special handling for banker beggar views - show Personal/Admin navigation
    if role_name == "banker":
        if current_detail == "beggar":
            return [
                ("Personal", "beggar"),
                ("Admin", "beggar_admin"),
            ]
        if current_detail == "beggar_admin":
            return [
                ("Personal", "beggar"),
                ("Admin", "beggar_admin"),
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
            ]
        if detail_name == "admin" and admin_visible:
            return [
                (_hunter_text("poe2_on", "POE2: On"), "poe2_on", _hunter_text("poe2_on_description", "Activate POE2 subrole"), "✅"),
                (_hunter_text("poe2_off", "POE2: Off"), "poe2_off", _hunter_text("poe2_off_description", "Deactivate POE2 subrole"), "❌"),
                (_hunter_text("hunter_frequency", "Hunter: Frequency"), "hunter_frequency", _hunter_text("hunter_frequency_description", "Number input target"), "⏰"),
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
        elif detail_name in {"ring", "ring_admin"}:
            ring_dropdown = trickster.get("ring", {}).get("dropdown", {})
            if isinstance(ring_dropdown, dict):
                trickster_descriptions.update(ring_dropdown)
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
        if detail_name == "ring":
            return [
                (_trickster_text("ring_accuse", "Ring: Accuse"), "ring_accuse", _trickster_text("ring_accuse_description", "User target input"), "👁️"),
            ]
        if detail_name == "ring_admin" and admin_visible:
            # Get ring descriptions for action items with robust fallbacks
            _personality_descriptions = _get_personality_descriptions(server_id)
            
            # Safe nested access with fallbacks
            roles_view = _personality_descriptions.get("role_descriptions", {})
            trickster = roles_view.get("trickster", {})
            ring_descriptions = trickster.get("ring", {})
            
            # Ensure ring_descriptions is a dict
            if not isinstance(ring_descriptions, dict):
                ring_descriptions = {}
            
            def _ring_text(key: str, fallback: str) -> str:
                value = ring_descriptions.get(key)
                if value:
                    value = str(value)
                return str(value).strip() if value else fallback
            
            return [
                (_ring_text("ring_on", "Ring: On"), "ring_on", _ring_text("ring_on_description", "Boolean toggle"), "👁️"),
                (_ring_text("ring_off", "Ring: Off"), "ring_off", _ring_text("ring_off_description", "Boolean toggle"), "🚫"),
                (_ring_text("ring_frequency", "Ring: Frequency"), "ring_frequency", _ring_text("ring_frequency_description", "Number input target"), "⏰"),
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
            (_mc_text("mc_clear", "Clear Queue"), "mc_clear", _mc_text("mc_clear_description", "Action"), "🗑️"),
            (_mc_text("mc_history", "Show History"), "mc_history", _mc_text("mc_history_description", "Action"), "📜"),
            (_mc_text("mc_volume", "Set Volume"), "mc_volume", _mc_text("mc_volume_description", "Number input"), "🔊"),
        ]

    return []


def _get_canvas_role_action_items(role_name: str, admin_visible: bool, agent_config: dict | None = None, server_id: str = None) -> list[tuple[str, str, str]]:
    actions: list[tuple[str, str, str]] = []
    for _label, detail_name in _get_canvas_role_detail_items(role_name, admin_visible, None, server_id):
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
        "commentary_on": ("Mission commentary", "On", f"`!talk{_personality_name} on`", "Boolean toggle"),
        "commentary_off": ("Mission commentary", "Off", f"`!talk{_personality_name} off`", "Boolean toggle"),
        "commentary_now": ("Mission commentary", "Run now", f"`!talk{_personality_name} now`", "Action button"),
        "commentary_frequency": ("Mission commentary", "Frequency", f"`!talk{_personality_name} frequency <minutes>`", "Number input"),
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
    
    personalitystatus = _home_text("personalitystatus", "**Personality:**" )
    homedescription = _home_text("description", "Interact with all of the bot feautures from this panel." )
    recentsynthesistitle = _home_text("recentsynthesistitle", "**Recent synthesis**" )
    personalsynthesistitle = _home_text("personalsynthesistitle", "**Personal synthesis with you**" )
    
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
    
    # Initialize records as None
    recent_record = None
    relationship_record = {"summary": "", "updated_at": None, "last_interaction_at": None, "metadata": {}}
    daily_record = None
    
    # Try to get database and records
    database = None
    try:
        database = AgentDatabase(server_id=server_id)
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
    
    status_lines.extend([
        f"{homedescription}",
        "",
        "─" * 45,
        "",
        
    ])
    
    if daily_summary:
        dailymemorytitle = home_messages.get("dailymemorytitle", "**Daily Memory**")
        status_lines.extend([
            "",
            "",
            f"{dailymemorytitle}",
            f"- {daily_summary[:500]}",
            "",
            "─" * 45,
            "",
        ])

    if recent_summary:
        status_lines.extend([
            "",
            "",
            f"{recentsynthesistitle}",
            f"- {recent_summary[:1000]}",
        ])

    if relationship_summary:
        status_lines.extend([
            "",
            "─" * 45,
            "",
            f"{personalsynthesistitle}",
            f"- {relationship_summary[:1000]}",
        ])
    
    # Add final separator
    status_lines.extend([
        "",
        "─" * 45,
        f"{personalitystatus} `{_get_server_personality_name(server_id)}`"
    ])
    
    return "\n".join(status_lines)


def _build_canvas_roles(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the role navigation Canvas view - now uses database as primary source."""
    # Initialize roles system to ensure database is primary source
    from discord_bot.discord_utils import initialize_roles_from_database
    initialize_roles_from_database(agent_config, guild)
    
    # Get roles view messages from personality with fallback
    server_id = core.get_server_key(guild) if guild else None
    _personality_descriptions = _get_personality_descriptions(server_id)
    roles_messages = _personality_descriptions.get("roles_view_messages", {})
    
    # Title and description from descriptions.json with fallback
    title = roles_messages.get("title", f"🎭 ROLE MANAGER - {server_id} 🎭")
    description = roles_messages.get("description", "🌟 The role manager oversees all aspects of the clan. Each role has unique abilities to serve the tribe. Explore different specializations and choose your path.")
    
    # Helper messages
    enabled_status = roles_messages.get("enabled_status", "ACTIVE")
    interval_info = roles_messages.get("interval_info", "⏰ Every {interval}h")
    inactive_status = roles_messages.get("inactive_status", "❌ INACTIVE")
    
    parts = [
        title,  # Add title as first line
        description,
        "──────────────────────────────",
        ""
    ]
    
    # Track active and inactive roles
    active_roles = []
    inactive_roles = []
    
    # Get database for role information
    db = _get_behavior_db_for_guild(guild)
    
    role_descriptions = _personality_descriptions.get("role_descriptions", {})

    def get_role_info(role_key):
        role_data = role_descriptions.get(role_key, {})
        title = str(role_data.get("title", "")).replace("**", "").strip() or role_key
        description = str(role_data.get("description", "")).strip() or role_key
        return {"title": title, "description": description}
    
    # News Watcher
    if is_role_enabled_check("news_watcher", None, guild):
        active_roles.append("news_watcher")
        interval = 1  # Default interval for news_watcher
        role_info = get_role_info("news_watcher")
        parts.append(
            f" **{role_info['title']}** {enabled_status} {interval_info.format(interval=interval)}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # Treasure Hunter
    if is_role_enabled_check("treasure_hunter", None, guild):
        active_roles.append("treasure_hunter")
        interval = 1  # Default interval for treasure_hunter
        role_info = get_role_info("treasure_hunter")
        parts.append(
            f" **{role_info['title']}** {enabled_status} {interval_info.format(interval=interval)}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # Trickster
    if is_role_enabled_check("trickster", None, guild):
        active_roles.append("trickster")
        role_info = get_role_info("trickster")
        parts.append(
            f" **{role_info['title']}** {enabled_status}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # Banker
    if is_role_enabled_check("banker", None, guild):
        active_roles.append("banker")
        interval = 24  # Default interval for banker
        role_info = get_role_info("banker")
        parts.append(
            f" **{role_info['title']}** {enabled_status} {interval_info.format(interval=interval)}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # MC
    if is_role_enabled_check("mc", None, guild):
        active_roles.append("mc")
        role_info = get_role_info("mc")
        parts.append(
            f" **{role_info['title']}** {enabled_status}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # Check for inactive roles
    all_possible_roles = ["news_watcher", "treasure_hunter", "trickster", "banker", "mc"]
    for role in all_possible_roles:
        if role not in active_roles:
            inactive_roles.append(role)
    
    # Add inactive roles section if any exist
    if inactive_roles:
        parts.extend([
            "",
            "**DEACTIVATE ROLES:**",
            ""
        ])
        
        for role in inactive_roles:
            role_info = get_role_info(role)
            role_icons = {
                "news_watcher": "📡",
                "treasure_hunter": "💎", 
                "trickster": "🎭",
                "banker": "💰",
                "mc": "🎵"
            }
            icon = role_icons.get(role, "📋")
            parts.append(f"{icon} {role_info['title']} {inactive_status}")
    
    # If no roles are active, show helpful message
    if not active_roles:
        no_roles_msg = roles_messages.get("no_roles_active", 
            "🌫️ **NO ACTIVE ROLES**\n\nNo specialized roles are currently active. Ask an administrator to activate some roles using `!canvas setup`.\n\n**Available roles to activate:**\n• 📡 News Watcher - News monitoring\n• 💎 Treasure Hunter - Treasure hunting\n• 🎭 Trickster - Games and tricks\n• 💰 Banker - Clan economy\n• 🎵 MC - Music and entertainment"
        )
        parts.append(no_roles_msg)
    
    # Add final separator if there are roles
    if active_roles or inactive_roles:
        parts.append("──────────────────────────────")
    
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
    if role_name == "mc" and is_role_enabled_check("mc", agent_config, guild):
        return build_canvas_role_mc(guild=guild)
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
    if role_name == "mc" and is_role_enabled_check("mc", agent_config, guild):
        return build_canvas_role_mc(guild=guild)
    return None
