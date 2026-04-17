import os
import json
from agent_logging import get_logger

logger = get_logger('banker_messages')


#Default english message Fallback
def get_default_messages():
    """Default messages if no customization available."""
    return {
        "title": "💰 Gold Banker",
        "description": "Banker allows you to hold a wallet and make transactions between users and the bot.",
        "wallet_information": "Wallet information:",
        "balance":"Balance:",
        "coin":"🪙",
        "button": "💰 Banker",
        "account_holder": "👤 Account Holder",
        "server": "🏦 Bank",
        "recent_transactions_title": "Recent Transactions:",
        "no_transactions_yet": "Not recent transactions.",
        "donation_label": "Donate:",
        "donation_custom_label": "Custom Amount",
        "donation_custom_message": "Use the Canvas 'Custom Amount' option to donate a custom amount!",
        "dropdown":{
            "select_banker_action": "💰 Select action",
            "config_tae": "Configure TAE",
            "config_tae_description": "Adjust the daily amount",
            "config_tae_emoji": "💰",
            "config_bonus": "Configure  Bonus",
            "config_bonus_description": "Set the amount of bonus",
            "config_bonus_emoji": "🎁",
            "beggar_donate": "Beggar: Donate",
            "beggar_donate_description": "Make a donation for clan projects",
            "beggar_donate_emoji": "🙏",
            "beggar_on": "Beggar: On",
            "beggar_on_description": "Enable beggar system",
            "beggar_on_emoji": "✅",
            "beggar_off": "Beggar: Off",
            "beggar_off_description": "Disable beggar system",
            "beggar_off_emoji": "❌",
            "beggar_frequency": "Beggar: Frequency",
            "beggar_frequency_description": "Set request frequency",
            "beggar_frequency_emoji": "⏰",
            "beggar_force_minigame": "Beggar: Force Minigame",
            "beggar_force_minigame_description": "Force minigame execution",
            "beggar_force_minigame_emoji": "🎲",
        } 
    }

def _lookup(raw: dict, key: str):
    """Look up a key in the messages dict: root first, then inside 'dropdown'.
    Supports dot notation for nested keys (e.g., 'beggar.dropdown.beggar_donate')."""
    # Try direct lookup first
    value = raw.get(key)
    if value is not None:
        return value
    
    # Handle dot notation for nested keys
    if "." in key:
        keys = key.split(".")
        value = raw
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                value = None
                break
        if value is not None:
            return value
    
    # Fallback to dropdown section for simple keys
    value = raw.get("dropdown", {}).get(key)
    return value

def get_messages(server_db_path: str, key: str, **kwargs) -> str:
    """Get a banker message for the given key, loading from the server-specific path.

    Args:
        server_db_path: Relative path like 'databases/<id_server>/<personality>'
        key: Message key to retrieve (top-level or inside 'dropdown')
        **kwargs: Optional variables to format into the message

    Returns:
        The formatted message string.
    """
    message = None

    try:
        json_path = os.path.join(server_db_path, "descriptions", "banker.json")
        if os.path.isfile(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            message = _lookup(raw, key)
    except Exception as e:
        logger.error(f"❌ Could not load banker messages from '{server_db_path}': {e}")

    if message is None:
        message = _lookup(get_default_messages(), key)

    if not isinstance(message, str):
        message = "Warning-Deprecated"

    if kwargs:
        try:
            return message.format(**kwargs)
        except KeyError as e:
            logger.error(f"❌ Error formatting banker message '{key}': variable not found {e}")
        except Exception as e:
            logger.error(f"❌ Error formatting banker message '{key}': {e}")

    return message