import os
import json
from agent_logging import get_logger

logger = get_logger('banker_messages')

def get_banker_messages():
    """Load custom Banker messages from personality file."""
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
            banker_messages = json.load(f).get("discord", {}).get("banker_messages", {})
        
        if not banker_messages:
            logger.warning("⚠️ No custom banker messages found in personality")
            return get_default_messages()
        
        logger.info("💰 Custom banker messages loaded from personality")
        return banker_messages
        
    except Exception as e:
        logger.error(f"❌ Error loading banker messages: {e}")
        return get_default_messages()

def get_default_messages():
    """Default messages if no customization available."""
    return {
        "balance_title": "💰 Gold Balance",
        "saldo_description": "Your gold balance status",
        "saldo_actual": "💎 Current Gold",
        "titular": "👤 Account Holder",
        "banco": "🏦 Bank",
        "nueva_cuenta": "🎉 New Account! You received {bonus} free coins!",
        "transacciones_recientes": "📊 Recent Transactions",
        "daily_allowance_config_title": "🏦 Daily Gold Configuration",
        "tae_description": "Daily gold distribution settings",
        "tae_actual": "💰 Current Daily Gold",
        "ultima_distribucion": "📅 Last Distribution",
        "tae_no_configurada": "⚠️ Daily gold not configured!",
        "tae_info": "ℹ️ Info: Each user receives {tae} coins daily",
        "tae_footer": "💼 Use !banker tae <amount> to configure",
        "tae_configurada": "✅ Daily Gold Configured",
        "tae_actualizada": "Daily gold updated successfully",
        "nueva_tae": "💰 New Daily Gold",
        "administrador": "👤 Administrator",
        "servidor": "🏦 Server",
        "proxima_distribucion": "ℹ️ Next Distribution: Daily",
        "bonus_config_title": "🎁 New Account Bonus",
        "bono_description": "Bonus for new accounts",
        "bono_actual": "💰 Current Bonus",
        "bono_info": "ℹ️ Info: New accounts receive {bonus} coins",
        "bono_footer": "💼 Use !banker bonus <amount> to configure",
        "bono_configurado": "✅ Account Bonus Configured",
        "bono_actualizado": "Account bonus updated successfully",
        "nuevo_bono": "💰 New Account Bonus",
        "aplicacion": "ℹ️ New accounts will receive this bonus",
        "help_title": "💰 Banker - Help",
        "help_description": "Commands to manage server economy",
        "ver_saldo": "💎 View Balance",
        "ver_saldo_desc": "`!banker balance`\nShows your current gold balance and recent transactions.\nNew accounts receive opening bonus automatically.",
        "configurar_tae": "🏦 Configure Daily Gold (Admins)",
        "configurar_tae_desc": "`!banker tae <amount>`\nSet daily gold for all users (0-1000 coins).\n`!banker tae` - View current settings.",
        "configurar_bono": "🎁 Configure Account Bonus (Admins)",
        "configurar_bono_desc": "`!banker bonus <amount>`\nSet bonus for new accounts (0-10000 coins).\n`!banker bonus` - View current bonus.",
        "informacion": "ℹ️ Information",
        "informacion_desc": "• Daily gold distributed to all accounts.\n• New accounts receive opening bonus.\n• All transactions are recorded.\n• Only administrators can configure economy settings.",
        "help_footer": "💼 Banker - Economic Management",
        "error_no_admin_tae": "❌ Only administrators can configure daily gold!",
        "error_no_admin_bono": "❌ Only administrators can configure account bonus!",
        "error_tae_rango": "❌ Daily gold must be between 0 and 1000 coins!",
        "error_bono_rango": "❌ Account bonus must be between 0 and 10000 coins!",
        "error_numero_invalido": "❌ Invalid amount! Use an integer number!",
        "error_configurar_tae": "❌ Error configuring daily gold!",
        "error_configurar_bono": "❌ Error configuring account bonus!",
        "error_bd_banquero": "❌ Error accessing banker database!",
        "comando_no_reconocido": "❌ Subcommand '{subcommand}' not recognized! Use `!banker help` to see help.",
        "help_enviada": "📩 Banker help sent by private message.",
        "saldo_enviado": "💰 Your balance information sent by private message.",
        "banquero_help": "💰 **Banker** - `!banker balance` | `!banker tae <amount>` (admins) | `!banker help` for complete help",
        "error_banker_db": "❌ Banker database not available.",
        "help_sent": "📩 Banker help sent by private message.",
        "balance_sent": "💰 Your wallet information sent by private message.",
        "command_not_recognized": "❌ Subcommand '{subcommand}' not recognized! Use `!banker help` to see help.",
        "error_no_admin_tae": "❌ Only administrators can configure TAE!",
        "error_no_admin_bonus": "❌ Only administrators can configure opening bonus!",
        "error_tae_range": "❌ TAE must be between 0 and 1000 daily coins!",
        "error_bonus_range": "❌ Opening bonus must be between 0 and 10000 coins!",
        "error_invalid_number": "❌ Invalid amount! Use an integer number!",
        "error_configuring_tae": "❌ Error configuring TAE!",
        "error_configuring_bonus": "❌ Error configuring opening bonus!",
        "help_title": "💰 Banker - Help",
        "help_description": "Available commands to manage server economy",
        "view_balance": "💎 View Balance",
        "view_balance_desc": "`!banker balance`\nShows your current gold balance and recent transactions.\nNew accounts receive opening bonus automatically.",
        "configure_tae": "🏦 Configure TAE (Admins)",
        "configure_tae_desc": "`!banker tae <amount>`\nSet daily gold for all users (0-1000 coins).\n`!banker tae` - View current settings.",
        "configure_bonus": "🎁 Configure Bonus (Admins)",
        "configure_bonus_desc": "`!banker bonus <amount>`\nSet bonus for new accounts (0-10000 coins).\n`!banker bonus` - View current bonus.",
        "tae_info": "ℹ️ Info: Each user will receive {tae:,} coins daily",
        "tae_footer": "💼 Use !banker tae <amount> to configure",
        "next_distribution": "ℹ️ Next Distribution",
        "bonus_info": "ℹ️ Info: Each new account will receive {bonus:,} coins automatically",
        "bonus_footer": "💼 Use !banker bonus <amount> to configure",
        "server": "🏦 Server",
        "application": "ℹ️ Application",
        "help_footer": "💼 Banker - Economic Management"
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
        "saldo_description": "Your gold balance status",
        "saldo_actual": "💎 Current Gold",
        "titular": "👤 Account Holder",
        "banco": "🏦 Bank",
        "nueva_cuenta": "🎉 New Account! You received {bonus} free coins!",
        "transacciones_recientes": "📊 Recent Transactions",
        "daily_allowance_config_title": "🏦 Daily Gold Configuration",
        "tae_description": "Daily gold distribution settings",
        "tae_actual": "💰 Current Daily Gold",
        "ultima_distribucion": "📅 Last Distribution",
        "tae_no_configurada": "⚠️ Daily gold not configured!",
        "tae_info": "ℹ️ Info: Each user receives {tae} coins daily",
        "tae_footer": "💼 Use !banker tae <amount> to configure",
        "tae_configurada": "✅ Daily Gold Configured",
        "tae_actualizada": "Daily gold updated successfully",
        "nueva_tae": "💰 New Daily Gold",
        "administrador": "👤 Administrator",
        "servidor": "🏦 Server",
        "proxima_distribucion": "ℹ️ Next Distribution: Daily",
        "bonus_config_title": "🎁 New Account Bonus",
        "bono_description": "Bonus for new accounts",
        "bono_actual": "💰 Current Bonus",
        "bono_info": "ℹ️ Info: New accounts receive {bonus} coins",
        "bono_footer": "💼 Use !banker bonus <amount> to configure",
        "bono_configurado": "✅ Account Bonus Configured",
        "bono_actualizado": "Account bonus updated successfully",
        "nuevo_bono": "💰 New Account Bonus",
        "aplicacion": "ℹ️ New accounts will receive this bonus",
        "help_title": "💰 Banker - Help",
        "help_description": "Commands to manage server economy",
        "ver_saldo": "💎 View Balance",
        "ver_saldo_desc": "`!banker balance`\nShows your current gold balance and recent transactions.\nNew accounts receive opening bonus automatically.",
        "configurar_tae": "🏦 Configure Daily Gold (Admins)",
        "configurar_tae_desc": "`!banker tae <amount>`\nSet daily gold for all users (0-1000 coins).\n`!banker tae` - View current settings.",
        "configurar_bono": "🎁 Configure Account Bonus (Admins)",
        "configurar_bono_desc": "`!banker bonus <amount>`\nSet bonus for new accounts (0-10000 coins).\n`!banker bonus` - View current bonus.",
        "informacion": "ℹ️ Information",
        "informacion_desc": "• Daily gold distributed to all accounts.\n• New accounts receive opening bonus.\n• All transactions are recorded.\n• Only administrators can configure economy settings.",
        "help_footer": "💼 Banker - Economic Management",
        "error_no_admin_tae": "❌ Only administrators can configure daily gold!",
        "error_no_admin_bono": "❌ Only administrators can configure account bonus!",
        "error_tae_rango": "❌ Daily gold must be between 0 and 1000 coins!",
        "error_bono_rango": "❌ Account bonus must be between 0 and 10000 coins!",
        "error_numero_invalido": "❌ Invalid amount! Use an integer number!",
        "error_configurar_tae": "❌ Error configuring daily gold!",
        "error_configurar_bono": "❌ Error configuring account bonus!",
        "error_bd_banquero": "❌ Error accessing banker database!",
        "comando_no_reconocido": "❌ Subcommand '{subcommand}' not recognized! Use `!banker help` to see help.",
        "help_enviada": "📩 Banker help sent by private message.",
        "saldo_enviado": "💰 Your balance information sent by private message.",
        "banquero_help": "💰 **Banker** - `!banker balance` | `!banker tae <amount>` (admins) | `!banker help` for complete help",
        "error_banker_db": "❌ Banker database not available.",
        "help_sent": "📩 Banker help sent by private message.",
        "balance_sent": "💰 Your wallet information sent by private message.",
        "command_not_recognized": "❌ Subcommand '{subcommand}' not recognized! Use `!banker help` to see help.",
        "view_balance": "💎 View Balance",
        "view_balance_desc": "`!banker balance`\nShows your current gold balance and recent transactions.\nNew accounts receive opening bonus automatically.",
        "configure_tae": "🏦 Configure TAE (Admins)",
        "configure_tae_desc": "`!banker tae <amount>`\nSet daily gold for all users (0-1000 coins).\n`!banker tae` - View current settings.",
        "configure_bonus": "🎁 Configure Bonus (Admins)",
        "configure_bonus_desc": "`!banker bonus <amount>`\nSet bonus for new accounts (0-10000 coins).\n`!banker bonus` - View current bonus.",
        "tae_info": "ℹ️ Info: Each user will receive {tae:,} coins daily",
        "next_distribution": "ℹ️ Next Distribution",
        "bonus_info": "ℹ️ Info: Each new account will receive {bonus:,} coins automatically",
        "server": "🏦 Server",
        "application": "ℹ️ Application",
        "help_footer": "💼 Banker - Economic Management"
    }
    
    return fallbacks.get(key, f"❌ Message not found: {key}")
