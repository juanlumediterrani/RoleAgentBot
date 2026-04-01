import os
import json
from agent_logging import get_logger

logger = get_logger('watcher_messages')

def get_watcher_messages():
    """Load custom Watcher messages from personality file."""
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "agent_config.json")
        with open(config_path, encoding="utf-8") as f:
            agent_cfg = json.load(f)
        personality_rel = agent_cfg.get("personality", "")
        answers_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            os.path.dirname(personality_rel),
            "answers.json",
        )
        with open(answers_path, encoding="utf-8") as f:
            watcher_messages = json.load(f).get("discord", {}).get("watcher_messages", {})
        
        # Also load from news_watcher.json for commands section
        news_watcher_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            os.path.dirname(personality_rel),
            "descriptions",
            "news_watcher.json",
        )
        
        try:
            with open(news_watcher_path, encoding="utf-8") as f:
                news_watcher_data = json.load(f)
                commands = news_watcher_data.get("commands", {})
                # Merge commands into watcher_messages
                watcher_messages.update(commands)
        except FileNotFoundError:
            logger.warning("⚠️ news_watcher.json not found, skipping commands section")
        
        if not watcher_messages:
            logger.warning("⚠️ No custom watcher messages found in personality")
            return get_default_messages()
        
        logger.info("🦅 Custom watcher messages loaded from personality")
        return watcher_messages
        
    except Exception as e:
        logger.error(f"❌ Error loading watcher messages: {e}")
        return get_default_messages()

def get_default_messages():
    """Default messages if no customization available."""
    return {
        "feeds_available_title": "📡 Available Feeds",
        "categories_available_title": "📂 Available Categories",
        "subscription_successful_category": "✅ You have subscribed to all news from '{category}'",
        "subscription_successful_feed": "✅ You have subscribed to feed {feed_id} from category '{category}'",
        "channel_subscription_successful_category": "✅ This channel has been subscribed to all news from '{category}'",
        "channel_subscription_successful_feed": "✅ This channel has been subscribed to feed {feed_id} from '{category}'",
        "subscription_cancelled_category": "✅ Subscription cancelled to category '{category}'",
        "subscription_cancelled_feed": "✅ Subscription cancelled to feed {feed_id} from '{category}'",
        "channel_subscription_cancelled_category": "✅ Subscription cancelled to category '{category}'",
        "channel_subscription_cancelled_feed": "✅ Subscription cancelled to feed {feed_id} from '{category}'",
        "error_general": "❌ Error: {error}",
        "error_subscription": "❌ Error performing subscription",
        "error_cancellation": "❌ Error cancelling subscription",
        "error_permissions": "❌ Only administrators can perform this action",
        "feed_id_not_found": "❌ Feed ID {feed_id} not found in category '{category}'",
        "error_category_not_found": "❌ Category '{category}' not found",
        "feed_id_must_be_number": "❌ Feed ID must be a number",
        "error_no_feeds": "📭 No feeds configured",
        "error_no_categories": "📭 No categories available",
        "error_no_subscriptions": "📭 You have no active subscriptions",
        "error_no_channel_subscriptions": "📭 This channel has no active subscriptions",
        "error_no_general_feeds": "❌ No general feeds for '{category}'",
        "error_no_keywords": "📭 You have no keyword subscriptions",
        "status_title": "📊 Your Subscriptions",
        "channel_status_title": "📊 Channel Subscriptions",
        "keywords_title": "🔍 Your Keywords",
        "usage_subscribe": "📝 Usage: `!watcher subscribe <category> [feed_id|all]`\nNo feed_id: first feed | 'all': all feeds",
        "usage_unsubscribe": "📝 Usage: `!watcher unsubscribe <category> [feed_id]`",
        "usage_general": "📝 Usage: `!watcher general <category> [feed_id|all]`\nNo feed_id: first feed | 'all': all feeds",
        "usage_keywords": "📝 Usage: `!watcher keywords \"word1,word2,word3\" [category] [feed_id|all]`",
        "usage_cancel_keywords": "📝 Usage: `!watcher keywords unsubscribe <category>`",
        "usage_mixed": "📝 Usage: `!watcher mixed <category>`",
        "usage_add_feed": "📝 Usage: `!watcher add_feed <name> <url> <category> [country] [language]`",
        "usage_channel_subscribe": "📝 Usage: `!watcherchannel subscribe <category> [feed_id|all]`\nNo feed_id: first feed | 'all': all feeds",
        "usage_channel_unsubscribe": "📝 Usage: `!watcherchannel unsubscribe <category> [feed_id]`",
        "usage_channel_keywords": "📝 Usage: `!watcherchannel keywords \"word1,word2\"`",
        "usage_channel_premises_add": "📝 Usage: `!watcherchannel premises add <premise>`",
        "usage_channel_premises_mod": "📝 Usage: `!watcherchannel premises mod <number> <premise>`",
        "usage_premises_add": "📝 Usage: `!watcher premises add \"premise text\"`",
        "usage_premises_mod": "📝 Usage: `!watcher premises mod <number> \"new premise\"`",
        "usage_premises_configure": "📝 Usage: `!watcher premises configure \"premise1,premise2,premise3\"`\nMaximum 7 premises, separated by commas.",
        "general_subscription_successful": "✅ Subscribed to general feeds from '{category}' with AI classification",
        "keywords_subscription_successful": "✅ Subscribed to keywords: '{keywords}'",
        "keywords_subscription_cancelled": "✅ Subscription cancelled: '{keywords}'",
        "mixed_subscription_successful": "✅ Subscribed to mixed coverage of '{category}' (specialized + general)",
        "mixed_subscription_partial": "✅ Subscribed to specialized coverage of '{category}'",
        "channel_keywords_subscription_successful": "✅ Channel subscribed to keywords: '{keywords}'",
        "critical_news_detected": "🚨 CRITICAL NEWS DETECTED! {title}",
        "normal_notification": "📡 New news: {title}",
        "feed_added_successful": "✅ Feed '{name}' added to category '{category}'"
    }

def get_message(key, **kwargs):
    """Get a custom message with variable formatting."""
    messages = get_watcher_messages()
    message = messages.get(key)
    
    # If personality doesn't have the message, use English fallback
    if message is None:
        message = get_english_fallback(key)
    
    # Replace variables in message
    try:
        return message.format(**kwargs)
    except KeyError as e:
        logger.error(f"❌ Error formatting message '{key}': variable not found {e}")
        return message
    except Exception as e:
        logger.error(f"❌ Error formatting message '{key}': {e}")
        return message

def get_english_fallback(key):
    """Get English fallback message for when personality doesn't have custom message."""
    fallbacks = {
        "error_no_subscriptions": "📭 You have no active subscriptions",
        "error_no_categories": "📝 No categories available",
        "usage_subscribe": "📝 Usage: `!watcher subscribe <category> [feed_id|all]`\nNo feed_id: first feed | 'all': all feeds",
        "feed_id_not_found": "❌ Feed ID {feed_id} not found in category '{category}'",
        "feed_id_must_be_number": "❌ Feed ID must be a number",
        "error_category_not_found": "❌ Category '{category}' not found. Use `!watcher categories`",
        "subscription_successful_category": "✅ You have subscribed to all news from '{category}'",
        "subscription_successful_feed": "✅ You have subscribed to feed {feed_id} from category '{category}'",
        "error_subscription": "❌ Error creating flat subscription",
        "usage_unsubscribe": "📝 Usage: `!watcher unsubscribe <category> [feed_id]`",
        "subscription_cancelled_category": "✅ Subscription cancelled to category '{category}'",
        "subscription_cancelled_feed": "✅ Subscription cancelled to feed {feed_id} from '{category}'",
        "error_cancellation": "❌ Error canceling flat subscription",
        "error_general": "❌ Error: {error}",
        "error_no_feeds": "📭 No feeds configured",
        "status_title": "📊 Your Subscriptions",
        "keywords_title": "🔍 Your Keywords",
        "usage_general": "📝 Usage: `!watcher general <category> [feed_id|all]`\nNo feed_id: first feed | 'all': all feeds",
        "usage_keywords": "📝 Usage: `!watcher keywords \"word1,word2,word3\" [category] [feed_id|all]`",
        "usage_cancel_keywords": "📝 Usage: `!watcher keywords unsubscribe <category>`",
        "usage_mixed": "📝 Usage: `!watcher mixed <category>`",
        "usage_add_feed": "📝 Usage: `!watcher add_feed <name> <url> <category> [country] [language]`",
        "usage_channel_premises_add": "📝 Usage: `!watcherchannel premises add <premise>`",
        "usage_channel_premises_mod": "📝 Usage: `!watcherchannel premises mod <number> <premise>`",
        "usage_premises_add": "📝 Usage: `!watcher premises add \"premise text\"`",
        "usage_premises_mod": "📝 Usage: `!watcher premises mod <number> \"new premise\"`",
        "usage_premises_configure": "📝 Usage: `!watcher premises configure \"premise1,premise2,premise3\"`\nMaximum 7 premises, separated by commas.",
        "general_subscription_successful": "✅ Subscribed to general feeds from '{category}' with AI classification",
        "keywords_subscription_successful": "✅ Subscribed to keywords: '{keywords}'",
        "keywords_subscription_cancelled": "✅ Subscription cancelled: '{keywords}'",
        "mixed_subscription_successful": "✅ Subscribed to mixed coverage of '{category}' (specialized + general)",
        "mixed_subscription_partial": "✅ Subscribed to specialized coverage of '{category}'",
        "channel_keywords_subscription_successful": "✅ Channel subscribed to keywords: '{keywords}'",
        "critical_news_detected": "🚨 CRITICAL NEWS DETECTED! {title}",
        "normal_notification": "📡 New news: {title}",
        "feed_added_successful": "✅ Feed '{name}' added to category '{category}'",
        "error_permissions": "❌ Only administrators can perform this action",
        "error_no_general_feeds": "❌ No general feeds for '{category}'",
        "error_no_keywords": "📭 You have no keyword subscriptions",
        "error_no_channel_subscriptions": "📭 This channel has no active subscriptions",
        "must_provide_keywords": "❌ You must provide keywords",
        "error_subscribing_keywords": "❌ Error subscribing to keywords",
        "no_keyword_subscription": "❌ No keyword subscription found",
        "error_canceling_keywords": "❌ Error canceling keyword subscription",
        "error_mixed_subscription": "❌ Error creating mixed subscription",
        "error_subscribing_coverage": "❌ Error subscribing to coverage",
        "permissions_manage_channels": "❌ Only administrators can manage channels",
        "error_subscribing_channel_keywords": "❌ Error subscribing channel to keywords",
        "permissions_cancel_channel": "❌ Only administrators can cancel channel subscriptions",
        "no_subscription_to_cancel": "❌ No subscription found to cancel",
        "error_canceling_channel_subscription": "❌ Error canceling channel subscription",
        "no_active_channel_subscriptions": "📭 This channel has no active subscriptions",
        "error_getting_channel_status": "❌ Error getting channel status",
        "error_getting_keywords": "❌ Error getting keywords",
        "error_getting_status": "❌ Error getting status",
        "error_listing_channel_premises": "❌ Error listing channel premises",
        "error_listing_premises": "❌ Error listing your premises",
        "no_channel_premises": "📭 No premises configured for this channel.",
        "no_channel_premises_configured": "⚠️ This channel has no premises configured. Use `!watcherchannel premises add \"premise\"` before subscribing with AI.",
        "no_personal_premises": "📭 You have no custom premises. You will use global premises.\nUse `!watcher premises configure` to create your custom premises.",
        "must_provide_premise": "❌ You must provide the premise text.",
        "max_personal_premises": "❌ You can have maximum 7 custom premises.",
        "must_provide_one_premise": "❌ You must provide at least one premise.",
        "error_adding_premise": "❌ Error adding premise",
        "error_configuring_premises": "❌ Error configuring your premises",
        "help_sent_private": "📝 Help sent via private message",
        "only_admins_feeds": "❌ Only administrators can add feeds",
        "error_adding_feed": "❌ Error adding feed",
        "no_general_feeds": "❌ No general feeds for '{category}'. Use `!watcher feeds`",
        "error_subscribing_general": "❌ Error subscribing to general feeds",
        "error_processing_subscription": "❌ Error processing subscription",
        "error_canceling_subscription": "❌ Error canceling flat subscription",
        "error_canceling_ai_subscription": "❌ Error canceling AI subscription",
        "error_showing_status": "❌ Error showing subscription status",
        "error_showing_categories": "❌ Error showing categories",
        "error_adding_feed": "❌ Error adding feed",
        "usage_general_unsubscribe": "📝 Usage: `!watcher general unsubscribe <category> [feed_id]`",
        "already_have_flat_subscription": "ℹ️ You already have an active flat subscription. Use `!watcher unsubscribe <category>` first if you want to change.",
        "already_have_keywords_subscription": "ℹ️ You already have an active keywords subscription. Use `!watcher keywords unsubscribe <category>` first if you want to change.",
        "no_flat_subscription": "❌ You don't have an active flat subscription in that category/feed",
        "already_have_ai_subscription": "ℹ️ You already have an active AI subscription. Use `!watcher general unsubscribe <category>` first if you want to change.",
        "no_ai_subscription": "❌ You don't have an active AI subscription for that category/feed",
        "no_active_flat_subscription": "📝 You don't have an active flat subscription",
        "no_active_keyword_subscription": "📝 You don't have an active keywords subscription",
        "no_active_ai_subscription": "📝 You don't have an active AI subscription",
        "no_premises_configured": "⚠️ You have no premises configured. Use `!watcher premises add <premise>` before subscribing with AI.",
        "ai_subscription_successful_feed": "✅ AI subscription created: Feed {feed_id} in category '{category}'",
        "ai_subscription_successful_category": "🤖 **AI subscription** to '{category}' - I will analyze critical news using your premises",
        "error_creating_ai_subscription": "❌ Error creating AI subscription",
        "error_processing_ai_subscription": "❌ Error processing AI subscription",
        "subscription_keywords_global": "🔍 **Global keywords subscription** - Searching: '{keywords}'",
        "error_subscribing_keywords": "❌ Error subscribing to keywords",
        "usage_keywords_add": "📝 Usage: `!watcher keywords add <keyword>`",
        "keyword_added": "✅ Keyword '{keyword}' added. List: {keywords}",
        "keyword_added_list": "✅ Keyword '{keyword}' added. Current list: {keywords}",
        "error_adding_keyword": "❌ Error adding keyword",
        "keyword_added_success": "✅ Keyword '{keyword}' added. List: {keywords}",
        "keyword_added_list_success": "✅ Keyword '{keyword}' added. Current list: {keywords}",
        "error_adding_keyword_error": "❌ Error adding keyword",
        "channel_ai_subscription_successful_category": "🤖 **AI subscription** to '{category}' - I will analyze critical news using your premises",
        "channel_ai_subscription_successful_feed": "🤖 **AI subscription** to feed {feed_id} in '{category}' - I will analyze critical news using your premises"
    }
    
    return fallbacks.get(key, f"❌ Message not found: {key}")
