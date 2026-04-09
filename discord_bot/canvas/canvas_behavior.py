"""Canvas Behavior content builders."""

from discord_bot import discord_core_commands as core

logger = core.logger
get_server_key = core.get_server_key
_bot_display_name = core._bot_display_name
_discord_cfg = core._discord_cfg
_talk_state_by_guild_id = core._talk_state_by_guild_id
get_taboo_state = core.get_taboo_state
get_greeting_enabled = core.get_greeting_enabled
get_behavior_db_instance = core.get_behavior_db_instance


def get_canvas_behavior_action_items_for_detail(detail_name: str, admin_visible: bool, guild=None) -> list[tuple[str, str, str]]:
    from .content import _get_personality_descriptions
    server_id = get_server_key(guild) if guild else None
    behavior_messages = _get_personality_descriptions(server_id).get("behavior_messages", {})
    button_greetings = behavior_messages.get("greetings", {}).get("button", "Greetings")
    button_welcome = behavior_messages.get("welcome", {}).get("button", "Welcome")
    button_commentary = behavior_messages.get("comentary", {}).get("button", "Commentary")
    button_taboo = behavior_messages.get("taboo", {}).get("button", "Taboo")
    button_role_control = behavior_messages.get("role_control", {}).get("button", "Role Control")

    common_options = [
        (f"{button_commentary}: On", "commentary_on", "Boolean toggle"),
        (f"{button_commentary}: Off", "commentary_off", "Boolean toggle"),
        (f"{button_commentary}: Now", "commentary_now", "Action"),
        (f"{button_taboo}: Add Keyword", "taboo_add", "Text input target"),
        (f"{button_taboo}: Remove Keyword", "taboo_del", "Text input target"),
    ]

    admin_options = [
        (f"{button_greetings}: On", "greetings_on", "Boolean toggle"),
        (f"{button_greetings}: Off", "greetings_off", "Boolean toggle"),
        (f"{button_welcome}: On", "welcome_on", "Boolean toggle"),
        (f"{button_welcome}: Off", "welcome_off", "Boolean toggle"),
        (f"{button_commentary}: Frequency", "commentary_frequency", "Number input target"),
        (f"{button_taboo}: On", "taboo_on", "Boolean toggle"),
        (f"{button_taboo}: Off", "taboo_off", "Boolean toggle"),
        (f"{button_role_control}", "role_control_open", "Select role and boolean state"),
    ]

    items_map: dict[str, list[tuple[str, str, str]]] = {
        "conversation": common_options + (admin_options if admin_visible else []),
        "greetings": [(f"{button_greetings}: On", "greetings_on", "Boolean toggle"), (f"{button_greetings}: Off", "greetings_off", "Boolean toggle")] if admin_visible else [],
        "welcome": [(f"{button_welcome}: On", "welcome_on", "Boolean toggle"), (f"{button_welcome}: Off", "welcome_off", "Boolean toggle")] if admin_visible else [],
        "commentary": common_options,
        "taboo": [(f"{button_taboo}: On", "taboo_on", "Boolean toggle"), (f"{button_taboo}: Off", "taboo_off", "Boolean toggle"), (f"{button_taboo}: Add Keyword", "taboo_add", "Text input target"), (f"{button_taboo}: Remove Keyword", "taboo_del", "Text input target")] if admin_visible else [(f"{button_taboo}: Add Keyword", "taboo_add", "Text input target"), (f"{button_taboo}: Remove Keyword", "taboo_del", "Text input target")],
        "role_control": [(f"{button_role_control}", "role_control_open", "Select role and boolean state")] if admin_visible else [],
    }
    return items_map.get(detail_name, [])


def get_canvas_behavior_detail_items(admin_visible: bool, current_detail: str = "conversation", guild=None) -> list[tuple[str, str]]:
    from .content import _get_personality_descriptions
    server_id = get_server_key(guild) if guild else None
    behavior_descriptions = _get_personality_descriptions(server_id).get("behavior_messages", {})
    conversation_button = behavior_descriptions.get("conversation", {}).get("button", "Conversation")
    greetings_button = behavior_descriptions.get("greetings", {}).get("button", "Greetings")
    welcome_button = behavior_descriptions.get("welcome", {}).get("button", "Welcome")
    commentary_button = behavior_descriptions.get("comentary", {}).get("button", "Commentary")
    taboo_button = behavior_descriptions.get("taboo", {}).get("button", "Taboo")
    role_control_button = behavior_descriptions.get("role_control", {}).get("button", "Role Control")

    items = []
    if current_detail != "conversation":
        items.append((conversation_button, "conversation"))

    if admin_visible:
        admin_items = [
            (greetings_button, "greetings"),
            (welcome_button, "welcome"),
            (commentary_button, "commentary"),
            (taboo_button, "taboo"),
            (role_control_button, "role_control"),
        ]
        items.extend([item for item in admin_items if item[1] != current_detail])
    return items


def build_canvas_behavior(
    greet_name: str,
    nogreet_name: str,
    welcome_name: str,
    nowelcome_name: str,
    role_cmd_name: str,
    talk_cmd_name: str,
    admin_visible: bool,
    guild=None,
) -> tuple[str, str, str]:
    """Return (title, description, content) tuple for behavior overview."""
    result = build_canvas_behavior_detail("conversation", admin_visible, guild, None)
    if result:
        return result
    # Fallback if build_canvas_behavior_detail returns None
    return (
        f"💬 {_bot_display_name} General Behavior",
        "Mention the bot in a server channel to talk\n- Send a DM to the bot for private interaction\n- Replies are shaped by the active personality and roles",
        "**Routing**\n- This is a shared global behavior, not a role-specific one\n- Use `!canvas roles` for role-specific flows"
    )


def build_canvas_behavior_detail(
    detail_name: str,
    admin_visible: bool,
    guild=None,
    agent_config: dict = None,
    setup_not_available_builder=None,
    behavior_db_loader=None,
) -> tuple[str, str, str] | None:
    """Return (title, description, content) tuple for behavior details."""
    from .content import _get_personality_descriptions
    server_id = get_server_key(guild) if guild else None
    _desc = _get_personality_descriptions(server_id)
    behavior_descriptions = _desc.get("behavior_messages", {})
    general_descriptions = _desc.get("general", {})
    title_status = general_descriptions.get("status", "**Current status**")

    if detail_name in {"conversation", "chat"}:
        conversations_messages = behavior_descriptions.get("conversation", {})
        conversation_title = conversations_messages.get("title", f"💬 {_bot_display_name} Canvas - General Behavior Conversation")
        conversation_description = conversations_messages.get("description", "**Conversation surface**\n- Mention the bot in a server channel to talk\n- Send a DM to the bot for private interaction\n- Replies are shaped by the active personality and roles\n")

        # Reemplazar placeholders con el nombre del bot
        conversation_title = conversation_title.replace("{_bot_display_name}", _bot_display_name)
        conversation_description = conversation_description.replace("{_bot_display_name}", _bot_display_name)

        if guild and hasattr(guild, "id"):
            guild_id = str(guild.id)
        elif guild:
            guild_id = int(guild)
        else:
            guild_id = 0

        taboo_title_keywords = behavior_descriptions.get("taboo", {}).get("title_keywords", "**Current keywords**")
        state = get_taboo_state(guild_id)
        keywords = ", ".join(state.get("keywords", [])) or "(none)"

        content = "\n".join([
            f"{taboo_title_keywords}\n",
            f"- {keywords}",
            "─" * 45,
        ])
        return (conversation_title, conversation_description, content)

    if detail_name in {"greetings"}:
        greeting_enabled = False
        if guild and hasattr(guild, "id"):
            greeting_enabled = get_greeting_enabled(guild)

        greetings_descriptions = behavior_descriptions.get("greetings", {})
        greetings_title = greetings_descriptions.get("title", f"👋 {_bot_display_name} Canvas - General Behavior Greetings")
        greetings_description = greetings_descriptions.get("description", "**Description**\n- Presence greetings are global server behavior\n- Uses behavior/greet.py module\n- Greets users when they come online (offline → online)\n- 5-minute cooldown between greetings per user")

        # Reemplazar placeholders con el nombre del bot
        greetings_title = greetings_title.replace("{_bot_display_name}", _bot_display_name)
        greetings_description = greetings_description.replace("{_bot_display_name}", _bot_display_name)

        content = "\n".join([
            f"{title_status}\n",
            f"- {'✅ Enabled' if greeting_enabled else '❌ Disabled'}",
            "",
            "─" * 45,
        ])
        return (greetings_title, greetings_description, content)

    if detail_name in {"welcome"}:
        if not admin_visible:
            if callable(setup_not_available_builder):
                return setup_not_available_builder()
            return "❌ This setup is only available to administrators."

        welcome_enabled = False
        if guild and get_behavior_db_instance is not None:
            try:
                guild_id = str(guild.id) if hasattr(guild, "id") else str(guild)
                db = get_behavior_db_instance(guild_id)
                welcome_enabled = db.get_welcome_enabled()
            except Exception as error:
                logger.warning(f"Error loading welcome state from behaviors database: {error}")
                greeting_cfg = _discord_cfg.get("member_greeting", {})
                welcome_enabled = greeting_cfg.get("enabled", False)
        else:
            greeting_cfg = _discord_cfg.get("member_greeting", {})
            welcome_enabled = greeting_cfg.get("enabled", False)

        welcome_messages = behavior_descriptions.get("welcome", {})
        welcome_title = welcome_messages.get("title", f"👋 {_bot_display_name} Canvas - General Behavior Welcome Messages")
        welcome_description = welcome_messages.get("description", "Configure the bot to give a good greeting when someone joins the server for the first time.")

        # Reemplazar placeholders con el nombre del bot
        welcome_title = welcome_title.replace("{_bot_display_name}", _bot_display_name)
        welcome_description = welcome_description.replace("{_bot_display_name}", _bot_display_name)

        content = "\n".join([
            f"{title_status}\n",
            f"- {'✅ Enabled' if welcome_enabled else '❌ Disabled'}",
            "",
            "─" * 45,
        ])
        return (welcome_title, welcome_description, content)

    if detail_name in {"commentary", "talk"}:
        if not admin_visible:
            if callable(setup_not_available_builder):
                return setup_not_available_builder()
            return "❌ This setup is only available to administrators."

        if guild and hasattr(guild, "id"):
            guild_id = int(guild.id)
            guild_id_str = str(guild.id)
        elif guild:
            guild_id = int(guild)
            guild_id_str = str(guild)
        else:
            guild_id = 0
            guild_id_str = "0"

        enabled = False
        interval_minutes = 180
        channel_id = None

        if get_behavior_db_instance is not None:
            try:
                db = get_behavior_db_instance(guild_id_str)
                db_state = db.get_commentary_state()
                enabled = db_state["enabled"]
                config = db_state.get("config", {})
                interval_minutes = config.get("interval_minutes", 180)
                channel_id = config.get("channel_id")
            except Exception as error:
                logger.warning(f"Error loading commentary from behaviors DB: {error}")

        if not enabled and not channel_id:
            state = _talk_state_by_guild_id.get(guild_id) or {}
            enabled = state.get("enabled", False)
            interval_minutes = state.get("interval_minutes", 180)
            channel_id = state.get("channel_id")

        commentary_messages = behavior_descriptions.get("comentary", {})
        commentary_title = commentary_messages.get("title", f"🗣️ {_bot_display_name} Canvas - General Behavior Mission Commentary")
        commentary_description = commentary_messages.get("description", "Commentary is global behavior driven by active roles")

        # Reemplazar placeholders con el nombre del bot
        commentary_title = commentary_title.replace("{_bot_display_name}", _bot_display_name)
        commentary_description = commentary_description.replace("{_bot_display_name}", _bot_display_name)

        content = "\n".join([
            f"{title_status}\n",
            f"- {'✅ Enabled' if enabled else '❌ Disabled'}",
            f"- Interval: {interval_minutes} minutes",
            f"- Channel: {f'<#{channel_id}>' if channel_id else 'Not set'}" if enabled else "- Channel: N/A (disabled)",
            "",
            "─" * 45,
        ])
        return (commentary_title, commentary_description, content)

    if detail_name in {"taboo"}:
        if not admin_visible:
            if callable(setup_not_available_builder):
                return setup_not_available_builder()
            return "❌ This setup is only available to administrators."

        if guild and hasattr(guild, "id"):
            guild_id = int(guild.id)
        elif guild:
            guild_id = int(guild)
        else:
            guild_id = 0

        state = get_taboo_state(guild_id)
        keywords = ", ".join(state.get("keywords", [])) or "(none)"

        taboo_messages = behavior_descriptions.get("taboo", {})
        taboo_title = taboo_messages.get("title", f"🚫 {_bot_display_name} Canvas - General Behavior Taboo")
        taboo_description = taboo_messages.get("description", "- Taboo watches normal server chat and can trigger an in-character reply")
        taboo_title_keywords = taboo_messages.get("title_keywords", "**Current keywords**")

        # Reemplazar placeholders con el nombre del bot
        taboo_title = taboo_title.replace("{_bot_display_name}", _bot_display_name)
        taboo_description = taboo_description.replace("{_bot_display_name}", _bot_display_name)

        content = "\n".join([
            f"{title_status}\n",
            f"- {'On' if state.get('enabled', False) else 'Off'}",
            "",
            f"{taboo_title_keywords}\n",
            f"- {keywords}",
            "─" * 45,
        ])
        return (taboo_title, taboo_description, content)

    if detail_name in {"role_control", "roles"}:
        if not admin_visible:
            if callable(setup_not_available_builder):
                return setup_not_available_builder()
            return "❌ This setup is only available to administrators."

        from discord_bot.discord_utils import initialize_roles_from_database
        initialize_roles_from_database(agent_config, guild)

        db = behavior_db_loader(guild) if callable(behavior_db_loader) else None
        all_roles = ["news_watcher", "treasure_hunter", "trickster", "banker", "mc"]
        role_labels = {
            "news_watcher": "News Watcher",
            "treasure_hunter": "Treasure Hunter",
            "trickster": "Trickster",
            "banker": "Banker",
            "mc": "MC",
        }

        status_lines = []
        for role_name in all_roles:
            label = role_labels.get(role_name, role_name.replace("_", " ").title())

            # For Canvas, always try to check roles_config regardless of db availability
            if role_name == "mc" and agent_config and agent_config.get("roles", {}).get("mc", {}).get("enabled", False):
                status_lines.append(f"- {label}: ✅ Always enabled")
                continue

            # PRIMARY: Check roles_config
            enabled = False
            try:
                from agent_roles_db import get_roles_db_instance

                # Use default server for Canvas (no guild context available)
                server_id = "default"
                roles_db = get_roles_db_instance(server_id)
                config = roles_db.get_role_config(role_name)
                if config:
                    enabled = config.get('enabled', False)
            except Exception as e:
                logger.warning(f"Error checking {role_name} in roles_config: {e}")
                enabled = False

            status_lines.append(f"- {label}: {'✅ Enabled' if enabled else '❌ Disabled'}")

        role_control_messages = behavior_descriptions.get("role_control", {})
        role_control_title = role_control_messages.get("title", f"🎛️ {_bot_display_name} Canvas - General Behavior Role Control")
        role_control_description = role_control_messages.get("description", "Role activation is managed through database - primary source")

        # Reemplazar placeholders con el nombre del bot
        role_control_title = role_control_title.replace("{_bot_display_name}", _bot_display_name)
        role_control_description = role_control_description.replace("{_bot_display_name}", _bot_display_name)

        content = "\n".join([
            f"{title_status}\n",
            *status_lines,
            "",
            "💡 **Database is primary source** - Changes are persisted immediately",
            "🔧 If you see 'System Error', the database is unavailable",
            "─" * 45,
        ])
        return (role_control_title, role_control_description, content)

    return None
