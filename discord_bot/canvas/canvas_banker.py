"""Canvas Banker content builders."""

import asyncio
import discord

from discord_bot import discord_core_commands as core
from .state import _get_canvas_beggar_state

logger = core.logger
get_banker_db_instance = None  # Now using roles_db directly
get_server_key = core.get_server_key
is_admin = core.is_admin

# Import roles database for banker functionality
try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None

# Import agent engine for subrole task execution
try:
    from agent_engine import execute_subrole_internal_task
except ImportError:
    execute_subrole_internal_task = None

# Import banker messages
try:
    from roles.banker.banker_messages import get_messages
except ImportError:
    get_messages = None


def _get_server_db_path(guild) -> str:
    """Get the server-specific personality directory path for banker messages."""
    try:
        from discord_bot.db_init import get_server_personality_dir
        server_id = str(guild.id)
        return get_server_personality_dir(server_id)
    except Exception:
        return None


def build_canvas_role_banker(agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str:
    """Build the unified Banker role view with wallet information."""
    server_id = get_server_key(guild) if guild else None
    server_db_path = _get_server_db_path(guild) if guild else None

    from .content import _get_personality_descriptions
    banker_descriptions = _get_personality_descriptions(server_id).get("role_descriptions", {}).get("banker", {})

    _fallbacks = {
        "title": "🏦 Canvas - Banker",
        "description": "Manage your clan wallet and transactions.",
        "wallet_information": "**Wallet Information**",
        "balance": "💰 Balance:",
        "coin": "coin",
        "server": "🏛️ Server",
        "account_holder": "👤 Account",
        "recent_transactions_title": "**Recent Transactions**",
        "no_transactions_yet": "- No transactions yet",
    }

    def _banker_text(key: str) -> str:
        if get_messages and server_db_path:
            value = get_messages(server_db_path, key)
        else:
            value = banker_descriptions.get(key)
        return str(value).strip() if value else _fallbacks.get(key, key)

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

    content_parts = [
        
        _banker_text("title"),
        _banker_text("description"),
        "-" * 45,
        _banker_text("wallet_information"),
        f"{_banker_text('current_balance')} {balance} {_banker_text('coin')}",
        f"{_banker_text('server')}: {server_id}",
        f"{_banker_text('account_holder')}: {user_name}",
        _banker_text("recent_transactions_title"),
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
        content_parts.append(_banker_text("no_transactions_yet"))

    return "\n".join(content_parts)


def build_canvas_role_banker_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None, agent_config: dict | None = None) -> str | None:
    """Build banker detail views including beggar subrole."""
    from .content import _get_personality_descriptions
    server_id = get_server_key(guild) if guild else None
    personality_descriptions = _get_personality_descriptions(server_id)
    roles_messages = personality_descriptions.get("role_descriptions", {})
    banker_messages = roles_messages.get("banker", {})
    beggar_messages = banker_messages.get("beggar", {})

    def _banker_text(key: str, fallback: str) -> str:
        """Get text from banker messages with dot notation support."""
        if "." in key:
            keys = key.split(".")
            value = banker_messages
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    value = None
                    break
        else:
            value = banker_messages.get(key)
        return str(value).strip() if value else fallback

    # Handle beggar subrole views
    if detail_name in {"beggar"}:
        beggar_state = _get_canvas_beggar_state(guild)
        
        title = _banker_text("beggar.title", "🙏 BEGGAR")
        fund_title = _banker_text("beggar.current_fund", "💰 **CURRENT FUND:**")
        description = _banker_text("beggar.description", "Help support the clan with your generous donations! Every gold piece counts towards our collective goals.")
        title_reason = _banker_text("beggar.title_reason", "**Reason:**")
        title_campaing = _banker_text("beggar.title_campaign", "**Current Campaign**")
        title_instructions = _banker_text("beggar.title_instructions", "**How it works**")
        instructions = _banker_text("beggar.instructions", "💝 Click the 'Donate' button below\n - Wait the weekly result at end of the week.\n - If you give whatever donation, the beggar will memory that.\n ")
        title_donations = _banker_text("beggar.title_donations", "**Recent Donations**")
    
        parts = [
            title,
            description,
            "-" * 45,
            title_campaing,
            f"{title_reason} {beggar_state['last_reason'] or 'Support the clan'}",
            f"{fund_title} {beggar_state['fund_balance']:,} :coin:",
            "-" * 45,
            "",
            title_instructions,
            instructions,
            "-" * 45,
            "",
            title_donations,
        ]   
        
        # Add recent donation history if available
        if beggar_state.get('recent_donations'):
            for donation in beggar_state['recent_donations'][:5]:
                donor = donation.get('donor_name', 'Anonymous')
                amount = donation.get('amount', 0)
                reason = donation.get('reason', 'Support')
                parts.append(f" - 💰 {donor}: {amount:,} :coin: -->  {reason}")
        else:
            no_donations = beggar_messages.get("no_donations", "📊 No donations yet. Be the first to contribute!")
            parts.append(no_donations)
        
        return "\n".join(parts)

    if detail_name in {"beggar_admin"}:
        beggar_state = _get_canvas_beggar_state(guild)
        general = personality_descriptions.get("general", {})
        
        title = _banker_text("beggar.title", "🙏 BEGGAR")
        description = _banker_text("beggar.description", "Help support the clan with your generous donations! Every gold piece counts towards our collective goals.")
        
        return "\n".join([
            title,
            description,
            "-" * 45,
            general.get("current_settings", "**Current Settings**"),
            "-" * 45,
            f"{general.get('status_label', '**Status:**')} {general.get('active', '✅ Enabled') if beggar_state['enabled'] else general.get('inactive','❌ Disabled')}",
            f"{general.get('frequency_label', '**Frequency:**')} {general.get('every', 'every')} {beggar_state['frequency_hours']}h",
            f"{_banker_text('beggar.current_fund', '**Current Fund:**')} {beggar_state['fund_balance']:,} :coin:",
            f"{_banker_text('beggar.title_reason', '**Last Reason:**')} {beggar_state['last_reason'] or general.get('none','None')}",
        ])

    # Default: return main banker view
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


class BeggarDonationModal(discord.ui.Modal):
    """Modal for custom beggar donation amount."""

    def __init__(self, guild, author_id, view):
        super().__init__(title="Make a Donation")
        self.guild = guild
        self.author_id = author_id
        self.view = view

        self.amount_input = discord.ui.TextInput(
            label="Amount (gold)",
            placeholder="Enter amount to donate",
            required=True,
            max_length=10,
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value)
            if amount <= 0:
                await interaction.response.send_message(
                    "❌ Donation amount must be positive.", ephemeral=True
                )
                return

            # Import the BeggarDonationView from beggar_discord
            from roles.banker.subroles.beggar.beggar_discord import BeggarDonationView
            from roles.banker.subroles.beggar.beggar_db import get_beggar_config

            server_id = str(interaction.guild.id)
            beggar_config = get_beggar_config(server_id)
            current_reason = beggar_config.get_current_reason()

            # Create donation view and handle the donation
            donation_view = BeggarDonationView(current_reason, server_id)
            await donation_view._handle_donation(interaction, amount)

        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number.", ephemeral=True
            )
        except Exception as e:
            logger.exception(f"Beggar donation modal failed: {e}")
            await interaction.response.send_message(
                "❌ Failed to process donation.", ephemeral=True
            )


class BeggarFrequencyModal(discord.ui.Modal):
    """Modal for configuring beggar frequency."""

    def __init__(self, view):
        super().__init__(title="Configure Beggar Frequency")
        self.view = view
        self.frequency = discord.ui.TextInput(
            label="Frequency (hours)",
            placeholder="Enter frequency in hours (e.g., 24)",
            required=True,
            max_length=10,
        )
        self.add_item(self.frequency)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            frequency_hours = int(self.frequency.value)
            if frequency_hours < 1 or frequency_hours > 168:
                await interaction.response.send_message(
                    "❌ Frequency must be between 1 and 168 hours.", ephemeral=True
                )
                return

            from roles.banker.subroles.beggar.beggar_db import get_beggar_config
            from agent_roles_db import get_roles_db_instance as get_roles_config_db
            from .content import _build_canvas_role_detail_view, _build_canvas_role_embed
            from .ui import CanvasRoleDetailView

            server_key = get_server_key(interaction.guild)
            server_id = str(interaction.guild.id)
            beggar_config = get_beggar_config(server_id)
            roles_config_db = get_roles_config_db(server_key)

            # Update frequency in beggar config
            if beggar_config.set_frequency(frequency_hours):
                # Update roles_config database
                if roles_config_db:
                    roles_config_db.set_subrole_config("banker", "beggar", "frequency_hours", frequency_hours)
                applied_text = f"Beggar frequency set to {frequency_hours} hours."
            else:
                applied_text = "Failed to update beggar frequency."

            current_detail = "beggar_admin"
            content = _build_canvas_role_detail_view("banker", current_detail, self.view.agent_config, self.view.admin_visible, interaction.guild, self.view.author_id)
            if content is None:
                content = "Beggar admin configuration"

            detail_embed = _build_canvas_role_embed("banker", content, self.view.admin_visible, current_detail, None, applied_text, server_id=server_key)
            next_view = CanvasRoleDetailView(
                author_id=self.view.author_id,
                role_name="banker",
                agent_config=self.view.agent_config,
                admin_visible=self.view.admin_visible,
                sections=self.view.sections,
                current_detail=current_detail,
                guild=self.view.guild,
                previous_view=self.view,
            )
            next_view.auto_response_preview = applied_text
            next_view.message = interaction.message

            await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number.", ephemeral=True
            )
        except Exception as e:
            logger.exception(f"Beggar frequency modal failed: {e}")
            await interaction.response.send_message(
                "❌ Failed to update beggar frequency.", ephemeral=True
            )


async def handle_canvas_banker_action(interaction: discord.Interaction, action_name: str, view) -> None:
    """Handle banker role actions like balance, TAE, bonus display, and beggar subrole."""
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

        # Handle beggar subrole actions
        if action_name in {"beggar_on", "beggar_off", "beggar_frequency", "beggar_force_minigame"}:
            from roles.banker.subroles.beggar.beggar_db import get_beggar_config
            from agent_roles_db import get_roles_db_instance as get_roles_config_db

            beggar_config = get_beggar_config(server_id)
            roles_config_db = get_roles_config_db(server_key)

            if action_name in {"beggar_on", "beggar_off"}:
                enabled = action_name == "beggar_on"
                if beggar_config.set_enabled(enabled):
                    # Update roles_config database - beggar is stored as its own role entry
                    if roles_config_db:
                        server_id = str(interaction.guild.id) if interaction.guild else "0"
                        roles_config_db.set_role_enabled("beggar", server_id, enabled)
                    # If enabling, execute task immediately and schedule next run
                    if enabled and execute_subrole_internal_task:
                        try:
                            logger.info(f"🎭 [CANVAS] Executing beggar task immediately after enable for server {server_key}")
                            # Execute task asynchronously with actual bot instance
                            asyncio.create_task(execute_subrole_internal_task("beggar", {}, bot_instance=interaction.client, server_id=server_key))
                            applied_text = f"Beggar enabled for this server. Task executed and next run scheduled."
                        except Exception as e:
                            logger.error(f"Failed to execute beggar task on enable: {e}")
                            applied_text = f"Beggar enabled but failed to execute initial task: {e}"
                    else:
                        applied_text = f"Beggar {'enabled' if enabled else 'disabled'} for this server."
                    current_detail = "beggar_admin"
                else:
                    current_detail = "beggar_admin"
                    applied_text = f"Failed to update beggar status."
            elif action_name == "beggar_frequency":
                # Show modal for frequency input
                from .ui import CanvasRoleDetailView
                modal = BeggarFrequencyModal(view)
                await interaction.response.send_modal(modal)
                return
            elif action_name == "beggar_force_minigame":
                # Force minigame execution
                from roles.banker.subroles.beggar.beggar_minigame import BeggarMinigame
                minigame = BeggarMinigame(server_id)
                result = await minigame.force_run_minigame(interaction.guild)
                current_detail = "beggar_admin"
                applied_text = f"🎲 Minigame forced: {result}"

            # Rebuild view for beggar admin
            from .content import _build_canvas_role_detail_view, _build_canvas_role_embed
            from .ui import CanvasRoleDetailView

            content = _build_canvas_role_detail_view("banker", current_detail, view.agent_config, view.admin_visible, interaction.guild, view.author_id)
            if content is None:
                content = "Beggar admin configuration"

            detail_embed = _build_canvas_role_embed("banker", content, view.admin_visible, current_detail, None, applied_text, server_id=server_key)
            next_view = CanvasRoleDetailView(
                author_id=view.author_id,
                role_name="banker",
                agent_config=view.agent_config,
                admin_visible=view.admin_visible,
                sections=view.sections,
                current_detail=current_detail,
                guild=view.guild,
                previous_view=view,
            )
            next_view.auto_response_preview = applied_text
            next_view.message = interaction.message

            await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)
            return

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

        role_embed = _build_canvas_role_embed("banker", content, view.admin_visible, "overview", None, "")
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

        try:
            await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)
        except discord.InteractionResponded:
            await interaction.followup.edit_message(interaction.message.id, embed=role_embed, view=next_view)
        except discord.NotFound:
            await interaction.followup.send(embed=role_embed, view=next_view, ephemeral=True)
    except Exception as e:
        logger.exception(f"Canvas banker action failed: {e}")
        await interaction.response.send_message("❌ Failed to process banker action.", ephemeral=True)
