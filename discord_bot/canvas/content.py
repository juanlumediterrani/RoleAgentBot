"""Canvas content builders and render helpers."""

from discord_bot import discord_core_commands as core

os = core.os
asyncio = core.asyncio
discord = core.discord
Path = core.Path
AgentDatabase = core.AgentDatabase
logger = core.logger
PERSONALITY = core.PERSONALITY
think = core.think
AGENT_CFG = core.AGENT_CFG
is_admin = core.is_admin
is_duplicate_command = core.is_duplicate_command
send_dm_or_channel = core.send_dm_or_channel
send_embed_dm_or_channel = core.send_embed_dm_or_channel
set_greeting_enabled = core.set_greeting_enabled
get_greeting_enabled = core.get_greeting_enabled
is_role_enabled_check = core.is_role_enabled_check
get_server_key = core.get_server_key
get_role_interval_hours = core.get_role_interval_hours
set_role_enabled = core.set_role_enabled
get_banker_db_instance = core.get_banker_db_instance
get_news_watcher_db_instance = core.get_news_watcher_db_instance

try:
    from roles.trickster.subroles.dice_game.db_dice_game import get_dice_game_db_instance
except Exception:
    get_dice_game_db_instance = None
get_watcher_messages = core.get_watcher_messages
get_poe2_manager = core.get_poe2_manager
get_beggar_db_instance = core.get_beggar_db_instance
get_behaviors_db_instance = core.get_behaviors_db_instance
get_taboo_db_instance = core.get_taboo_db_instance
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

def _build_canvas_sections(agent_config: dict, greet_name: str, nogreet_name: str, welcome_name: str, nowelcome_name: str,
                           role_cmd_name: str, talk_cmd_name: str, admin_visible: bool, server_name: str = "default",
                           author_id: int = 0, guild=None) -> dict[str, str]:
    """Build the top-level Canvas sections for the current user context."""
    return {
        "home": _build_canvas_home(
            agent_config, greet_name, nogreet_name, welcome_name, nowelcome_name, role_cmd_name, talk_cmd_name,
            admin_visible, server_name, author_id
        ),
        "behavior": _build_canvas_behavior(
            greet_name, nogreet_name, welcome_name, nowelcome_name, role_cmd_name, talk_cmd_name, admin_visible
        ),
        "roles": _build_canvas_roles(agent_config, admin_visible, guild),
        "personal": _build_canvas_personal(),
        "help": _build_canvas_help(),
    }


def _build_canvas_embed(section_name: str, content: str, admin_visible: bool) -> discord.Embed:
    # Get behavior title from personality descriptions for consistency
    if section_name == "behavior":
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        behavior_title = behavior_descriptions.get("canvas_conversation_title", f"💬 {_bot_display_name} Comportamiento General")
        # Replace {_bot} placeholder
        behavior_title = behavior_title.replace("{_bot}", _bot_display_name)
        # Remove ** for embed title
        behavior_title = behavior_title.replace("**", "")
        titles = {
            "home": f"🧭 {_bot_display_name} Canvas Hub",
            "behavior": behavior_title,
            "roles": "🎭 Roles de Putre 🎭",
            "personal": f"👤 {_bot_display_name} Canvas - Personal Space",
            "help": f"📚 {_bot_display_name} Canvas - Help & Troubleshooting",
        }
    else:
        titles = {
            "home": f"🧭 {_bot_display_name} Canvas Hub",
            "behavior": f"⚙️ {_bot_display_name} Canvas - General Behavior",
            "roles": "🎭 Roles de Putre 🎭",
            "personal": f"👤 {_bot_display_name} Canvas - Personal Space",
            "help": f"📚 {_bot_display_name} Canvas - Help & Troubleshooting",
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
        description = "Find command entry points, troubleshooting hints, and the fastest recovery paths."
    elif section_name == "behavior":
        description = "Shared bot behavior that sits above any individual role."

    embed = discord.Embed(
        title=titles.get(section_name, f"{_bot_display_name} Canvas"),
        description=description[:4096],
        color=colors.get(section_name, discord.Color.blurple()),
    )
    blocks = _split_canvas_blocks(content)
    for block_title, block_lines in blocks[:4]:
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


def _get_canvas_role_gui_controls(role_name: str, surface_name: str, admin_visible: bool) -> list[str]:
    controls_map: dict[str, dict[str, list[str]]] = {
        "news_watcher": {
            "overview": [
                "- Buttons: open `Personal` or `Admin`",
                "- Boolean toggle: quick alerts on/off (`watchernotify`)",
                "- Text input: category or feed to subscribe",
            ],
            "personal": [
                "- Select menu: subscription method (flat, keyword, general)",
                "- Select menu: category/feed selection before subscribing",
                "- Text input: feed id when a category requires a specific source",
                "- Boolean toggle: critical alerts on/off",
            ],
            "admin": [
                "- Select menu: filtering state `flat`, `keyword`, or `general`",
                "- Number input: watcher frequency in hours",
                "- Text input: category/feed for channel subscription",
                "- Boolean action: force one iteration now",
            ],
        },
        "treasure_hunter": {
            "overview": [
                "- Buttons: open `Items`, `League`, or `Admin`",
                "- Text input: tracked item name",
                "- Select menu: league selection",
            ],
            "personal": [
                "- Text input: item name to add/remove",
                "- Select menu: tracked items shortcuts",
                "- Select menu: open league management",
            ],
            "league": [
                "- Select menu: choose target league",
                "- Text input: custom league name if needed",
            ],
            "admin": [
                "- Boolean toggle: POE2 subrole on/off",
                "- Number input: execution frequency in hours",
            ],
        },
        "trickster": {
            "overview": [
                "- Buttons: open `Dice`, `Ring`, or `Beggar`",
                "- Boolean toggles: subrole enable/disable where applicable",
            ],
            "dice": [
                "- Number input: fixed bet amount",
                "- Boolean toggle: announcements on/off",
                "- Action button: play now",
            ],
            "ring": [
                "- Boolean toggle: ring on/off",
                "- Number input: ring frequency in hours",
                "- User picker/text input: accusation target",
            ],
            "beggar": [
                "- Boolean toggle: beggar on/off",
                "- Number input: beggar frequency in hours",
            ],
        },
        "banker": {
            "overview": [
                "- Buttons: open `Wallet`, `Guide`, or `Admin`",
                "- Number input: economy values for admin setup",
            ],
            "wallet": [
                "- Action button: refresh wallet view",
                "- Select menu: recent wallet/help shortcuts",
            ],
            "guide": [
                "- Select menu: choose `Wallet` or `Admin` focus",
            ],
            "admin": [
                "- Number input: daily allowance (`tae`)",
                "- Number input: opening bonus",
            ],
        },
        "mc": {
            "overview": [
                "- Text input: song/query to play or add",
                "- Select menu: queue/history actions",
                "- Boolean-style action buttons: pause/resume/stop",
            ],
        },
    }
    role_controls = controls_map.get(role_name, {})
    controls = role_controls.get(surface_name, [])
    if not admin_visible:
        controls = [line for line in controls if "admin" not in line.lower()]
    return controls


def _build_canvas_role_embed(role_name: str, content: str, admin_visible: bool, surface_name: str = "overview", user=None,
                             auto_response: str | None = None) -> discord.Embed:
    """Render a role/detail Canvas screen with a role-specific embed layout."""
    role_titles = {
        "news_watcher": "📡 News Watcher",
        "treasure_hunter": "💎 Treasure Hunter",
        "trickster": "🎭 Trickster",
        "banker": "💰 Banker",
        "mc": "🎵 MC",
    }
    role_colors = {
        "news_watcher": discord.Color.blue(),
        "treasure_hunter": discord.Color.dark_gold(),
        "trickster": discord.Color.magenta(),
        "banker": discord.Color.green(),
        "mc": discord.Color.purple(),
    }

    # Process all content as blocks, including intro
    blocks = _split_canvas_blocks(content)
    
    # Use the first block as title and description if available
    title = f"{_bot_display_name} Canvas"
    description = ""
    
    if blocks:
        first_block_title, first_block_lines = blocks[0]
        if first_block_lines:
            title = first_block_title
            # Use ALL lines from first block as description, not just the first one
            description = "\n".join(first_block_lines)
            # Skip the first block for field processing
        blocks_to_process = blocks[1:4]  # Take next 3 blocks
    else:
        blocks_to_process = []

    embed = discord.Embed(
        title=title.replace("**", ""),
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
        "taboo_list": "Showing the current taboo keywords.",
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


def _get_canvas_behavior_action_items(admin_visible: bool) -> list[tuple[str, str, str]]:
    if not admin_visible:
        return []
    return [
        ("Greetings: On", "greetings_on", "Boolean toggle"),
        ("Greetings: Off", "greetings_off", "Boolean toggle"),
        ("Welcome: On", "welcome_on", "Boolean toggle"),
        ("Welcome: Off", "welcome_off", "Boolean toggle"),
        ("Commentary: On", "commentary_on", "Boolean toggle"),
        ("Commentary: Off", "commentary_off", "Boolean toggle"),
        ("Commentary: Now", "commentary_now", "Action"),
        ("Role Control", "role_control_open", "Select role and boolean state"),
    ]


def _get_canvas_behavior_action_items_for_detail(detail_name: str, admin_visible: bool) -> list[tuple[str, str, str]]:
    if not admin_visible:
        return []
    items_map: dict[str, list[tuple[str, str, str]]] = {
        "greetings": [
            ("Greetings: On", "greetings_on", "Boolean toggle"),
            ("Greetings: Off", "greetings_off", "Boolean toggle"),
        ],
        "welcome": [
            ("Welcome: On", "welcome_on", "Boolean toggle"),
            ("Welcome: Off", "welcome_off", "Boolean toggle"),
        ],
        "commentary": [
            ("Commentary: On", "commentary_on", "Boolean toggle"),
            ("Commentary: Off", "commentary_off", "Boolean toggle"),
            ("Commentary: Now", "commentary_now", "Action"),
            ("Commentary: Frequency", "commentary_frequency", "Number input target"),
        ],
        "taboo": [
            ("Taboo: On", "taboo_on", "Boolean toggle"),
            ("Taboo: Off", "taboo_off", "Boolean toggle"),
            ("Taboo: List", "taboo_list", "Action"),
            ("Taboo: Add Keyword", "taboo_add", "Text input target"),
            ("Taboo: Remove Keyword", "taboo_del", "Text input target"),
        ],
        "role_control": [
            ("Role Control", "role_control_open", "Select role and boolean state"),
        ],
    }
    return items_map.get(detail_name, [])


def _get_canvas_behavior_detail_items(admin_visible: bool) -> list[tuple[str, str]]:
    items = [("Conversation", "conversation")]
    if admin_visible:
        items.extend([
            ("Greetings", "greetings"),
            ("Welcome", "welcome"),
            ("Commentary", "commentary"),
            ("Taboo", "taboo"),
            ("Role Control", "role_control"),
        ])
    return items


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
            ("Items", "personal"),
            ("League", "league"),
        ] + ([("Admin", "admin")] if admin_visible else []),
        "trickster": (
            [("Personal", trickster_personal_map.get(current_detail or "dice", "dice"))]
            + ([("Admin", trickster_admin_map.get(current_detail or "dice", "dice_admin"))] if admin_visible else [])
        ) if current_detail in {"dice", "ring", "beggar", "dice_admin", "ring_admin", "beggar_admin"} else [
            ("Dice", "dice"),
            ("Ring", "ring"),
            ("Beggar", "beggar"),
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

    if role_name == "banker" and admin_visible and detail_name == "admin":
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
        "taboo_list": ("Taboo", "List", "`!taboo list`", "Action"),
        "taboo_add": ("Taboo", "Add keyword", "`!taboo add <keyword>`", "Text input"),
        "taboo_del": ("Taboo", "Remove keyword", "`!taboo del <keyword>`", "Text input"),
        "role_control_open": ("Role control", "Choose role + on/off", f"`!role{_personality_name} <role> <on|off>`", "Select menu + boolean toggle"),
    }
    selected = action_map.get(action_name)
    if not selected:
        return None
    surface, state, command_name, input_type = selected
    return "\n".join([
        f"⚙️ **{_bot_display_name} Canvas - General Behavior Action Choice**\n",
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


def _build_canvas_role_action_view(role_name: str, action_name: str, admin_visible: bool) -> str | None:
    if role_name == "news_watcher":
        # Method selection actions
        method_map = {
            "method_flat": ("Flat Method", "`!watcher method flat`", "All news with AI opinions.", "Server-wide method selection"),
            "method_keyword": ("Keyword Method", "`!watcher method keyword`", "News filtered by keywords.", "Server-wide method selection"),
            "method_general": ("General Method", "`!watcher method general`", "AI critical news analysis.", "Server-wide method selection"),
        }
        
        # Subscription and listing actions
        subscription_map = {
            "subscribe_categories": ("Subscribe Categories", "`!watcher subscribe <method> <category> [feed_id]`", "Browse and subscribe to news categories.", "Category selection + method"),
            "list_keywords": ("List Keywords", "`!watcher keywords list`", "View your configured keywords.", "Display current keywords"),
            "list_premises": ("List Premises", "`!watcher premises list`", "View your AI analysis premises.", "Display current premises"),
        }
        
        # Check subscription/listing actions first
        selected = subscription_map.get(action_name)
        if selected:
            label, command_name, explanation, input_type = selected
            return "\n".join([
                f"📡 **{_bot_display_name} Canvas - News Watcher: {label}**\n",
                "**Selected option**",
                f"- Command: {command_name}",
                f"- Meaning: {explanation}",
                "",
                "**GUI input model**",
                f"- Input type: {input_type}",
                "- Best use: manage your subscriptions and configuration",
                "",
                "**Next step**",
                "- Browse available options and make selections",
                "- Configure your filtering preferences",
            ])
        
        # Check method actions
        selected = method_map.get(action_name)
        if selected:
            label, command_name, explanation, input_type = selected
            return "\n".join([
                f"📡 **{_bot_display_name} Canvas - News Watcher: {label}**\n",
                "**Selected option**",
                f"- Command: {command_name}",
                f"- Meaning: {explanation}",
                "",
                "**GUI input model**",
                f"- Input type: {input_type}",
                "- Best use: set default behavior for new subscriptions",
                "",
                "**Next step**",
                "- Choose method that matches your news preferences",
                "- Configure specific filtering if needed",
            ])

    if role_name == "treasure_hunter":
        league_map = {
            "league_standard": "Standard",
            "league_fate_of_the_vaal": "Fate of the Vaal",
            "league_hardcore": "Hardcore",
        }
        selected_league = league_map.get(action_name)
        if selected_league:
            return "\n".join([
                f"💎 **{_bot_display_name} Canvas - Treasure Hunter League Choice**\n",
                "**Selected option**",
                f"- League: `{selected_league}`",
                f"- Command: `!hunter poe2 league \"{selected_league}\"`",
                "",
                "**GUI input model**",
                "- Input type: select menu with league options",
                "- Fallback: text input for a custom league name if needed",
                "",
                "**Next step**",
                "- Apply the league and then review your tracked items",
            ])
        if action_name == "poe2_item_add":
            return "\n".join([
                f"💎 **{_bot_display_name} Canvas - Treasure Hunter Add Item**\n",
                "**Selected option**",
                "- Command: `!hunter poe2 add \"Item Name\"`",
                "",
                "**GUI input model**",
                "- Input type: text input",
                "- Validation: exact POE2 item name",
            ])
        if action_name == "poe2_item_remove":
            return "\n".join([
                f"💎 **{_bot_display_name} Canvas - Treasure Hunter Remove Item**\n",
                "**Selected option**",
                "- Command: `!hunter poe2 del \"Item Name\"`",
                "",
                "**GUI input model**",
                "- Input type: text input",
                "- Validation: item name or visible item number",
            ])
        if action_name in {"poe2_on", "poe2_off"} and admin_visible:
            state = "On" if action_name == "poe2_on" else "Off"
            return "\n".join([
                f"💎 **{_bot_display_name} Canvas - Treasure Hunter POE2 Toggle**\n",
                "**Selected option**",
                f"- State: {state}",
                f"- Command: `!hunter poe2 {'on' if action_name == 'poe2_on' else 'off'}`",
                "",
                "**GUI input model**",
                "- Input type: boolean selector",
            ])
        if action_name == "hunter_frequency" and admin_visible:
            return "\n".join([
                f"💎 **{_bot_display_name} Canvas - Treasure Hunter Frequency**\n",
                "**Selected option**",
                "- Command: `!hunterfrequency <hours>`",
                "- Meaning: adjust how often treasure hunter runs automatically",
                "",
                "**GUI input model**",
                "- Input type: number input",
                "- Valid range: 1 to 168 hours",
                "",
                "**Next step**",
                "- Choose a stable interval before enabling more tracked items",
            ])

    if role_name == "trickster":
        action_map = {
            "ring_on": ("Ring", "On", "`!trickster ring enable`", "Boolean toggle"),
            "ring_off": ("Ring", "Off", "`!trickster ring disable`", "Boolean toggle"),
            "ring_frequency": ("Ring", "Frequency", "`!trickster ring frequency <hours>`", "Number input"),
            "ring_target": ("Ring", "Target", "`!trickster ring target @user`", "User input"),
            "beggar_on": ("Beggar", "On", "`!trickster beggar enable`", "Boolean toggle"),
            "beggar_off": ("Beggar", "Off", "`!trickster beggar disable`", "Boolean toggle"),
            "beggar_frequency": ("Beggar", "Frequency", "`!trickster beggar frequency <hours>`", "Number input"),
            "beggar_donate": ("Beggar", "Donate", "`!trickster beggar donate <gold>`", "Number input"),
            "announcements_on": ("Dice announcements", "On", "`!dice config announcements on`", "Boolean toggle"),
            "announcements_off": ("Dice announcements", "Off", "`!dice config announcements off`", "Boolean toggle"),
            "dice_fixed_bet": ("Dice fixed bet", "Set", "`!dice config bet <amount>`", "Number input"),
            "dice_pot_value": ("Dice pot", "Set", "Banker wallet update", "Number input"),
            "dice_play": ("Dice", "Play", "`!dice play`", "Action"),
            "dice_ranking": ("Dice", "Ranking", "`!dice ranking`", "Action"),
            "dice_history": ("Dice", "History", "`!dice history`", "Action"),
            "dice_help": ("Dice", "Help", "`!dice help`", "Action"),
        }
        selected = action_map.get(action_name)
        if selected:
            surface, value, command_name, input_type = selected
            return "\n".join([
                f"🎭 **{_bot_display_name} Canvas - Trickster Action Choice**\n",
                "**Selected option**",
                f"- Surface: {surface}",
                f"- State: {value}",
                f"- Command: {command_name}",
                "",
                "**GUI input model**",
                f"- Input type: {input_type}",
                "",
                "**Next step**",
                "- Apply the change and observe the subrole behavior on the server",
            ])

    if role_name == "banker" and admin_visible:
        config_map = {
            "config_tae": ("Daily allowance", "Configure daily TAE from unified view"),
            "config_bonus": ("Opening bonus", "Configure opening bonus from unified view"),
        }
        selected = config_map.get(action_name)
        if selected:
            label, command_name = selected
            return "\n".join([
                f"💰 **{_bot_display_name} Canvas - Banker Config Target**\n",
                "**Selected option**",
                f"- Target: {label}",
                f"- Command pattern: {command_name}",
                "",
                "**GUI input model**",
                "- Input type: number input",
                "- Validation: accept only positive numeric values",
                "",
                "**Next step**",
                "- Inspect the current value before changing it",
            ])

    if role_name == "mc":
        playback_map = {
            "playback_play": ("Play", "`!mc play \"song name\"`", "Text input"),
            "playback_add": ("Add", "`!mc add \"song name\"`", "Text input"),
            "queue_show": ("Queue", "`!mc queue`", "Action button"),
        }
        selected = playback_map.get(action_name)
        if selected:
            label, command_name, input_type = selected
            return "\n".join([
                f"🎵 **{_bot_display_name} Canvas - MC Action Choice**\n",
                "**Selected option**",
                f"- Action: {label}",
                f"- Command: {command_name}",
                "",
                "**GUI input model**",
                f"- Input type: {input_type}",
                "",
                "**Next step**",
                "- Use this action from a server voice-channel context",
            ])

    if role_name == "mc":
        action_map = {
            "mc_play": ("Play Now", "`!mc play <song>`", "Immediately play a song (replaces current)", "Text input with song name/URL"),
            "mc_add": ("Add to Queue", "`!mc add <song>`", "Add song to end of queue", "Text input with song name/URL"),
            "mc_skip": ("Skip", "`!mc skip`", "Skip current song", "Action button"),
            "mc_pause": ("Pause", "`!mc pause`", "Pause current playback", "Action button"),
            "mc_resume": ("Resume", "`!mc resume`", "Resume paused playback", "Action button"),
            "mc_stop": ("Stop", "`!mc stop`", "Stop playback and clear queue", "Action button"),
            "mc_queue": ("View Queue", "`!mc queue`", "Show current playback queue", "Action button"),
            "mc_clear": ("Clear Queue", "`!mc clear`", "Clear entire queue (DJ only)", "Action button"),
            "mc_history": ("History", "`!mc history`", "Show recently played songs", "Action button"),
            "mc_volume": ("Volume", "`!mc volume <0-100>`", "Adjust playback volume", "Number input 0-100"),
        }
        selected = action_map.get(action_name)
        if selected:
            label, command_name, explanation, input_type = selected
            return "\n".join([
                f"🎵 **{_bot_display_name} Canvas - MC Action: {label}**\n",
                "**Selected option**",
                f"- Command: {command_name}",
                f"- Meaning: {explanation}",
                "",
                "**GUI input model**",
                f"- Input type: {input_type}",
                "",
                "**Next step**",
                "- Use this action from a server voice-channel context",
            ])

    return None


def _get_canvas_role_action_surface_name(role_name: str, action_name: str) -> str:
    if role_name == "news_watcher" and action_name.startswith("method_"):
        return "overview"  # Same view for both overview and personal
    if role_name == "news_watcher" and action_name.startswith("subscribe_"):
        return "overview"  # Same view for both overview and personal
    if role_name == "news_watcher" and action_name.startswith("list_"):
        return "overview"  # Same view for both overview and personal
    if role_name == "treasure_hunter" and action_name.startswith("league_"):
        return "league"
    if role_name == "treasure_hunter" and action_name.startswith("poe2_item_"):
        return "personal"
    if role_name == "treasure_hunter" and action_name.startswith("poe2_"):
        return "admin"
    if role_name == "trickster":
        if action_name.startswith("ring_"):
            return "ring" if action_name == "ring_accuse" else "ring_admin"
        if action_name.startswith("beggar_"):
            return "beggar" if action_name == "beggar_donate" else "beggar_admin"
        if action_name.startswith("announcements_"):
            return "dice_admin"
        if action_name.startswith("dice_"):
            return "dice_admin" if action_name in {"dice_fixed_bet", "dice_pot_value"} else "dice"
    if role_name == "banker" and action_name.startswith("config_"):
        return "admin"
    if role_name == "mc":
        return "overview"
    return "overview"

def _build_canvas_home(agent_config: dict, greet_name: str, nogreet_name: str, welcome_name: str, nowelcome_name: str,
                       role_cmd_name: str, talk_cmd_name: str, admin_visible: bool, server_name: str = "default",
                       author_id: int = 0) -> str:
    """Build the main Canvas hub view with status information."""
    enabled_roles = _get_enabled_roles(agent_config)
    roles_text = ", ".join(enabled_roles) if enabled_roles else "none"
    
    # Get home messages from personality with fallback
    home_messages = _personality_descriptions.get("canvas_home_messages", {})
    
    def _home_text(key: str, fallback: str) -> str:
        value = home_messages.get(key)
        return str(value).strip() if value else fallback
    
    # Build status content
    status_lines: list[str] = []
    
    try:
        database = AgentDatabase(server_name=server_name)
        daily_record = database.get_daily_memory_record()
        recent_record = database.get_recent_memory_record()
        relationship_record = database.get_user_relationship_memory(author_id)
    except Exception as e:
        logger.warning(f"Canvas status could not load memory data for server={server_name}: {e}")
        daily_record = None
        recent_record = None
        relationship_record = {"summary": "", "updated_at": None, "last_interaction_at": None, "metadata": {}}
    
    mission_prompt_lines = _load_role_mission_prompts(enabled_roles)
    mission_prompt_count = len(mission_prompt_lines)
    
    daily_summary = (daily_record or {}).get("summary", "").strip()
    recent_summary = (recent_record or {}).get("summary", "").strip()
    relationship_summary = (relationship_record or {}).get("summary", "").strip()
    
    status_lines.extend([
        f"**Personality:** `{_personality_name}`",
        f"**Active roles:** {roles_text}",
        "",
        "──────────────────────────────",
        "",
        "**Status**",
        f"- Mission prompt paragraphs active: {mission_prompt_count}",
        f"- Recent memory: {'available' if recent_summary else 'empty'}",
        f"- Daily memory: {'available' if daily_summary else 'empty'}",
        f"- Personal memory with you: {'available' if relationship_summary else 'empty'}",
    ])
    
    if recent_summary:
        status_lines.extend([
            "",
            "──────────────────────────────",
            "",
            "**Recent synthesis**",
            f"- {recent_summary[:900]}",
        ])
    
    if relationship_summary:
        status_lines.extend([
            "",
            "──────────────────────────────",
            "",
            "**Personal synthesis with you**",
            f"- {relationship_summary[:900]}",
        ])
    
    # Add final separator
    status_lines.extend([
        "",
        "──────────────────────────────"
    ])
    
    return "\n".join(status_lines)


def _build_canvas_behavior(greet_name: str, nogreet_name: str, welcome_name: str, nowelcome_name: str,
                           role_cmd_name: str, talk_cmd_name: str, admin_visible: bool) -> str:
    """Build the shared non-role behavior view - now shows conversation as default."""
    # Return the conversation view as the behavior overview
    return _build_canvas_behavior_detail("conversation", admin_visible, None, None) or f"**💬 {_bot_display_name} Comportamiento General**\n**Conversation surface**\n- Mention the bot in a server channel to talk\n- Send a DM to the bot for private interaction\n- Replies are shaped by the active personality and roles\n\n**Routing**\n- This is a shared global behavior, not a role-specific one\n- Use `!canvas roles` for role-specific flows"


def _build_canvas_behavior_detail(detail_name: str, admin_visible: bool, guild=None, agent_config: dict = None) -> str | None:
    """Build a detailed General Behavior view."""
    if detail_name in {"conversation", "chat"}:
        # Get conversation title from personality descriptions with fallback
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        conversation_title = behavior_descriptions.get("canvas_conversation_title", f"💬 {_bot_display_name} Canvas - General Behavior Conversation")
        
        # Replace {_bot} placeholder
        conversation_title = conversation_title.replace("{_bot}", _bot_display_name)
        
        return "\n".join([
            f"{conversation_title}\n",
            "**Conversation surface**",
            "- Mention the bot in a server channel to talk",
            "- Send a DM to the bot for private interaction",
            "- Replies are shaped by the active personality and roles",
            "",
            "**Routing**",
            "- This is a shared global behavior, not a role-specific one",
            "- Use `!canvas roles` for role-specific flows",
        ])
    if detail_name in {"greetings"}:
        from behavior.greet import clear_greeting_cache
        # Get greeting state from behaviors database first, fallback to memory
        greeting_enabled = False
        guild_id = "unknown"
        if guild:
            if hasattr(guild, 'id'):
                # guild is a guild object
                guild_id = str(guild.id)
                greeting_enabled = get_greeting_enabled(guild)
        else:
            greeting_enabled = False
            guild_id = "unknown"
        
        # Get title from personality descriptions with fallback
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        greetings_title = behavior_descriptions.get("canvas_greetings_title", f"👋 {_bot_display_name} Canvas - General Behavior Greetings")
        
        # Replace {_bot} placeholder
        greetings_title = greetings_title.replace("{_bot}", _bot_display_name)
        
        # Debug info
        from discord_bot.discord_utils import _greeting_config
        debug_config = _greeting_config.get(guild_id, {})
        
        return "\n".join([
            f"{greetings_title}\n",
            "**Admin controls**",
            f"- `!greet{_personality_name}` - Enable presence greetings",
            f"- `!nogreet{_personality_name}` - Disable presence greetings",
            "",
            "**Current status**",
            f"- {'✅ Enabled' if greeting_enabled else '❌ Disabled'}",
            "",
            "**Debug info**",
            f"- Guild ID: {guild_id}",
            f"- Behaviors DB available: {get_behaviors_db_instance is not None}",
            f"- Config exists: {guild_id in _greeting_config}",
            f"- Raw config: {debug_config}",
            f"- Final state: {greeting_enabled}",
            "",
            "**Routing**",
            "- Presence greetings are global server behavior",
            "- Uses behavior/greet.py module",
            "- Greets users when they come online (offline → online)",
            "- 5-minute cooldown between greetings per user",
        ])
    if detail_name in {"welcome"}:
        if not admin_visible:
            return _build_canvas_setup_not_available()
        
        # Get welcome state from behaviors database first, fallback to memory
        welcome_enabled = False
        if guild and get_behaviors_db_instance is not None:
            try:
                if hasattr(guild, 'id'):
                    guild_id = str(guild.id)
                else:
                    guild_id = str(guild)
                
                db = get_behaviors_db_instance(guild_id)
                welcome_enabled = db.get_welcome_enabled()
            except Exception as e:
                logger.warning(f"Error loading welcome state from behaviors database: {e}")
                # Fallback to memory config
                greeting_cfg = _discord_cfg.get("member_greeting", {})
                welcome_enabled = greeting_cfg.get("enabled", False)
        else:
            # Fallback to memory config
            greeting_cfg = _discord_cfg.get("member_greeting", {})
            welcome_enabled = greeting_cfg.get("enabled", False)
        
        # Get title from personality descriptions with fallback
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        welcome_title = behavior_descriptions.get("canvas_welcome_title", f"👋 {_bot_display_name} Canvas - General Behavior Welcome Messages")
        
        # Replace {_bot} placeholder
        welcome_title = welcome_title.replace("{_bot}", _bot_display_name)
        
        # Debug info
        guild_id = str(guild.id) if hasattr(guild, 'id') else str(guild) if guild else "unknown"
        
        return "\n".join([
            f"{welcome_title}\n",
            "**Admin controls**",
            "- `!welcome{_personality_name}` - Enable member welcome messages",
            "- `!nowelcome{_personality_name}` - Disable member welcome messages",
            "",
            "**Current status**",
            f"- {'✅ Enabled' if welcome_enabled else '❌ Disabled'}",
            "",
            "**Debug info**",
            f"- Guild ID: {guild_id}",
            f"- Behaviors DB available: {get_behaviors_db_instance is not None}",
            f"- Memory cfg: {greeting_cfg.get('enabled', False) if 'greeting_cfg' in locals() else 'N/A'}",
            f"- Final state: {welcome_enabled}",
            "",
            "**Concrete choices**",
            "- Boolean toggle: welcome messages on/off",
            "",
            "**Routing**",
            "- Welcome behavior is global to the server",
            "- Uses behavior/welcome.py module",
            "- Welcomes new members when they join the server",
            "- Only administrators can change it",
        ])
    if detail_name in {"commentary", "talk"}:
        if not admin_visible:
            return _build_canvas_setup_not_available()
        
        # Handle both guild object and guild ID
        if guild:
            if hasattr(guild, 'id'):
                guild_id = int(guild.id)
                guild_id_str = str(guild.id)
            else:
                guild_id = int(guild)
                guild_id_str = str(guild)
        else:
            guild_id = 0
            guild_id_str = "0"
        
        # Try to get state from behaviors database first
        enabled = False
        interval_minutes = 180
        channel_id = None
        
        if get_behaviors_db_instance is not None:
            try:
                db = get_behaviors_db_instance(guild_id_str)
                db_state = db.get_commentary_state()
                enabled = db_state['enabled']
                config = db_state.get('config', {})
                interval_minutes = config.get('interval_minutes', 180)
                channel_id = config.get('channel_id')
            except Exception as e:
                logger.warning(f"Error loading commentary from behaviors DB: {e}")
        
        # Fallback to memory if DB not available or no state found
        if not enabled and not channel_id:
            state = _talk_state_by_guild_id.get(guild_id) or {}
            enabled = state.get("enabled", False)
            interval_minutes = state.get("interval_minutes", 180)
            channel_id = state.get("channel_id")
        
        # Get title from personality descriptions with fallback
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        commentary_title = behavior_descriptions.get("canvas_commentary_title", f"🗣️ {_bot_display_name} Canvas - General Behavior Mission Commentary")
        
        # Replace {_bot} placeholder
        commentary_title = commentary_title.replace("{_bot}", _bot_display_name)
        
        return "\n".join([
            f"{commentary_title}\n",
            "**Admin controls**",
            f"- `!talk{_personality_name} on` - Enable commentary",
            f"- `!talk{_personality_name} off` - Disable commentary",
            f"- `!talk{_personality_name} now` - Trigger commentary now",
            f"- `!talk{_personality_name} status` - Inspect current status",
            f"- `!talk{_personality_name} frequency <minutes>` - Set frequency",
            "",
            "**Current status**",
            f"- {'✅ Enabled' if enabled else '❌ Disabled'}",
            f"- Interval: {interval_minutes} minutes",
            f"- Channel: {f'<#{channel_id}>' if channel_id else 'Not set'}" if enabled else "- Channel: N/A (disabled)",
            "",
            "**Debug info**",
            f"- Guild ID: {guild_id_str}",
            f"- Behaviors DB available: {get_behaviors_db_instance is not None}",
            f"- Memory state: {_talk_state_by_guild_id.get(guild_id, 'None')}",
            "",
            "**Concrete choices**",
            "- Boolean toggle: commentary on/off",
            "- Action button: run commentary now",
            "- Number input: frequency in minutes",
            "",
            "**Routing**",
            "- Commentary is global behavior driven by active roles",
            "- Only administrators can configure it",
        ])
    if detail_name in {"taboo"}:
        if not admin_visible:
            return _build_canvas_setup_not_available()
        
        # Handle both guild object and guild ID
        if guild:
            if hasattr(guild, 'id'):
                guild_id = int(guild.id)
            else:
                guild_id = int(guild)
        else:
            guild_id = 0
        
        state = get_taboo_state(guild_id)
        keywords = ", ".join(state.get("keywords", [])) or "(none)"
        
        # Get title from personality descriptions with fallback
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        taboo_title = behavior_descriptions.get("canvas_taboo_title", f"🚫 {_bot_display_name} Canvas - General Behavior Taboo")
        
        # Replace {_bot} placeholder
        taboo_title = taboo_title.replace("{_bot}", _bot_display_name)
        
        return "\n".join([
            f"{taboo_title}\n",
            "**Admin controls**",
            "- `!taboo on` - Enable taboo responses",
            "- `!taboo off` - Disable taboo responses",
            "- `!taboo add <keyword>` - Add a forbidden keyword",
            "- `!taboo del <keyword>` - Remove a forbidden keyword",
            "- `!taboo list` - Inspect the current keyword list",
            "",
            "**Current status**",
            f"- {'On' if state.get('enabled', False) else 'Off'}",
            "",
            "**Current keywords**",
            f"- {keywords}",
            "",
            "**Debug info**",
            f"- Guild ID: {guild_id}",
            f"- Taboo DB available: {get_taboo_db_instance is not None}",
            f"- Keywords count: {len(state.get('keywords', []))}",
            f"- Default from prompts: {'orco' in state.get('keywords', [])}",
            "",
            "**Routing**",
            "- Taboo watches normal server chat and can trigger an in-character reply",
            "- Only administrators can configure it",
        ])
    if detail_name in {"role_control", "roles"}:
        if not admin_visible:
            return _build_canvas_setup_not_available()
        enabled_roles = _get_enabled_roles(agent_config) if agent_config else []
        all_roles = ["news_watcher", "treasure_hunter", "trickster", "banker", "mc"]
        role_labels = {
            "news_watcher": "News Watcher",
            "treasure_hunter": "Treasure Hunter", 
            "trickster": "Trickster",
            "banker": "Banker",
            "mc": "MC",
        }
        
        # Debug info - check actual config
        roles_cfg = (agent_config or {}).get("roles", {})
        
        status_lines = []
        for role_name in all_roles:
            label = role_labels.get(role_name, role_name.replace("_", " ").title())
            # Check both methods for consistency
            method1_status = role_name in enabled_roles
            method2_status = roles_cfg.get(role_name, {}).get("enabled", False)
            status = "✅ Enabled" if method1_status else "❌ Disabled"
            # Add debug info if there's a mismatch
            debug_info = f" (cfg:{method2_status})" if method1_status != method2_status else ""
            status_lines.append(f"- {label}: {status}{debug_info}")
        
        # Add debug section
        debug_lines = [
            "**Debug Info**",
            f"- Total roles in config: {len(roles_cfg)}",
            f"- Enabled roles found: {len(enabled_roles)}",
            f"- Config keys: {list(roles_cfg.keys())}",
            f"- Enabled list: {enabled_roles}",
            ""
        ]
        
        # Get title from personality descriptions with fallback
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        role_control_title = behavior_descriptions.get("canvas_role_control_title", f"🎛️ {_bot_display_name} Canvas - General Behavior Role Control")
        
        # Replace {_bot} placeholder
        role_control_title = role_control_title.replace("{_bot}", _bot_display_name)
        
        return "\n".join([
            f"{role_control_title}\n",
            "**Admin controls**",
            f"- `!role{_personality_name} <role> on` - Activate a role",
            f"- `!role{_personality_name} <role> off` - Deactivate a role",
            "",
            *debug_lines,
            "**Current status**",
            *status_lines,
            "",
            "**Concrete choices**",
            "- Select menu: choose role",
            "- Boolean toggle: on/off",
            "",
            "**Routing**",
            "- Role activation is global server behavior",
            "- Detailed per-role work continues in `!canvas roles`",
        ])
    return None


def _build_canvas_roles(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the role navigation Canvas view."""
    roles_config = (agent_config or {}).get("roles", {})
    
    # Get roles view messages from personality with fallback
    roles_messages = _personality_descriptions.get("roles_view_messages", {})
    role_descriptions = roles_messages.get("role_descriptions", {})
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
    
    # Helper function to get role info with fallback
    def get_role_info(role_key):
        role_info = role_descriptions.get(role_key, {})
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
    if is_role_enabled_check("news_watcher", agent_config, guild):
        active_roles.append("news_watcher")
        interval = get_role_interval_hours("news_watcher", agent_config, guild, 1)
        role_info = get_role_info("news_watcher")
        parts.append(
            f"📡 **{role_info['title']}** {enabled_status} {interval_info.format(interval=interval)}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # Treasure Hunter
    if is_role_enabled_check("treasure_hunter", agent_config, guild):
        active_roles.append("treasure_hunter")
        interval = get_role_interval_hours("treasure_hunter", agent_config, guild, 1)
        role_info = get_role_info("treasure_hunter")
        parts.append(
            f"💎 **{role_info['title']}** {enabled_status} {interval_info.format(interval=interval)}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # Trickster
    if is_role_enabled_check("trickster", agent_config, guild):
        active_roles.append("trickster")
        role_info = get_role_info("trickster")
        parts.append(
            f"🎭 **{role_info['title']}** {enabled_status}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # Banker
    if is_role_enabled_check("banker", agent_config, guild):
        active_roles.append("banker")
        interval = get_role_interval_hours("banker", agent_config, guild, 24)
        role_info = get_role_info("banker")
        parts.append(
            f"💰 **{role_info['title']}** {enabled_status} {interval_info.format(interval=interval)}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # MC
    mc_cfg = roles_config.get("mc", {})
    if mc_cfg.get("enabled", False):
        active_roles.append("mc")
        role_info = get_role_info("mc")
        parts.append(
            f"🎵 **{role_info['title']}** {enabled_status}\n"
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
        f"👤 **{_bot_display_name} Canvas - Personal Space**\n\n"
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
    return (
        f"📚 **{_bot_display_name} Canvas - Help & Troubleshooting**\n\n"
        "**Command lookup**\n"
        "- `!agenthelp` - Full command summary\n"
        "- `!readme` - Complete guide by private message\n"
        "- `!watcherhelp` - News Watcher user guide\n"
        "- `!watcherchannelhelp` - News Watcher channel/admin guide\n"
        "- `!hunterhelp` / `!hunter poe2 help`\n"
        "- `!trickster help`\n"
        "- `!banker help`\n"
        "- `!mc help`\n\n"
        "**Common issues**\n"
        "- If a command fails in DM, retry it in a server channel\n"
        "- If a command fails in a server, check whether it is DM-only\n"
        "- If setup commands fail, verify administrator permissions\n"
        "- If a role command is missing, verify the role is enabled in configuration\n\n"
        "**Concrete choices**\n"
        "- Use role surfaces when you need command-specific options\n"
        "- Use setup/behavior surfaces when you need server-wide toggles\n"
        "- Use personal surfaces when you need DM-oriented text or list management\n\n"
        "**Navigation**\n"
        "- `!canvas home`\n"
        "- `!canvas setup`\n"
        "- `!canvas roles`\n"
        "- `!canvas role <name>`\n"
        "- `!canvas role news_watcher personal`\n"
        "- `!canvas role trickster dice`\n"
        "- `!canvas role treasure_hunter personal`\n"
        "- `!canvas role banker wallet`\n"
        "- `!canvas personal`"
    )


def _build_canvas_role_news_watcher(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the News Watcher role view (same as personal view)."""
    # Use the personal view content directly
    return _build_canvas_role_news_watcher_detail("personal", admin_visible, guild, 0, None, None, None)


def _get_canvas_channel_subscriptions_info(guild) -> str:
    """Get formatted channel subscriptions information for canvas display."""
    try:
        if get_news_watcher_db_instance is None:
            return "**Channel subscriptions**\n- Unable to load channel subscription data"
        
        db = get_news_watcher_db_instance(str(guild.id))
        
        # Get all channel subscriptions for this server
        all_channel_subs = db.get_all_channels_with_subscriptions()
        
        # Count total subscriptions across all channels
        total_count = 0
        subscriptions_list = []
        
        # Count regular channel subscriptions
        for channel_id, channel_name, server_id in all_channel_subs:
            if str(server_id) == str(guild.id):  # Only show subscriptions for this server
                channel_subs = db.get_channel_subscriptions(channel_id)
                total_count += len(channel_subs)
                
                for category, feed_id, _ in channel_subs:
                    if feed_id:
                        subscriptions_list.append(f"  📡 {category} (feed #{feed_id}) - #{channel_name}")
                    else:
                        subscriptions_list.append(f"  📡 {category} (all feeds) - #{channel_name}")
        
        # Count keyword subscriptions
        keyword_subs = db.get_all_active_keyword_subscriptions()
        for user_id, channel_id, keywords, category, feed_id in keyword_subs:
            if channel_id:  # Only count channel subscriptions (not user-only)
                # Get channel name from Discord channel cache or use ID
                try:
                    # Try to get channel name from the guild
                    channel = guild.get_channel(int(channel_id))
                    channel_name = channel.name if channel else f"Channel-{channel_id}"
                except:
                    channel_name = f"Channel-{channel_id}"
                
                total_count += 1
                if feed_id:
                    subscriptions_list.append(f"  🔍 {category} (keywords: {keywords}, feed #{feed_id}) - #{channel_name}")
                else:
                    subscriptions_list.append(f"  🔍 {category} (keywords: {keywords}, all feeds) - #{channel_name}")
        
        max_subs = 5  # Channel subscriptions limit per channel
        usage_info = f"**Channel subscriptions** ({total_count}/{max_subs})\n"
        
        if total_count == 0:
            usage_info += "- No active channel subscriptions\n"
        else:
            for sub in subscriptions_list:
                usage_info += f"{sub}\n"
        
        # Add server configuration info
        config_info = "\n──────────────────────────────\n\n**Server configuration**\n"
        
        # Get frequency
        try:
            frequency = db.get_frequency_config(str(guild.id))
            config_info += f"- ⏰ **Check frequency**: Every {frequency} hours\n"
        except:
            config_info += "- ⏰ **Check frequency**: Not configured\n"
        
        # Get method
        method = db.get_method_config(str(guild.id))
        method_labels = {
            "flat": "Flat (All news)",
            "keyword": "Keyword (Filtered)",
            "general": "General (AI-critical)"
        }
        config_info += f"- 🔧 **Default method**: {method_labels.get(method, 'Unknown')}\n"
        
        return usage_info + config_info
        
    except Exception as e:
        logger.warning(f"Could not load channel subscriptions for Canvas: {e}")
        return "**Channel subscriptions**\n- Error loading channel subscription data"


def _get_canvas_user_subscriptions_info(guild, author_id: int) -> str:
    """Get formatted user subscriptions information for canvas display."""
    try:
        if get_news_watcher_db_instance is None:
            return "**Active subscriptions**\n- Unable to load subscription data"
        
        db = get_news_watcher_db_instance(str(guild.id))
        user_id = str(author_id)
        
        # Get subscription count and limits
        current_count = db.count_user_subscriptions(user_id)
        max_subs = 3
        usage_info = f"**Active subscriptions** ({current_count}/{max_subs})\n"
        
        if current_count == 0:
            usage_info += "- No active subscriptions\n"
        else:
            # Get all subscriptions with their methods
            subscriptions_info = "- **Your subscriptions:**\n"
            
            # Get flat subscriptions
            flat_subs = db.get_user_subscriptions(user_id)
            for i, (category, feed_id, _) in enumerate(flat_subs, 1):
                if feed_id:
                    subscriptions_info += f"  {i}. 📰 Flat: {category} (feed #{feed_id})\n"
                else:
                    subscriptions_info += f"  {i}. 📰 Flat: {category} (all feeds)\n"
            
            # Get keyword subscriptions
            keyword_subs = db.get_user_keyword_subscriptions(user_id)
            for i, (category, keywords, _) in enumerate(keyword_subs, len(flat_subs) + 1):
                subscriptions_info += f"  {i}. 🔍 Keywords: {category} - {keywords}\n"
            
            # Get AI subscriptions
            ai_subs = db.get_user_ai_subscriptions(user_id)
            for i, (category, feed_id, _) in enumerate(ai_subs, len(flat_subs) + len(keyword_subs) + 1):
                if feed_id:
                    subscriptions_info += f"  {i}. 🤖 AI: {category} (feed #{feed_id})\n"
                else:
                    subscriptions_info += f"  {i}. 🤖 AI: {category} (all feeds)\n"
            
            usage_info += subscriptions_info
        
        # Add configuration info
        config_info = "\n──────────────────────────────\n\n**Configuration status**\n"
        
        # Check keywords
        keywords = db.get_user_keywords(user_id)
        if keywords:
            config_info += f"- 🔍 **Keywords**: {', '.join(keywords[:3])}"
            if len(keywords) > 3:
                config_info += f" (+{len(keywords) - 3} more)"
            config_info += "\n"
        else:
            config_info += "- 🔍 **Keywords**: None configured\n"
        
        # Check premises
        premises, _ = db.get_premises_with_context(user_id)
        if premises:
            config_info += f"- 🤖 **Premises**: {len(premises)} configured"
            if premises:
                preview = premises[0][:50] + "..." if len(premises[0]) > 50 else premises[0]
                config_info += f" - \"{preview}\""
            config_info += "\n"
        else:
            config_info += "- 🤖 **Premises**: None configured\n"
        
        return usage_info + config_info
        
    except Exception as e:
        logger.warning(f"Could not load user subscriptions for Canvas: {e}")
        return "**Active subscriptions**\n- Error loading subscription data"


def _build_canvas_role_news_watcher_detail(
    detail_name: str,
    admin_visible: bool,
    guild=None,
    author_id: int = 0,
    selected_method: str | None = None,
    last_action: str | None = None,
    selected_category: str = None,
) -> str | None:
    """Build a detailed News Watcher view with 3-block structure."""
    watcher_messages = get_watcher_messages() if get_watcher_messages else {}
    watcher_descriptions = _personality_descriptions.get("watcher_messages", {})

    def _watcher_text(key: str, fallback: str) -> str:
        value = watcher_descriptions.get(key, watcher_messages.get(key))
        return str(value).strip() if value else fallback

    def _get_watcher_personal_intro_block() -> str:
        """Get the standard watcher personal introduction block."""
        return "\n".join([
            f"**📡 {_watcher_text('canvas_personal_title', 'News Watcher Personal')}**",
            _watcher_text('canvas_personal_description', 'Build and maintain your personal news subscriptions. Choose a method first, then subscribe to categories or feeds, or review your keywords and premises.'),
            "──────────────────────────────",
        ])

    def _get_watcher_admin_intro_block() -> str:
        """Get the standard watcher admin introduction block."""
        return "\n".join([
            f"**{_watcher_text('canvas_admin_title', '📡 News Watcher')} Admin**",
            "",
            _watcher_text("canvas_admin_description", "Manage channel subscriptions with the same flow as personal view, but applied to channels. Choose a method, then manage categories, feeds, and server actions."),
            "──────────────────────────────",
        ])

    def _format_categories() -> str:
        if not guild or get_news_watcher_db_instance is None:
            return "- Economy\n- Technology\n- International\n- General\n- Crypto"
        try:
            db = get_news_watcher_db_instance(str(guild.id))
            categories = db.get_available_categories()
            if not categories:
                return "- No categories available"
            return "\n".join([
                f"- {str(category).title()} ({count} feeds)"
                for category, count in categories
            ])
        except Exception as e:
            logger.warning(f"Could not load watcher categories for Canvas: {e}")
            return "- Error loading categories"

    def _format_feeds(category: str = None) -> str:
        if not guild or get_news_watcher_db_instance is None:
            return "- No feed data available"
        try:
            db = get_news_watcher_db_instance(str(guild.id))
            
            if category:
                # Show feeds for specific category
                feeds = db.get_active_feeds(category)
                if not feeds:
                    return f"- No feeds found for category '{category}'"
                lines = [f"**{category.title()} Feeds ({len(feeds)} total):**"]
                for i, (feed_id, name, _url, feed_category, country, language, _priority, _keywords, feed_type) in enumerate(feeds, 1):
                    meta = []
                    if country:
                        meta.append(str(country).upper())
                    if language:
                        meta.append(str(language))
                    if feed_type:
                        meta.append(str(feed_type))
                    meta_text = " | ".join(meta) if meta else "Feed"
                    lines.append(f"- Feed {i}: {name} ({meta_text})")
                return "\n".join(lines)
            else:
                # Show all feeds (original behavior)
                feeds = db.get_active_feeds()
                if not feeds:
                    return "- No feeds available"
                lines = []
                for feed_id, name, _url, category, country, language, _priority, _keywords, feed_type in feeds[:12]:
                    meta = []
                    if category:
                        meta.append(str(category).title())
                    if feed_type:
                        meta.append(str(feed_type))
                    if country:
                        meta.append(str(country).upper())
                    if language:
                        meta.append(str(language))
                    meta_text = " | ".join(meta) if meta else "Feed"
                    lines.append(f"- #{feed_id} {name} ({meta_text})")
                if len(feeds) > 12:
                    lines.append(f"- ... and {len(feeds) - 12} more feeds")
                return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Could not load watcher feeds for Canvas: {e}")
            return "- Error loading feeds"

    def _format_keywords() -> str:
        if not guild or not author_id or get_news_watcher_db_instance is None:
            return "- No keywords configured"
        try:
            db = get_news_watcher_db_instance(str(guild.id))
            raw_keywords = db.get_user_keywords(str(author_id))
            if not raw_keywords:
                return "- No keywords configured"
            parts = [item.strip() for item in str(raw_keywords).split(",") if item.strip()]
            return "\n".join([f"- {keyword}" for keyword in parts[:15]])
        except Exception as e:
            logger.warning(f"Could not load watcher keywords for Canvas: {e}")
            return "- Error loading keywords"

    def _format_premises() -> str:
        if not guild or not author_id or get_news_watcher_db_instance is None:
            return "- No premises configured"
        try:
            db = get_news_watcher_db_instance(str(guild.id))
            # For admin view, check if we're showing channel premises or user premises
            if detail_name == "admin":
                # For admin view, try to get channel premises first
                try:
                    # Try to get channel premises (this would need channel_id which we don't have here)
                    # For now, show user premises in admin view too
                    premises, scope = db.get_premises_with_context(str(author_id))
                except:
                    premises, scope = [], "none"
            else:
                # Personal view - get user premises
                premises, scope = db.get_premises_with_context(str(author_id))
            
            if not premises:
                # Check if user has ever initialized (by checking if they had premises before)
                # For now, if user has no premises, assume they need to initialize or add
                # We'll show a cleaner message without global references to avoid confusion
                lines = ["- Scope: No custom premises"]
                lines.append("")
                lines.append("- 💡 **No custom premises configured**")
                lines.append("- 💡 Use 'Add Premises' to create custom premises")
                lines.append("- 💡 Or use !canvas to auto-initialize with defaults")
                return "\n".join(lines)
            
            lines = [f"- Scope: {scope}"]
            for i, premise in enumerate(premises[:8], 1):
                lines.append(f"- {i}. {premise}")
            
            if len(premises) > 8:
                lines.append(f"- ... and {len(premises) - 8} more premises")
            
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Could not load watcher premises for Canvas: {e}")
            return "- Error loading premises"

    method_labels = {
        "flat": "Flat",
        "keyword": "Keyword",
        "general": "General",
        None: "Not selected",
    }
    method_label = method_labels.get(selected_method, str(selected_method).title() if selected_method else "Not selected")

    if detail_name in {"personal", "overview"}:
        block1 = _get_watcher_personal_intro_block()

        subscriptions_info = _get_canvas_user_subscriptions_info(guild, author_id) if guild and author_id else "**Active subscriptions**\n- No subscription data available"
        block2 = "\n".join([
            f"**Selected Method**: {method_label}",
            "",
            subscriptions_info,
        ])
        
        # Add separator after block2
        block2 += "\n──────────────────────────────"

        if last_action == "list_feeds":
            block3_title = "**Available Feeds**"
            block3_body = _format_feeds()
        elif last_action == "list_feeds_by_category":
            block3_title = f"**{selected_category.title()} Feeds**"
            block3_body = _format_feeds(selected_category)
        elif last_action == "list_keywords":
            block3_title = "**Configured Keywords**"
            block3_body = _format_keywords()
        elif last_action == "list_premises":
            block3_title = "**Configured Premises**"
            block3_body = _format_premises()
        elif last_action == "list_categories":
            block3_title = "**Available Categories**"
            block3_body = _format_categories()
        else:
            block3_title = "**Available Categories**"
            block3_body = _format_categories()

        block3 = "\n".join([
            block3_title,
            "",
            block3_body,
        ])

        return "\n".join([block1, "", block2, "", block3])

    if detail_name == "admin" and admin_visible:
        block1 = _get_watcher_admin_intro_block()

        channel_subscriptions = _get_canvas_channel_subscriptions_info(guild) if guild else "**Channel subscriptions**\n- No channel data available"
        block2 = "\n".join([
            f"**Selected Method**: {method_label}",
            "",
            channel_subscriptions,
            "──────────────────────────────"
        ])

        if last_action == "list_feeds":
            block3_title = "**Available Feeds**"
            block3_body = _format_feeds()
        elif last_action == "list_feeds_by_category":
            block3_title = f"**{selected_category.title()} Feeds**"
            block3_body = _format_feeds(selected_category)
        elif last_action == "channel_view_subscriptions":
            block3_title = "**Current Channel Subscriptions**"
            block3_body = channel_subscriptions
        elif last_action == "channel_unsubscribe":
            block3_title = "**Channel Unsubscribe**"
            block3_body = "\n".join([
                "- Use the numbered list from block 2",
                "- Choose the subscription number to remove",
                "- The change affects this channel",
            ])
        elif last_action == "watcher_frequency":
            block3_title = "**Watcher Frequency**"
            block3_body = "\n".join([
                "- Set how often the watcher checks for news",
                "- Recommended range: 1 to 24 hours",
                "- This affects the server-wide watcher schedule",
            ])
        elif last_action == "watcher_run_now":
            block3_title = "**Force Watcher Run**"
            block3_body = "\n".join([
                "- Runs the watcher immediately",
                "- Useful after adding or changing channel subscriptions",
                "- May generate notifications in subscribed channels",
            ])
        elif last_action == "watcher_run_personal":
            block3_title = "**Force Personal Subscriptions**"
            block3_body = "\n".join([
                "- Runs personal subscriptions immediately",
                "- Processes flat, keyword, and AI subscriptions",
                "- Sends notifications to users via DMs",
                "- Useful for testing personal subscription setup",
            ])
        elif last_action == "list_premises":
            block3_title = "**Configured Premises**"
            block3_body = _format_premises()
        elif last_action == "list_keywords":
            block3_title = "**Configured Keywords**"
            block3_body = _format_keywords()
        elif last_action == "list_categories":
            block3_title = "**Available Categories**"
            block3_body = _format_categories()
        elif last_action == "list_feeds":
            block3_title = "**Available Feeds**"
            block3_body = _format_feeds()
        elif last_action == "list_feeds_by_category":
            block3_title = f"**{selected_category.title()} Feeds**"
            block3_body = _format_feeds(selected_category)
        else:
            block3_title = "**Available Categories**"
            block3_body = _format_categories()

        block3 = "\n".join([
            block3_title,
            "",
            block3_body,
        ])

        return "\n".join([block1, "", block2, "", block3])
    if detail_name in {"keywords", "filters"}:
        return "\n".join([
            f"**📡 {_bot_display_name} Canvas - News Watcher Keywords**",
            "**Main goal**",
            "- Shape what the watcher considers relevant for you",
            "",
            "**Keyword management**",
            "- `!watcher keywords add <word>` - Add a keyword",
            "- `!watcher keywords del <word>` - Remove a keyword",
            "- `!watcher keywords list` - Review your active keywords",
            "",
            "**AI premises**",
            "- `!watcher premises add \"text\"` - Add a premise",
            "- `!watcher premises del <number>` - Remove a premise",
            "- `!watcher premises list` - Review premises",
            "",
            "**Best next actions**",
            "- Add only a few strong keywords first",
            "- Use premises when raw keywords are too noisy",
            "",
            "**Concrete choices**",
            "- Text input: keyword or premise text",
            "- Number input: premise index to delete",
            "",
            "**Routing**",
            "- These settings shape your personal watcher filtering",
            "- Use `!canvas role news_watcher` to return to the role overview",
        ])
    if detail_name in {"admin", "channel", "setup"}:
        if not admin_visible:
            return _build_canvas_setup_not_available()
        current_method = _get_canvas_watcher_method_label(str(guild.id)) if guild else "Unknown"
        current_frequency = _get_canvas_watcher_frequency_hours(str(guild.id)) if guild else 1
        return "\n".join([
            f"**{_watcher_text('canvas_admin_title', '📡 News Watcher')} Admin**",
            "**Main goal**",
            "- Configure how the server receives and filters watcher output",
            "",
            "**Channel and server setup**",
            "- `!watcherchannelhelp` - Open the channel/admin help surface",
            "- `!watcherchannel subscribe <category> [feed_id]` - Subscribe the current channel",
            "- `!watcherchannel unsubscribe <category>` - Remove a channel subscription",
            "- `watcherchannel status` - Inspect the current channel state",
            "",
            "**Server filtering state**",
            f"- Current method: {current_method}",
            "- `Method: Flat` - all news with opinions",
            "- `Method: Keyword` - filtered by keywords",
            "- `Method: General` - AI-based critical news",
            "",
            "**Operations**",
            f"- Current frequency: every {current_frequency}h",
            "- `Watcher: Frequency` - Adjust watcher frequency",
            "- `Watcher: Run Now` - Force one watcher iteration",
            "",
            "**Best next actions**",
            "- Confirm channel status before changing filtering state",
            "- Use `!forcewatcher` after setup to verify the pipeline",
            "",
            "**Concrete choices**",
            "- Selector options: `flat` / `keyword` / `general`",
            "- Number input: watcher frequency in hours",
            "- Text input: category or feed id for channel routing",
            "",
            "**Routing**",
            "- These actions are server-only and admin-only",
            "- Use `!canvas role news_watcher` to return to the role overview",
        ])
    return None


def _build_canvas_role_treasure_hunter(agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str:
    """Build the Treasure Hunter role view."""
    treasure_messages = _personality_answers.get("treasure_hunter_messages", {})
    treasure_descriptions = _personality_descriptions.get("treasure_hunter_messages", {})
    
    def _treasure_text(key: str, fallback: str) -> str:
        value = treasure_descriptions.get(key, treasure_messages.get(key))
        # Replace {_bot} placeholder
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback
    
    def _get_treasure_overview_intro_block() -> str:
        return "\n".join([
            _treasure_text("canvas_th_overview_title", f"💎 {_bot_display_name} Canvas - Treasure Hunter"),
        ])
    
    def _get_treasure_poe2_intro_block() -> str:
        return "\n".join([
            _treasure_text("canvas_th_poe2_title", f"💎 {_bot_display_name} Canvas - Treasure Hunter POE2"),
        ])
    
    interval = (agent_config or {}).get("roles", {}).get("treasure_hunter", {}).get("interval_hours", 1)
    state = _get_canvas_poe2_state(guild, author_id)
    objective_count = len(state.get("objectives", []))
    parts = [
        _get_treasure_overview_intro_block(),
        "**Role type:** item-tracking surface with personal and admin paths\n",
        f"**Status:** enabled | every {interval}h\n",
        f"**POE2 state:** {'On' if state.get('activated', False) else 'Off'} | league {state.get('league', 'Standard')} | {objective_count} tracked item(s)\n",
        "**User flows**",
        "- `!hunterhelp` - General role help",
        "- `!hunter poe2 help` - POE2 help",
        "- `!hunter poe2 list` - Show tracked objectives",
        "- `!hunter poe2 add \"Item Name\"` - Add an objective",
        "- `!hunter poe2 del \"Item Name\"` - Remove an objective",
        "- `!hunter poe2 league \"Standard\"` - Show or change your league in DM",
        "",
        "**Task map**",
        "- Items: maintain tracked objectives",
        "- League: align search scope with your economy through concrete league options",
        "- Admin: enable and schedule the subrole",
        "",
        "**Concrete choices**",
        "- League selector: `Standard`, `Fate of the Vaal`, or another supported league",
    ]
    if admin_visible:
        parts.extend([
            "",
            "**Admin flows**",
            "- `!hunter poe2 on` - Activate the POE2 subrole",
            "- `!hunter poe2 off` - Deactivate the POE2 subrole",
            "- `!hunterfrequency <hours>` - Set execution frequency",
        ])
    parts.extend([
        "",
        "**Routing**",
        "- Personal POE2 management is DM-oriented",
        "- Server activation and frequency are admin-only",
        "- Detail views: `!canvas role treasure_hunter personal`",
    ])
    if admin_visible:
        parts[-1] += "\n- Admin detail: `!canvas role treasure_hunter admin`"
    return "\n".join(parts)


def _build_canvas_role_treasure_hunter_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Build a detailed Treasure Hunter view."""
    treasure_messages = _personality_answers.get("treasure_hunter_messages", {})
    treasure_descriptions = _personality_descriptions.get("treasure_hunter_messages", {})
    
    def _treasure_text(key: str, fallback: str) -> str:
        value = treasure_descriptions.get(key, treasure_messages.get(key))
        # Replace {_bot} placeholder
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback
    
    def _get_treasure_overview_intro_block() -> str:
        return "\n".join([
            _treasure_text("canvas_th_overview_title", f"💎 {_bot_display_name} Canvas - Treasure Hunter"),
        ])
    
    def _get_treasure_poe2_intro_block() -> str:
        return "\n".join([
            _treasure_text("canvas_th_poe2_title", f"💎 {_bot_display_name} Canvas - Treasure Hunter POE2"),
        ])
    if detail_name in {"personal", "poe2", "items"}:
        state = _get_canvas_poe2_state(guild, author_id)
        items_block = "\n".join([f"- {item}" for item in state["objectives"]]) if state["objectives"] else "- No tracked items yet"
        return "\n".join([
            _get_treasure_poe2_intro_block(),
            "**Current league**",
            f"- {state['league']}",
            "",
            "**Tracked items**",
            items_block,
            "",
            "**Remove tracked items**",
            "- Use the remove action selector and confirm the item name or index",
            "",
            "**Add a new item**",
            "- Use the add action selector and submit the exact POE2 item name",
            "",
            "**Concrete choices**",
            "- Text input to add an exact POE2 item name",
            "- Text input to remove by item name or visible item number",
            "",
            "**Routing**",
            "- Personal POE2 management updates the current server-linked user profile",
            "- Use `!canvas role treasure_hunter` to return to the role overview",
        ])
    if detail_name in {"league"}:
        state = _get_canvas_poe2_state(guild, author_id)
        return "\n".join([
            f"**💎 {_bot_display_name} Canvas - Treasure Hunter League**",
            "Configure your POE2 league setting for item tracking",
            "**Current league**",
            f"- {state['league']}",
            "",
            "**League actions**",
            "- `!hunter poe2 league` - Show your current league",
            "- `!hunter poe2 league \"Standard\"` - Change to Standard",
            "- `!hunter poe2 league \"Fate of the Vaal\"` - Change to Fate of the Vaal",
            "- `!hunter poe2 league \"Hardcore\"` - Change to Hardcore if supported",
            "",
            "**Concrete choices**",
            "- Preferred selector options: `Standard` / `Fate of the Vaal`",
            "- Fallback: text input for a custom or future league",
            "",
            "**Routing**",
            "- League management is DM-oriented",
            "- Use `!canvas role treasure_hunter` to return to the role overview",
        ])
    if detail_name in {"admin", "setup"}:
        if not admin_visible:
            return _build_canvas_setup_not_available()
        state = _get_canvas_poe2_state(guild, author_id)
        interval = (AGENT_CFG or {}).get("roles", {}).get("treasure_hunter", {}).get("interval_hours", 1)
        return "\n".join([
            f"**💎 {_bot_display_name} Canvas - Treasure Hunter Admin**",
            "Configure POE2 tracking and automation settings",
            "**POE2 activation**",
            f"- Current state: {'On' if state['activated'] else 'Off'}",
            "",
            "**Active league**",
            f"- {state['league']}",
            "",
            "**Execution frequency**",
            f"- Current interval: {interval}h",
            "",
            "**Concrete choices**",
            "- Toggle selector: POE2 on/off",
            "- Number input: hunter frequency in hours",
            "",
            "**Best next actions**",
            "- Enable POE2 only after confirming the active league",
            "- Adjust frequency after your tracked items are stable",
            "",
            "**Routing**",
            "- Activation and scheduler controls are admin-only",
            "- Use `!canvas role treasure_hunter` to return to the role overview",
        ])
    return None


def _build_canvas_role_trickster(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the Trickster role view."""
    # Try to get trickster messages, fallback to empty dict
    trickster_messages = {}
    try:
        trickster_messages = _personality_descriptions.get("ring_view_messages", {})
    except Exception:
        pass
    
    def _trickster_text(key: str, fallback: str) -> str:
        value = trickster_messages.get(key)
        # Replace {_bot} placeholder
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback
    
    def _get_trickster_overview_intro_block() -> str:
        return "\n".join([
            _trickster_text("canvas_trickster_overview_title", f"🎭Trilero de Putre"),
        ])
    
    subroles = (agent_config or {}).get("roles", {}).get("trickster", {}).get("subroles", {})
    active_subroles = [name for name, cfg in subroles.items() if isinstance(cfg, dict) and cfg.get("enabled", False)]
    subroles_text = ", ".join(active_subroles) if active_subroles else "none"
    dice_state = _get_canvas_dice_state(guild)
    ring_state = _get_canvas_ring_state(guild)
    beggar_state = _get_canvas_beggar_state(guild)
    
    # Get separator and subrole descriptions
    separator = _trickster_text("canvas_trickster_overview_separator", "──────────────────────────────")
    subrole_descriptions = trickster_messages.get("canvas_trickster_subrole_descriptions", {})
    
    # Build subrole descriptions for active subroles
    active_descriptions = []
    for subrole in active_subroles:
        if subrole in subrole_descriptions:
            active_descriptions.append(subrole_descriptions[subrole])
    
    parts = [
        _get_trickster_overview_intro_block(),
        separator,
        "**Role type:** multi-surface role with subroles",
        f"**Active subroles:** {subroles_text}",
        f"**Live state:** dice bet {dice_state['bet']:,} | pot {dice_state['pot_balance']:,} | ring {'On' if ring_state['enabled'] else 'Off'} | beggar {'On' if beggar_state['enabled'] else 'Off'}",
        separator,
    ]
    
    # Add subrole descriptions if available
    if active_descriptions:
        parts.extend(active_descriptions)
        parts.append(separator)
    
    parts.append("🎭 Trickster • admin/user view")
    
    return "\n".join(parts)


def _build_canvas_role_trickster_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Build a detailed Trickster view."""
    # Try to get trickster messages, fallback to empty dict
    trickster_messages = {}
    try:
        trickster_messages = _personality_descriptions.get("ring_view_messages", {})
    except Exception:
        pass
    
    def _trickster_text(key: str, fallback: str) -> str:
        value = trickster_messages.get(key)
        # Replace {_bot} placeholder
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback
    
    
    def _get_ring_intro_block() -> str:
        return "\n".join([
            _trickster_text("canvas_ring_title", f"🎭 {_bot_display_name} Canvas - Trickster Ring"),
        ])
    
    def _get_beggar_intro_block() -> str:
        return "\n".join([
            _trickster_text("canvas_beggar_title", f"🎭 {_bot_display_name} Canvas - Trickster Beggar"),
        ])
    
    if detail_name in {"dice", "game"}:
        dice_state = _get_canvas_dice_state(guild)
        balance_messages = _personality_descriptions.get("dice_game_balance_messages", {})
        descriptions = _personality_descriptions.get("dice_game_messages", {})
        # Build the base content with personality title and pot balance
        title = descriptions.get("current_pot_title", "🎲 **DICE GAME** 🎲")
        pot_title = balance_messages.get("current_balance", "💎 **CURRENT POT:**")
        fixed_bet = balance_messages.get("fixed_bet", "💎 **FIXED BET:**")
        parts = [
            title,
            f"{pot_title} **{dice_state['pot_balance']:,}** :coin: ",
            f"{fixed_bet} {dice_state.get('bet', 1):,} :coin:",
            "─" * 45,
            ""
        ]
        
        # Add some quick stats
        ranking_data = _get_canvas_dice_ranking(guild, 10)
            
        rankingtitle = descriptions.get("ranking", "**🏆 DICE RANKING**")
        parts.append(rankingtitle)
        if ranking_data:
            for player in ranking_data:
                medal = "🥇" if player["position"] == 1 else "🥈" if player["position"] == 2 else "🥉" if player["position"] == 3 else "🏅"
                parts.append(
                    f"{medal} **#{player['position']}** {player['player_name']} | Won: {player['total_won']:,} | Games: {player['total_plays']}"
                )
        else:
            rankingvoid = descriptions.get("rankingvoid", "📊 No ranked players yet. Be the first to play!")
            parts.append(rankingvoid)
            
        parts.append("─" * 45)       
        server_key = get_server_key(guild)
        server_id = str(guild.id)
        db_dice = get_dice_game_db_instance(server_key)
        history = db_dice.get_game_history(server_id, 10)
        historytitle = descriptions.get("history", "**📜 DICE HISTORY**")
        parts.append(historytitle)
            
        if history:
            for record in history:
                # Parse tuple: (id, user_id, user_name, server_id, server_name, bet, dice, combination, prize, pot_before, pot_after, date)
                user_name = record[2] if len(record) > 2 else "Unknown"
                dice = record[6] if len(record) > 6 else ""
                combination = record[7] if len(record) > 7 else ""
                prize = record[8] if len(record) > 8 else 0
                    
                dice_display = "🎲".join(dice.split('-')) if dice else "???"
                prize_emoji = "💰" if prize > 0 else "💸"
                    
                parts.append(
                    f"👤 {user_name} | {dice_display} → {combination} | {prize_emoji} {prize:,}"
                )
        else:
            historyvoid = descriptions.get("historyvoid", "📊 Any play in the game. Be the first!")
            parts.append(historyvoid)
        
        return "\n".join(parts)
    if detail_name in {"dice_admin"}:
        dice_state = _get_canvas_dice_state(guild)
        hot_pot = int(dice_state["bet"] * 73)
        return "\n".join([
            f"**🎲 {_bot_display_name} Canvas - Trickster / Dice / Admin**",
            "Configure dice game settings and announcements",
            "**Current settings**",
            f"**Current fixed bet:** {dice_state['bet']:,} gold",
            f"**Current pot:** {dice_state['pot_balance']:,} gold",
            f"**Big pot threshold:** ~{hot_pot:,} gold",
            "",
            "**Controls**",
            f"- Announcements: {'On' if dice_state['announcements_active'] else 'Off'}",
            "- Editable fixed bet input",
            "- Editable pot value input",
            "- Announcement on/off selector",
            "",
            "**Routing**",
            "- Back only from here",
            "- No other subrole buttons are shown in this admin screen",
        ])
    if detail_name in {"beggar"}:
        beggar_state = _get_canvas_beggar_state(guild)
        return "\n".join([
            _trickster_text("canvas_beggar_title", f"**🙏 {_bot_display_name} Canvas - Trickster / Beggar**"),
            _trickster_text("canvas_beggar_description", "Donate gold to support the clan project"),
            beggar_state["message"].format(reason=beggar_state["last_reason"] or "the current clan project") if beggar_state["message"] else "",
            "",
            f"**Current fund:** {beggar_state['fund_balance']:,} gold",
            f"**Last reason:** {beggar_state['last_reason']}",
            "",
            "**Donate gold**",
            "- Enter the amount in the donation modal",
            "- Confirm to transfer gold from your wallet",
            "",
            "**Routing**",
            "- This is the user-facing beggar surface",
            "- Use `Admin` for enable/frequency controls",
        ])
    if detail_name in {"beggar_admin"}:
        beggar_state = _get_canvas_beggar_state(guild)
        return "\n".join([
            f"**🙏 {_bot_display_name} Canvas - Trickster / Beggar / Admin**",
            "Configure beggar functionality and frequency",
            f"**Status:** {'On' if beggar_state['enabled'] else 'Off'}",
            f"**Frequency:** every {beggar_state['frequency_hours']}h",
            "",
            "**Controls**",
            "- Enable or disable beggar",
            "- Editable frequency box",
            "- Users can donate from the personal beggar surface",
            "",
            "**Routing**",
            "- Back only from here",
        ])
    if detail_name in {"ring"}:
        ring_state = _get_canvas_ring_state(guild)
        
        # Get ring view messages from personality with fallback
        ring_messages = _personality_descriptions.get("ring_view_messages", {})
        server_name = guild.name if guild else "Server"
        
        # Title and description from personality files with fallback
        title = _trickster_text("canvas_ring_title", f"👁️ **{_bot_display_name} Cazador del Anillo**")
        # Remove ** from title for embed title
        clean_title = title.replace("**", "")
        description = _trickster_text("canvas_ring_description", "🔍 Putre the ring hunter seeks the lost artifact. Your boss tasked you with finding that cursed jewel and you won't return until you have it. Interrogate suspects and make them talk.")
        
        # Status messages
        status_active = ring_messages.get("status_active", "✅ **HUNT ACTIVE** - Putre is seeking the ring")
        status_inactive = ring_messages.get("status_inactive", "❌ **HUNT INACTIVE** - Putre is resting")
        
        # Target messages
        current_target_label = ring_messages.get("current_target", "🎯 **CURRENT TARGET:**")
        target_unknown = ring_messages.get("target_unknown", "👤 No suspect selected")
        
        # Investigation messages
        investigation_title = ring_messages.get("investigation_title", "🔍 **MAKE AN ACCUSATION:**")
        investigation_instructions = ring_messages.get("investigation_instructions", 
            "• Use **Ring: Accuse** from the dropdown below\n"
            "• Enter: @username, user ID, or visible name\n"
            "• The AI will generate a threatening accusation\n"
            "• Accusation will be posted publicly in the channel"
        )
        investigation_warning = ring_messages.get("investigation_warning",
            "⚠️ **IMPORTANT:**\n"
            "• You cannot accuse yourself\n"
            "• You cannot accuse bots\n"
            "• Ring must be enabled by an admin first"
        )
        
        # Inactive messages
        inactive_title = ring_messages.get("inactive_title", "⚠️ **THE HUNT IS INACTIVE**")
        inactive_instructions = ring_messages.get("inactive_instructions",
            "To enable ring functionality:\n"
            "• An admin must go to **Ring Admin**\n"
            "• Click **Ring: On** to activate\n"
            "• Set frequency for automatic investigations\n\n"
            "Once enabled, you can accuse users of carrying the One Ring!"
        )
        
        # Navigation messages
        navigation_info = ring_messages.get("navigation_info",
            "📍 **NAVIGATION:**\n"
            "• You are at `trickster / ring / personal`\n"
            "• Use `Admin` for on/off and frequency controls\n"
            "• Select **Ring: Accuse** from the dropdown to make accusations"
        )
        
        parts = [
            f"**{clean_title}**",
            description,
            f"**Status:** {'✅ Active' if ring_state['enabled'] else '❌ Inactive'}",
            f"**Frequency:** Every {ring_state['frequency_hours']} hours",
            "",
        ]
        
        if ring_state['enabled']:
            parts.extend([
                current_target_label,
                f"👤 {ring_state['target_user_name']}" if ring_state['target_user_name'] != "Unknown bearer" else target_unknown,
                "",
                investigation_title,
                investigation_instructions,
                "",
                investigation_warning,
            ])
        else:
            parts.extend([
                inactive_title,
                "",
                inactive_instructions,
            ])
        
        parts.extend([
            "",
            navigation_info,
        ])
        
        return "\n".join(parts)
    if detail_name in {"ring_admin"}:
        ring_state = _get_canvas_ring_state(guild)
        return "\n".join([
            f"**👁️ {_bot_display_name} Canvas - Trickster / Ring / Admin**",
            "Configure ring hunt functionality and frequency",
            f"**Status:** {'On' if ring_state['enabled'] else 'Off'}",
            f"**Frequency:** every {ring_state['frequency_hours']}h",
            "",
            "**Controls**",
            "- Enable or disable ring",
            "- Editable frequency box",
            "",
            "**Routing**",
            "- Back only from here",
        ])
    return None


def _build_canvas_role_banker(agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str:
    """Build the unified Banker role view with wallet information."""
    banker_messages = _personality_answers.get("banker_messages", {})
    banker_descriptions = _personality_descriptions.get("banker_messages", {})
    
    def _banker_text(key: str, fallback: str) -> str:
        value = banker_descriptions.get(key, banker_messages.get(key))
        # Replace {_bot} placeholder
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback
    
    # Get banker data
    balance = 0
    tae = 1
    bonus = 10
    user_name = "Unknown"
    server_name = "Unknown Server"
    history = []
    dice_game_ready = False
    
    if guild is not None and get_banker_db_instance is not None:
        try:
            server_key = get_server_key(guild)
            db_banker = get_banker_db_instance(server_key)
            server_id = str(guild.id)
            
            # Get server info
            from agent_db import get_active_server_name
            server_name = get_active_server_name() or guild.name
            
            if author_id is not None:
                user_id = str(author_id)
                user_name = guild.get_member(author_id).display_name if guild.get_member(author_id) else "Unknown User"
                
                # Create wallet if needed
                was_created, initial_balance = db_banker.create_wallet(user_id, user_name, server_id, server_name)
                
                # Initialize dice game account
                try:
                    from roles.banker.banker_discord import _initialize_dice_game_account
                    dice_game_ready = _initialize_dice_game_account(user_id, user_name, server_id, server_key, server_name)
                except:
                    pass
                
                # Get balance and history
                balance = db_banker.get_balance(user_id, server_id)
                history = db_banker.get_transaction_history(user_id, server_id, limit=5)
            
            tae = db_banker.obtener_tae(server_id)
            bonus = db_banker.obtener_opening_bonus(server_id)
        except Exception as e:
            logger.warning(f"Could not load banker state for Canvas: {e}")
    
    # Build the unified view with clean format - title as first line
    title = _banker_text('canvas_title', '💰 El Gran Kofre de Putre')
    content_parts = [
        f"**{title}**",
        "──────────────────────────────",
        f":coin: {balance:,} gold coins",
        f":bank: {server_name}",
        f":bust_in_silhouette: {user_name}",
        _banker_text('canvas_description', '¡mira tu montaña de oro o iora por zer probe umano!'),
        "──────────────────────────────",
        "- Recent Transactions",
    ]
    
    # Add recent transactions
    if history:
        for trans in history[:3]:  # Show only last 3 transactions
            trans_type, amount, balance_before, balance_after, description, date, admin = trans
            emoji = ":inbox_tray:" if amount > 0 else ":outbox_tray:"
            content_parts.append(f"{emoji} {amount:,} ({trans_type})")
    else:
        content_parts.append("No transactions yet")
    
    # Return content with properly formatted title for embed
    return "\n".join(content_parts)


def _build_canvas_role_banker_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Redirect all banker details to the unified main view."""
    # All banker details (including 'wallet' and 'overview') redirect to the same unified view
    return _build_canvas_role_banker({}, admin_visible, guild, author_id)


def _build_canvas_role_mc(last_action=None, queue_info=None, mc_messages=None) -> str:
    """Build the MC role view with dynamic state."""
    # Try to get MC messages, fallback to empty dict
    mc_messages_dict = {}
    try:
        mc_messages_dict = _personality_descriptions.get("mc_messages", {})
    except Exception:
        pass
    
    def _mc_text(key: str, fallback: str) -> str:
        value = mc_messages_dict.get(key)
        # Replace {_bot} placeholder
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback
    
    # Title as first line (will become embed title)
    parts = [_mc_text("canvas_mc_title", f"**🎵 {_bot_display_name} Canvas - MC (Master of Ceremonies)**")]
    
    # Add subtitle and separator as separate lines
    parts.append(_mc_text("canvas_mc_subtitle", "Klavijas de kontrol"))
    parts.append(_mc_text("canvas_mc_separator", "──────────────────────────────"))
    
    # Show last action if available
    if last_action:
        parts.append(f"✅ **Last Action:** {last_action}")
    
    # Add description from JSON or fallback
    if not (last_action or queue_info or mc_messages):
        parts.append(_mc_text("canvas_mc_description", "**Music Control Center**\nUse the dropdown below to control music playback\n🎵 Play Now - ➕ Add to Queue - ⏭️ Skip\n⏸️ Pause - ▶️ Resume - ⏹️ Stop\n📋 View Queue - 🔊 Volume"))
        parts.append(_mc_text("canvas_mc_voice_required", "**Voice Channel Required**\nYou must be in a voice channel to use MC\nBot will auto-connect to your channel"))
    
    # Show queue information
    if queue_info:
        parts.append("\n📋 **Current Queue:**")
        if queue_info and len(queue_info) > 0:
            for i, (title, artist, duration, user) in enumerate(queue_info[:5], 1):
                parts.append(f"  {i}. {title}")
                if artist:
                    parts.append(f"     👤 {artist}")
                if duration and duration != "Desconocida":
                    parts.append(f"     ⏱️ {duration}")
            if len(queue_info) > 5:
                parts.append(f"  ... and {len(queue_info) - 5} more songs")
        else:
            parts.append("  📭 Queue is empty")
    
    # Show MC messages if available
    if mc_messages:
        parts.append("\n📋 **MC Status:**")
        for msg in mc_messages[-3:]:  # Show last 3 messages
            parts.append(f"  {msg}")
    
    return "\n".join(parts)


def _build_canvas_role_view(role_name: str, agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Build a role-specific Canvas view."""
    if role_name == "news_watcher" and is_role_enabled_check("news_watcher", agent_config, guild):
        return _build_canvas_role_news_watcher(agent_config, admin_visible, guild)
    if role_name == "treasure_hunter" and is_role_enabled_check("treasure_hunter", agent_config, guild):
        return _build_canvas_role_treasure_hunter(agent_config, admin_visible, guild, author_id)
    if role_name == "trickster" and is_role_enabled_check("trickster", agent_config, guild):
        return _build_canvas_role_trickster(agent_config, admin_visible, guild)
    if role_name == "banker" and is_role_enabled_check("banker", agent_config, guild):
        return _build_canvas_role_banker(agent_config, admin_visible, guild, author_id)
    if role_name == "mc" and (agent_config or {}).get("roles", {}).get("mc", {}).get("enabled", False):
        return _build_canvas_role_mc()
    return None


def _build_canvas_role_detail_view(role_name: str, detail_name: str, agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Build a role detail Canvas view."""
    if role_name == "news_watcher" and is_role_enabled_check("news_watcher", agent_config, guild):
        return _build_canvas_role_news_watcher_detail(detail_name, admin_visible, guild, author_id or 0, None, None, None)
    if role_name == "treasure_hunter" and is_role_enabled_check("treasure_hunter", agent_config, guild):
        return _build_canvas_role_treasure_hunter_detail(detail_name, admin_visible, guild, author_id)
    if role_name == "trickster" and is_role_enabled_check("trickster", agent_config, guild):
        return _build_canvas_role_trickster_detail(detail_name, admin_visible, guild, author_id)
    if role_name == "banker" and is_role_enabled_check("banker", agent_config, guild):
        return _build_canvas_role_banker_detail(detail_name, admin_visible, guild, author_id)
    if role_name == "mc" and (agent_config or {}).get("roles", {}).get("mc", {}).get("enabled", False):
        return _build_canvas_role_mc()
    return None
