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
    get_server_key, get_role_interval_hours, set_role_enabled,
)
get_news_watcher_db_instance = core.get_news_watcher_db_instance

try:
    from roles.trickster.subroles.dice_game.db_dice_game import get_dice_game_db_instance
except Exception:
    get_dice_game_db_instance = None
get_watcher_messages = core.get_watcher_messages
get_poe2_manager = core.get_poe2_manager
get_beggar_db_instance = core.get_beggar_db_instance
get_banker_db_instance = core.get_banker_db_instance
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
from .canvas_treasurehunter import (
    build_canvas_role_treasure_hunter,
    build_canvas_role_treasure_hunter_detail,
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
            "roles": "🎭 Roles",
            "personal": f"👤 {_bot_display_name} Canvas - Personal Space",
            "help": help_title,
        }
    else:
        titles = {
            "home": f"🧭 {_bot_display_name} Canvas Hub",
            "behavior": f"⚙️ {_bot_display_name} Canvas - General Behavior",
            "roles": "🎭 Roles",
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
            "runes_history": "Show your recent rune casting history.",
            "runes_types": "Show available rune reading types and descriptions.",
            "runes_help": "Show help and instructions for rune casting.",
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
    }
    trickster_admin_map = {
        "dice": "dice_admin",
        "dice_admin": "dice_admin",
        "ring": "ring_admin",
        "ring_admin": "ring_admin",
        "beggar": "beggar_admin",
        "beggar_admin": "beggar_admin",
    }
    items_map: dict[str, list[tuple[str, str]]] = {
        "news_watcher": [
            ("Personal", "personal"),
        ] + ([("Admin", "admin")] if admin_visible else []),
        "treasure_hunter": [
            # Show Items and League buttons in POE2 subrol views, but not in main treasure_hunter overview
        ] + ([("Items", "personal"), ("League", "league")] if current_detail in {"personal", "league"} else []) + ([("Admin", "admin")] if admin_visible and current_detail in {"personal", "league", "admin"} else []),
        "trickster": (
            [("Personal", trickster_personal_map.get(current_detail or "dice", "dice"))]
            + ([("Admin", trickster_admin_map.get(current_detail or "dice", "dice_admin"))] if admin_visible else [])
        ) if current_detail in {"dice", "ring", "beggar", "runes", "dice_admin", "ring_admin", "beggar_admin"} else [
            (_personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("subrole_buttons", {}).get("dice", "Dice"), "dice"),
            (_personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("subrole_buttons", {}).get("ring", "Ring"), "ring"),
            (_personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("subrole_buttons", {}).get("beggar", "Beggar"), "beggar"),
            (_personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("subrole_buttons", {}).get("runes", "Runes"), "runes"),
        ],
        "banker": [
            ("Wallet", "overview"),  # Wallet maps to overview since they're the same view
        ] + ([("Admin", "admin")] if admin_visible else []),
        "mc": [
            ("Overview", "overview"),
        ],
    }
    return items_map.get(role_name, [])


def _get_canvas_role_action_items_for_detail(role_name: str, detail_name: str, admin_visible: bool) -> list[tuple[str, str, str]]:
    if role_name == "news_watcher":
        if detail_name in {"personal", "overview"}:  # Same view for both
            return [
                ("Method: Flat", "method_flat", "Set subscription method to flat"),
                ("Method: Keyword", "method_keyword", "Set subscription method to keyword"),
                ("Method: General", "method_general", "Set subscription method to general"),
                ("Subscribe: Categories", "subscribe_categories", "Browse and subscribe to categories"),
                ("List: Keywords", "list_keywords", "View your configured keywords"),
                ("List: Premises", "list_premises", "View your configured premises"),
            ]
        if detail_name == "admin" and admin_visible:
            return [
                ("Watcher: Frequency", "watcher_frequency", "Number input target"),
                ("Watcher: Run Now", "watcher_run_now", "Action"),
            ]
        return []

    if role_name == "treasure_hunter":
        if detail_name == "league":
            return [
                ("League: Standard", "league_standard", "Choose POE2 league"),
                ("League: Fate of the Vaal", "league_fate_of_the_vaal", "Choose POE2 league"),
                ("League: Hardcore", "league_hardcore", "Choose POE2 league"),
            ]
        if detail_name == "personal":
            return [
                ("Items: Add", "poe2_item_add", "Add a new POE2 item"),
                ("Items: Remove", "poe2_item_remove", "Remove a tracked POE2 item"),
            ]
        if detail_name == "admin" and admin_visible:
            return [
                ("POE2: On", "poe2_on", "Activate POE2 subrole"),
                ("POE2: Off", "poe2_off", "Deactivate POE2 subrole"),
                ("Hunter: Frequency", "hunter_frequency", "Number input target"),
            ]
        return []

    if role_name == "trickster":
        if detail_name == "dice":
            return [
                ("Dice: Play", "dice_play", "Play action"),
                ("Dice: Ranking", "dice_ranking", "Ranking action"),
                ("Dice: History", "dice_history", "History action"),
                ("Dice: Help", "dice_help", "Help action"),
            ]
        if detail_name == "runes":
            return [
                ("Runes: Single Cast", "runes_single", "Text input target"),
                ("Runes: Three Cast", "runes_three", "Text input target"),
                ("Runes: Cross Cast", "runes_cross", "Text input target"),
                ("Runes: History", "runes_history", "Action"),
                ("Runes: Types", "runes_types", "Action"),
                ("Runes: Help", "runes_help", "Action"),
            ]
        if detail_name == "dice_admin" and admin_visible:
            return [
                ("Announcements: On", "announcements_on", "Dice config"),
                ("Announcements: Off", "announcements_off", "Dice config"),
                ("Dice: Fixed Bet", "dice_fixed_bet", "Number input target"),
                ("Dice: Pot Value", "dice_pot_value", "Number input target"),
            ]
        if detail_name == "ring":
            return [
                ("Ring: Accuse", "ring_accuse", "User target input"),
            ]
        if detail_name == "ring_admin" and admin_visible:
            return [
                ("Ring: On", "ring_on", "Boolean toggle"),
                ("Ring: Off", "ring_off", "Boolean toggle"),
                ("Ring: Frequency", "ring_frequency", "Number input target"),
            ]
        if detail_name == "beggar":
            return [
                ("Beggar: Donate", "beggar_donate", "Number input target"),
            ]
        if detail_name == "beggar_admin" and admin_visible:
            return [
                ("Beggar: On", "beggar_on", "Boolean toggle"),
                ("Beggar: Off", "beggar_off", "Boolean toggle"),
                ("Beggar: Frequency", "beggar_frequency", "Number input target"),
            ]
        return []

    if role_name == "banker":
        if detail_name == "admin" and admin_visible:
            return [
                ("Config: TAE", "config_tae", "Number input target"),
                ("Config: Bonus", "config_bonus", "Number input target"),
            ]
    
    if role_name == "mc":
        return [
            ("Play Now", "mc_play", "Text input target"),
            ("Add to Queue", "mc_add", "Text input target"),
            ("Skip Song", "mc_skip", "Action"),
            ("Pause", "mc_pause", "Action"),
            ("Resume", "mc_resume", "Action"),
            ("Stop", "mc_stop", "Action"),
            ("View Queue", "mc_queue", "Action"),
            ("Clear Queue", "mc_clear", "Action"),
            ("Show History", "mc_history", "Action"),
            ("Set Volume", "mc_volume", "Number input"),
        ] if detail_name == "overview" else []

    return []


def _get_canvas_role_action_items(role_name: str, admin_visible: bool) -> list[tuple[str, str, str]]:
    actions: list[tuple[str, str, str]] = []
    for _label, detail_name in _get_canvas_role_detail_items(role_name, admin_visible):
        actions.extend(_get_canvas_role_action_items_for_detail(role_name, detail_name, admin_visible))
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
    
    try:
        database = AgentDatabase(server_name=server_name)
        recent_record = database.get_recent_memory_record()
        relationship_record = database.get_user_relationship_memory(author_id)
        daily_record = database.get_daily_memory_record()
    except Exception as e:
        logger.warning(f"Canvas status could not load memory data for server={server_name}: {e}")
        recent_record = None
        relationship_record = {"summary": "", "updated_at": None, "last_interaction_at": None, "metadata": {}}
        daily_record = None
    
    recent_summary = (recent_record or {}).get("summary", "").strip()
    relationship_summary = (relationship_record or {}).get("summary", "").strip()
    daily_summary = (daily_record or {}).get("summary", "").strip()
    
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
    title = roles_messages.get("title", f"🎭 PUTRE ROLE MANAGER - {server_name} 🎭\n")
    description = roles_messages.get("description", "🌟 Putre the role manager oversees all aspects of the clan. Each role has unique abilities to serve the tribe. Explore different specializations and choose your path.")
    
    # Helper messages
    enabled_status = roles_messages.get("enabled_status", "ACTIVE")
    interval_info = roles_messages.get("interval_info", "⏰ Every {interval}h")
    inactive_status = roles_messages.get("inactive_status", "❌ INACTIVE")
    
    parts = [
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
        interval = get_role_interval_hours("news_watcher", None, guild, 1)
        role_info = get_role_info("news_watcher")
        parts.append(
            f" **{role_info['title']}** {enabled_status} {interval_info.format(interval=interval)}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # Treasure Hunter
    if is_role_enabled_check("treasure_hunter", None, guild):
        active_roles.append("treasure_hunter")
        interval = get_role_interval_hours("treasure_hunter", None, guild, 1)
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
        interval = get_role_interval_hours("banker", None, guild, 24)
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
    if role_name == "mc" and (agent_config or {}).get("roles", {}).get("mc", {}).get("enabled", False):
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
        return build_canvas_role_trickster_detail(detail_name, admin_visible, guild, author_id)
    if role_name == "banker" and is_role_enabled_check("banker", agent_config, guild):
        return build_canvas_role_banker_detail(detail_name, admin_visible, guild, author_id)
    if role_name == "mc" and (agent_config or {}).get("roles", {}).get("mc", {}).get("enabled", False):
        return build_canvas_role_mc()
    return None
