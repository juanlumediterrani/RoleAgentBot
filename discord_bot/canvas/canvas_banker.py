"""Canvas Banker content builders."""

import discord

from discord_bot import discord_core_commands as core

logger = core.logger
_personality_answers = core._personality_answers
_personality_descriptions = core._personality_descriptions
_bot_display_name = core._bot_display_name
get_banker_db_instance = None  # Now using roles_db directly
get_server_key = core.get_server_key
is_admin = core.is_admin

# Import roles database for banker functionality
try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None


def build_canvas_role_banker(agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str:
    """Build the unified Banker role view with wallet information."""
    from .content import _build_canvas_intro_block
    banker_messages = _personality_answers.get("banker_messages", {})
    banker_descriptions = _personality_descriptions.get("roles_view_messages", {}).get("banker", {})

    def _banker_text(key: str, fallback: str) -> str:
        value = banker_descriptions.get(key, banker_messages.get(key))
        if value:
            value = str(value).replace("{_bot_display_name}", _bot_display_name)
        return str(value).strip() if value else fallback

    balance = 0
    user_name = "Unknown"
    server_id = "Unknown Server"
    history = []

    if guild is not None and get_roles_db_instance is not None:
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
                db_banker_roles.create_wallet(user_id, user_name, 'user')

                try:
                    from roles.banker.banker_discord import _initialize_dice_game_account
                    _initialize_dice_game_account(user_id, user_name, server_id, server_key)
                except Exception:
                    pass

                balance = db_banker_roles.get_balance(user_id)
                # Get transaction history from the banker database
                history = db_banker_roles.roles_db.get_banker_transactions(user_id, limit=5)

                tae = db_banker_roles.get_tae(server_id)
        except Exception as error:
            logger.warning(f"Could not load banker state for Canvas: {error}")

    title = _banker_text("canvas_title", f"💰 {_bot_display_name} Treasury")
    content_parts = [
        _build_canvas_intro_block(
            title,
            _banker_text("canvas_description", "Check your gold balance and recent account activity."),
        ),
        _banker_text("wallet_status_title", "**Wallet status**"),
        f":coin: {_banker_text('gold_coins', '{amount} monedas de oro').replace('{amount}', f'{balance:,}')}",
        f":bank: {_banker_text('server_label', 'Server')}: {server_id}",
        f":bust_in_silhouette: {_banker_text('user_label', 'User')}: {user_name}",
        _banker_text("recent_transactions_title", "**Recent transactions**"),
    ]

    if history:
        for transaction in history[:3]:
            # transaction is a dictionary, not a tuple
            transaction_type = transaction.get('transaction_type', 'Unknown')
            amount = transaction.get('amount', 0)
            try:
                amount_int = int(amount)
                emoji = ":inbox_tray:" if amount_int > 0 else ":outbox_tray:"
            except (ValueError, TypeError):
                emoji = ":question:"  # Default emoji for invalid amounts
            content_parts.append(f"{emoji} {amount_int:,} ({transaction_type})")
    else:
        content_parts.append(_banker_text("no_transactions_yet", "No transactions yet"))

    return "\n".join(content_parts)


def build_canvas_role_banker_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Redirect all banker details to the unified main view."""
    return build_canvas_role_banker({}, admin_visible, guild, author_id)


class BankerConfigModal(discord.ui.Modal):
    def __init__(self, action_name: str):
        title = "Banker TAE" if action_name == "config_tae" else "Banker Bonus"
        super().__init__(title=title)
        self.action_name = action_name
        label = "TAE value" if action_name == "config_tae" else "Bonus value"
        placeholder = "0-1000" if action_name == "config_tae" else "0-10000"
        self.value_input = discord.ui.TextInput(label=label, placeholder=placeholder, required=True, max_length=10)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Banker config is only available in a server.", ephemeral=True)
            return
        if not is_admin(interaction):
            await interaction.response.send_message("❌ This banker option is admin-only.", ephemeral=True)
            return
        if get_roles_db_instance is None:
            await interaction.response.send_message("❌ Banker database is not available.", ephemeral=True)
            return
        try:
            amount = int(str(self.value_input.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number.", ephemeral=True)
            return

        if self.action_name == "config_tae":
            if amount < 0 or amount > 1000:
                await interaction.response.send_message("❌ TAE must be between 0 and 1000.", ephemeral=True)
                return
        else:
            if amount < 0 or amount > 10000:
                await interaction.response.send_message("❌ Bonus must be between 0 and 10000.", ephemeral=True)
                return

        try:
            db_banker = get_roles_db_instance(str(interaction.guild.id))
            if self.action_name == "config_tae":
                ok = db_banker.set_tae(str(interaction.guild.id), amount)
                label = "TAE"
            else:
                ok = db_banker.set_tae(str(interaction.guild.id), amount)
                label = "TAE (affects bonus)"
        except Exception as e:
            logger.exception(f"Canvas banker config failed: {e}")
            await interaction.response.send_message("❌ Could not update banker configuration.", ephemeral=True)
            return

        if not ok:
            await interaction.response.send_message("❌ Could not update banker configuration.", ephemeral=True)
            return

        try:
            current_tae = db_banker.get_tae(str(interaction.guild.id))
            current_bonus = current_tae * 10
        except Exception:
            current_tae = amount if label == "TAE" else "Unknown"
            current_bonus = amount if "bonus" in label.lower() else "Unknown"

        await interaction.response.send_message(
            f"✅ {label} updated to `{amount}`.\nCurrent config: TAE {current_tae}% | opening bonus {current_bonus}",
            ephemeral=True,
        )


async def handle_canvas_banker_action(interaction: discord.Interaction, action_name: str, view) -> None:
    """Handle banker role actions like balance, TAE, and bonus display."""
    if get_roles_db_instance is None:
        await interaction.response.send_message("❌ Banker systems are not available.", ephemeral=True)
        return

    try:
        server_key = get_server_key(interaction.guild)
        db_banker = get_roles_db_instance(server_key)
        server_id = str(interaction.guild.id)
        server_name = interaction.guild.name
        user_id = str(view.author_id)

        user_name = interaction.user.display_name
        content_parts = [f"🏦 **BANKER - {action_name.upper()}** 🏦", ""]

        if action_name == "balance":
            wallet = db_banker.get_banker_wallet(user_id)
            balance = wallet.get("balance", 0) if wallet else 0
            content_parts.extend([
                f"💰 **Your Balance:** {balance:,} :coin:",
                f"👤 **Account:** {user_name}",
                f"🏛️ **Server:** {server_id}",
            ])
        elif action_name == "tae":
            try:
                from agent_db import get_tae_config
                tae_config = get_tae_config(server_id)
                tae_rate = tae_config.get("rate", 1.0)
                tae_enabled = tae_config.get("enabled", False)
                content_parts.extend([
                    "📊 **TAE Configuration**",
                    f"📈 **Rate:** {tae_rate:.2%}",
                    f"🔧 **Status:** {'✅ Enabled' if tae_enabled else '❌ Disabled'}",
                    f"🏛️ **Server:** {server_id}",
                ])
            except Exception:
                content_parts.extend([
                    "📊 **TAE Configuration**",
                    "❌ **Error:** Could not load TAE configuration",
                ])
        elif action_name == "bonus":
            try:
                from agent_db import get_bonus_config
                bonus_config = get_bonus_config(server_id)
                bonus_rate = bonus_config.get("rate", 10)
                bonus_enabled = bonus_config.get("enabled", False)
                content_parts.extend([
                    "🎁 **Bonus Configuration**",
                    f"💎 **Rate:** {bonus_rate}%",
                    f"🔧 **Status:** {'✅ Enabled' if bonus_enabled else '❌ Disabled'}",
                    f"🏛️ **Server:** {server_id}",
                ])
            except Exception:
                content_parts.extend([
                    "🎁 **Bonus Configuration**",
                    "❌ **Error:** Could not load bonus configuration",
                ])
        else:
            await interaction.response.send_message("❌ Unknown banker action.", ephemeral=True)
            return

        content = "\n".join(content_parts)

        from .content import _build_canvas_role_embed
        from discord_bot.canvas.ui import CanvasRoleDetailView

        role_embed = _build_canvas_role_embed("banker", content, view.admin_visible, "overview", None, f"Viewed {action_name.title()}")
        view.current_embed = role_embed

        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail="overview",
            guild=view.guild,
            previous_view=view,
        )
        next_view.auto_response_preview = f"Viewed {action_name.title()}"

        try:
            await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)
        except discord.InteractionResponded:
            await interaction.followup.edit_message(interaction.message.id, embed=role_embed, view=next_view)
        except discord.NotFound:
            await interaction.followup.send(embed=role_embed, view=next_view, ephemeral=True)
    except Exception as e:
        logger.exception(f"Canvas banker action failed: {e}")
        await interaction.response.send_message("❌ Failed to process banker action.", ephemeral=True)
