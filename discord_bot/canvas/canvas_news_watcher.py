"""Canvas News Watcher content builders and UI components."""

import discord

from discord_bot import discord_core_commands as core
from .state import _get_canvas_watcher_method_label, _get_canvas_watcher_frequency_hours

logger = core.logger
get_news_watcher_db_instance = core.get_news_watcher_db_instance
get_watcher_messages = core.get_watcher_messages


def _get_nw_descriptions(guild=None) -> dict:
    """Get news_watcher descriptions from server-specific databases path."""
    import json
    from pathlib import Path
    from discord_bot.db_init import get_server_personality_dir
    
    if not guild:
        return {}
    
    try:
        server_id = str(guild.id)
        personality_dir = get_server_personality_dir(server_id)
        
        if personality_dir:
            descriptions_dir = Path(personality_dir) / "descriptions"
            news_watcher_path = descriptions_dir / "news_watcher.json"
            
            if news_watcher_path.exists():
                with open(news_watcher_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load news_watcher descriptions: {e}")
    
    return {}


def _build_watcher_role_embed(role_name: str, content: str, admin_visible: bool, surface_name: str, user=None, auto_response: str | None = None):
    from .content import _build_canvas_role_embed
    return _build_canvas_role_embed(role_name, content, admin_visible, surface_name, user, auto_response)


def _get_watcher_auto_response_preview(role_name: str, action_name: str | None = None):
    from .content import _get_canvas_auto_response_preview
    return _get_canvas_auto_response_preview(role_name, action_name)


def _build_watcher_next_view(view, interaction: discord.Interaction, current_detail: str, auto_response_preview: str | None = None):
    from .ui import CanvasRoleDetailView

    next_view = CanvasRoleDetailView(
        author_id=view.author_id,
        role_name=view.role_name,
        agent_config=view.agent_config,
        admin_visible=view.admin_visible,
        sections=view.sections,
        current_detail=current_detail,
        guild=view.guild,
        message=interaction.message,
        watcher_selected_method=view.watcher_selected_method,
        watcher_last_action=view.watcher_last_action,
        watcher_selected_category=getattr(view, 'watcher_selected_category', None),
        previous_view=view,
    )
    next_view.auto_response_preview = auto_response_preview
    return next_view


class CanvasWatcherMethodSelect(discord.ui.Select):
    """Dynamic method selection dropdown for News Watcher."""

    def __init__(self, view):
        # Safe nested access with fallbacks
        news_watcher = _get_nw_descriptions(getattr(view, 'guild', None))
        
        # Now dropdown is directly in news_watcher, not nested under canvas
        watcher_descriptions = news_watcher.get("dropdown", {}) if isinstance(news_watcher, dict) else {}
        
        # Ensure watcher_descriptions is a dict
        if not isinstance(watcher_descriptions, dict):
            watcher_descriptions = {}

        def _watcher_text(key: str, fallback: str) -> str:
            value = watcher_descriptions.get(key)
            return str(value).strip() if value else fallback

        options = [
            discord.SelectOption(label=_watcher_text("method_flat", "Method: Flat"), value="method_flat", description=_watcher_text("option_flat_description", "All news with AI opinions"), emoji="📰"),
            discord.SelectOption(label=_watcher_text("method_keyword", "Method: Keyword"), value="method_keyword", description=_watcher_text("option_keyword_description", "News filtered by keywords"), emoji="🔍"),
            discord.SelectOption(label=_watcher_text("method_general", "Method: General"), value="method_general", description=_watcher_text("option_general_description", "AI critical news analysis"), emoji="🤖"),
        ]
        placeholder = _watcher_text("select_method", "🔧 Select method...")
        if view.watcher_selected_method:
            method_display = view.watcher_selected_method.title()
            placeholder = _watcher_text("method_selected", f"🔧 Method: {method_display} (selected)").format(method=method_display)

        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1, row=0)
        self.canvas_view = view

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        self.canvas_view.watcher_selected_method = action_name.replace("method_", "")
        self.canvas_view.watcher_last_action = None
        self.canvas_view.auto_response_preview = _get_watcher_auto_response_preview(self.canvas_view.role_name, action_name)

        for child in self.canvas_view.children:
            if isinstance(child, CanvasWatcherSubscriptionSelect):
                child.set_method(self.canvas_view.watcher_selected_method)
                break

        await handle_canvas_watcher_action(interaction, action_name, self.canvas_view)


class CanvasWatcherSubscriptionSelect(discord.ui.Select):
    """Dynamic subscription dropdown for News Watcher based on selected method."""

    def _watcher_text(self, key: str, fallback: str) -> str:
        # Safe nested access with fallbacks
        news_watcher = _get_nw_descriptions(getattr(self, '_guild', None))
        
        # Now dropdown is directly in news_watcher, not nested under canvas
        watcher_descriptions = news_watcher.get("dropdown", {}) if isinstance(news_watcher, dict) else {}
        
        # Ensure watcher_descriptions is a dict
        if not isinstance(watcher_descriptions, dict):
            watcher_descriptions = {}
            
        value = watcher_descriptions.get(key)
        return str(value).strip() if value else fallback

    def __init__(self, view):
        self._guild = getattr(view, 'guild', None)
        super().__init__(placeholder=self._watcher_text("select_action", "📋 Select action..."), options=self._build_options(view.watcher_selected_method), min_values=1, max_values=1, row=1)
        self.canvas_view = view

    def _build_options(self, method: str | None) -> list[discord.SelectOption]:
        options = [
            discord.SelectOption(label=self._watcher_text("categories", "Categories"), value="list_categories", description=self._watcher_text("categories_description", "List available categories"), emoji="📂"),
            discord.SelectOption(label=self._watcher_text("feeds_by_category", "Feeds by Category"), value="list_feeds_by_category", description=self._watcher_text("feeds_by_category_description", "List feeds from a specific category"), emoji="🔗"),
        ]
        if method:
            subscribe_desc = self._watcher_text("subscribe_categories_description", "Subscribe to categories with {method} method")
            options.append(discord.SelectOption(label=self._watcher_text("subscribe_categories", "Subscribe Categories"), value="subscribe_categories", description=subscribe_desc.format(method=method), emoji="➕"))
            options.append(discord.SelectOption(label=self._watcher_text("unsubscribe", "Unsubscribe"), value="unsubscribe", description=self._watcher_text("unsubscribe_description", "Unsubscribe from your subscriptions"), emoji="🗑️"))
        if method == "keyword":
            options.append(discord.SelectOption(label=self._watcher_text("keywords", "Keywords"), value="list_keywords", description=self._watcher_text("keywords_description", "View your configured keywords"), emoji="🔍"))
            options.append(discord.SelectOption(label=self._watcher_text("add_keywords", "Add Keywords"), value="add_keywords", description=self._watcher_text("add_keywords_description", "Add new keywords"), emoji="➕"))
            options.append(discord.SelectOption(label=self._watcher_text("delete_keywords", "Delete Keywords"), value="delete_keywords", description=self._watcher_text("delete_keywords_description", "Remove keywords"), emoji="🗑️"))
        elif method == "general":
            options.append(discord.SelectOption(label=self._watcher_text("premises", "Premises"), value="list_premises", description=self._watcher_text("premises_description", "View your AI analysis premises"), emoji="🤖"))
            options.append(discord.SelectOption(label=self._watcher_text("add_premises_new", "Add Premises"), value="add_premises", description=self._watcher_text("add_premises_new_description", "Add new premises"), emoji="➕"))
            options.append(discord.SelectOption(label=self._watcher_text("delete_premises_new", "Delete Premises"), value="delete_premises", description=self._watcher_text("delete_premises_new_description", "Remove premises"), emoji="🗑️"))
        return options

    def set_method(self, method: str | None) -> None:
        self.options = self._build_options(method)

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        self.canvas_view.watcher_last_action = action_name

        if action_name == "subscribe_categories":
            await interaction.response.send_modal(CanvasWatcherSubscribeModal(action_name, self.canvas_view, interaction.client))
            return
        if action_name == "unsubscribe":
            await interaction.response.send_modal(CanvasWatcherPersonalUnsubscribeModal(self.canvas_view, interaction.client))
            return
        if action_name in {"add_keywords", "add_premises"}:
            await interaction.response.send_modal(CanvasWatcherAddModal(action_name, self.canvas_view, interaction.client))
            return
        if action_name in {"delete_keywords", "delete_premises"}:
            await interaction.response.send_modal(CanvasWatcherDeleteModal(action_name, self.canvas_view, interaction.client))
            return
        if action_name in {"list_categories", "list_feeds", "list_keywords", "list_premises"}:
            content = build_canvas_role_news_watcher_detail(
                self.canvas_view.current_detail,
                self.canvas_view.admin_visible,
                self.canvas_view.guild,
                self.canvas_view.author_id,
                selected_method=self.canvas_view.watcher_selected_method,
                last_action=action_name,
            )
            next_view = _build_watcher_next_view(self.canvas_view, interaction, self.canvas_view.current_detail, self.canvas_view.auto_response_preview)
            embed = _build_watcher_role_embed(self.canvas_view.role_name, content or "", self.canvas_view.admin_visible, self.canvas_view.current_detail, None, next_view.auto_response_preview)
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            return
        if action_name == "list_feeds_by_category":
            await interaction.response.send_modal(CanvasWatcherFeedsByCategoryModal(self.canvas_view))


class CanvasWatcherAdminMethodSelect(discord.ui.Select):
    """Dynamic method selection dropdown for News Watcher Admin."""

    def __init__(self, view):
        # Safe nested access with fallbacks
        news_watcher = _get_nw_descriptions(getattr(view, 'guild', None))
        
        # Now dropdown is directly in news_watcher, not nested under canvas
        watcher_descriptions = news_watcher.get("dropdown", {}) if isinstance(news_watcher, dict) else {}
        
        # Ensure watcher_descriptions is a dict
        if not isinstance(watcher_descriptions, dict):
            watcher_descriptions = {}

        def _watcher_text(key: str, fallback: str) -> str:
            value = watcher_descriptions.get(key)
            return str(value).strip() if value else fallback

        options = [
            discord.SelectOption(label=_watcher_text("method_flat", "Method: Flat"), value="method_flat", description=_watcher_text("option_flat_description", "All news with AI opinions (server default)"), emoji="📰"),
            discord.SelectOption(label=_watcher_text("method_keyword", "Method: Keyword"), value="method_keyword", description=_watcher_text("option_keyword_description", "News filtered by keywords (server default)"), emoji="🔍"),
            discord.SelectOption(label=_watcher_text("method_general", "Method: General"), value="method_general", description=_watcher_text("option_general_description", "AI critical news analysis (server default)"), emoji="🤖"),
        ]
        placeholder = _watcher_text("set_channel_method", "🔧 Set channel method...")
        if view.watcher_selected_method:
            method_display = view.watcher_selected_method.title()
            placeholder = _watcher_text("server_method_selected", f"🔧 Server Method: {method_display} (selected)").format(method=method_display)

        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1, row=0)
        self.canvas_view = view

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        self.canvas_view.watcher_selected_method = action_name.replace("method_", "")
        self.canvas_view.watcher_last_action = None
        self.canvas_view.auto_response_preview = _get_watcher_auto_response_preview(self.canvas_view.role_name, action_name)
        for child in self.canvas_view.children:
            if isinstance(child, CanvasWatcherAdminActionSelect):
                child.update_options_for_method(self.canvas_view.watcher_selected_method)
                break
        await handle_canvas_watcher_action(interaction, action_name, self.canvas_view)


class CanvasWatcherAdminActionSelect(discord.ui.Select):
    """Dynamic admin action dropdown for News Watcher."""

    def __init__(self, view):
        # Safe nested access with fallbacks
        news_watcher = _get_nw_descriptions(getattr(view, 'guild', None))
        
        # Now dropdown is directly in news_watcher, not nested under canvas
        watcher_descriptions = news_watcher.get("dropdown", {}) if isinstance(news_watcher, dict) else {}
        
        # Ensure watcher_descriptions is a dict
        if not isinstance(watcher_descriptions, dict):
            watcher_descriptions = {}

        def _watcher_text(key: str, fallback: str) -> str:
            value = watcher_descriptions.get(key)
            return str(value).strip() if value else fallback

        self._watcher_text = _watcher_text
        options = self._build_options(getattr(view, 'watcher_selected_method', None))
        super().__init__(placeholder=_watcher_text("select_admin_action", "⚙️ Select admin action..."), options=options, min_values=1, max_values=1, row=1)
        self.canvas_view = view

    def _build_options(self, method: str | None) -> list[discord.SelectOption]:
        base_options = [
            discord.SelectOption(label=self._watcher_text("feeds_by_category", "Feeds by Category"), value="list_feeds_by_category", description=self._watcher_text("feeds_by_category_description", "List feeds from a specific category"), emoji="🔗"),
            discord.SelectOption(label=self._watcher_text("list_categories", "List categories"), value="list_categories", description=self._watcher_text("list_categories_description", "List available categories"), emoji="📂"),
        ]
        if method == "general":
            method_specific_options = [
                discord.SelectOption(label=self._watcher_text("subscribe_category", "Subscribe Category"), value="channel_subscribe_category", description=self._watcher_text("subscribe_category_description", "Subscribe category <name> <optional feed> for channel"), emoji="➕"),
                discord.SelectOption(label=self._watcher_text("unsubscribe_category", "Unsubscribe Category"), value="channel_unsubscribe_category", description=self._watcher_text("unsubscribe_category_description", "Unsubscribe category <name> <optional feed> for channel"), emoji="🗑️"),
                discord.SelectOption(label=self._watcher_text("list_premises", "List premises"), value="list_premises", description=self._watcher_text("list_premises_description", "List premises for next subscription for channel"), emoji="🤖"),
                discord.SelectOption(label=self._watcher_text("add_premise", "Add premise"), value="add_premise", description=self._watcher_text("add_premises_description", "Add new premise for channel"), emoji="➕"),
                discord.SelectOption(label=self._watcher_text("delete_premise", "Delete premise"), value="delete_premise", description=self._watcher_text("delete_premise_description", "Delete premise <number> for current"), emoji="🗑️"),
            ]
        elif method == "keyword":
            method_specific_options = [
                discord.SelectOption(label=self._watcher_text("subscribe_category", "Subscribe Category"), value="channel_subscribe_category", description=self._watcher_text("subscribe_category_description", "Subscribe category <name> <optional feed> for channel"), emoji="➕"),
                discord.SelectOption(label=self._watcher_text("unsubscribe_category", "Unsubscribe Category"), value="channel_unsubscribe_category", description=self._watcher_text("unsubscribe_category_description", "Unsubscribe category <name> <optional feed> for channel"), emoji="🗑️"),
                discord.SelectOption(label=self._watcher_text("list_keywords", "List keywords"), value="list_keywords", description=self._watcher_text("list_keywords_description", "List keywords for channel"), emoji="🔍"),
                discord.SelectOption(label=self._watcher_text("add_keywords", "Add keywords"), value="add_keywords", description=self._watcher_text("add_keywords_description", "Add new keywords for channel"), emoji="➕"),
                discord.SelectOption(label=self._watcher_text("delete_keywords", "Delete keywords"), value="delete_keywords", description=self._watcher_text("delete_keywords_description", "Delete keywords for channel"), emoji="🗑️"),
            ]
        else:
            method_specific_options = [
                discord.SelectOption(label=self._watcher_text("subscribe_category", "Subscribe Category"), value="channel_subscribe_category", description=self._watcher_text("subscribe_category_description", "Subscribe category <name> <optional feed> for channel"), emoji="➕"),
                discord.SelectOption(label=self._watcher_text("unsubscribe_category", "Unsubscribe Category"), value="channel_unsubscribe_category", description=self._watcher_text("unsubscribe_category_description", "Unsubscribe category <name> <optional feed> for channel"), emoji="🗑️"),
            ]
        server_options = [
            discord.SelectOption(label=self._watcher_text("modify_watcher_frequency", "Modify watcher task frequency"), value="watcher_frequency", description=self._watcher_text("modify_watcher_frequency_description", "Set news check frequency"), emoji="⏰"),
            discord.SelectOption(label=self._watcher_text("force_watcher_channel", "Force watcher channel now"), value="watcher_run_now", description=self._watcher_text("force_watcher_channel_description", "Run news check immediately"), emoji="▶️"),
            discord.SelectOption(label=self._watcher_text("force_personal_subscriptions", "Force personal subscriptions now"), value="watcher_run_personal", description=self._watcher_text("force_personal_subscriptions_description", "Run personal subscriptions immediately"), emoji="👤"),
        ]
        return base_options + method_specific_options + server_options

    def update_options_for_method(self, method: str):
        self.options = self._build_options(method)

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        self.canvas_view.watcher_last_action = action_name
        if action_name in {"list_categories", "list_feeds", "list_premises", "list_keywords"}:
            content = build_canvas_role_news_watcher_detail(
                "admin",
                self.canvas_view.admin_visible,
                self.canvas_view.guild,
                self.canvas_view.author_id,
                selected_method=self.canvas_view.watcher_selected_method,
                last_action=action_name,
                selected_category=getattr(self.canvas_view, 'watcher_selected_category', None),
            )
            embed = _build_watcher_role_embed(self.canvas_view.role_name, content or "", self.canvas_view.admin_visible, "admin", None, self.canvas_view.auto_response_preview)
            if not interaction.response.is_done():
                await interaction.response.edit_message(content=None, embed=embed, view=self.canvas_view)
            return
        if action_name == "list_feeds_by_category":
            if not interaction.response.is_done():
                await interaction.response.send_modal(CanvasWatcherFeedsByCategoryModal(self.canvas_view))
            return
        await handle_canvas_watcher_action(interaction, action_name, self.canvas_view)


class CanvasWatcherSubscribeModal(discord.ui.Modal):
    def __init__(self, action_name: str, view, bot):
        self.action_name = action_name
        self.view = view
        self.bot = bot
        super().__init__(title="Subscribe to Categories", timeout=300)
        self.category_input = discord.ui.TextInput(label="Category", placeholder="Enter category (economy, technology, gaming, international, general, crypto)...", style=discord.TextStyle.short, required=True, max_length=50)
        self.add_item(self.category_input)
        self.feed_id_input = discord.ui.TextInput(label="Feed ID (Optional)", placeholder="Enter specific feed ID number, 'all' for all feeds, or leave empty for first feed...", style=discord.TextStyle.short, required=False, max_length=10, default="")
        self.add_item(self.feed_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands

            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild

            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)

            if interaction.guild:
                server_id = str(interaction.guild.id)
                watcher_commands = WatcherCommands(self.bot)
                db_instance = get_news_watcher_db_instance(server_id)
                if not db_instance.db_path.exists() or db_instance.db_path.stat().st_size == 0:
                    db_instance._init_db()
                watcher_commands.db_watcher = db_instance
            else:
                watcher_commands = WatcherCommands(self.bot)
                db_instance = None

            method = (self.view.watcher_selected_method or "flat").strip().lower()
            category = str(self.category_input.value).strip().lower()
            args = [method, category]
            feed_id = str(self.feed_id_input.value).strip()
            if feed_id:
                args.append(feed_id)

            if self.view.current_detail == "admin":
                channel_id = str(interaction.channel.id)
                channel_name = interaction.channel.name
                server_id = str(interaction.guild.id)
                server_name = interaction.guild.name

                if method == "general":
                    try:
                        db_watcher = get_news_watcher_db_instance(server_id)
                        default_premises_list = db_watcher._get_default_premises()
                        default_premises = ", ".join(default_premises_list)
                    except Exception:
                        default_premises = "interesting news, relevant events, important developments"

                    feed_id_num = None
                    if feed_id:
                        feed_id_num = await watcher_commands._validate_category_and_feed(
                            mock_message, category, [method, feed_id], db_watcher
                        )

                    subscription_id = db_watcher.create_subscription(
                        user_id=None,
                        channel_id=channel_id,
                        category=category,
                        feed_id=feed_id_num,
                        premises=default_premises,
                        method="general",
                        created_by=str(view.author_id)
                    )
                    
                    if subscription_id:
                        result_msg = f"General channel subscription created for {category}"
                        if feed_id:
                            result_msg += f" (feed #{feed_id})"
                    else:
                        result_msg = "Failed to create channel subscription"
                else:
                    args = [category] + ([feed_id] if feed_id else [])
                    await watcher_commands.cmd_channel_subscribe(mock_message, args)
                    result_msg = f"✅ {method.title()} channel subscription created for {category}"
                    if feed_id:
                        result_msg += f" (feed #{feed_id})"
            else:
                if method == "general":
                    user_id = str(interaction.user.id)
                    feed_id_num = None
                    if feed_id and db_instance is not None:
                        feed_id_num = await watcher_commands._validate_category_and_feed(
                            mock_message, category, [method, feed_id], db_instance
                        )

                    success, result_msg = await watcher_commands._handle_general_subscribe(
                        mock_message, user_id, category, feed_id_num, return_result=True
                    )
                    if not success:
                        result_msg = f"❌ {result_msg}"
                else:
                    await watcher_commands.cmd_unified_subscribe(mock_message, args)
                    method_titles = {
                        "flat": "Flat Subscription (All News)",
                        "keyword": "Keyword Subscription (Filtered)",
                        "general": "General Subscription (AI Analysis)",
                    }
                    result_msg = f"✅ {method_titles.get(method, 'Subscription')} created for {category}"
                    if feed_id:
                        result_msg += f" (feed #{feed_id})"
                    else:
                        result_msg += " (all feeds in category)"

            try:
                self.view.watcher_last_action = self.action_name
                current_detail = self.view.current_detail
                content = build_canvas_role_news_watcher_detail(
                    current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = _build_watcher_next_view(self.view, interaction, current_detail, result_msg)
                embed = _build_watcher_role_embed("news_watcher", content or "", self.view.admin_visible, current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                logger.info(f"Watcher Canvas subscription {self.action_name} completed but interaction expired")
            except discord.HTTPException as error:
                logger.warning(f"Could not update Canvas for Watcher subscription {self.action_name}: {error}")

        except Exception as error:
            logger.exception(f"Error in Watcher subscription modal: {error}")


class CanvasWatcherAddModal(discord.ui.Modal):
    def __init__(self, action_name: str, view, bot):
        self.action_name = action_name
        self.view = view
        self.bot = bot
        if action_name == "add_keywords":
            title = "Add Keywords"
            label = "Keywords"
            placeholder = "Enter keywords separated by commas (e.g., bitcoin, ethereum, crypto)..."
            style = discord.TextStyle.short
            max_length = 200
        else:
            title = "Add Premises"
            label = "Premise"
            placeholder = "Enter your AI analysis premise (e.g., Focus on market impact)..."
            style = discord.TextStyle.paragraph
            max_length = 500
        super().__init__(title=title, timeout=300)
        self.content_input = discord.ui.TextInput(label=label, placeholder=placeholder, style=style, required=True, max_length=max_length)
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands

            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild

            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)

            if interaction.guild:
                server_id = str(interaction.guild.id)
                watcher_commands = WatcherCommands(self.bot)
                db_instance = get_news_watcher_db_instance(server_id)
                if not db_instance.db_path.exists() or db_instance.db_path.stat().st_size == 0:
                    db_instance._init_db()
                watcher_commands.db_watcher = db_instance
            else:
                watcher_commands = WatcherCommands(self.bot)

            content_value = str(self.content_input.value).strip()

            if self.action_name == "add_keywords":
                result_msg = await watcher_commands.cmd_keywords_add_canvas(mock_message, [content_value])
            else:
                result_msg = await watcher_commands.cmd_premises_add_canvas(mock_message, [content_value])

            try:
                self.view.watcher_last_action = "list_keywords" if self.action_name == "add_keywords" else "list_premises"
                content = build_canvas_role_news_watcher_detail(
                    self.view.current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = _build_watcher_next_view(self.view, interaction, self.view.current_detail, result_msg if isinstance(result_msg, str) else None)
                embed = _build_watcher_role_embed("news_watcher", content or "", self.view.admin_visible, self.view.current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                logger.info(f"Watcher Canvas add {self.action_name} completed but interaction expired")
            except discord.HTTPException as error:
                logger.warning(f"Could not update Canvas for Watcher add {self.action_name}: {error}")

        except Exception as error:
            logger.exception(f"Error in Watcher add modal: {error}")


class CanvasWatcherDeleteModal(discord.ui.Modal):
    def __init__(self, action_name: str, view, bot):
        self.action_name = action_name
        self.view = view
        self.bot = bot
        if action_name == "delete_keywords":
            title = "Delete Keywords"
            label = "Keyword to Delete"
            placeholder = "Enter keyword to remove (e.g., bitcoin)..."
        else:
            title = "Delete Premises"
            label = "Premise Number"
            placeholder = "Enter premise number to delete (e.g., 1, 2, 3)..."
        super().__init__(title=title, timeout=300)
        self.content_input = discord.ui.TextInput(label=label, placeholder=placeholder, style=discord.TextStyle.short, required=True, max_length=100)
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands

            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild

            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)

            if interaction.guild:
                server_id = str(interaction.guild.id)
                watcher_commands = WatcherCommands(self.bot)
                db_instance = get_news_watcher_db_instance(server_id)
                if not db_instance.db_path.exists() or db_instance.db_path.stat().st_size == 0:
                    db_instance._init_db()
                watcher_commands.db_watcher = db_instance
            else:
                watcher_commands = WatcherCommands(self.bot)

            content_value = str(self.content_input.value).strip()

            if self.action_name == "delete_keywords":
                result_msg = await watcher_commands.cmd_keywords_del(mock_message, [content_value])
                if isinstance(result_msg, str):
                    result_msg = f"✅ Keyword deleted: {content_value}"
            else:
                result_msg = await watcher_commands.cmd_premises_del_canvas(mock_message, [content_value])

            try:
                self.view.watcher_last_action = "list_keywords" if self.action_name == "delete_keywords" else "list_premises"
                content = build_canvas_role_news_watcher_detail(
                    self.view.current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = _build_watcher_next_view(self.view, interaction, self.view.current_detail, result_msg if isinstance(result_msg, str) else None)
                embed = _build_watcher_role_embed("news_watcher", content or "", self.view.admin_visible, self.view.current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                logger.info(f"Watcher Canvas delete {self.action_name} completed but interaction expired")
            except discord.HTTPException as error:
                logger.warning(f"Could not update Canvas for Watcher delete {self.action_name}: {error}")

        except Exception as error:
            logger.exception(f"Error in Watcher delete modal: {error}")


class CanvasWatcherListModal(discord.ui.Modal):
    def __init__(self, list_type: str, view, bot):
        self.list_type = list_type
        self.view = view
        self.bot = bot
        super().__init__(title={"keywords": "View Keywords", "premises": "View Premises"}.get(list_type, "View Configuration"), timeout=300)
        self.action_input = discord.ui.TextInput(label="Action", placeholder="Enter: list, add, mod, or del", style=discord.TextStyle.short, required=True, max_length=10)
        self.add_item(self.action_input)
        if list_type == "keywords":
            self.value_input = discord.ui.TextInput(label="Keywords", placeholder="Enter keyword(s) separated by commas (for add/del)...", style=discord.TextStyle.short, required=False, max_length=200)
        else:
            self.value_input = discord.ui.TextInput(label="Premise Text", placeholder="For mod use: <number> | <new premise text>", style=discord.TextStyle.long, required=False, max_length=500)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands

            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild

            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)

            if interaction.guild:
                server_id = str(interaction.guild.id)
                watcher_commands = WatcherCommands(self.bot)
                db_instance = get_news_watcher_db_instance(server_id)
                if not db_instance.db_path.exists() or db_instance.db_path.stat().st_size == 0:
                    db_instance._init_db()
                watcher_commands.db_watcher = db_instance
            else:
                watcher_commands = WatcherCommands(self.bot)

            action = str(self.action_input.value).strip().lower()
            value = str(self.value_input.value).strip() if self.value_input.value else ""

            if self.list_type == "keywords":
                if action == "add" and value:
                    args = ["add"] + [keyword.strip() for keyword in value.split(",")]
                    await watcher_commands.cmd_keywords_add(mock_message, args)
                    result_msg = f"✅ Keywords added: {value}"
                elif action == "list":
                    await watcher_commands.cmd_keywords_list(mock_message, [])
                    result_msg = "📋 Keywords list sent by DM"
                elif action == "del" and value:
                    args = ["del"] + [keyword.strip() for keyword in value.split(",")]
                    await watcher_commands.cmd_keywords_del(mock_message, args)
                    result_msg = f"🗑️ Keywords deleted: {value}"
                else:
                    result_msg = "❌ Invalid action or missing keywords"
            else:
                if action == "add" and value:
                    result_msg = await watcher_commands.cmd_premises_add_canvas(mock_message, [value])
                elif action == "list":
                    result_msg = await watcher_commands.cmd_premises_list_canvas(mock_message, [])
                elif action == "del" and value:
                    result_msg = await watcher_commands.cmd_premises_del_canvas(mock_message, [value])
                elif action == "mod" and value:
                    if "|" not in value:
                        result_msg = "❌ For mod use: <number> | <new premise text>"
                    else:
                        index_text, premise_text = value.split("|", 1)
                        result_msg = await watcher_commands.cmd_premises_mod_canvas(mock_message, [index_text.strip(), premise_text.strip()])
                else:
                    result_msg = "❌ Invalid action or missing premise text"

            try:
                next_view = _build_watcher_next_view(self.view, interaction, "overview", result_msg if isinstance(result_msg, str) else None)
                embed = _build_watcher_role_embed("news_watcher", "", self.view.admin_visible, "overview", None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                logger.info(f"Watcher Canvas list {self.list_type} completed but interaction expired")
            except discord.HTTPException as error:
                logger.warning(f"Could not update Canvas for Watcher list {self.list_type}: {error}")

        except Exception as error:
            logger.exception(f"Error in Watcher list modal: {error}")


class CanvasWatcherChannelSubscribeModal(discord.ui.Modal):
    def __init__(self, action_name: str, view, bot):
        self.action_name = action_name
        self.view = view
        self.bot = bot
        title = "Channel Subscribe Categories" if action_name == "channel_subscribe_categories" else "Channel Subscribe Feeds"
        super().__init__(title=title, timeout=300)
        self.category_input = discord.ui.TextInput(label="Category", placeholder="Enter category (economy, technology, gaming, crypto)...", style=discord.TextStyle.short, required=True, max_length=50)
        self.add_item(self.category_input)
        self.feed_id_input = discord.ui.TextInput(label="Feed IDs (Optional)", placeholder="Enter feed number (1, 2, 3...)\nFeed 1 = First feed in category\nLeave empty for all feeds", style=discord.TextStyle.paragraph, required=False, max_length=50, default="")
        self.add_item(self.feed_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if get_news_watcher_db_instance is None or not interaction.guild:
                await interaction.response.send_message("❌ Watcher database is not available.", ephemeral=True)
                return

            db = get_news_watcher_db_instance(str(interaction.guild.id))
            if not db.db_path.exists() or db.db_path.stat().st_size == 0:
                db._init_db()
            method = (self.view.watcher_selected_method or "flat").strip().lower()
            category = str(self.category_input.value).strip().lower()
            feed_ids = []

            feed_ids_str = str(self.feed_id_input.value).strip()
            if feed_ids_str:
                try:
                    feed_ids = [int(id_str.strip()) for id_str in feed_ids_str.split(",") if id_str.strip()]
                    if not feed_ids:
                        await interaction.response.send_message("❌ No valid Feed IDs found", ephemeral=True)
                        return
                except ValueError:
                    await interaction.response.send_message("❌ Feed IDs must be numbers separated by commas", ephemeral=True)
                    return

            channel_id = str(interaction.channel.id)
            channel_name = interaction.channel.name
            server_id = str(interaction.guild.id)
            server_name = interaction.guild.name
            successful_subscriptions = 0
            failed_subscriptions = 0

            if feed_ids:
                feeds = db.get_active_feeds(category)
                for feed_id in feed_ids:
                    if 1 <= feed_id <= len(feeds):
                        global_feed_id = feeds[feed_id - 1][0]
                        ok = False
                        
                        if method == "flat":
                            # Create flat subscription
                            ok = db.create_subscription(
                                channel_id=channel_id,
                                category=category,
                                feed_id=global_feed_id,
                                method="flat",
                                created_by=str(self.view.author_id)
                            ) is not None
                        elif method == "keyword":
                            user_id = str(interaction.user.id)
                            user_keywords = db.get_user_keywords(user_id)
                            if user_keywords:
                                # Create keyword subscription
                                ok = db.create_subscription(
                                    channel_id=channel_id,
                                    category=category,
                                    feed_id=global_feed_id,
                                    keywords=",".join(user_keywords),
                                    method="keyword",
                                    created_by=str(self.view.author_id)
                                ) is not None
                        elif method == "general":
                            # Get premises for channel
                            premises, _ = db.get_premises_with_context(str(self.view.author_id))
                            if premises:
                                premises_str = ",".join(premises)
                            else:
                                # Use default premises from personality config
                                try:
                                    from agent_engine import PERSONALITY
                                    news_watcher_config = PERSONALITY.get("roles", {}).get("news_watcher", {})
                                    default_premises = news_watcher_config.get("premises", [
                                        "War outbreak or nuclear escalation",
                                        "Bankruptcy of a country or large corporation",
                                        "Global magnitude catastrophe"
                                    ])
                                    premises_str = ",".join(default_premises)
                                except Exception:
                                    # English fallback
                                    premises_str = "War outbreak or nuclear escalation,Bankruptcy of a country or large corporation,Global magnitude catastrophe"
                            
                            # Create general subscription
                            ok = db.create_subscription(
                                channel_id=channel_id,
                                category=category,
                                feed_id=global_feed_id,
                                premises=premises_str,
                                method="general",
                                created_by=str(self.view.author_id)
                            ) is not None
                        if ok:
                            successful_subscriptions += 1
                        else:
                            failed_subscriptions += 1
                    else:
                        failed_subscriptions += 1
            else:
                ok = False
                if method == "flat":
                    # Create flat subscription for all feeds
                    ok = db.create_subscription(
                        channel_id=channel_id,
                        category=category,
                        feed_id=None,
                        method="flat",
                        created_by=str(self.view.author_id)
                    ) is not None
                elif method == "keyword":
                    user_id = str(interaction.user.id)
                    user_keywords = db.get_user_keywords(user_id)
                    if user_keywords:
                        # Create keyword subscription for all feeds
                        ok = db.create_subscription(
                            channel_id=channel_id,
                            category=category,
                            feed_id=None,
                            keywords=",".join(user_keywords),
                            method="keyword",
                            created_by=str(self.view.author_id)
                        ) is not None
                elif method == "general":
                    # Get premises for channel
                    premises, _ = db.get_premises_with_context(str(self.view.author_id))
                    if premises:
                        premises_str = ",".join(premises)
                    else:
                        # Use default premises from personality config
                        try:
                            from agent_engine import PERSONALITY
                            news_watcher_config = PERSONALITY.get("roles", {}).get("news_watcher", {})
                            default_premises = news_watcher_config.get("premises", [
                                "War outbreak or nuclear escalation",
                                "Bankruptcy of a country or large corporation",
                                "Global magnitude catastrophe"
                            ])
                            premises_str = ",".join(default_premises)
                        except Exception:
                            # English fallback
                            premises_str = "War outbreak or nuclear escalation,Bankruptcy of a country or large corporation,Global magnitude catastrophe"
                    
                    # Create general subscription for all feeds
                    ok = db.create_subscription(
                        channel_id=channel_id,
                        category=category,
                        feed_id=None,
                        premises=premises_str,
                        method="general",
                        created_by=str(self.view.author_id)
                    ) is not None

                if ok:
                    successful_subscriptions = 1
                else:
                    failed_subscriptions = 1

            if failed_subscriptions > 0 and successful_subscriptions == 0:
                await interaction.response.send_message("❌ Could not create channel subscription. Please try again.", ephemeral=True)
                return

            self.view.watcher_last_action = self.action_name
            content = build_canvas_role_news_watcher_detail(
                "admin",
                self.view.admin_visible,
                self.view.guild,
                self.view.author_id,
                selected_method=self.view.watcher_selected_method,
                last_action=self.view.watcher_last_action,
            )
            if feed_ids:
                if successful_subscriptions == len(feed_ids):
                    if successful_subscriptions == 1:
                        feed_list = f"feed #{feed_ids[0]}"
                    else:
                        feed_list = f"feeds {', '.join(map(str, feed_ids))}"
                    success_msg = f"✅ {method.title()} channel subscription created for `{category}` ({feed_list})."
                else:
                    success_msg = f"⚠️ {method.title()} channel subscription partially created for `{category}`. {successful_subscriptions}/{len(feed_ids)} feeds successful."
            else:
                success_msg = f"✅ {method.title()} channel subscription created for `{category}` (all feeds)."

            next_view = _build_watcher_next_view(self.view, interaction, "admin", success_msg)
            embed = _build_watcher_role_embed("news_watcher", content or "", self.view.admin_visible, "admin", None, next_view.auto_response_preview)
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        except ValueError:
            logger.warning("Invalid Feed ID in channel subscription modal")
        except Exception as error:
            logger.exception(f"Error in Watcher channel subscription modal: {error}")


class CanvasWatcherChannelUnsubscribeModal(discord.ui.Modal):
    def __init__(self, view, bot):
        self.view = view
        self.bot = bot
        super().__init__(title="Channel Unsubscribe", timeout=300)
        self.number_input = discord.ui.TextInput(label="Subscription Number", placeholder="Enter the numbered subscription from block 2...", style=discord.TextStyle.short, required=True, max_length=5)
        self.add_item(self.number_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if get_news_watcher_db_instance is None or not interaction.guild:
                logger.warning("Watcher database not available for channel unsubscribe")
                return

            db = get_news_watcher_db_instance(str(interaction.guild.id))
            channel_id = str(interaction.channel.id)
            index = int(str(self.number_input.value).strip())
            
            # Get unified channel subscriptions
            channel_subscriptions = db.get_channel_subscriptions(channel_id)
            
            if index < 1 or index > len(channel_subscriptions):
                logger.warning(f"Invalid subscription number: {index}")
                return

            # Get the subscription to delete
            sub_id, sub_user_id, sub_channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by = channel_subscriptions[index - 1]
            
            # Delete using the new unified system
            ok = db.delete_subscription(sub_id)
            
            if not ok:
                logger.warning("Could not cancel channel subscription")
                return

            self.view.watcher_last_action = "channel_unsubscribe"
            content = build_canvas_role_news_watcher_detail(
                "admin",
                self.view.admin_visible,
                self.view.guild,
                self.view.author_id,
                selected_method=self.view.watcher_selected_method,
                last_action=self.view.watcher_last_action,
            )
            next_view = _build_watcher_next_view(self.view, interaction, "admin", f"✅ Removed channel subscription #{index} from `{category}`.")
            embed = _build_watcher_role_embed("news_watcher", content or "", self.view.admin_visible, "admin", None, next_view.auto_response_preview)
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number.", ephemeral=True)
        except Exception as error:
            logger.exception(f"Error in Watcher channel unsubscribe modal: {error}")


class CanvasWatcherPersonalUnsubscribeModal(discord.ui.Modal):
    def __init__(self, view, bot):
        self.view = view
        self.bot = bot
        super().__init__(title="Personal Unsubscribe", timeout=300)
        self.number_input = discord.ui.TextInput(label="Subscription Number", placeholder="Enter the numbered subscription from block 2...", style=discord.TextStyle.short, required=True, max_length=3)
        self.add_item(self.number_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands

            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild

            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)

            if interaction.guild:
                server_id = str(interaction.guild.id)
                watcher_commands = WatcherCommands(self.bot)
                db_instance = get_news_watcher_db_instance(server_id)
                if not db_instance.db_path.exists() or db_instance.db_path.stat().st_size == 0:
                    db_instance._init_db()
                watcher_commands.db_watcher = db_instance
            else:
                watcher_commands = WatcherCommands(self.bot)

            try:
                index = int(self.number_input.value.strip())
                if index <= 0:
                    raise ValueError("Number must be positive")
            except ValueError:
                await interaction.response.send_message("❌ Enter a valid positive number.", ephemeral=True)
                return

            user_id = str(interaction.user.id)
            
            # Get unified subscriptions
            subscriptions = watcher_commands.db_watcher.get_user_subscriptions(user_id)
            
            if not subscriptions:
                await interaction.response.send_message("❌ You have no active subscriptions to unsubscribe from.", ephemeral=True)
                return
            
            if index > len(subscriptions):
                await interaction.response.send_message(f"❌ Invalid subscription number. You only have {len(subscriptions)} subscription(s).", ephemeral=True)
                return
            
            # Get the subscription to delete
            sub_id, sub_user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by = subscriptions[index - 1]
            
            # Delete using the new unified system
            success = watcher_commands.db_watcher.delete_subscription(sub_id)

            if success:
                self.view.watcher_last_action = "unsubscribe"
                content = build_canvas_role_news_watcher_detail(
                    self.view.current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = _build_watcher_next_view(self.view, interaction, self.view.current_detail, f"✅ Unsubscribed from `{category}`.")
                embed = _build_watcher_role_embed("news_watcher", content or "", self.view.admin_visible, self.view.current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            else:
                await interaction.response.send_message("❌ Failed to unsubscribe. Please try again.", ephemeral=True)

        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number.", ephemeral=True)
        except Exception as error:
            logger.exception(f"Error in Watcher personal unsubscribe modal: {error}")


class CanvasWatcherFrequencyModal(discord.ui.Modal):
    def __init__(self, view, bot):
        self.view = view
        self.bot = bot
        super().__init__(title="Set Watcher Frequency", timeout=300)
        self.hours_input = discord.ui.TextInput(label="Hours", placeholder="Enter number of hours (1-24)...", style=discord.TextStyle.short, required=True, max_length=5)
        self.add_item(self.hours_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Validate input first
            hours_str = str(self.hours_input.value).strip()
            
            try:
                hours_int = int(hours_str)
            except ValueError:
                await interaction.response.send_message("❌ Invalid format. Please enter a number between 1 and 24.", ephemeral=True)
                return
            
            if not 1 <= hours_int <= 24:
                await interaction.response.send_message("❌ Frequency must be between 1 and 24 hours.", ephemeral=True)
                return

            from roles.news_watcher.watcher_commands import WatcherCommands

            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild

            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)

            if interaction.guild:
                server_id = str(interaction.guild.id)
                watcher_commands = WatcherCommands(self.bot)
                db_instance = get_news_watcher_db_instance(server_id)
                if not db_instance.db_path.exists() or db_instance.db_path.stat().st_size == 0:
                    db_instance._init_db()
                watcher_commands.db_watcher = db_instance
                
                # Direct database update instead of using cmd_frequency (which sends embeds)
                if db_instance.set_frequency_setting(hours_int):
                    result_msg = f"✅ Watcher frequency set to {hours_int} hours"
                else:
                    await interaction.response.send_message("❌ Error updating frequency setting", ephemeral=True)
                    return
            else:
                await interaction.response.send_message("❌ Guild context required", ephemeral=True)
                return

            try:
                self.view.watcher_last_action = "watcher_frequency"
                current_detail = "admin" if self.view.current_detail == "admin" else "personal"
                content = build_canvas_role_news_watcher_detail(
                    current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = _build_watcher_next_view(self.view, interaction, current_detail, result_msg)
                embed = _build_watcher_role_embed("news_watcher", content or "", self.view.admin_visible, current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                logger.info("Watcher Canvas frequency completed but interaction expired")
            except discord.HTTPException as error:
                logger.warning(f"Could not update Canvas for Watcher frequency: {error}")

        except Exception as error:
            logger.exception(f"Error in Watcher frequency modal: {error}")


class CanvasWatcherFeedsByCategoryModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="List Feeds by Category")
        self.view = view
        self.category_input = discord.ui.TextInput(label="Category", placeholder="Enter category (economy, technology, gaming, crypto, international, general, patch_notes)...", style=discord.TextStyle.short, required=True, max_length=50)
        self.add_item(self.category_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            category = str(self.category_input.value).strip().lower()
            if get_news_watcher_db_instance is None or not interaction.guild:
                await interaction.response.send_message("❌ Watcher database is not available.", ephemeral=True)
                return

            db = get_news_watcher_db_instance(str(interaction.guild.id))
            feeds = db.get_active_feeds(category)
            if not feeds:
                await interaction.response.send_message(f"❌ No feeds found for category '{category}'. Available categories: economy, technology, gaming, crypto, international, general, patch_notes", ephemeral=True)
                return

            self.view.watcher_last_action = "list_feeds_by_category"
            self.view.watcher_selected_category = category
            content = build_canvas_role_news_watcher_detail(
                self.view.current_detail,
                self.view.admin_visible,
                self.view.guild,
                self.view.author_id,
                selected_method=self.view.watcher_selected_method,
                last_action="list_feeds_by_category",
                selected_category=category,
            )
            next_view = _build_watcher_next_view(self.view, interaction, self.view.current_detail)
            next_view.watcher_last_action = "list_feeds_by_category"
            next_view.watcher_selected_category = category
            embed = _build_watcher_role_embed("news_watcher", content or "", self.view.admin_visible, self.view.current_detail, None, next_view.auto_response_preview)
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        except Exception as error:
            logger.exception(f"Error in feeds by category modal: {error}")
            await interaction.response.send_message("❌ Error listing feeds. Please try again.", ephemeral=True)


async def handle_canvas_watcher_action(interaction: discord.Interaction, action_name: str, view) -> None:
    if get_news_watcher_db_instance is None:
        await interaction.response.send_message("❌ Watcher database is not available.", ephemeral=True)
        return

    if not interaction.guild:
        await interaction.response.send_message("❌ Watcher actions require a server context.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)

    if action_name in {"method_flat", "method_keyword", "method_general"}:
        method_name = action_name.replace("method_", "")
        try:
            # Method configuration per server is no longer supported with unified subscription system
            # Each subscription now has its own method
            ok = True  # Always succeed, but show informational message
        except Exception as error:
            logger.exception(f"Canvas watcher method update failed: {error}")
            ok = False
        if not ok:
            await interaction.response.send_message("❌ Could not update watcher method.", ephemeral=True)
            return

        view.watcher_selected_method = method_name
        view.watcher_last_action = None
        current_detail = "admin" if view.current_detail == "admin" else "personal"
        
        # Add informational message about system update
        info_message = f"Method `{method_name}` noted. Note: Server-wide method configuration has been replaced with individual subscription methods."
        content = build_canvas_role_news_watcher_detail(current_detail, view.admin_visible, view.guild, view.author_id, selected_method=view.watcher_selected_method, last_action=view.watcher_last_action)
        next_view = _build_watcher_next_view(view, interaction, current_detail, info_message)
        embed = _build_watcher_role_embed("news_watcher", content or "", view.admin_visible, current_detail, None, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        return

    if action_name == "subscribe_categories":
        await interaction.response.send_modal(CanvasWatcherSubscribeModal(action_name, view, interaction.client))
        return
    if action_name == "channel_subscribe_categories":
        await interaction.response.send_modal(CanvasWatcherChannelSubscribeModal(action_name, view, interaction.client))
        return
    if action_name == "channel_unsubscribe":
        await interaction.response.send_modal(CanvasWatcherChannelUnsubscribeModal(view, interaction.client))
        return
    if action_name == "channel_subscribe_category":
        await interaction.response.send_modal(CanvasWatcherChannelSubscribeModal(action_name, view, interaction.client))
        return
    if action_name == "channel_unsubscribe_category":
        await interaction.response.send_modal(CanvasWatcherChannelUnsubscribeModal(view, interaction.client))
        return
    if action_name == "delete_premise":
        await interaction.response.send_modal(CanvasWatcherDeleteModal("delete_premises", view, interaction.client))
        return
    if action_name == "add_premise":
        await interaction.response.send_modal(CanvasWatcherAddModal("add_premises", view, interaction.client))
        return
    if action_name == "add_keywords":
        await interaction.response.send_modal(CanvasWatcherAddModal("add_keywords", view, interaction.client))
        return
    if action_name == "delete_keywords":
        await interaction.response.send_modal(CanvasWatcherDeleteModal("delete_keywords", view, interaction.client))
        return
    if action_name in {"list_keywords", "list_premises"}:
        await interaction.response.send_modal(CanvasWatcherListModal(action_name.replace("list_", ""), view, interaction.client))
        return
    if action_name == "watcher_frequency":
        await interaction.response.send_modal(CanvasWatcherFrequencyModal(view, interaction.client))
        return

    if action_name == "channel_view_subscriptions":
        view.watcher_last_action = action_name
        content = build_canvas_role_news_watcher_detail(
            "admin",
            view.admin_visible,
            view.guild,
            view.author_id,
            selected_method=view.watcher_selected_method,
            last_action=view.watcher_last_action,
        )
        next_view = _build_watcher_next_view(view, interaction, "admin")
        embed = _build_watcher_role_embed("news_watcher", content or "", view.admin_visible, "admin", None, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        return

    if action_name == "watcher_run_now":
        try:
            from roles.news_watcher.news_watcher import process_subscriptions
            from discord_bot.discord_http import DiscordHTTP
            from agent_engine import get_discord_token

            if not view.guild:
                await interaction.response.send_message("Guild context is required to run watcher actions.", ephemeral=True)
                return

            http = DiscordHTTP(get_discord_token())
            server_id = str(view.guild.id)
            await process_subscriptions(http, server_id)
        except Exception as error:
            logger.exception(f"Canvas watcher run now failed: {error}")
            await interaction.response.send_message("Failed to run watcher. Check logs.", ephemeral=True)
        return
    elif action_name == "watcher_run_personal":
        try:
            from roles.news_watcher.news_watcher import process_subscriptions
            from discord_bot.discord_http import DiscordHTTP
            from agent_engine import get_discord_token

            if not view.guild:
                await interaction.response.send_message("Guild context is required to run watcher actions.", ephemeral=True)
                return

            http = DiscordHTTP(get_discord_token())
            server_id = str(view.guild.id)
            await process_subscriptions(http, server_id, include_channels=False)
        except Exception as error:
            logger.exception(f"Canvas watcher run personal failed: {error}")
            await interaction.response.send_message("Failed to run personal subscriptions. Check logs.", ephemeral=True)
        return

    await interaction.response.send_message("❌ Unknown watcher action.", ephemeral=True)


def build_canvas_role_news_watcher(agent_config: dict, admin_visible: bool, guild=None, author_id: int = 0) -> str:
    """Build the News Watcher role view (same as personal view)."""
    return build_canvas_role_news_watcher_detail("personal", admin_visible, guild, author_id, None, None, None)


def get_canvas_channel_subscriptions_info(guild) -> str:
    """Get formatted channel subscriptions information for canvas display."""
    try:
        # Safe nested access with fallbacks
        news_watcher = _get_nw_descriptions(guild)
        dropdown = news_watcher.get("dropdown", {}) if isinstance(news_watcher, dict) else {}
        
        def _watcher_text(key: str, fallback: str) -> str:
            # Try dropdown first, then main level
            value = dropdown.get(key)
            if value is None:
                value = news_watcher.get(key)
            return str(value).strip() if value else fallback

        if get_news_watcher_db_instance is None:
            return f"**{_watcher_text('channel_subscriptions_title', 'Channel subscriptions')}**\n- Unable to load channel subscription data"

        db = get_news_watcher_db_instance(str(guild.id))
        
        # Get all channel subscriptions with unified system
        all_channel_subs = []
        
        # Get all unified subscriptions and filter for channel subscriptions
        unified_subs = db.get_all_active_subscriptions()
        for subscription_id, user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by in unified_subs:
            # Only include channel subscriptions
            if not channel_id:
                continue
                
            channel_name = f"#{channel_id}"  # Fallback name
            
            # Determine content based on method
            if method == "flat":
                content = ""
            elif method == "keyword":
                content = keywords or ""
            elif method == "general":
                content = premises or ""
            else:
                content = ""
            
            all_channel_subs.append((channel_id, channel_name, category, content, feed_id is None))
        
        total_count = len(all_channel_subs)
        max_subs = 5
        usage_info = f"**{_watcher_text('channel_subscriptions_title', 'Channel subscriptions')}** ({total_count}/{max_subs})\n"

        if total_count == 0:
            usage_info += "- No active channel subscriptions\n"
        else:
            subscriptions_list = []
            for channel_id, channel_name, category, keywords, all_feeds in all_channel_subs:
                if all_feeds:
                    subscriptions_list.append(f"  📰 {category} (all feeds) - #{channel_name}")
                elif keywords:
                    subscriptions_list.append(f"  🔍 {category} (keywords: {keywords}, all feeds) - #{channel_name}")
                else:
                    subscriptions_list.append(f"  📰 {category} (feed #{channel_name})")
            
            for sub in subscriptions_list:
                usage_info += f"{sub}\n"

        config_info = f"\n──────────────────────────────\n\n{_watcher_text('server_configuration_title', '**Server configuration**')}\n"

        try:
            frequency = db.get_frequency_config(str(guild.id))
            config_info += f"- ⏰ **{_watcher_text('watcher_frequency_title', 'Check frequency')}**: Every {frequency} hours\n"
        except Exception:
            config_info += f"- ⏰ **{_watcher_text('watcher_frequency_title', 'Check frequency')}**: Not configured\n"

        # Method configuration per server is no longer available - use default
        method = "general"
        method_labels = {
            "flat": "Flat (All news)",
            "keyword": "Keyword (Filtered)",
            "general": "General (AI-critical)",
        }
        config_info += f"- 🔧 **Default method**: {method_labels.get(method, 'Unknown')} (individual subscription methods)\n"

        return usage_info + config_info

    except Exception as e:
        logger.warning(f"Could not load channel subscriptions for Canvas: {e}")
        return f"**{_watcher_text('channel_subscriptions_title', 'Channel subscriptions')}**\n- Error loading channel subscription data"


def get_canvas_user_subscriptions_info(guild, author_id: int) -> str:
    """Get formatted user subscriptions information for canvas display."""
    try:
        if get_news_watcher_db_instance is None:
            return "**Active subscriptions**\n- Unable to load subscription data"

        db = get_news_watcher_db_instance(str(guild.id))
        user_id = str(author_id)

        # Get unified subscriptions
        subscriptions = db.get_user_subscriptions(user_id)
        current_count = len(subscriptions)
        max_subs = 10  # Increased limit for unified system
        
        _nw = _get_nw_descriptions(guild)
        title_active_subscriptions = _nw.get("title_active_subscriptions", "**Active subscriptions**")
        usage_info = f"{title_active_subscriptions} ({current_count}/{max_subs})\n"
        title_no_active_subscriptions = _nw.get("title_no_active_subscriptions", "- No active subscriptions")
        
        if current_count == 0:
            usage_info += f"{title_no_active_subscriptions}\n"
        else:
            title_your_subscriptions = _nw.get("title_your_subscriptions", "- **Your subscriptions:**")
            subscriptions_info = f"{title_your_subscriptions}\n"

            # Display unified subscriptions with method-specific formatting
            for i, (sub_id, sub_user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by) in enumerate(subscriptions, 1):
                if method == "flat":
                    icon = "📰"
                    method_name = "Flat"
                    content = ""
                elif method == "keyword":
                    icon = "🔍"
                    method_name = "Keywords"
                    content = f" - {keywords}" if keywords else ""
                elif method == "general":
                    icon = "🤖"
                    method_name = "AI"
                    content = f" - {premises[:30]}..." if premises and len(premises) > 30 else f" - {premises}" if premises else ""
                else:
                    icon = "❓"
                    method_name = method.title()
                    content = ""
                
                if feed_id:
                    subscriptions_info += f"  {i}. {icon} {method_name}: {category} (feed #{feed_id}){content}\n"
                else:
                    subscriptions_info += f"  {i}. {icon} {method_name}: {category} (all feeds){content}\n"

            usage_info += subscriptions_info

        title_configuration_status = _nw.get("title_configuration_status", "**Configuration status**")
        config_info = "\n"
        config_info += "-" * 45
        config_info += f"\n {title_configuration_status}\n"

        # Get user premises (standalone premises, not subscription-specific)
        title_premises = _nw.get("premises_title", "🤖**Premises:**")
        no_premises = _nw.get("no_premises", "None configured")
        patch_premises_configured = _nw.get("premises_configured", "configured")
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
    
    # Safe nested access with fallbacks
    news_watcher = _get_nw_descriptions(guild)
    
    # Ensure watcher_descriptions is a dict
    if not isinstance(news_watcher, dict):
        watcher_descriptions = {}
    else:
        watcher_descriptions = news_watcher

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

            # Initialize lines list
            lines = []

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
        if not guild or not author_id:
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
                lines = ["- **No custom premises configured**", "- Use 'Add Premises' to create custom premises", "- Or use !canvas to auto-initialize with defaults"]
                return "\n".join(lines)

            lines = []
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
        "flat": _watcher_text("method_flat", "Flat"),
        "keyword": _watcher_text("method_keyword", "Keyword"),
        "general": _watcher_text("method_general", "General"),
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
                "📡 News Watcher Canvas - Keywords",
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
            "**Routing**",
            "- These settings shape your personal watcher filtering",
            "- Use `!canvas role news_watcher` to return to the role overview",
        ])

    if detail_name == "feeds":
        return "\n".join([
            _build_canvas_intro_block(
                "📡 News Watcher Canvas - Feeds",
                "Browse and manage available news sources",
            ),
            "**Available feeds**",
            _format_feeds(),
            "",
            "**Feed categories**",
            _format_categories(),
            "",
            "**Routing**",
            "- Use category filters to browse specific feed types",
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
