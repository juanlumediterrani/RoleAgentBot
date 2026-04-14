import os
import json
from agent_logging import get_logger

logger = get_logger('banker_messages')

def get_banker_messages():
    """Load custom Banker messages from personality file."""
    return get_default_messages()

def get_default_messages():
    """Default messages if no customization available."""
    return {
        "balance_title": "💰 Gold Balance",
        "balance_description": "Your gold balance status",
        "current_balance": "💎 Current Gold",
        "account_holder": "👤 Account Holder",
        "bank": "🏦 Bank",
        "new_account": "🎉 New Account! You received {bonus} free coins!",
        "recent_transactions": "📊 Recent Transactions",
        "daily_allowance_config_title": "🏦 Daily Gold Configuration",
        "daily_allowance_description": "Daily gold distribution settings",
        "current_daily_gold": "💰 Current Daily Gold",
        "last_distribution": "📅 Last Distribution",
        "daily_gold_not_configured": "⚠️ Daily gold not configured!",
        "daily_gold_info": "ℹ️ Info: Each user receives {tae} coins daily",
        "daily_gold_footer": "💼 Use !banker tae <amount> to configure",
        "daily_gold_configured": "✅ Daily Gold Configured",
        "daily_gold_updated": "Daily gold updated successfully",
        "new_daily_gold": "💰 New Daily Gold",
        "administrator": "👤 Administrator",
        "server": "🏦 Server",
        "next_distribution": "ℹ️ Next Distribution: Daily",
        "account_bonus_title": "🎁 New Account Bonus",
        "account_bonus_description": "Bonus for new accounts",
        "current_bonus": "💰 Current Bonus",
        "account_bonus_info": "ℹ️ Info: New accounts receive {bonus} coins",
        "account_bonus_footer": "💼 Use !banker bonus <amount> to configure",
        "account_bonus_configured": "✅ Account Bonus Configured",
        "account_bonus_updated": "Account bonus updated successfully",
        "new_account_bonus": "💰 New Account Bonus",
        "application": "ℹ️ New accounts will receive this bonus",
        "help_title": "💰 Banker - Help",
        "help_description": "Commands to manage server economy",
        "view_balance": "💎 View Balance",
        "view_balance_desc": "`!banker balance`\nShows your current gold balance and recent transactions.\nNew accounts receive opening bonus automatically.",
        "configure_daily_gold": "🏦 Configure Daily Gold (Admins)",
        "configure_daily_gold_desc": "`!banker tae <amount>`\nSet daily gold for all users (0-1000 coins).\n`!banker tae` - View current settings.",
        "configure_account_bonus": "🎁 Configure Account Bonus (Admins)",
        "configure_account_bonus_desc": "`!banker bonus <amount>`\nSet bonus for new accounts (0-10000 coins).\n`!banker bonus` - View current bonus.",
        "information": "ℹ️ Information",
        "information_desc": "• Daily gold distributed to all accounts.\n• New accounts receive opening bonus.\n• All transactions are recorded.\n• Only administrators can configure economy settings.",
        "help_footer": "💼 Banker - Economic Management",
        "error_admin_daily_gold": "❌ Only administrators can configure daily gold!",
        "error_admin_account_bonus": "❌ Only administrators can configure account bonus!",
        "error_daily_gold_range": "❌ Daily gold must be between 0 and 1000 coins!",
        "error_account_bonus_range": "❌ Account bonus must be between 0 and 10000 coins!",
        "error_invalid_amount": "❌ Invalid amount! Use an integer number!",
        "error_configuring_daily_gold": "❌ Error configuring daily gold!",
        "error_configuring_account_bonus": "❌ Error configuring account bonus!",
        "error_banker_database": "❌ Error accessing banker database!",
        "command_not_recognized": "❌ Subcommand '{subcommand}' not recognized! Use `!banker help` to see help.",
        "help_sent": "📩 Banker help sent by private message.",
        "balance_sent": "💰 Your balance information sent by private message.",
        "banker_help": "💰 **Banker** - `!banker balance` | `!banker tae <amount>` (admins) | `!banker help` for complete help",
        "error_banker_db": "❌ Banker database not available."
    }

def get_message(key, **kwargs):
    """Get a custom message with variable formatting."""
    messages = get_banker_messages()
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
        "balance_title": "💰 Gold Balance",
        "balance_description": "Your gold balance status",
        "current_balance": "💎 Current Gold",
        "account_holder": "👤 Account Holder",
        "bank": "🏦 Bank",
        "new_account": "🎉 New Account! You received {bonus} free coins!",
        "recent_transactions": "📊 Recent Transactions",
        "daily_allowance_config_title": "🏦 Daily Gold Configuration",
        "daily_allowance_description": "Daily gold distribution settings",
        "current_daily_gold": "💰 Current Daily Gold",
        "last_distribution": "📅 Last Distribution",
        "daily_gold_not_configured": "⚠️ Daily gold not configured!",
        "daily_gold_info": "ℹ️ Info: Each user receives {tae} coins daily",
        "daily_gold_footer": "💼 Use !banker tae <amount> to configure",
        "daily_gold_configured": "✅ Daily Gold Configured",
        "daily_gold_updated": "Daily gold updated successfully",
        "new_daily_gold": "💰 New Daily Gold",
        "administrator": "👤 Administrator",
        "server": "🏦 Server",
        "next_distribution": "ℹ️ Next Distribution: Daily",
        "account_bonus_title": "🎁 New Account Bonus",
        "account_bonus_description": "Bonus for new accounts",
        "current_bonus": "💰 Current Bonus",
        "account_bonus_info": "ℹ️ Info: New accounts receive {bonus} coins",
        "account_bonus_footer": "💼 Use !banker bonus <amount> to configure",
        "account_bonus_configured": "✅ Account Bonus Configured",
        "account_bonus_updated": "Account bonus updated successfully",
        "new_account_bonus": "💰 New Account Bonus",
        "application": "ℹ️ New accounts will receive this bonus",
        "help_title": "💰 Banker - Help",
        "help_description": "Commands to manage server economy",
        "view_balance": "💎 View Balance",
        "view_balance_desc": "`!banker balance`\nShows your current gold balance and recent transactions.\nNew accounts receive opening bonus automatically.",
        "configure_daily_gold": "🏦 Configure Daily Gold (Admins)",
        "configure_daily_gold_desc": "`!banker tae <amount>`\nSet daily gold for all users (0-1000 coins).\n`!banker tae` - View current settings.",
        "configure_account_bonus": "🎁 Configure Account Bonus (Admins)",
        "configure_account_bonus_desc": "`!banker bonus <amount>`\nSet bonus for new accounts (0-10000 coins).\n`!banker bonus` - View current bonus.",
        "information": "ℹ️ Information",
        "information_desc": "• Daily gold distributed to all accounts.\n• New accounts receive opening bonus.\n• All transactions are recorded.\n• Only administrators can configure economy settings.",
        "help_footer": "💼 Banker - Economic Management",
        "error_admin_daily_gold": "❌ Only administrators can configure daily gold!",
        "error_admin_account_bonus": "❌ Only administrators can configure account bonus!",
        "error_daily_gold_range": "❌ Daily gold must be between 0 and 1000 coins!",
        "error_account_bonus_range": "❌ Account bonus must be between 0 and 10000 coins!",
        "error_invalid_amount": "❌ Invalid amount! Use an integer number!",
        "error_configuring_daily_gold": "❌ Error configuring daily gold!",
        "error_configuring_account_bonus": "❌ Error configuring account bonus!",
        "error_banker_database": "❌ Error accessing banker database!",
        "command_not_recognized": "❌ Subcommand '{subcommand}' not recognized! Use `!banker help` to see help.",
        "help_sent": "📩 Banker help sent by private message.",
        "balance_sent": "💰 Your balance information sent by private message.",
        "banker_help": "💰 **Banker** - `!banker balance` | `!banker tae <amount>` (admins) | `!banker help` for complete help",
        "error_banker_db": "❌ Banker database not available."
    }
    
    return fallbacks.get(key, f"❌ Message not found: {key}")
