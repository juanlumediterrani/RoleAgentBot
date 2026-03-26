"""Canvas News Watcher content builders."""

from discord_bot import discord_core_commands as core
from .state import _get_canvas_watcher_method_label, _get_canvas_watcher_frequency_hours

logger = core.logger
get_news_watcher_db_instance = core.get_news_watcher_db_instance
get_watcher_messages = core.get_watcher_messages
_personality_descriptions = core._personality_descriptions
_bot_display_name = core._bot_display_name


def build_canvas_role_news_watcher(agent_config: dict, admin_visible: bool, guild=None, author_id: int = 0) -> str:
    """Build the News Watcher role view (same as personal view)."""
    return build_canvas_role_news_watcher_detail("personal", admin_visible, guild, author_id, None, None, None)


def get_canvas_channel_subscriptions_info(guild) -> str:
    """Get formatted channel subscriptions information for canvas display."""
    try:
        if get_news_watcher_db_instance is None:
            return "**Channel subscriptions**\n- Unable to load channel subscription data"

        db = get_news_watcher_db_instance(str(guild.id))
        all_channel_subs = db.get_all_channels_with_subscriptions()

        total_count = 0
        subscriptions_list = []

        for channel_id, channel_name, server_id in all_channel_subs:
            if str(server_id) == str(guild.id):
                channel_subs = db.get_channel_subscriptions(channel_id)
                total_count += len(channel_subs)

                for category, feed_id, _ in channel_subs:
                    if feed_id:
                        subscriptions_list.append(f"  📡 {category} (feed #{feed_id}) - #{channel_name}")
                    else:
                        subscriptions_list.append(f"  📡 {category} (all feeds) - #{channel_name}")

        keyword_subs = db.get_all_active_keyword_subscriptions()
        for _user_id, channel_id, keywords, category, feed_id in keyword_subs:
            if channel_id:
                try:
                    channel = guild.get_channel(int(channel_id))
                    channel_name = channel.name if channel else f"Channel-{channel_id}"
                except Exception:
                    channel_name = f"Channel-{channel_id}"

                total_count += 1
                if feed_id:
                    subscriptions_list.append(f"  🔍 {category} (keywords: {keywords}, feed #{feed_id}) - #{channel_name}")
                else:
                    subscriptions_list.append(f"  🔍 {category} (keywords: {keywords}, all feeds) - #{channel_name}")

        max_subs = 5
        usage_info = f"**Channel subscriptions** ({total_count}/{max_subs})\n"

        if total_count == 0:
            usage_info += "- No active channel subscriptions\n"
        else:
            for sub in subscriptions_list:
                usage_info += f"{sub}\n"

        config_info = "\n──────────────────────────────\n\n**Server configuration**\n"

        try:
            frequency = db.get_frequency_config(str(guild.id))
            config_info += f"- ⏰ **Check frequency**: Every {frequency} hours\n"
        except Exception:
            config_info += "- ⏰ **Check frequency**: Not configured\n"

        method = db.get_method_config(str(guild.id))
        method_labels = {
            "flat": "Flat (All news)",
            "keyword": "Keyword (Filtered)",
            "general": "General (AI-critical)",
        }
        config_info += f"- 🔧 **Default method**: {method_labels.get(method, 'Unknown')}\n"

        return usage_info + config_info

    except Exception as e:
        logger.warning(f"Could not load channel subscriptions for Canvas: {e}")
        return "**Channel subscriptions**\n- Error loading channel subscription data"


def get_canvas_user_subscriptions_info(guild, author_id: int) -> str:
    """Get formatted user subscriptions information for canvas display."""
    try:
        if get_news_watcher_db_instance is None:
            return "**Active subscriptions**\n- Unable to load subscription data"

        db = get_news_watcher_db_instance(str(guild.id))
        user_id = str(author_id)

        current_count = db.count_user_subscriptions(user_id)
        max_subs = 3
        title_active_subscriptions = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {}).get("title_active_subscriptions", "**Active subscriptions**")
        usage_info = f"{title_active_subscriptions} ({current_count}/{max_subs})\n"
        title_no_active_subscriptions = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {}).get("title_no_active_subscriptions", "- No active subscriptions")
        if current_count == 0:
            usage_info += f"{title_no_active_subscriptions}\n"
        else:
            title_your_subscriptions = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {}).get("title_your_subscriptions", "- **Your subscriptions:**")
            subscriptions_info = f"{title_your_subscriptions}\n"

            flat_subs = db.get_user_subscriptions(user_id)
            for i, (category, feed_id, _) in enumerate(flat_subs, 1):
                if feed_id:
                    subscriptions_info += f"  {i}. 📰 Flat: {category} (feed #{feed_id})\n"
                else:
                    subscriptions_info += f"  {i}. 📰 Flat: {category} (all feeds)\n"

            keyword_subs = db.get_user_keyword_subscriptions(user_id)
            for i, (category, keywords, _) in enumerate(keyword_subs, len(flat_subs) + 1):
                subscriptions_info += f"  {i}. 🔍 Keywords: {category} - {keywords}\n"

            ai_subs = db.get_user_ai_subscriptions(user_id)
            for i, (category, feed_id, _) in enumerate(ai_subs, len(flat_subs) + len(keyword_subs) + 1):
                if feed_id:
                    subscriptions_info += f"  {i}. 🤖 AI: {category} (feed #{feed_id})\n"
                else:
                    subscriptions_info += f"  {i}. 🤖 AI: {category} (all feeds)\n"

            usage_info += subscriptions_info

        title_configuration_status = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {}).get("title_configuration_status", "**Configuration status**")
        config_info = "\n"
        config_info += "-" * 45
        config_info += f"\n {title_configuration_status}\n"

        title_keyword = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {}).get("keywords_title", "🔍**Keywords:**")
        no_keywords = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {}).get("no_keywords", "None configured")
        keywords = db.get_user_keywords(user_id)
        if keywords:
            config_info += f"-  {title_keyword} {', '.join(keywords[:5])}"
            if len(keywords) > 5:
                config_info += f" (+{len(keywords) - 5} ..."
            config_info += "\n"
        else:
            config_info += f"- {title_keyword} {no_keywords}\n"

        title_premises = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {}).get("premises_title", "🤖**Premises:**")
        no_premises = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {}).get("no_premises", "None configured")
        patch_premises_configured = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {}).get("premises_configured", "configured")
        premises, _ = db.get_premises_with_context(user_id)
        if premises:
            config_info += f"-  {title_premises} {len(premises)} {patch_premises_configured}"
            preview = premises[0][:50] + "..." if len(premises[0]) > 50 else premises[0]
            config_info += f" - \"{preview}\"\n"
        else:
            config_info += f"- {title_premises} {no_premises}\n"

        return usage_info + config_info

    except Exception as e:
        logger.warning(f"Could not load user subscriptions for Canvas: {e}")
        return "**Active subscriptions**\n- Error loading subscription data"


def build_canvas_role_news_watcher_detail(
    detail_name: str,
    admin_visible: bool,
    guild=None,
    author_id: int = 0,
    selected_method: str | None = None,
    last_action: str | None = None,
    selected_category: str = None,
    setup_not_available_builder=None,
) -> str | None:
    """Build a detailed News Watcher view with 3-block structure."""
    from .content import _build_canvas_intro_block
    watcher_messages = get_watcher_messages() if get_watcher_messages else {}
    watcher_descriptions = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {})

    def _watcher_text(key: str, fallback: str) -> str:
        value = watcher_descriptions.get(key, watcher_messages.get(key))
        return str(value).strip() if value else fallback

    def _get_watcher_personal_intro_block() -> str:
        return _build_canvas_intro_block(
            _watcher_text('title', 'News Watcher Personal'),
            _watcher_text('description', 'Build and maintain your personal news subscriptions. Choose a method first, then subscribe to categories or feeds, or review your keywords and premises.'),
        )

    def _get_watcher_admin_intro_block() -> str:
        return _build_canvas_intro_block(
            f"{_watcher_text('title', '📡 News Watcher')} Admin",
            _watcher_text("description", "Manage channel subscriptions with the same flow as personal view, but applied to channels. Choose a method, then manage categories, feeds, and server actions."),
        )

    def _format_categories() -> str:
        if not guild or get_news_watcher_db_instance is None:
            return "- Economy\n- Technology\n- International\n- General\n- Crypto"
        try:
            db = get_news_watcher_db_instance(str(guild.id))
            categories = db.get_available_categories()
            if not categories:
                return "- No categories available"
            return "\n".join([f"- {str(category).title()} ({count} feeds)" for category, count in categories])
        except Exception as e:
            logger.warning(f"Could not load watcher categories for Canvas: {e}")
            return "- Error loading categories"

    def _format_feeds(category: str = None) -> str:
        if not guild or get_news_watcher_db_instance is None:
            return "- No feed data available"
        try:
            db = get_news_watcher_db_instance(str(guild.id))

            if category:
                feeds = db.get_active_feeds(category)
                if not feeds:
                    return f"- No feeds found for category '{category}'"
                lines = [f"**{category.title()} Feeds ({len(feeds)} total):**"]
                for i, (_feed_id, name, _url, _feed_category, country, language, _priority, _keywords, feed_type) in enumerate(feeds, 1):
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

            feeds = db.get_active_feeds()
            if not feeds:
                return "- No feeds available"
            lines = []
            for feed_id, name, _url, category_name, country, language, _priority, _keywords, feed_type in feeds[:12]:
                meta = []
                if category_name:
                    meta.append(str(category_name).title())
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
            if detail_name == "admin":
                try:
                    premises, scope = db.get_premises_with_context(str(author_id))
                except Exception:
                    premises, scope = [], "none"
            else:
                premises, scope = db.get_premises_with_context(str(author_id))

            if not premises:
                lines = ["- Scope: No custom premises", "", "- 💡 **No custom premises configured**", "- 💡 Use 'Add Premises' to create custom premises", "- 💡 Or use !canvas to auto-initialize with defaults"]
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

    not_selected_method = _watcher_text("not_selected_method", "Not selected")
    method_labels = {
        "flat": _watcher_text("flat_method", "Flat"),
        "keyword": _watcher_text("keyword_method", "Keyword"),
        "general": _watcher_text("general_method", "General"),
        None: not_selected_method,
    }
    method_label = method_labels.get(selected_method, str(selected_method).title() if selected_method else not_selected_method)

    if detail_name in {"personal", "overview"}:
        block1 = _get_watcher_personal_intro_block()
        title_actual_method = _watcher_text("title_actual_method", "**Selected Method**:")
        subscriptions_info = get_canvas_user_subscriptions_info(guild, author_id) if guild and author_id else "**Active subscriptions**\n- No subscription data available"
        block2 = "\n".join([f"{title_actual_method} {method_label}", "", subscriptions_info])
        block2 += "\n──────────────────────────────"

        if last_action == "list_feeds":
            block3_title = _watcher_text("available_feeds_title", "**Available Feeds**")
            block3_body = _format_feeds()
        elif last_action == "list_feeds_by_category":
            category_title_template = _watcher_text("category_feeds_title", "**{category} Feeds**")
            block3_title = category_title_template.format(category=selected_category.title())
            block3_body = _format_feeds(selected_category)
        elif last_action == "list_keywords":
            block3_title = _watcher_text("configured_keywords_title", "**Configured Keywords**")
            block3_body = _format_keywords()
        elif last_action == "list_premises":
            block3_title = _watcher_text("configured_premises_title", "**Configured Premises**")
            block3_body = _format_premises()
        else:
            block3_title = _watcher_text("available_categories_title", "**Available Categories**")
            block3_body = _format_categories()

        block3 = "\n".join([block3_title, "", block3_body])
        return "\n".join([block1, "", block2, "", block3])

    if detail_name == "admin" and admin_visible:
        block1 = _get_watcher_admin_intro_block()
        title_actual_method = _watcher_text("title_actual_method", "**Selected Method**:")
        channel_subscriptions = get_canvas_channel_subscriptions_info(guild) if guild else "**Channel subscriptions**\n- No channel data available"
        block2 = "\n".join([f"{title_actual_method} {method_label}", "", channel_subscriptions, "──────────────────────────────"])

        if last_action == "list_feeds":
            block3_title = _watcher_text("available_feeds_title", "**Available Feeds**")
            block3_body = _format_feeds()
        elif last_action == "list_feeds_by_category":
            category_title_template = _watcher_text("category_feeds_title", "**{category} Feeds**")
            block3_title = category_title_template.format(category=selected_category.title())
            block3_body = _format_feeds(selected_category)
        elif last_action == "channel_view_subscriptions":
            block3_title = _watcher_text("channel_subscriptions_title", "**Current Channel Subscriptions**")
            block3_body = channel_subscriptions
        elif last_action == "channel_unsubscribe":
            block3_title = _watcher_text("channel_unsubscribe_title", "**Channel Unsubscribe**")
            block3_body = "\n".join(["- Use the numbered list from block 2", "- Choose the subscription number to remove", "- The change affects this channel"])
        elif last_action == "watcher_frequency":
            block3_title = _watcher_text("watcher_frequency_title", "**Watcher Frequency**")
            block3_body = "\n".join(["- Set how often the watcher checks for news", "- Recommended range: 1 to 24 hours", "- This affects the server-wide watcher schedule"])
        elif last_action == "watcher_run_now":
            block3_title = _watcher_text("force_watcher_run_title", "**Force Watcher Run**")
            block3_body = "\n".join(["- Runs the watcher immediately", "- Useful after adding or changing channel subscriptions", "- May generate notifications in subscribed channels"])
        elif last_action == "watcher_run_personal":
            block3_title = _watcher_text("force_personal_subscriptions_title", "**Force Personal Subscriptions**")
            block3_body = "\n".join(["- Runs personal subscriptions immediately", "- Processes flat, keyword, and AI subscriptions", "- Sends notifications to users via DMs", "- Useful for testing personal subscription setup"])
        elif last_action == "list_premises":
            block3_title = _watcher_text("configured_premises_title", "**Configured Premises**")
            block3_body = _format_premises()
        elif last_action == "list_keywords":
            block3_title = _watcher_text("configured_keywords_title", "**Configured Keywords**")
            block3_body = _format_keywords()
        else:
            block3_title = _watcher_text("available_categories_title", "**Available Categories**")
            block3_body = _format_categories()

        block3 = "\n".join([block3_title, "", block3_body])
        return "\n".join([block1, "", block2, "", block3])

    if detail_name in {"keywords", "filters"}:
        return "\n".join([
            _build_canvas_intro_block(
                f"📡 {_bot_display_name} Canvas - News Watcher Keywords",
                "Shape what the watcher considers relevant for you",
            ),
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
            if callable(setup_not_available_builder):
                return setup_not_available_builder()
            return "❌ This setup is only available to administrators."

        current_method = _get_canvas_watcher_method_label(str(guild.id)) if guild else "Unknown"
        current_frequency = _get_canvas_watcher_frequency_hours(str(guild.id)) if guild else 1
        return "\n".join([
            _build_canvas_intro_block(
                f"{_watcher_text('title', '📡 News Watcher')} Admin",
                "Configure how the server receives and filters watcher output",
            ),
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
