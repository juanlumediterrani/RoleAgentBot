"""Canvas News Watcher Wizard - Step-by-step subscription flow."""

import discord
from discord_bot import discord_core_commands as core
from discord_bot.discord_utils import get_server_key
from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance

logger = core.logger


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


def _get_server_language(guild) -> str:
    """Get server language from server_config.json."""
    try:
        from discord_bot.canvas.server_config import get_server_language
        server_id = str(guild.id)
        language = get_server_language(server_id)
        # Extract base language code (e.g., 'es-ES' -> 'es')
        if language:
            return language.split('-')[0].lower()
    except Exception as e:
        logger.warning(f"Could not get server language: {e}")
    
    # Default to English if not available
    return 'en'


def _watcher_text(guild, key: str, fallback: str) -> str:
    """Helper to get watcher text with fallback."""
    news_watcher = _get_nw_descriptions(guild)
    watcher_descriptions = news_watcher.get("dropdown", {}) if isinstance(news_watcher, dict) else {}
    if not isinstance(watcher_descriptions, dict):
        watcher_descriptions = {}
    value = watcher_descriptions.get(key)
    return str(value).strip() if value else fallback


class NewsWatcherWizard:
    """Manages the step-by-step subscription wizard."""
    
    def __init__(self, interaction: discord.Interaction, is_admin: bool = False):
        self.original_interaction = interaction  # Store the original interaction
        self.interaction = interaction  # Current interaction (updates with each selection)
        self.is_admin = is_admin
        self.step = 0
        self.wizard_message = None  # Store the wizard message for editing
        self.data = {
            'method': None,
            'category': None,
            'feed_id': None,
            'feed_url': None,
            'feed_name': None,
            'keywords': [],
            'premises': []
        }
        self.guild = interaction.guild
        self.user_id = str(interaction.user.id)
        self.channel_id = str(interaction.channel.id) if interaction.channel else None
    
    async def start(self):
        """Start the wizard by showing method and category selection."""
        self.step = 1
        await self._show_method_category_selection()
    
    async def _show_method_category_selection(self):
        """Show method and category selection dropdowns in one ephemeral."""
        # Get descriptions from news_watcher.json
        news_watcher = _get_nw_descriptions(self.guild)
        dropdown_descriptions = news_watcher.get("dropdown", {}) if isinstance(news_watcher, dict) else {}
        
        # Method dropdown using descriptions from news_watcher.json
        method_options = [
            discord.SelectOption(
                label=dropdown_descriptions.get("method_flat_label", "📰 Flat - All news with opinions"),
                value="flat",
                description=dropdown_descriptions.get("method_flat_desc", "Receive all news with AI-generated opinions")
            ),
            discord.SelectOption(
                label=dropdown_descriptions.get("method_keyword_label", "🔍 Keyword - Filter by keywords"),
                value="keyword",
                description=dropdown_descriptions.get("method_keyword_desc", "Receive news matching specific keywords")
            ),
            discord.SelectOption(
                label=dropdown_descriptions.get("method_general_label", "🤖 General - AI critical analysis"),
                value="general",
                description=dropdown_descriptions.get("method_general_desc", "AI analyzes news for critical events")
            ),
        ]
        
        method_select = discord.ui.Select(
            placeholder=dropdown_descriptions.get("wizard_method_placeholder", "🔧 Select subscription method..."),
            options=method_options,
            min_values=1,
            max_values=1,
            row=0
        )
        
        # Category dropdown
        from roles.news_watcher.global_feed_health import get_healthy_feeds
        
        # Get server language and filter feeds by language
        server_language = _get_server_language(self.guild)
        healthy_feeds = get_healthy_feeds(language=server_language)
        
        # Get unique categories
        categories = sorted(set(feed[3] for feed in healthy_feeds))
        
        # Get category descriptions from news_watcher.json
        category_descriptions = news_watcher.get("category_descriptions", {}) if isinstance(news_watcher, dict) else {}
        
        category_options = [
            discord.SelectOption(
                label=category.title(), 
                value=category, 
                description=category_descriptions.get(category, f"News from {category.title()}")
            )
            for category in categories
        ]
        
        category_select = discord.ui.Select(
            placeholder=dropdown_descriptions.get("wizard_category_placeholder", "📂 Select news category..."),
            options=category_options,
            min_values=1,
            max_values=1,
            row=1
        )
        
        view = discord.ui.View()
        view.add_item(method_select)
        view.add_item(category_select)
        
        async def method_callback(interaction: discord.Interaction):
            self.data['method'] = method_select.values[0]
            self.interaction = interaction
            # Don't send feedback message, just update state and check
            await interaction.response.defer()  # Defer to allow the interaction to complete
            await self._check_and_proceed()
        
        async def category_callback(interaction: discord.Interaction):
            self.data['category'] = category_select.values[0]
            self.interaction = interaction
            # Don't send feedback message, just update state and check
            await interaction.response.defer()  # Defer to allow the interaction to complete
            await self._check_and_proceed()
        
        method_select.callback = method_callback
        category_select.callback = category_callback
        
        # Get translations from news_watcher.json
        news_watcher = _get_nw_descriptions(self.guild)
        step1_title = news_watcher.get("wizard_step1_title", "📋 **Step 1/3: Select Method and Category**")
        step1_desc = news_watcher.get("wizard_step1_desc", "Choose subscription method and news category:")
        
        await self.interaction.response.send_message(
            content=f"{step1_title}\n{step1_desc}",
            view=view,
            ephemeral=True
        )
        try:
            self.wizard_message = await self.interaction.original_response()
        except Exception as e:
            logger.warning(f"Could not get original response for wizard message: {e}")
            self.wizard_message = None
    
    async def _check_and_proceed(self):
        """Check if both method and category are selected, then proceed."""
        if self.data['method'] and self.data['category']:
            # Both selected, proceed to feed selection
            # Use the original interaction to edit the first message
            news_watcher = _get_nw_descriptions(self.guild)
            method_label = news_watcher.get("wizard_method_label", "Method")
            category_label = news_watcher.get("wizard_category_label", "Category")
            
            await self.original_interaction.edit_original_response(
                content=f"✅ {method_label}: {self.data['method'].title()}\n✅ {category_label}: {self.data['category'].title()}",
                view=None
            )
            await self._show_feed_selection()
    
    async def _show_feed_selection(self):
        """Show feed selection dropdown for the selected category."""
        from roles.news_watcher.global_feed_health import get_healthy_feeds
        from collections import defaultdict
        
        # Get descriptions from news_watcher.json
        news_watcher = _get_nw_descriptions(self.guild)
        
        # Get server language and filter feeds by language
        server_language = _get_server_language(self.guild)
        healthy_feeds = get_healthy_feeds(language=server_language)
        categories = defaultdict(list)
        for feed_id, name, url, category in healthy_feeds:
            categories[category].append((feed_id, name, url))
        
        feeds = categories[self.data['category']]
        
        options = [
            discord.SelectOption(
                label=f"📡 {name}",
                value=str(feed_id),
                description=url[:80] + "..." if len(url) > 80 else url
            )
            for feed_id, name, url in feeds
        ]
        
        options.append(
            discord.SelectOption(
                label=news_watcher.get("wizard_all_feeds_label", "🌐 All feeds in this category"),
                value="all",
                description=news_watcher.get("wizard_all_feeds_desc", "Subscribe to all feeds in this category")
            )
        )
        
        select = discord.ui.Select(
            placeholder=news_watcher.get("wizard_feed_placeholder", "📡 Select a news source..."),
            options=options,
            min_values=1,
            max_values=1
        )
        
        view = discord.ui.View()
        view.add_item(select)
        
        async def callback(interaction: discord.Interaction):
            selected_value = select.values[0]
            if selected_value == "all":
                self.data['feed_id'] = None
                self.data['feed_url'] = None
                self.data['feed_name'] = "All feeds"
            else:
                feed_id = int(selected_value)
                feed_data = next((f for f in feeds if f[0] == feed_id), None)
                if feed_data:
                    self.data['feed_id'] = feed_id
                    self.data['feed_url'] = feed_data[2]
                    self.data['feed_name'] = feed_data[1]
            
            # Check if we need to show modal for keywords/premises
            if self.data['method'] in ['keyword', 'general']:
                # Send modal directly instead of editing first
                if self.data['method'] == 'keyword':
                    await self._show_keywords_modal(interaction)
                else:
                    await self._show_premises_modal(interaction)
            else:
                # Fallback to original interaction if wizard_message is None
                if self.wizard_message:
                    await self.wizard_message.edit(
                        content=f"✅ Source selected: {self.data['feed_name']}",
                        view=None
                    )
                else:
                    await self.original_interaction.edit_original_response(
                        content=f"✅ Source selected: {self.data['feed_name']}",
                        view=None
                    )
                await self._complete_subscription()
        
        select.callback = callback
        
        step2_title = news_watcher.get("wizard_step2_title", "📋 **Step 2/3: Select News Source**")
        step2_desc = news_watcher.get("wizard_step2_desc", "Choose a specific feed or all feeds:")

        # Fallback to original interaction if wizard_message is None
        if self.wizard_message:
            await self.wizard_message.edit(
                content=f"{step2_title}\n{step2_desc}",
                view=view
            )
        else:
            await self.original_interaction.edit_original_response(
                content=f"{step2_title}\n{step2_desc}",
                view=view
            )
    
    async def _show_keywords_modal(self, interaction: discord.Interaction):
        """Show modal for entering 5 keywords with personality defaults."""
        # Get default keywords from personality
        default_keywords = self._get_default_keywords()
        
        modal = discord.ui.Modal(title="🔍 Configure Keywords", timeout=300)
        
        for i in range(5):
            default_val = default_keywords[i] if i < len(default_keywords) else ""
            text_input = discord.ui.TextInput(
                label=f"Keyword {i+1}",
                placeholder=f"Enter keyword {i+1}...",
                style=discord.TextStyle.short,
                required=False,
                max_length=50,
                default=default_val
            )
            modal.add_item(text_input)
        
        async def on_submit(modal_interaction: discord.Interaction):
            keywords = []
            for item in modal.children:
                if item.value and item.value.strip():
                    keywords.append(item.value.strip())
            
            self.data['keywords'] = keywords
            await modal_interaction.response.edit_message(
                content=f"✅ Keywords configured: {', '.join(keywords)}",
                view=None
            )
            await self._complete_subscription()
        
        modal.on_submit = on_submit
        
        # Send modal directly using the interaction from the callback
        await interaction.response.send_modal(modal)
    
    async def _show_premises_modal(self, interaction: discord.Interaction):
        """Show modal for entering up to 3 premises with personality defaults."""
        # Get default premises from personality
        default_premises = self._get_default_premises()
        
        modal = discord.ui.Modal(title="🤖 Configure AI Premises (Max 3)", timeout=300)
        
        # Limit to 3 premises maximum
        for i in range(3):
            default_val = default_premises[i] if i < len(default_premises) else ""
            text_input = discord.ui.TextInput(
                label=f"Premise {i+1}",
                placeholder=f"Enter AI analysis premise {i+1}...",
                style=discord.TextStyle.paragraph,
                required=False,
                max_length=200,
                default=default_val
            )
            modal.add_item(text_input)
        
        async def on_submit(modal_interaction: discord.Interaction):
            premises = []
            for item in modal.children:
                if item.value and item.value.strip():
                    premises.append(item.value.strip())
            
            # Validate maximum 3 premises
            if len(premises) > 3:
                await modal_interaction.response.send_message(
                    "❌ Maximum 3 premises allowed. Please remove some and try again.",
                    ephemeral=True
                )
                return
            
            self.data['premises'] = premises
            await modal_interaction.response.edit_message(
                content=f"✅ Premises configured: {len(premises)} premises set",
                view=None
            )
            await self._complete_subscription()
        
        modal.on_submit = on_submit
        
        # Send modal directly using the interaction from the callback
        await interaction.response.send_modal(modal)
    
    def _get_default_keywords(self) -> list:
        """Get default keywords from personality config."""
        try:
            from agent_engine import PERSONALITY
            news_watcher_config = PERSONALITY.get("roles", {}).get("news_watcher", {})
            return news_watcher_config.get("default_keywords", [
                "breaking news",
                "important",
                "urgent"
            ])
        except Exception:
            return ["breaking news", "important", "urgent"]
    
    def _get_default_premises(self) -> list:
        """Get default premises from server-specific news_watcher.json file."""
        try:
            from roles.news_watcher.news_watcher import _get_news_watcher_descriptions
            from agent_db import get_server_id
            server_id = str(self.guild.id) if self.guild else None
            descriptions = _get_news_watcher_descriptions(server_id)
            return descriptions.get("premises", [
                "War outbreak or nuclear escalation",
                "Bankruptcy of a country or large corporation",
                "Global magnitude catastrophe",
                "Major technological breakthrough",
                "Significant political shift"
            ])
        except Exception:
            return [
                "War outbreak or nuclear escalation",
                "Bankruptcy of a country or large corporation",
                "Global magnitude catastrophe",
                "Major technological breakthrough",
                "Significant political shift"
            ]
    
    async def _complete_subscription(self):
        """Complete the subscription by writing to database."""
        try:
            if not self.guild:
                await self.interaction.followup.send("❌ Subscriptions are only available in servers", ephemeral=True)
                return
            
            server_id = str(self.guild.id)
            db = get_news_watcher_db_instance(server_id)
            
            logger.info(f"[Wizard _complete_subscription] server_id={server_id}, db={db is not None}")
            
            if db is None:
                await self.interaction.followup.send("❌ Failed to initialize database for this server", ephemeral=True)
                return
            
            # Check subscription limit before creating
            from roles.news_watcher.subscription_limits import check_user_subscription_limit, increment_user_subscription_count
            
            # Check limit (no admin exemption - only premium SKU users)
            logger.info(f"[Wizard _complete_subscription] Checking subscription limit for user_id={self.user_id}")
            limit_check = await check_user_subscription_limit(self.user_id, is_admin=False)
            logger.info(f"[Wizard _complete_subscription] Limit check: allowed={limit_check.allowed}, reason={limit_check.reason}")
            if not limit_check.allowed:
                await self.interaction.followup.send(f"❌ {limit_check.reason}", ephemeral=True)
                return
            
            # Prepare subscription data
            user_id = self.user_id if not self.is_admin else None
            channel_id = self.channel_id if self.is_admin else None
            
            # Convert lists to comma-separated strings
            keywords_str = ",".join(self.data['keywords']) if self.data['keywords'] else None
            premises_str = ",".join(self.data['premises']) if self.data['premises'] else None
            
            # Get feed_id from global feeds if needed
            feed_id = self.data['feed_id']
            if feed_id is None and self.data['feed_url']:
                # Look up feed_id from global feeds
                from roles.news_watcher.global_feed_health import get_healthy_feeds
                server_language = _get_server_language(self.guild)
                healthy_feeds = get_healthy_feeds(language=server_language)
                for fid, name, url, category in healthy_feeds:
                    if url == self.data['feed_url']:
                        feed_id = fid
                        break
            
            # Create subscription (don't increment global count here, we do it manually after)
            logger.info(f"[Wizard _complete_subscription] Calling create_subscription with user_id={user_id}, channel_id={channel_id}, category={self.data['category']}, feed_id={feed_id}, method={self.data['method']}")
            try:
                subscription_id = await db.create_subscription(
                    user_id=user_id,
                    channel_id=channel_id,
                    category=self.data['category'],
                    feed_id=feed_id,
                    premises=premises_str,
                    keywords=keywords_str,
                    method=self.data['method'],
                    created_by=self.user_id,
                    increment_global_count=False
                )
            except Exception as create_err:
                logger.exception(f"[Wizard _complete_subscription] Exception during create_subscription: {create_err}")
                await self.interaction.followup.send(f"❌ Error creating subscription: {str(create_err)}", ephemeral=True)
                return
            logger.info(f"[Wizard _complete_subscription] create_subscription returned subscription_id={subscription_id}")
            
            if subscription_id:
                # Increment global subscription count
                await increment_user_subscription_count(self.user_id)

                target = "channel" if self.is_admin else "your DM"
                source_desc = self.data['feed_name']

                # Load descriptions from news_watcher.json
                news_watcher = _get_nw_descriptions(self.guild)
                success_title = news_watcher.get("wizard_success_title", "✅ **Subscription Created!**")
                category_label = news_watcher.get("wizard_category_label", "Category")
                source_label = news_watcher.get("wizard_source_label", "Source")
                delivery_label = news_watcher.get("wizard_delivery_label", "Delivery")
                delivery_channel = news_watcher.get("wizard_delivery_channel", "channel")
                delivery_dm = news_watcher.get("wizard_delivery_dm", "your DM")
                footer_text = news_watcher.get("wizard_footer_text", "You'll receive news matching your configuration.")

                target_text = delivery_channel if self.is_admin else delivery_dm

                # Fallback to original interaction if wizard_message is None
                if self.wizard_message:
                    await self.wizard_message.edit(
                        content=f"{success_title}\n\n"
                        f"{category_label}: {self.data['category'].title()}\n"
                        f"{source_label}: {source_desc}\n"
                        f"{delivery_label}: {target_text}\n\n"
                        f"{footer_text}\n"
                        f"📊 {limit_check.reason}",
                        view=None
                    )
                else:
                    await self.original_interaction.edit_original_response(
                        content=f"{success_title}\n\n"
                        f"{category_label}: {self.data['category'].title()}\n"
                        f"{source_label}: {source_desc}\n"
                        f"{delivery_label}: {target_text}\n\n"
                        f"{footer_text}\n"
                        f"📊 {limit_check.reason}",
                        view=None
                    )
            else:
                await self.interaction.followup.send("❌ Failed to create subscription. You may already be subscribed to this combination.", ephemeral=True)
        
        except Exception as e:
            logger.exception(f"Error completing subscription: {e}")
            await self.interaction.followup.send(f"❌ Error creating subscription: {str(e)}", ephemeral=True)
