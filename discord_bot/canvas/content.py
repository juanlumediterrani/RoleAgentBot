"""Canvas content builders and render helpers."""

from discord_bot import discord_core_commands as core
from roles import news_watcher
from roles.news_watcher import watcher_messages

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
    is_admin, is_duplicate_command, is_role_enabled_check,
    get_greeting_enabled, set_greeting_enabled,
    check_chat_rate_limit, is_already_initialized, mark_as_initialized,
    acquire_connection_lock, acquire_process_lock,
    get_server_key, set_role_enabled,
)
get_news_watcher_db_instance = core.get_news_watcher_db_instance

try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None
get_watcher_messages = core.get_watcher_messages
get_poe2_manager = core.get_poe2_manager
get_banker_db_instance = None  # Now using roles_db directly
get_behavior_db_instance = core.get_behavior_db_instance
_discord_cfg = core._discord_cfg
_personality_name = core._personality_name
_bot_display_name = core._bot_display_name
_insult_cfg = core._insult_cfg
_personality_answers = core._personality_answers
_personality_descriptions = core._personality_descriptions
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
                           role_cmd_name: str, talk_cmd_name: str, admin_visible: bool, server_name: str = "default",
                           author_id: int = 0, guild=None, is_dm: bool = False) -> dict[str, str]:
    """Build the top-level Canvas sections for the current user context."""
    return {
        "home": _build_canvas_home(
            agent_config, greet_name, nogreet_name, welcome_name, nowelcome_name, role_cmd_name, talk_cmd_name,
            admin_visible, server_name, author_id, guild, is_dm
        ),
        "behavior": build_canvas_behavior(
            greet_name, nogreet_name, welcome_name, nowelcome_name, role_cmd_name, talk_cmd_name, admin_visible
        ),
        "roles": _build_canvas_roles(agent_config, admin_visible, guild),
        "personal": _build_canvas_personal(),
        "help": _build_canvas_help(),
    }


def _build_canvas_embed(section_name: str, content: str, admin_visible: bool) -> discord.Embed:
    # Get title from personality descriptions for consistency
    
    help_title = _personality_descriptions.get("help_menu", {}).get("title", f"📚 {_bot_display_name} Canvas - Help & Troubleshooting")
    # Replace {_bot_display_name} placeholder if present
    help_title = help_title.replace("{_bot_display_name}", _bot_display_name)
    
    if section_name == "behavior":
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        behavior_title = behavior_descriptions.get("canvas_conversation_title", f"💬 {_bot_display_name} General Behavior")
        # Replace {_bot} placeholder
        behavior_title = behavior_title.replace("{_bot}", _bot_display_name)
        # Remove ** for embed title
        behavior_title = behavior_title.replace("**", "")
        titles = {
            "home": f"🧭 {_bot_display_name} Canvas Hub",
            "behavior": behavior_title,
            "roles": None,  # Will be set from content
            "personal": f"👤 {_bot_display_name} Canvas - Personal Space",
            "help": help_title,
        }
    else:
        titles = {
            "home": f"🧭 {_bot_display_name} Canvas Hub",
            "behavior": f"⚙️ {_bot_display_name} Canvas - General Behavior",
            "roles": None,  # Will be set from content
            "personal": f"👤 {_bot_display_name} Canvas - Personal Space",
            "help": help_title,
        }
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
        description = "\n".join(description_parts)
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
        description = _personality_descriptions.get("help_menu").get("description", "Find command entry points, troubleshooting hints, and the fastest recovery paths.")
    elif section_name == "behavior":
        description = "Shared bot behavior that sits above any individual role."

    # Fallback title if none was extracted
    if titles.get(section_name) is None:
        titles[section_name] = f"{_bot_display_name} Canvas"

    embed = discord.Embed(
        title=titles.get(section_name, f"{_bot_display_name} Canvas"),
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
        if value:
            embed.add_field(name=block_title, value=value, inline=False)
    embed.set_footer(text=f"Canvas section: {section_name}")
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


def _build_canvas_intro_block(title: str, description: str | None = None) -> str:
    normalized_title = _normalize_canvas_title(title)
    parts = [f"**{normalized_title}**"] if normalized_title else []
    normalized_description = str(description or "").strip()
    if normalized_description:
        parts.append(normalized_description)
    return "\n".join(parts)


def _build_canvas_role_embed(role_name: str, content: str, admin_visible: bool, surface_name: str = "overview", user=None,
                             auto_response: str | None = None) -> discord.Embed:
    """Render a role/detail Canvas screen with a role-specific embed layout."""
    role_descriptions = _personality_descriptions.get("roles_view_messages", {})
    role_titles = {
        "news_watcher": _normalize_canvas_title(role_descriptions.get("news_watcher", {}).get("title", "📡 News Watcher")),
        "treasure_hunter": _normalize_canvas_title(role_descriptions.get("treasure_hunter", {}).get("title", "💎 Treasure Hunter")),
        "trickster": _normalize_canvas_title(role_descriptions.get("trickster", {}).get("title", "🎭 Trickster")),
        "banker": _normalize_canvas_title(role_descriptions.get("banker", {}).get("title", "💰 Banker")),
        "mc": _normalize_canvas_title(role_descriptions.get("mc", {}).get("title", "🎵 MC")),
    }
    blocks = _split_canvas_blocks(content)
    title = role_titles.get(role_name, f"{_bot_display_name} Canvas")
     
    role_colors = {
        "news_watcher": discord.Color.blue(),
        "treasure_hunter": discord.Color.dark_gold(),
        "trickster": discord.Color.magenta(),
        "banker": discord.Color.green(),
        "mc": discord.Color.purple(),
    }
     
    description = ""
     
    if blocks:
        first_block_title, first_block_lines = blocks[0]
        if first_block_title:
            title = _normalize_canvas_title(first_block_title)
        if first_block_lines:
            description = "\n".join(first_block_lines)
        blocks_to_process = blocks[1:4]
    else:
        blocks_to_process = []

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

    embed.set_footer(text=f"{role_titles.get(role_name, role_name)} • {'admin' if admin_visible else 'user'} view")
    
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
        "role_control_open": "The bot will ask which role to enable or disable for this server.",
    }

    if role_name:
        return role_action_map.get(role_name, {}).get(action_name)
    return behavior_action_map.get(action_name)


def _build_canvas_behavior_embed(content: str, admin_visible: bool, auto_response: str | None = None) -> discord.Embed:
    """Render a General Behavior Canvas screen with a specific embed layout."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    title_line = lines[0] if lines else f"{_bot_display_name} Canvas - General Behavior"
    embed = discord.Embed(
        title=title_line.replace("**", ""),
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

def _get_canvas_role_detail_items(role_name: str, admin_visible: bool, current_detail: str | None = None) -> list[tuple[str, str]]:
    trickster_personal_map = {
        "dice": "dice",
        "dice_admin": "dice",
        "ring": "ring",
        "ring_admin": "ring",
        "beggar": "beggar",
        "beggar_admin": "beggar",
        "runes": "",  # Empty string indicates navigation to role overview
        "runes_admin": "runes",
    }
    trickster_admin_map = {
        "dice": "dice_admin",
        "dice_admin": "dice_admin",
        "ring": "ring_admin",
        "ring_admin": "ring_admin",
        "beggar": "beggar_admin",
        "beggar_admin": "beggar_admin",
        "runes": "runes_admin",
        "runes_admin": "runes",
    }
    items_map: dict[str, list[tuple[str, str]]] = {
        "news_watcher": [
            ("Personal", "personal"),
        ] + ([("Admin", "admin")] if admin_visible else []),
        "treasure_hunter": [
            # Main overview shows POE2 subrole button via CanvasTreasureHunterPoe2Button, internal views show navigation
        ] + ([("Items", "personal"), ("League", "league")] if current_detail in {"personal", "league"} else []) + ([("Admin", "admin")] if admin_visible and current_detail in {"personal", "league", "admin"} else []),
        "trickster": (
            # Regular subrole views
            [("Personal", trickster_personal_map.get(current_detail or "dice", "dice"))]
            + ([("Admin", trickster_admin_map.get(current_detail or "dice", "dice_admin"))] if admin_visible else [])
        ) if current_detail in {"dice", "ring", "beggar", "runes"} else (
            # Admin views
            [("Personal", trickster_personal_map.get(current_detail or "dice", "dice"))]
            + ([("Admin", trickster_admin_map.get(current_detail or "dice", "dice_admin"))] if admin_visible else [])
        ) if current_detail in {"dice_admin", "ring_admin", "beggar_admin", "runes_admin"} else [
            # Main trickster overview - show all subroles
            (_personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("subrole_buttons", {}).get("dice", "Dice"), "dice"),
            (_personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("subrole_buttons", {}).get("ring", "Ring"), "ring"),
            (_personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("subrole_buttons", {}).get("beggar", "Beggar"), "beggar"),
            (_personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("subrole_buttons", {}).get("runes", "Runes"), "runes"),
        ] if current_detail not in {"dice", "ring", "beggar", "runes", "dice_admin", "ring_admin", "beggar_admin", "runes_admin"} else [],
        "banker": [
            ("Personal", "overview"),  # Personal maps to overview since they're the same view
        ] + ([("Admin", "admin")] if admin_visible else []),
        "mc": [
            ("Personal", "overview"),
        ],
    }
    
    # Special handling for treasure_hunter POE2 subroles
    if role_name == "treasure_hunter" and current_detail in {"personal", "league", "admin"}:
        # Don't return from items_map, let specific treasure_hunter logic handle these
        pass
    elif role_name == "treasure_hunter":
        # For other treasure_hunter details, use items_map
        return items_map.get(role_name, [])
    else:
        # For non-treasure_hunter roles, use items_map
        return items_map.get(role_name, [])

    # Specific treasure_hunter logic for POE2 subroles
    if role_name == "treasure_hunter":
        # Safe nested access with fallbacks
        roles_view = _personality_descriptions.get("roles_view_messages", {})
        treasure_hunter = roles_view.get("treasure_hunter", {})
        poe2 = treasure_hunter.get("poe2", {})
        
        # Use poe2.dropdown for the dropdown options
        hunter_descriptions = poe2.get("dropdown", {})
        
        # Ensure hunter_descriptions is a dict
        if not isinstance(hunter_descriptions, dict):
            hunter_descriptions = {}
        
        def _hunter_text(key: str, fallback: str) -> str:
            value = hunter_descriptions.get(key)
            return str(value).strip() if value else fallback
        
        if current_detail in {"league", "personal", "admin"}:
            return [
                ("Items", "personal"),
                ("League", "league"),
                ("Admin", "admin"),
            ] if admin_visible else [
                ("Items", "personal"),
                ("League", "league"),
            ]
        # If no specific detail matched, return empty list for treasure_hunter
        return []


def _get_canvas_role_action_items_for_detail(role_name: str, detail_name: str, admin_visible: bool, agent_config: dict | None = None) -> list[tuple[str, str, str]]:
    if role_name == "news_watcher":
        # Get news_watcher descriptions for action items with robust fallbacks
        _personality_descriptions = core._personality_descriptions or {}
        
        # Safe nested access with fallbacks
        roles_view = _personality_descriptions.get("roles_view_messages", {})
        news_watcher = roles_view.get("news_watcher", {})
        
        # Now dropdown is directly in news_watcher, not nested under canvas
        news_descriptions = news_watcher.get("dropdown", {}) if isinstance(news_watcher, dict) else {}
        
        # Ensure news_descriptions is a dict
        if not isinstance(news_descriptions, dict):
            news_descriptions = {}
        
        def _news_text(key: str, fallback: str) -> str:
            value = news_descriptions.get(key)
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
        _personality_descriptions = core._personality_descriptions or {}
        
        # Safe nested access with fallbacks
        roles_view = _personality_descriptions.get("roles_view_messages", {})
        treasure_hunter = roles_view.get("treasure_hunter", {})
        poe2 = treasure_hunter.get("poe2", {})
        
        # Use poe2.dropdown for the dropdown options
        hunter_descriptions = poe2.get("dropdown", {})
        
        # Ensure hunter_descriptions is a dict
        if not isinstance(hunter_descriptions, dict):
            hunter_descriptions = {}
        
        def _hunter_text(key: str, fallback: str) -> str:
            value = hunter_descriptions.get(key)
            return str(value).strip() if value else fallback
        
        if detail_name == "league":
            return [
                (_hunter_text("league_standard", "League: Standard"), "league_standard", _hunter_text("league_standard_description", "Choose POE2 league"), "🏆"),
                (_hunter_text("league_fate_of_the_vaal", "League: Fate of the Vaal"), "league_fate_of_the_vaal", _hunter_text("league_fate_of_the_vaal_description", "Choose POE2 league"), "⚡"),
                (_hunter_text("league_hardcore", "League: Hardcore"), "league_hardcore", _hunter_text("league_hardcore_description", "Choose POE2 league"), "💀"),
            ]
        if detail_name == "personal":
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
        _personality_descriptions = core._personality_descriptions or {}
        
        # Safe nested access with fallbacks
        roles_view = _personality_descriptions.get("roles_view_messages", {})
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
            beggar_dropdown = trickster.get("beggar", {}).get("dropdown", {})
            if isinstance(beggar_dropdown, dict):
                trickster_descriptions.update(beggar_dropdown)
        elif detail_name in {"runes", "runes_admin"}:
            runes_dropdown = trickster.get("nordic_runes", {}).get("dropdown", {})
            if isinstance(runes_dropdown, dict):
                trickster_descriptions.update(runes_dropdown)
        
        # Ensure trickster_descriptions is a dict
        if not isinstance(trickster_descriptions, dict):
            trickster_descriptions = {}
        
        def _trickster_text(key: str, fallback: str) -> str:
            value = trickster_descriptions.get(key)
            return str(value).strip() if value else fallback
        
        if detail_name == "overview":
            # Overview shows navigation to subroles, no specific actions
            return []
        if detail_name == "dice":
            # Get dice_game descriptions for action items
            dice_descriptions = _personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("dice_game", {})
            
            def _dice_text(key: str, fallback: str) -> str:
                value = dice_descriptions.get(key)
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
                runes_enabled = agent_config.get("roles", {}).get("trickster", {}).get("subroles", {}).get("nordic_runes", {}).get("enabled", False)
            
            if not runes_enabled:
                # Runes disabled - only show info actions
                return [
                    ("Runes: Types", "runes_types", "Action"),
                ]
            
            # Runes enabled - show all casting actions
            # Get personality messages for dropdown labels
            roles_messages = _personality_descriptions.get("roles_view_messages", {})
            nordic_runes_messages = roles_messages.get("trickster", {}).get("nordic_runes", {})
            canvas_labels = nordic_runes_messages.get("dropdown", {})
            
            def _runes_text(key: str, fallback: str) -> str:
                value = canvas_labels.get(key)
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
            _personality_descriptions = core._personality_descriptions or {}
            
            # Safe nested access with fallbacks
            roles_view = _personality_descriptions.get("roles_view_messages", {})
            trickster = roles_view.get("trickster", {})
            dice_game = trickster.get("dice_game", {})
            
            # Ensure dice_descriptions is a dict
            if not isinstance(dice_game, dict):
                dice_descriptions = {}
            else:
                dice_descriptions = dice_game
            
            def _dice_text(key: str, fallback: str) -> str:
                value = dice_descriptions.get(key)
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
            _personality_descriptions = core._personality_descriptions or {}
            
            # Safe nested access with fallbacks
            roles_view = _personality_descriptions.get("roles_view_messages", {})
            trickster = roles_view.get("trickster", {})
            dice_game = trickster.get("dice_game", {})
            
            # Ensure ring_descriptions is a dict
            if not isinstance(dice_game, dict):
                ring_descriptions = {}
            else:
                ring_descriptions = dice_game
            
            def _ring_text(key: str, fallback: str) -> str:
                value = ring_descriptions.get(key)
                return str(value).strip() if value else fallback
            
            return [
                (_ring_text("ring_on", "Ring: On"), "ring_on", _ring_text("ring_on_description", "Boolean toggle"), "👁️"),
                (_ring_text("ring_off", "Ring: Off"), "ring_off", _ring_text("ring_off_description", "Boolean toggle"), "🚫"),
                (_ring_text("ring_frequency", "Ring: Frequency"), "ring_frequency", _ring_text("ring_frequency_description", "Number input target"), "⏰"),
            ]
        if detail_name == "beggar":
            return [
                (_trickster_text("beggar_donate", "Beggar: Donate"), "beggar_donate", _trickster_text("beggar_donate_description", "Number input target"), "🙏"),
            ]
        if detail_name == "beggar_admin" and admin_visible:
            return [
                (_trickster_text("beggar_on", "Beggar: On"), "beggar_on", _trickster_text("beggar_on_description", "Boolean toggle"), "✅"),
                (_trickster_text("beggar_off", "Beggar: Off"), "beggar_off", _trickster_text("beggar_off_description", "Boolean toggle"), "❌"),
                (_trickster_text("beggar_frequency", "Beggar: Frequency"), "beggar_frequency", _trickster_text("beggar_frequency_description", "Number input target"), "⏰"),
                (_trickster_text("beggar_force_minigame", "Beggar: Force Minigame"), "beggar_force_minigame", _trickster_text("beggar_force_minigame_description", "Action button"), "🎲"),
            ]
        if detail_name == "runes_admin" and admin_visible:
            return [
                (_trickster_text("runes_on", "Runes: On"), "runes_on", _trickster_text("runes_on_description", "Boolean toggle"), "✅"),
                (_trickster_text("runes_off", "Runes: Off"), "runes_off", _trickster_text("runes_off_description", "Boolean toggle"), "❌"),
            ]
        return []

    if role_name == "banker":
        if detail_name == "overview":
            # Overview shows wallet info, no specific actions
            return []
        if detail_name == "admin" and admin_visible:
            # Get banker descriptions for action items with robust fallbacks
            _personality_descriptions = core._personality_descriptions or {}
            
            # Safe nested access with fallbacks
            roles_view = _personality_descriptions.get("roles_view_messages", {})
            banker = roles_view.get("banker", {})
            
            # Ensure banker_descriptions is a dict
            if not isinstance(banker, dict):
                banker_descriptions = {}
            else:
                banker_descriptions = banker
            
            def _banker_text(key: str, fallback: str) -> str:
                value = banker_descriptions.get(key)
                return str(value).strip() if value else fallback
            
            return [
                (_banker_text("config_tae", "Config: TAE"), "config_tae", _banker_text("config_tae_description", "Number input target"), "💰"),
                (_banker_text("config_bonus", "Config: Bonus"), "config_bonus", _banker_text("config_bonus_description", "Number input target"), "🎁"),
            ]
    
    if role_name == "mc":
        # Get MC descriptions for action items with robust fallbacks
        _personality_descriptions = core._personality_descriptions or {}
        
        # Safe nested access with fallbacks
        roles_view = _personality_descriptions.get("roles_view_messages", {})
        mc = roles_view.get("mc", {})
        
        # Ensure mc_descriptions is a dict
        if not isinstance(mc, dict):
            mc_descriptions = {}
        else:
            mc_descriptions = mc
        
        def _mc_text(key: str, fallback: str) -> str:
            value = mc_descriptions.get(key)
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


def _get_canvas_role_action_items(role_name: str, admin_visible: bool, agent_config: dict | None = None) -> list[tuple[str, str, str]]:
    actions: list[tuple[str, str, str]] = []
    for _label, detail_name in _get_canvas_role_detail_items(role_name, admin_visible):
        actions.extend(_get_canvas_role_action_items_for_detail(role_name, detail_name, admin_visible, agent_config))
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
        "role_control_open": ("Role control", "Choose role + on/off", f"`!role{_personality_name} <role> <on|off>`", "Select menu + boolean toggle"),
    }
    selected = action_map.get(action_name)
    if not selected:
        return None
    surface, state, command_name, input_type = selected
    return "\n".join([
        f"⚙️ {_bot_display_name} Canvas - General Behavior Action Choice\n",
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

def _get_last_saved_memory_fallback(database, memory_type: str, author_id: int = None, user_name: str = None) -> str:
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
    
    # If no saved records found, use the default fallback
    from agent_mind import _get_daily_memory_fallback, _get_recent_memory_fallback, _get_relationship_memory_fallback
    
    if memory_type == "daily":
        return _get_daily_memory_fallback()
    elif memory_type == "recent":
        return _get_recent_memory_fallback()
    elif memory_type == "relationship":
        return _get_relationship_memory_fallback(user_name or "este umano")
    
    return ""


def _build_canvas_home(agent_config: dict, greet_name: str, nogreet_name: str, welcome_name: str, nowelcome_name: str,
                       role_cmd_name: str, talk_cmd_name: str, admin_visible: bool, server_name: str = "default",
                       author_id: int = 0, guild=None, is_dm: bool = False) -> str:
    """Build the main Canvas hub view with status information."""
    enabled_roles = _get_enabled_roles(agent_config)
    roles_text = ", ".join(enabled_roles) if enabled_roles else "none"
    
    # Get home messages from personality with fallback
    home_messages = _personality_descriptions.get("canvas_home_messages", {})
    personalitystatus = home_messages.get("personalitystatus", "**Personality:**" )
    homedescription = home_messages.get("description", "Interact with all of the bot feautures from this panel." )
    recentsynthesistitle = home_messages.get("recentsynthesistitle", "**Recent synthesis**" )
    personalsynthesistitle = home_messages.get("personalsynthesistitle", "**Personal synthesis with you**" )
    
    def _home_text(key: str, fallback: str) -> str:
        value = home_messages.get(key)
        return str(value).strip() if value else fallback
    
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
        database = AgentDatabase(server_name=server_name)
        recent_record = database.get_recent_memory_record()
        relationship_record = database.get_user_relationship_memory(author_id)
        daily_record = database.get_daily_memory_record()
    except Exception as e:
        logger.warning(f"Canvas status could not load memory data for server={server_name}: {e}")
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
            recent_summary = _get_last_saved_memory_fallback(database, "recent")
        else:
            from agent_mind import _get_recent_memory_fallback
            recent_summary = _get_recent_memory_fallback()
    
    if not daily_summary:
        if database:
            daily_summary = _get_last_saved_memory_fallback(database, "daily")
        else:
            from agent_mind import _get_daily_memory_fallback
            daily_summary = _get_daily_memory_fallback()
    
    if not relationship_summary:
        # Try to get user name from guild member or fallback to "este umano"
        user_name = None
        if guild and author_id:
            try:
                member = guild.get_member(author_id)
                if member and member.display_name:
                    user_name = member.display_name
            except:
                pass
        if not user_name:
            user_name = "este umano"
            
        if database:
            relationship_summary = _get_last_saved_memory_fallback(database, "relationship", author_id, user_name)
        else:
            from agent_mind import _get_relationship_memory_fallback
            relationship_summary = _get_relationship_memory_fallback(user_name)
    
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
            f"- {daily_summary[:900]}",
            "",
            "─" * 45,
            "",
        ])
    
    if recent_summary:
        status_lines.extend([
            "",
            "",
            f"{recentsynthesistitle}",
            f"- {recent_summary[:900]}",
        ])
    
    if relationship_summary:
        status_lines.extend([
            "",
            "─" * 45,
            "",
            f"{personalsynthesistitle}",
            f"- {relationship_summary[:900]}",
        ])
    
    # Add final separator
    status_lines.extend([
        "",
        "─" * 45,
        f"{personalitystatus} `{_personality_name}`"
    ])
    
    return "\n".join(status_lines)


def _build_canvas_roles(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the role navigation Canvas view - now uses database as primary source."""
    # Initialize roles system to ensure database is primary source
    from discord_bot.discord_utils import initialize_roles_from_database
    initialize_roles_from_database(agent_config)
    
    # Get roles view messages from personality with fallback
    roles_messages = _personality_descriptions.get("roles_view_messages", {})
    server_name = "Server"  # We don't have guild context here
    
    # Title and description from descriptions.json with fallback
    title = roles_messages.get("title", f"🎭 ROLE MANAGER - {server_name} 🎭")
    description = roles_messages.get("description", "🌟 Putre the role manager oversees all aspects of the clan. Each role has unique abilities to serve the tribe. Explore different specializations and choose your path.")
    
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
    
    # Helper function to get role info with fallback
    def get_role_info(role_key):
        # Role info is directly under the role key in roles_view_messages
        role_info = roles_messages.get(role_key, {})
        fallback_titles = {
            "news_watcher": "News Watcher",
            "treasure_hunter": "Treasure Hunter", 
            "trickster": "Trickster",
            "banker": "Banker",
            "mc": "MC"
        }
        fallback_descriptions = {
            "news_watcher": "News monitoring for the clan",
            "treasure_hunter": "Treasure hunting and POE2 monitoring",
            "trickster": "Games, tricks, and accusations",
            "banker": "Clan economy and personal wallets",
            "mc": "Music playback and queue management"
        }
        
        return {
            "title": role_info.get("title", fallback_titles.get(role_key, role_key)),
            "description": role_info.get("description", fallback_descriptions.get(role_key, "Role functionality"))
        }
    
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
        f"👤 {_bot_display_name} Canvas - Personal Space\n\n"
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


def _build_canvas_help() -> str:
    """Build the help and troubleshooting Canvas view."""
    #2nd block for this view
    help_messages = _personality_descriptions.get("help_menu", {})
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
    if role_name == "mc" and is_role_enabled_check("mc", agent_config, guild):
        return build_canvas_role_mc()
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
    if role_name == "mc" and is_role_enabled_check("mc", agent_config, guild):
        return build_canvas_role_mc()
    return None
