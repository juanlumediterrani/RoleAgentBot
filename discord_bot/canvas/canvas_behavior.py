"""Canvas Behavior content builders."""

from discord_bot import discord_core_commands as core

logger = core.logger
get_server_key = core.get_server_key
_discord_cfg = core._discord_cfg
_talk_state_by_guild_id = core._talk_state_by_guild_id
get_taboo_state = core.get_taboo_state
get_greeting_enabled = core.get_greeting_enabled


def get_canvas_behavior_action_items_for_detail(detail_name: str, admin_visible: bool, guild=None) -> list[tuple[str, str, str]]:
    from .content import _get_personality_descriptions
    server_id = get_server_key(guild) if guild else None
    descriptions = _get_personality_descriptions(server_id)
    behavior_messages = descriptions.get("behavior_messages", {})
    general = descriptions.get("general", {})

    button_greetings = behavior_messages.get("greetings", {}).get("button", "Greetings")
    button_welcome = behavior_messages.get("welcome", {}).get("button", "Welcome")
    button_memory = behavior_messages.get("memory", {}).get("button", "Memory")
    button_taboo = behavior_messages.get("taboo", {}).get("button", "Taboo")
    button_settings = behavior_messages.get("settings", {}).get("button", "Settings")

    # Get action descriptions and labels from general
    action_descriptions = general.get("action_descriptions", {})
    action_labels = general.get("action_labels", {})

    label_on = action_labels.get("on", "On")
    label_off = action_labels.get("off", "Off")
    label_now = action_labels.get("now", "Now")
    label_frequency = action_labels.get("frequency", "Frequency")
    label_add_keyword = action_labels.get("add_keyword", "Add Keyword")
    label_remove_keyword = action_labels.get("remove_keyword", "Remove Keyword")

    desc_boolean_toggle = action_descriptions.get("boolean_toggle", "Boolean toggle")
    desc_number_input = action_descriptions.get("number_input_target", "Number input target")
    desc_text_input = action_descriptions.get("text_input_target", "Text input target")
    desc_action = action_descriptions.get("action", "Action")

    # GDPR self-service option — always available to every user, both in
    # guild channels and DMs. Placed inside common_options so admin-visible
    # sections (which extend common_options) still include it.
    label_forget_me = general.get("forget_me_label", "🧹 Forget me (erase my data)")
    desc_forget_me = general.get(
        "forget_me_description",
        "Erase your personal data from every server this bot knows (GDPR Art. 17)",
    )

    common_options = [
        (f"{button_taboo}: {label_add_keyword}", "taboo_add", desc_text_input),
        (f"{button_taboo}: {label_remove_keyword}", "taboo_del", desc_text_input),
        (label_forget_me, "forget_me", desc_forget_me),
    ]

    button_personality = behavior_messages.get("personality", {}).get("button", "Personality")

    # Get settings language and role labels
    label_server_language = action_labels.get("server_language", "🌐 Server Language")
    label_role_management = action_labels.get("role_management", "🎛️ Role Management")
    label_current = action_labels.get("current", "Current:")
    label_enabled = action_labels.get("enabled", "Enabled")
    label_disabled = action_labels.get("disabled", "Disabled")
    label_always_enabled = action_labels.get("always_enabled", "Always enabled")
    settings_lang = behavior_messages.get("settings", {}).get("language_select", {}).get("description", "Change the bot's language for this server")
    settings_role = "Enable or disable bot roles"  # This could also be added to descriptions if needed

    admin_options = [
        (f"{button_greetings}: {label_on}", "greetings_on", desc_boolean_toggle),
        (f"{button_greetings}: {label_off}", "greetings_off", desc_boolean_toggle),
        (f"{button_welcome}: {label_on}", "welcome_on", desc_boolean_toggle),
        (f"{button_welcome}: {label_off}", "welcome_off", desc_boolean_toggle),
        (f"{button_taboo}: {label_on}", "taboo_on", desc_boolean_toggle),
        (f"{button_taboo}: {label_off}", "taboo_off", desc_boolean_toggle),
        (f"{button_settings}", "settings_open", "Manage server settings, roles and language"),
        (f"{button_personality}", "personality_open", "Manage bot personality"),
    ]

    items_map: dict[str, list[tuple[str, str, str]]] = {
        "conversation": common_options + (admin_options if admin_visible else []),
        "greetings": [(f"{button_greetings}: {label_on}", "greetings_on", desc_boolean_toggle), (f"{button_greetings}: {label_off}", "greetings_off", desc_boolean_toggle)] if admin_visible else [],
        "welcome": [(f"{button_welcome}: {label_on}", "welcome_on", desc_boolean_toggle), (f"{button_welcome}: {label_off}", "welcome_off", desc_boolean_toggle)] if admin_visible else [],
        "memory": [],
        "taboo": [(f"{button_taboo}: {label_on}", "taboo_on", desc_boolean_toggle), (f"{button_taboo}: {label_off}", "taboo_off", desc_boolean_toggle), (f"{button_taboo}: {label_add_keyword}", "taboo_add", desc_text_input), (f"{button_taboo}: {label_remove_keyword}", "taboo_del", desc_text_input)] if admin_visible else [(f"{button_taboo}: {label_add_keyword}", "taboo_add", desc_text_input), (f"{button_taboo}: {label_remove_keyword}", "taboo_del", desc_text_input)],
        "settings": [
            (f"{label_server_language}", "language_settings", settings_lang),
            (f"{label_role_management}", "role_control", settings_role),
        ] if admin_visible else [],
        "personality": [],  # Personality view uses custom dropdown, not action items
    }
    return items_map.get(detail_name, [])


def get_canvas_behavior_detail_items(admin_visible: bool, current_detail: str = "conversation", guild=None) -> list[tuple[str, str]]:
    from .content import _get_personality_descriptions
    server_id = get_server_key(guild) if guild else None
    behavior_descriptions = _get_personality_descriptions(server_id).get("behavior_messages", {})
    conversation_button = behavior_descriptions.get("conversation", {}).get("button", "Conversation")
    greetings_button = behavior_descriptions.get("greetings", {}).get("button", "Greetings")
    welcome_button = behavior_descriptions.get("welcome", {}).get("button", "Welcome")
    memory_button = behavior_descriptions.get("memory", {}).get("button", "Memory")
    taboo_button = behavior_descriptions.get("taboo", {}).get("button", "Taboo")
    settings_button = behavior_descriptions.get("settings", {}).get("button", "Settings")
    personality_button = behavior_descriptions.get("personality", {}).get("button", "Personality")

    items = []
    if current_detail != "conversation":
        items.append((conversation_button, "conversation"))

    if admin_visible:
        admin_items = [
            (greetings_button, "greetings"),
            (welcome_button, "welcome"),
            (memory_button, "memory"),
            (taboo_button, "taboo"),
            (settings_button, "settings"),
            (personality_button, "personality"),
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
    result = build_canvas_behavior_detail("conversation", admin_visible, guild, None, author_id=None)
    if result:
        return result
    # Fallback if build_canvas_behavior_detail returns None
    return (
        "💬 General Behavior",
        "Mention the bot in a server channel to talk\n- Send a DM to the bot for private interaction\n- Replies are shaped by the active personality and roles",
        "**Routing**\n- This is a shared global behavior, not a role-specific one\n- Use `!canvas roles` for role-specific flows"
    )


def build_canvas_behavior_detail(
    detail_name: str,
    admin_visible: bool,
    guild=None,
    agent_config: dict = None,
    setup_not_available_builder=None,
    author_id: str = None,
) -> tuple[str, str, str] | None:
    """Return (title, description, content) tuple for behavior details."""
    from .content import _get_personality_descriptions, _get_server_personality_name
    from discord_bot.db_init import get_server_personality_dir
    from pathlib import Path
    server_id = get_server_key(guild) if guild else None
    _desc = _get_personality_descriptions(server_id)
    behavior_descriptions = _desc.get("behavior_messages", {})
    general_descriptions = _desc.get("general", {})
    title_status = general_descriptions.get("status", "**Current status**")
    
    # Get personality directory name for prompts.json path
    personality_dir = get_server_personality_dir(server_id)
    personality_name = Path(personality_dir).name if personality_dir else _get_server_personality_name(server_id)

    if detail_name in {"conversation", "chat"}:
        conversations_messages = behavior_descriptions.get("conversation", {})
        conversation_title = conversations_messages.get("title", "💬 Canvas - General Behavior Conversation")
        conversation_description = conversations_messages.get("description", "**Conversation surface**\n- Mention the bot in a server channel to talk\n- Send a DM to the bot for private interaction\n- Replies are shaped by the active personality and roles\n")

        # Reemplazar placeholders con el nombre del bot
        conversation_title = conversation_title
        conversation_description = conversation_description
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
            f"{taboo_title_keywords}",
            f"- {keywords}",
            "─" * 45,
        ])
        return (conversation_title, conversation_description, content)

    if detail_name in {"greetings"}:
        greeting_enabled = False
        if guild and hasattr(guild, "id"):
            greeting_enabled = get_greeting_enabled(guild)

        greetings_descriptions = behavior_descriptions.get("greetings", {})
        greetings_title = greetings_descriptions.get("title", "👋 Canvas - General Behavior Greetings")
        greetings_description = greetings_descriptions.get("description", "**Description**\n- Presence greetings are global server behavior\n- Uses behavior/greet.py module\n- Greets users when they come online (offline → online)\n- 5-minute cooldown between greetings per user")

        # Get localized labels
        action_labels = general_descriptions.get("action_labels", {})
        label_enabled = action_labels.get("enabled", "Enabled")
        label_disabled = action_labels.get("disabled", "Disabled")

        # Reemplazar placeholders con el nombre del bot
        greetings_title = greetings_title
        greetings_description = greetings_description
        content = "\n".join([
            f"{title_status}",
            f"- {'✅ ' + label_enabled if greeting_enabled else '❌ ' + label_disabled}",
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
        if guild:
            try:
                guild_id = str(guild.id) if hasattr(guild, "id") else str(guild)
                from discord_bot.canvas.server_config import get_welcome_enabled
                welcome_enabled = get_welcome_enabled(guild_id)
            except Exception as error:
                logger.warning(f"Error loading welcome state from server_config: {error}")
                greeting_cfg = _discord_cfg.get("member_greeting", {})
                welcome_enabled = greeting_cfg.get("enabled", False)
        else:
            greeting_cfg = _discord_cfg.get("member_greeting", {})
            welcome_enabled = greeting_cfg.get("enabled", False)

        welcome_messages = behavior_descriptions.get("welcome", {})
        welcome_title = welcome_messages.get("title", "👋 Canvas - General Behavior Welcome Messages")
        welcome_description = welcome_messages.get("description", "Configure the bot to give a good greeting when someone joins the server for the first time.")

        # Get localized labels
        action_labels = general_descriptions.get("action_labels", {})
        label_enabled = action_labels.get("enabled", "Enabled")
        label_disabled = action_labels.get("disabled", "Disabled")

        # Reemplazar placeholders con el nombre del bot
        welcome_title = welcome_title
        welcome_description = welcome_description
        content = "\n".join([
            f"{title_status}",
            f"- {'✅ ' + label_enabled if welcome_enabled else '❌ ' + label_disabled}",
            "",
            "─" * 45,
        ])
        return (welcome_title, welcome_description, content)

    if detail_name in {"memory"}:
        if not admin_visible:
            if callable(setup_not_available_builder):
                return setup_not_available_builder()
            return "❌ This setup is only available to administrators."

        # Get selected memory type from agent_config (will be set by dropdown)
        # Default to "long" if not set
        selected_memory_type = (agent_config or {}).get("selected_memory_type", "long") if agent_config else "long"

        # Ensure personality_name is defined for prompts.json path
        if 'personality_name' not in locals() or not personality_name:
            personality_name = _get_server_personality_name(server_id)

        # Load personality memory content from agent database
        memory_content = ""
        try:
            from agent_db import get_db_instance
            
            db = get_db_instance(server_id)
            
            # Map memory types to database methods
            if selected_memory_type == "long":
                record = db.get_daily_memory_record()
                if record:
                    memory_content = record.get("summary", "")
                else:
                    # Load fallback from prompts.json in databases directory
                    try:
                        import json
                        import os
                        prompts_path = f"databases/{server_id}/{personality_name}/prompts.json"
                        if os.path.exists(prompts_path):
                            with open(prompts_path, 'r', encoding='utf-8') as f:
                                prompts_data = json.load(f)
                                fallbacks = prompts_data.get("synthesis_paragraphs", {}).get("fallbacks", {})
                                memory_content = fallbacks.get("daily_memory", "No daily memory available.")
                    except Exception as e:
                        logger.warning(f"Could not load daily memory fallback from prompts: {e}")
                        memory_content = "No daily memory available."
            elif selected_memory_type == "recent":
                record = db.get_recent_memory_record()
                if record:
                    memory_content = record.get("summary", "")
                else:
                    # Load fallback from prompts.json in databases directory
                    try:
                        import json
                        import os
                        prompts_path = f"databases/{server_id}/{personality_name}/prompts.json"
                        if os.path.exists(prompts_path):
                            with open(prompts_path, 'r', encoding='utf-8') as f:
                                prompts_data = json.load(f)
                                fallbacks = prompts_data.get("synthesis_paragraphs", {}).get("fallbacks", {})
                                memory_content = fallbacks.get("recent_memory", "No recent memory available.")
                    except Exception as e:
                        logger.warning(f"Could not load recent memory fallback from prompts: {e}")
                        memory_content = "No recent memory available."
            elif selected_memory_type == "relationship":
                # Try to get actual relationship memory from database
                memory_content = ""
                if author_id:
                    try:
                        record = db.get_user_relationship_memory(author_id)
                        if record and record.get("summary"):
                            memory_content = record.get("summary", "")
                        else:
                            # Load fallback from prompts.json in databases directory
                            try:
                                import json
                                import os
                                prompts_path = f"databases/{server_id}/{personality_name}/prompts.json"
                                if os.path.exists(prompts_path):
                                    with open(prompts_path, 'r', encoding='utf-8') as f:
                                        prompts_data = json.load(f)
                                        fallbacks = prompts_data.get("synthesis_paragraphs", {}).get("fallbacks", {})
                                        relationship_fallback = fallbacks.get("relationship_memory", "No relationship memory available.")
                                        # Format with user_name if needed
                                        memory_content = relationship_fallback.format(user_name="{usuario}")
                                else:
                                    memory_content = "No relationship memory available."
                            except Exception as e:
                                logger.warning(f"Could not load relationship fallback from prompts: {e}")
                                memory_content = "No relationship memory available."
                    except Exception as e:
                        logger.warning(f"Could not load relationship memory from database: {e}")
                        # Load fallback from prompts.json
                        try:
                            import json
                            import os
                            prompts_path = f"databases/{server_id}/{personality_name}/prompts.json"
                            if os.path.exists(prompts_path):
                                with open(prompts_path, 'r', encoding='utf-8') as f:
                                    prompts_data = json.load(f)
                                    fallbacks = prompts_data.get("synthesis_paragraphs", {}).get("fallbacks", {})
                                    relationship_fallback = fallbacks.get("relationship_memory", "No relationship memory available.")
                                    memory_content = relationship_fallback.format(user_name="{usuario}")
                            else:
                                memory_content = "No relationship memory available."
                        except Exception as e2:
                            logger.warning(f"Could not load relationship fallback from prompts: {e2}")
                            memory_content = "No relationship memory available."
                else:
                    # No author_id provided, load fallback
                    try:
                        import json
                        import os
                        prompts_path = f"databases/{server_id}/{personality_name}/prompts.json"
                        if os.path.exists(prompts_path):
                            with open(prompts_path, 'r', encoding='utf-8') as f:
                                prompts_data = json.load(f)
                                fallbacks = prompts_data.get("synthesis_paragraphs", {}).get("fallbacks", {})
                                relationship_fallback = fallbacks.get("relationship_memory", "No relationship memory available.")
                                memory_content = relationship_fallback.format(user_name="{usuario}")
                        else:
                            memory_content = "No relationship memory available."
                    except Exception as e:
                        logger.warning(f"Could not load relationship fallback from prompts: {e}")
                        memory_content = "No relationship memory available."
            else:
                # Unknown memory type - use English hardcoded fallback
                memory_content = "Unrecognized memory type."
                
        except Exception as e:
            logger.warning(f"Could not load memory content from database: {e}")
            memory_content = "Error loading memory content."

        memory_messages = behavior_descriptions.get("memory", {})
        memory_title = memory_messages.get("title", "🧠 Canvas - General Behavior Memory")
        memory_description = memory_messages.get("description", "View the personality's memory in different formats")

        # Get localized labels from memory dropdown configuration
        memory_config = memory_messages.get("dropdown", {})
        long_config = memory_config.get("long", {})
        recent_config = memory_config.get("recent", {})
        relationship_config = memory_config.get("relationship", {})
        
        label_long = long_config.get("label", "Long Memory")
        label_recent = recent_config.get("label", "Recent Memory")
        label_relationship = relationship_config.get("label", "Relationship Memory")

        # Get memory titles from canvas_home_messages (at discord level, not inside general)
        canvas_home = _desc.get("canvas_home_messages", {})
        dailymemorytitle = canvas_home.get("dailymemorytitle", "🗿 **Memory**")
        recentsynthesistitle = canvas_home.get("recentsynthesistitle", "🚩 **Recent Events**")
        personalsynthesistitle = canvas_home.get("personalsynthesistitle", "🍻 **Relationship**")

        # Map memory types to their canvas_home_messages titles
        type_titles = {
            "long": dailymemorytitle,
            "recent": recentsynthesistitle,
            "relationship": personalsynthesistitle
        }
        selected_title = type_titles.get(selected_memory_type, dailymemorytitle)


        # Mark selected memory type
        type_labels = {
            "long": label_long,
            "recent": label_recent,
            "relationship": label_relationship
        }
        selected_label = type_labels.get(selected_memory_type, label_long)

        # Reemplazar placeholders con el nombre del bot
        memory_title = memory_title
        memory_description = memory_description
        
        # Build content with memory content based on selected type
        content_lines = [
            f"{selected_title}",
            "",
            memory_content
        ]
        
        content_lines.extend([
            "",
            "─" * 45,
        ])
        
        content = "\n".join(content_lines)
        return (memory_title, memory_description, content)

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
        taboo_title = taboo_messages.get("title", "🚫 Canvas - General Behavior Taboo")
        taboo_description = taboo_messages.get("description", "- Taboo watches normal server chat and can trigger an in-character reply")
        taboo_title_keywords = taboo_messages.get("title_keywords", "**Current keywords**")

        # Get localized labels
        action_labels = general_descriptions.get("action_labels", {})
        label_enabled = action_labels.get("enabled", "Enabled")
        label_disabled = action_labels.get("disabled", "Disabled")

        # Reemplazar placeholders con el nombre del bot
        taboo_title = taboo_title
        taboo_description = taboo_description
        content = "\n".join([
            f"{title_status}",
            f"- {'✅ ' + label_enabled if state.get('enabled', False) else '❌ ' + label_disabled}",
            "",
            f"{taboo_title_keywords}",
            f"- {keywords}",
            "─" * 45,
        ])
        return (taboo_title, taboo_description, content)

    if detail_name in {"settings", "role_control"}:
        if not admin_visible:
            if callable(setup_not_available_builder):
                return setup_not_available_builder()
            return "❌ This setup is only available to administrators."

        # Note: Roles initialization happens once at server startup via server_config.json
        from .server_config import get_server_language, get_available_languages

        server_id = str(guild.id) if guild else "0"
        
        # Get current server language
        current_language = get_server_language(server_id)
        available_langs = get_available_languages()
        language_display = available_langs.get(current_language, current_language)

        # Get labels for status display from action_labels
        action_labels = general_descriptions.get("action_labels", {})
        label_enabled = action_labels.get("enabled", "Enabled")
        label_disabled = action_labels.get("disabled", "Disabled")
        label_always_enabled = action_labels.get("always_enabled", "Always enabled")
        label_server_language = action_labels.get("server_language", "🌐 Server Language")
        label_role_management = action_labels.get("role_management", "🎛️ Role Management")
        label_current = action_labels.get("current", "Current:")

        # Filter roles that are enabled in agent_config globally
        # Roles disabled in agent_config should not appear at all (like they don't exist)
        # Also filter out subroles (beggar is a subrole of banker)
        roles_cfg = (agent_config or {}).get("roles", {})
        all_roles = [
            role for role in ["news_watcher", "treasure_hunter", "trickster", "banker", "mc", "juggler", "shaman", "scholar"]
            if roles_cfg.get(role, {}).get("enabled", False)
        ]

        # Load role titles from individual role description files
        role_labels_from_desc = {}
        from .content import _get_server_personality_name
        from pathlib import Path
        import json

        # Get personality name from server_config
        try:
            from pathlib import Path
            server_config_path = Path(__file__).parent.parent.parent / "databases" / server_id / "server_config.json"
            if server_config_path.exists():
                import json
                with open(server_config_path, 'r', encoding='utf-8') as f:
                    server_config = json.load(f)
                personality_name = server_config.get("active_personality", "bot")
            else:
                personality_name = "bot"
        except Exception:
            personality_name = "bot"

        base_dir = Path(__file__).parent.parent.parent
        descriptions_dir = base_dir / "databases" / server_id / personality_name / "descriptions"

        for role_name in all_roles:
            role_file = descriptions_dir / f"{role_name}.json"
            try:
                if role_file.exists():
                    with open(role_file, 'r', encoding='utf-8') as f:
                        role_data = json.load(f)
                    # Use the title from the role description file
                    title = role_data.get("title", role_name.replace("_", " ").title())
                    role_labels_from_desc[role_name] = title.strip()
                else:
                    role_labels_from_desc[role_name] = role_name.replace("_", " ").title()
            except Exception as e:
                logger.warning(f"Error loading role title for {role_name}: {e}")
                role_labels_from_desc[role_name] = role_name.replace("_", " ").title()

        status_lines = []
        for role_name in all_roles:
            label = role_labels_from_desc.get(role_name, role_name.replace("_", " ").title())

            # For Canvas, always try to check server_config regardless of db availability
            if role_name == "mc" and agent_config and agent_config.get("roles", {}).get("mc", {}).get("enabled", False):
                status_lines.append(f"- {label}: ✅ {label_always_enabled}")
                continue

            # PRIMARY: Check server_config
            enabled = False
            try:
                from .server_config import is_role_enabled
                from agent_db import get_server_id

                server_id = str(guild.id) if guild else get_server_id()
                enabled = is_role_enabled(server_id, role_name, default_enabled=False)
            except Exception as e:
                logger.warning(f"Error checking {role_name} in server_config: {e}")
                enabled = False

            status_lines.append(f"- {label}: {'✅ ' + label_enabled if enabled else '❌ ' + label_disabled}")

        settings_messages = behavior_descriptions.get("settings", {})
        settings_title = settings_messages.get("title", "⚙️ Canvas - Server Settings")
        settings_description = settings_messages.get("description", "Manage server language and role activations")

        # Build three sections
        # Section 1: Language (now second as requested)
        language_section = [
            f"**{label_server_language}**",
            f"- {label_current} {language_display} ({current_language})",
            "",
        ]

        # Section 2: Roles (now third)
        roles_section = [
            f"**{label_role_management}**",
            *status_lines,
            "",
        ]

        content = "\n".join([
            *language_section,
            "─" * 45,
            "",
            *roles_section,
            "─" * 45,
        ])
        return (settings_title, settings_description, content)

    if detail_name in {"personality"}:
        if not admin_visible:
            if callable(setup_not_available_builder):
                return setup_not_available_builder()
            return "❌ This setup is only available to administrators."

        personality_messages = behavior_descriptions.get("personality", {})
        personality_title = personality_messages.get("title", "🎭 Canvas - Personality Management")
        personality_description = personality_messages.get("description", "Manage the bot's personality for this server")

        # Replace placeholders
        personality_title = personality_title
        personality_description = personality_description

        # Load identity_body from current personality
        identity_body_text = ""
        try:
            from .content import _get_server_personality_name
            from pathlib import Path
            import json

            personality_name = _get_server_personality_name(server_id)
            base_dir = Path(__file__).parent.parent.parent
            personality_file = base_dir / "personalities" / personality_name / "personality.json"

            if personality_file.exists():
                with open(personality_file, 'r', encoding='utf-8') as f:
                    personality_data = json.load(f)
                identity_body = personality_data.get("system_prompt_template", {}).get("identity_body", [])
                if identity_body:
                    identity_body_text = "\n".join(identity_body)
        except Exception as e:
            logger.warning(f"Could not load identity_body: {e}")

        content_lines = [
            f"{title_status}\n",
        ]

        if identity_body_text:
            content_lines.append(identity_body_text)
            content_lines.append("─" * 45)

        content = "\n".join(content_lines)
        return (personality_title, personality_description, content)

    return None
