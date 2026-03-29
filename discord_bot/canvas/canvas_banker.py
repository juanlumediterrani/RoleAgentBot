"""Canvas Banker content builders."""

from discord_bot import discord_core_commands as core

logger = core.logger
_personality_answers = core._personality_answers
_personality_descriptions = core._personality_descriptions
_bot_display_name = core._bot_display_name
get_banker_db_instance = None  # Now using roles_db directly
get_server_key = core.get_server_key


def build_canvas_role_banker(agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str:
    """Build the unified Banker role view with wallet information."""
    from .content import _build_canvas_intro_block
    banker_messages = _personality_answers.get("banker_messages", {})
    banker_descriptions = _personality_descriptions.get("roles_view_messages", {}).get("banker", {})

    def _banker_text(key: str, fallback: str) -> str:
        value = banker_descriptions.get(key, banker_messages.get(key))
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback

    balance = 0
    user_name = "Unknown"
    server_name = "Unknown Server"
    history = []

    if guild is not None and get_banker_db_instance is not None:
        try:
            server_key = get_server_key(guild)
            server_id = str(guild.id)
            server_name = guild.name

            if author_id is not None:
                user_id = str(author_id)
                member = guild.get_member(author_id)
                user_name = member.display_name if member else "Unknown User"

                from roles.banker.banker_db import get_banker_roles_db_instance
                db_banker_roles = get_banker_roles_db_instance(server_key)
                db_banker_roles.create_wallet(user_id, user_name, server_id, server_name, 'user')

                try:
                    from roles.banker.banker_discord import _initialize_dice_game_account
                    _initialize_dice_game_account(user_id, user_name, server_id, server_key, server_name)
                except Exception:
                    pass

                balance = db_banker_roles.get_balance(user_id, server_id)
                # Get transaction history from the underlying roles database
                roles_db = get_roles_db_instance(server_key)
                history = roles_db.get_banker_transaction_history(user_id, server_id, limit=5)

                tae = db_banker_roles.get_tae(server_id)
        except Exception as error:
            logger.warning(f"Could not load banker state for Canvas: {error}")

    title = _banker_text("canvas_title", f"💰 {_bot_display_name} Treasury")
    content_parts = [
        _build_canvas_intro_block(
            title,
            _banker_text("canvas_description", "Check your gold balance and recent account activity."),
        ),
        "**Wallet status**",
        f":coin: {balance:,} gold coins",
        f":bank: {server_name}",
        f":bust_in_silhouette: {user_name}",
        "**Recent transactions**",
    ]

    if history:
        for transaction in history[:3]:
            transaction_type, amount, *_rest = transaction
            emoji = ":inbox_tray:" if amount > 0 else ":outbox_tray:"
            content_parts.append(f"{emoji} {amount:,} ({transaction_type})")
    else:
        content_parts.append("No transactions yet")

    return "\n".join(content_parts)


def build_canvas_role_banker_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Redirect all banker details to the unified main view."""
    return build_canvas_role_banker({}, admin_visible, guild, author_id)
