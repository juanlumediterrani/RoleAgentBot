"""Canvas Treasure Hunter content builders and UI handlers."""

import discord
from datetime import datetime

from discord_bot import discord_core_commands as core
from .state import _get_canvas_poe2_state
from .canvas_base import CanvasModal

_personality_answers = core._personality_answers


AGENT_CFG = core.AGENT_CFG
logger = core.logger
is_admin = core.is_admin

try:
    from roles.treasure_hunter.poe2.poe2_subrole_manager import get_poe2_manager
except Exception:
    get_poe2_manager = None


async def _handle_canvas_followup_edit(interaction, embed, view, error_context=""):
    """Handle common pattern of editing message with error handling."""
    try:
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
    except discord.NotFound:
        try:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except discord.NotFound:
            logger.warning(f"Canvas treasure hunter interaction expired completely - unable to send followup {error_context}")
        except Exception as e:
            logger.exception(f"Failed to send canvas treasure hunter followup {error_context}: {e}")
    except Exception as e:
        logger.exception(f"Failed to edit canvas treasure hunter message {error_context}: {e}")
        try:
            await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
        except discord.NotFound:
            logger.warning(f"Canvas treasure hunter interaction expired during error handling {error_context}")
        except Exception as followup_e:
            logger.exception(f"Failed to send error followup {error_context}: {followup_e}")


def _get_treasure_text_factory(guild=None):
    """Get treasure text factory with common initialization."""
    from .content import _get_personality_descriptions
    server_id = core.get_server_key(guild) if guild else None
    personality_descriptions = _get_personality_descriptions(server_id)
    treasure_messages = _personality_answers.get("treasure_hunter_messages", {})
    treasure_descriptions = personality_descriptions.get("role_descriptions", {}).get("treasure_hunter", {})
    return _treasure_text_factory(treasure_messages, treasure_descriptions)


class Poe2PurchaseAddModal(discord.ui.Modal):
    def __init__(self, author_id: int, guild, view, item_name: str = None, current_price: float = None):
        logger.info(f"Poe2PurchaseAddModal __init__: item_name={item_name}, current_price={current_price}")
        super().__init__(title="Record Purchase", custom_id="poe2_purchase_add_modal")
        self.guild = guild
        self.view = view
        self.item_name = item_name
        self.current_price = current_price
        self.author_id = author_id

        try:
            # Get translations
            translations = self._get_translations()
            title_text = translations.get("modal_purchase_title", "Record Purchase")
            label_text = translations.get("modal_purchase_label", "Purchase Price")

            self.title = title_text

            # Price input with placeholder showing current price (if available)
            price_placeholder = "Purchase price (e.g., 100.50)"
            if current_price is not None:
                price_placeholder = f"Current price: {current_price:.2f} Div (enter purchase price)"

            self.price_input = discord.ui.TextInput(
                label=label_text,
                placeholder=price_placeholder,
                required=True,
                max_length=20
            )
            self.add_item(self.price_input)
            logger.info("Poe2PurchaseAddModal __init__ completed successfully")
        except Exception as e:
            logger.exception(f"Error in Poe2PurchaseAddModal __init__: {e}")
            raise

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the modal to the original Canvas author."""
        logger.info(f"Poe2PurchaseAddModal interaction_check: interaction.user.id={interaction.user.id}, self.author_id={self.author_id}")
        if interaction.user.id != self.author_id:
            logger.warning(f"Poe2PurchaseAddModal interaction rejected: user {interaction.user.id} != author {self.author_id}")
            await interaction.response.send_message("❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        logger.info("Poe2PurchaseAddModal interaction check passed")
        return True

    def _get_translations(self) -> dict:
        """Get treasure_hunter translations from personality descriptions."""
        try:
            from .content import _get_personality_descriptions
            server_id = str(self.guild.id) if self.guild else None
            descriptions = _get_personality_descriptions(server_id)
            return descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("poe2", {})
        except Exception as e:
            logger.exception(f"Error getting treasure_hunter translations: {e}")
            return {}

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if get_poe2_manager is None:
                translations = self._get_translations()
                error_message = translations.get("poe2_manager_not_available", "❌ POE2 manager is not available.")
                await interaction.response.send_message(error_message, ephemeral=True)
                return

            if self.item_name is None:
                await interaction.response.send_message("❌ No item selected.", ephemeral=True)
                return

            item_name = self.item_name.strip()

            try:
                purchase_price = float(self.price_input.value.strip())
            except ValueError:
                await interaction.response.send_message("❌ Invalid price. Please enter a valid number.", ephemeral=True)
                return

            manager = get_poe2_manager()
            server_id = "" if self.guild is None else str(self.guild.id)
            user_id = str(self.author_id)

            from agent_roles_db import get_roles_db_instance
            roles_db = get_roles_db_instance(server_id)
            subscription = roles_db.get_poe2_subscription(user_id, server_id)

            if not subscription:
                await interaction.response.send_message("❌ No POE2 subscription found.", ephemeral=True)
                return

            league = subscription.get("league", "Standard")

            # Get item_id from item list
            item_id = None
            try:
                items = manager.load_item_list(league)
                item_id = items.get(item_name.lower())
            except Exception as e:
                logger.warning(f"Could not find item_id for '{item_name}': {e}")

            purchases = subscription.get("purchases", [])
            existing = next((p for p in purchases if p["item_name"] == item_name), None)
            if existing:
                await interaction.response.send_message(f"❌ Item '{item_name}' already purchased at {existing['buy_price']:.2f} Div.", ephemeral=True)
                return

            new_purchase = {
                "item_name": item_name,
                "item_id": item_id,
                "buy_price": purchase_price,
                "buy_timestamp": datetime.now().isoformat()
            }
            purchases.append(new_purchase)

            tracked_items = subscription.get("tracked_items", [])

            if not roles_db.save_poe2_subscription(user_id, server_id, league, tracked_items, purchases):
                await interaction.response.send_message("❌ Failed to save purchase.", ephemeral=True)
                return

            from .content import _build_canvas_role_detail_view, _build_canvas_role_embed
            from discord_bot.canvas.ui import CanvasRoleDetailView

            content = _build_canvas_role_detail_view(
                "treasure_hunter",
                "poe2",
                self.view.agent_config,
                self.view.admin_visible,
                self.view.guild,
                self.view.author_id,
            )
            next_view = CanvasRoleDetailView(
                author_id=self.view.author_id,
                role_name=self.view.role_name,
                agent_config=self.view.agent_config,
                admin_visible=self.view.admin_visible,
                sections=self.view.sections,
                current_detail="poe2",
                guild=self.view.guild,
                message=interaction.message,
            )

            translations = self._get_translations()
            purchase_msg_template = translations.get("purchase_recorded_message", "✅ Purchase recorded: {item_name} at {purchase_price:.2f} Div")
            success_msg = purchase_msg_template.format(item_name=item_name, purchase_price=purchase_price)
            next_view.auto_response_preview = success_msg

            server_id = core.get_server_key(self.view.guild) if self.view.guild else None
            detail_embed = _build_canvas_role_embed(
                "treasure_hunter",
                content or "",
                self.view.admin_visible,
                "poe2",
                None,
                next_view.auto_response_preview,
                server_id=server_id,
            )
            await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)
        except Exception as e:
            logger.exception(f"Error in on_submit: {e}")
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


class Poe2PurchaseItemSelectView(discord.ui.View):
    """View for selecting an item before opening the purchase modal."""
    def __init__(self, author_id: int, guild, view, tracked_items: list[str], current_prices: dict[str, float]):
        super().__init__(timeout=900)
        self.author_id = author_id
        self.guild = guild
        self.view = view
        self.tracked_items = tracked_items
        self.current_prices = current_prices

        # Get translations
        translations = self._get_translations()
        select_placeholder = translations.get("modal_select_placeholder", "Choose an option from your list")

        # Add current price to each option label
        options = []
        for idx, item in enumerate(tracked_items):
            # Handle both old format (string) and new format (dict with item_name)
            if isinstance(item, dict):
                item_name = item.get('item_name', '')
                item_id = item.get('item_id')
                # Use item_id as value if available, otherwise use index to ensure uniqueness
                value = str(item_id) if item_id is not None else str(idx)
            else:
                item_name = item
                # Use index as value for string format to ensure uniqueness
                value = str(idx)

            label = item_name
            if item_name in current_prices:
                current_price = current_prices[item_name]
                label = f"{item_name} (Current: {current_price:.2f} Div)"
            options.append(discord.SelectOption(label=label, value=value))

        self.item_select = discord.ui.Select(
            placeholder=select_placeholder,
            min_values=1,
            max_values=1,
            options=options
        )
        self.item_select.callback = self.on_select
        self.add_item(self.item_select)

    def _get_translations(self) -> dict:
        """Get treasure_hunter translations from personality descriptions."""
        try:
            from .content import _get_personality_descriptions
            server_id = str(self.guild.id) if self.guild else None
            descriptions = _get_personality_descriptions(server_id)
            return descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("poe2", {})
        except Exception as e:
            logger.exception(f"Error getting treasure_hunter translations: {e}")
            return {}

    async def on_select(self, interaction: discord.Interaction):
        """Handle item selection and open the purchase modal."""
        selected_value = self.item_select.values[0]

        # Get item_name from tracked_items using the selected value (which could be item_id or index)
        item_name = None
        try:
            # Try to parse as integer (could be item_id or index)
            selected_int = int(selected_value)
            # Check if this matches an item_id
            for item in self.tracked_items:
                if isinstance(item, dict) and item.get('item_id') == selected_int:
                    item_name = item.get('item_name')
                    break
            # If not found by item_id, use as index
            if item_name is None and 0 <= selected_int < len(self.tracked_items):
                item = self.tracked_items[selected_int]
                item_name = item.get('item_name') if isinstance(item, dict) else item
        except ValueError:
            # If not an integer, treat as item_name (fallback for old format)
            item_name = selected_value

        if not item_name:
            await interaction.response.send_message("❌ Error: Invalid selection", ephemeral=True)
            return

        current_price = self.current_prices.get(item_name)

        try:
            await interaction.response.send_modal(
                Poe2PurchaseAddModal(self.author_id, self.guild, self.view, item_name, current_price)
            )
        except Exception as e:
            logger.exception(f"Error sending modal: {e}")
            await interaction.response.send_message(f"❌ Error opening modal: {e}", ephemeral=True)

    def _get_tracked_items(self) -> list[str]:
        """Get tracked items from user's POE2 objectives table."""
        try:
            if get_poe2_manager is None:
                return []
            manager = get_poe2_manager()
            server_id = "" if self.guild is None else str(self.guild.id)
            user_id = str(self.author_id)

            league = manager.get_user_league(user_id, server_id)

            conn = manager.init_price_history_db(league)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT item_name FROM objectives
                WHERE user_id = ? AND league = ? AND active = 1
                ORDER BY id
            ''', (user_id, league))
            items = [row[0] for row in cursor.fetchall()]
            conn.close()
            return items
        except Exception as e:
            logger.exception(f"Error getting tracked items: {e}")
            return []

    def _get_current_prices(self, tracked_items: list[str]) -> dict[str, float]:
        """Get current prices for tracked items from the database."""
        try:
            if get_poe2_manager is None:
                return {}
            manager = get_poe2_manager()
            server_id = "" if self.guild is None else str(self.guild.id)
            user_id = str(self.author_id)

            from agent_roles_db import get_roles_db_instance
            roles_db = get_roles_db_instance(server_id)
            subscription = roles_db.get_poe2_subscription(user_id, server_id)

            if not subscription:
                return {}

            league = subscription.get("league", "Standard")
            from roles.treasure_hunter.db_role_treasure_hunter import DatabaseRolePoe, get_db_path
            db_path = get_db_path(server_id, league)
            db = DatabaseRolePoe(server_id, league, db_path=db_path)

            current_prices = {}
            for item in tracked_items:
                current_price = db.get_current_price(item, league)
                if current_price is not None:
                    current_prices[item] = current_price

            return current_prices
        except Exception as e:
            logger.exception(f"Error getting current prices: {e}")
            return {}

    async def on_submit(self, interaction: discord.Interaction):
        logger.info(f"Poe2PurchaseAddModal on_submit called with item_name={self.item_name}")
        await interaction.response.send_message(f"✅ Test: item={self.item_name}, price={self.price_input.value}", ephemeral=True)


class Poe2PurchaseLiquidateView(discord.ui.View):
    """View for selecting a purchase to liquidate."""
    def __init__(self, author_id: int, guild, view, purchases: list[dict]):
        super().__init__(timeout=900)
        self.author_id = author_id
        self.guild = guild
        self.view = view
        self.purchases = purchases

        # Get translations
        translations = self._get_translations()
        select_placeholder = translations.get("modal_select_placeholder", "Choose a purchase to liquidate")

        # Build options from purchases
        options = []
        for idx, purchase in enumerate(purchases):
            item_name = purchase.get('item_name', 'Unknown')
            buy_price = purchase.get('buy_price', 0)
            label = f"{item_name} (bought at {buy_price:.2f} Div)"
            options.append(discord.SelectOption(label=label, value=str(idx)))

        self.purchase_select = discord.ui.Select(
            placeholder=select_placeholder,
            min_values=1,
            max_values=1,
            options=options
        )
        self.purchase_select.callback = self.on_select
        self.add_item(self.purchase_select)

    def _get_translations(self) -> dict:
        """Get treasure_hunter translations from personality descriptions."""
        try:
            from .content import _get_personality_descriptions
            server_id = str(self.guild.id) if self.guild else None
            descriptions = _get_personality_descriptions(server_id)
            return descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("poe2", {})
        except Exception as e:
            logger.exception(f"Error getting treasure_hunter translations: {e}")
            return {}

    async def on_select(self, interaction: discord.Interaction):
        """Handle purchase selection and liquidate it."""
        selected_idx = int(self.purchase_select.values[0])
        purchase = self.purchases[selected_idx]
        item_name = purchase.get('item_name')

        manager = get_poe2_manager()
        server_id = "" if self.guild is None else str(self.guild.id)
        user_id = str(self.author_id)

        # Get current subscription
        from agent_roles_db import get_roles_db_instance
        roles_db = get_roles_db_instance(server_id)
        subscription = roles_db.get_poe2_subscription(user_id, server_id)

        if not subscription:
            await interaction.response.send_message("❌ No POE2 subscription found.", ephemeral=True)
            return

        # Remove purchase from subscription
        purchases = subscription.get("purchases", [])
        updated_purchases = [p for p in purchases if p.get('item_name') != item_name]

        # Save updated subscription
        league = subscription.get("league", "Standard")
        tracked_items = subscription.get("tracked_items", [])

        if not roles_db.save_poe2_subscription(user_id, server_id, league, tracked_items, updated_purchases):
            await interaction.response.send_message("❌ Failed to liquidate purchase.", ephemeral=True)
            return

        # Refresh view
        from .content import _build_canvas_role_detail_view, _build_canvas_role_embed
        from discord_bot.canvas.ui import CanvasRoleDetailView

        content = _build_canvas_role_detail_view(
            "treasure_hunter",
            "poe2",
            self.view.agent_config,
            self.view.admin_visible,
            self.view.guild,
            self.view.author_id,
        )
        next_view = CanvasRoleDetailView(
            author_id=self.view.author_id,
            role_name=self.view.role_name,
            agent_config=self.view.agent_config,
            admin_visible=self.view.admin_visible,
            sections=self.view.sections,
            current_detail="poe2",
            guild=self.view.guild,
            message=interaction.message,
        )

        translations = self._get_translations()
        liquidate_msg = translations.get("purchase_liquidated_message", "✅ Purchase liquidated: {item_name}")
        success_msg = liquidate_msg.format(item_name=item_name)
        next_view.auto_response_preview = success_msg

        server_id_for_embed = core.get_server_key(self.view.guild) if self.view.guild else None
        detail_embed = _build_canvas_role_embed(
            "treasure_hunter",
            content or "",
            self.view.admin_visible,
            "poe2",
            None,
            next_view.auto_response_preview,
            server_id=server_id_for_embed,
        )
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


class Poe2ItemModal(CanvasModal):
    def __init__(self, action_name: str, author_id: int, guild, view):
        self.action_name = action_name
        self.guild = guild
        self.view = view

        # Get translations after self.guild is set
        translations = self._get_translations()

        # Use translated title
        if action_name == "poe2_item_add":
            title = translations.get("modal_item_add_title", "Add POE2 Item")
            label = translations.get("modal_item_add_label", "Item name")
            placeholder = translations.get("modal_item_add_placeholder", "Ancient Rib")
        else:
            title = translations.get("modal_item_remove_title", "Remove POE2 Item")
            label = translations.get("modal_item_remove_label", "Item name or item number")
            placeholder = translations.get("modal_item_remove_placeholder", "Ancient Rib or 1")

        super().__init__(title=title, author_id=author_id)
        self.value_input = discord.ui.TextInput(label=label, placeholder=placeholder, required=True, max_length=120)
        self.add_item(self.value_input)

    def _get_translations(self) -> dict:
        """Get treasure_hunter translations from personality descriptions."""
        try:
            from .content import _get_personality_descriptions
            server_id = str(self.guild.id) if self.guild else None
            descriptions = _get_personality_descriptions(server_id)
            return descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("poe2", {})
        except Exception as e:
            logger.exception(f"Error getting treasure_hunter translations: {e}")
            return {}

    async def on_submit(self, interaction: discord.Interaction):
        translations = self._get_translations()
        if get_poe2_manager is None:
            error_message = translations.get("poe2_manager_not_available", "❌ POE2 manager is not available.")
            await interaction.response.send_message(error_message, ephemeral=True)
            return
        manager = get_poe2_manager()
        server_id = "" if self.guild is None else str(self.guild.id)
        user_id = str(self.author_id)
        item_value = str(self.value_input.value).strip()
        if not item_value:
            error_message = translations.get("invalid_item_error", "❌ Enter a valid POE2 item.")
            await interaction.response.send_message(error_message, ephemeral=True)
            return
        try:
            if self.action_name == "poe2_item_add":
                # Use async version with background download and placeholder
                ok, message = await manager.add_objective_async(server_id, user_id, item_value)
            else:
                ok, message = manager.remove_objective(server_id, user_id, item_value)
        except Exception as e:
            logger.exception(f"Canvas POE2 item update failed: {e}")
            error_message = translations.get("update_item_error", "❌ Could not update POE2 items.")
            await interaction.response.send_message(error_message, ephemeral=True)
            return
        if not ok:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        from .content import _build_canvas_role_detail_view, _build_canvas_role_embed
        from discord_bot.canvas.ui import CanvasRoleDetailView

        content = _build_canvas_role_detail_view(
            "treasure_hunter",
            "poe2",
            self.view.agent_config,
            self.view.admin_visible,
            self.view.guild,
            self.view.author_id,
        )
        next_view = CanvasRoleDetailView(
            author_id=self.view.author_id,
            role_name=self.view.role_name,
            agent_config=self.view.agent_config,
            admin_visible=self.view.admin_visible,
            sections=self.view.sections,
            current_detail="poe2",
            guild=self.view.guild,
            message=interaction.message,
        )
        next_view.auto_response_preview = f"✅ {message}"
        server_id = core.get_server_key(self.view.guild) if self.view.guild else None
        detail_embed = _build_canvas_role_embed(
            "treasure_hunter",
            content or "",
            self.view.admin_visible,
            "poe2",
            None,
            next_view.auto_response_preview,
            server_id=server_id,
        )
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


async def handle_canvas_treasure_hunter_action(interaction: discord.Interaction, action_name: str, view) -> None:
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    # Effective guild: fall back to view.guild in DM.
    eff_guild = interaction.guild or getattr(view, 'guild', None)

    # Get translations
    from .content import _get_personality_descriptions
    server_id = str(eff_guild.id) if eff_guild else None
    descriptions = _get_personality_descriptions(server_id)
    treasure_translations = descriptions.get("role_descriptions", {}).get("treasure_hunter", {}).get("poe2", {})

    if get_poe2_manager is None:
        error_message = treasure_translations.get("poe2_manager_not_available", "❌ POE2 manager is not available.")
        await interaction.followup.send(error_message, ephemeral=True)
        return

    manager = get_poe2_manager()
    server_id = "" if eff_guild is None else str(eff_guild.id)
    user_id = str(interaction.user.id)

    from .content import _build_canvas_role_detail_view, _build_canvas_role_embed
    from discord_bot.canvas.ui import CanvasRoleDetailView

    if action_name in {"league_standard", "league_fate_of_the_vaal", "league_hardcore"}:
        league_map = {
            "league_standard": "Standard",
            "league_fate_of_the_vaal": "Fate of the Vaal",
            "league_hardcore": "Hardcore",
        }
        league = league_map[action_name]
        try:
            # Check if user has existing subscription
            from agent_roles_db import get_roles_db_instance
            roles_db = get_roles_db_instance(server_id)
            existing_subscription = roles_db.get_poe2_subscription(user_id, server_id)

            if existing_subscription:
                # User has subscription - just update league
                ok = manager.set_user_league(user_id, league, server_id)
                if ok:
                    # Initialize league if needed (downloads item list and starts background downloads)
                    await manager.initialize_league_if_needed(league)
            else:
                # New user - create subscription with default items copied
                ok, message = await manager.create_user_subscription(user_id, server_id, league)
                if not ok:
                    logger.error(f"Failed to create user subscription: {message}")
        except Exception as e:
            logger.exception(f"Canvas POE2 league update failed: {e}")
            ok = False
        if not ok:
            await interaction.followup.send("❌ Could not update POE2 league.", ephemeral=True)
            return

        target_detail = view.current_detail if view.current_detail == "poe2" else "league"
        server_id = core.get_server_key(view.guild) if view.guild else None
        content = _build_canvas_role_detail_view(
            "treasure_hunter",
            target_detail,
            view.agent_config,
            view.admin_visible,
            view.guild,
            view.author_id,
        )
        next_view = CanvasRoleDetailView(view.author_id, view.role_name, view.agent_config, view.admin_visible, view.sections, current_detail=target_detail, guild=view.guild)
        next_view.auto_response_preview = f"✅ League changed to `{league}` and default items were synced."
        embed = _build_canvas_role_embed("treasure_hunter", content, view.admin_visible, target_detail, None, next_view.auto_response_preview, server_id=server_id)
        next_view.current_embed = embed
        await _handle_canvas_followup_edit(interaction, embed, next_view, "for league update")
        return

    # Handle purchase add/remove actions (user actions, not admin-only)
    if action_name in {"poe2_purchase_add", "poe2_purchase_remove"}:
        if action_name == "poe2_purchase_add":
            modal = Poe2PurchaseAddModal(interaction.user.id, eff_guild, view)
        else:
            modal = Poe2PurchaseRemoveModal(interaction.user.id, eff_guild, view)
        await interaction.response.send_modal(modal)
        return

    # Handle item add/remove actions (user actions, not admin-only)
    if action_name in {"poe2_item_add", "poe2_item_remove"}:
        modal = Poe2ItemModal(action_name, interaction.user.id, eff_guild, view)
        await interaction.response.send_modal(modal)
        return

    if not view.admin_visible or not is_admin(interaction, guild=eff_guild):
        await interaction.followup.send("❌ This POE2 option is admin-only.", ephemeral=True)
        return

    try:
        if action_name == "poe2_on":
            # Use async activation with league initialization
            ok, activation_message = await manager.activate_subrole_async(server_id)
            logger.info(f"POE2 activation result: {ok}, message: {activation_message}")
        else:
            ok = manager.deactivate_subrole(server_id)
            activation_message = "POE2 disabled"
    except Exception as e:
        logger.exception(f"Canvas POE2 activation toggle failed: {e}")
        ok = False
        activation_message = f"Error: {e}"

    if not ok:
        await interaction.followup.send("❌ Could not update POE2 activation state.", ephemeral=True)
        return

    # Save activation state to server_config.json (per-server setting)
    try:
        from .server_config import set_role_config_value
        server_key = core.get_server_key(view.guild) if view.guild else None
        if server_key:
            set_role_config_value(server_key, "treasure_hunter", "poe2_activated", (action_name == "poe2_on"))
            logger.info(f"POE2 activation state saved to server_config.json: {(action_name == 'poe2_on')}")
    except Exception as e:
        logger.error(f"Failed to save POE2 activation state to server_config.json: {e}")

    target_detail = view.current_detail if view.current_detail in {"personal", "league"} else "admin"
    content = _build_canvas_role_detail_view(
        "treasure_hunter",
        target_detail,
        view.agent_config,
        view.admin_visible,
        view.guild,
        view.author_id,
    )
    server_id = core.get_server_key(view.guild) if view.guild else None
    next_view = CanvasRoleDetailView(view.author_id, view.role_name, view.agent_config, view.admin_visible, view.sections, current_detail=target_detail, guild=view.guild)
    next_view.auto_response_preview = f"✅ {activation_message}"
    embed = _build_canvas_role_embed("treasure_hunter", content, view.admin_visible, target_detail, None, next_view.auto_response_preview, server_id=server_id)
    next_view.current_embed = embed
    await _handle_canvas_followup_edit(interaction, embed, next_view, "for activation toggle")


def _treasure_text_factory(treasure_messages: dict, treasure_descriptions: dict):
    def _treasure_text(key: str, fallback: str) -> str:
        if "." in key:
            keys = key.split(".")
            value = treasure_descriptions
            for key_part in keys:
                if isinstance(value, dict) and key_part in value:
                    value = value[key_part]
                else:
                    value = None
                    break
        else:
            value = treasure_descriptions.get(key, treasure_messages.get(key))

        return str(value).strip() if value else fallback

    return _treasure_text


def build_canvas_role_treasure_hunter(agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str:
    """Build the Treasure Hunter role view.

    POE2 subrole is only shown if:
    1. treasure_hunter is enabled in agent_config.json (global setting)
    2. POE2 is activated for this server (local toggle)
    """
    _treasure_text = _get_treasure_text_factory(guild)

    # Check if treasure_hunter is enabled in agent_config (global setting)
    th_global_enabled = (agent_config or {}).get("roles", {}).get("treasure_hunter", {}).get("enabled", False)

    state = _get_canvas_poe2_state(guild, author_id)
    objective_count = len(state.get("objectives", []))

    parts = [
        _treasure_text("description", "Item-tracking and alerts setup for different games."),
        f"**{_treasure_text('user_flows_title', 'User flows')}**",
        f"- {_treasure_text('user_flows_1', 'Select the game that you want to track.')}",
        f"- {_treasure_text('user_flows_2', 'Navigate inside to configure the differents aspects and select the items.')}",
        f"**{_treasure_text('task_map_title', 'Task map')}**",
        f"- {_treasure_text('task_map_1', 'Items: maintain tracked objectives')}",
        f"- {_treasure_text('task_map_2', 'Alerts: Receive some alerts when the prize of the items touch som max/min prize')}",
    ]

    # Only show POE2 subrole info if treasure_hunter is enabled globally
    if th_global_enabled:
        parts.extend([
            "",
            f"**{_treasure_text('available_subroles_title', 'Available Subroles')}**",
            f"**POE2 state:** {'On' if state.get('activated', False) else 'Off'} | league {state.get('league', 'Standard')} | {objective_count} tracked item(s)",
        ])

    if admin_visible:
        parts.extend([
            "",
            f"**{_treasure_text('admin_flows_title', 'Admin flows')}**",
            f"- {_treasure_text('admin_flows_1', 'Navigate inside of the subroles and activate it in the admin buttons in each one.')}",
        ])
    return "\n".join(parts)


def build_canvas_role_treasure_hunter_detail(
    detail_name: str,
    admin_visible: bool,
    guild=None,
    author_id: int | None = None,
    setup_not_available_builder=None,
) -> str | None:
    """Build a detailed Treasure Hunter view based on detail_name."""
    _treasure_text = _get_treasure_text_factory(guild)

    if detail_name in {"personal", "poe2", "items"}:
        state = _get_canvas_poe2_state(guild, author_id)
        # Handle both old format (strings) and new format (dicts with item_name and current_price)
        items_block = ""
        if state["objectives"]:
            items_lines = []
            for item in state["objectives"]:
                if isinstance(item, dict):
                    item_name = item.get('item_name', 'Unknown')
                    current_price = item.get('current_price')
                else:
                    item_name = item
                    current_price = None

                # Show item name with current price if available
                if current_price is not None:
                    items_lines.append(f"- {item_name}: **{current_price:.2f} Div**")
                else:
                    items_lines.append(f"- {item_name}: *No price data*")
            items_block = "\n".join(items_lines)
        else:
            items_block = "- No tracked items yet"

        # Build purchases block with current prices
        purchases = state.get("purchases", [])
        purchases_block = ""
        if purchases:
            purchases_lines = []
            for purchase in purchases:
                item_name = purchase.get("item_name", "Unknown")
                buy_price = purchase.get("buy_price", 0)
                current_price = purchase.get('current_price')

                # Show purchase with buy price and current price if available
                if current_price is not None:
                    profit = current_price - buy_price
                    profit_emoji = "📈" if profit > 0 else "📉" if profit < 0 else "➡️"
                    buy_label = _treasure_text("poe2.alert_buy_price", "Buy")
                    current_label = _treasure_text("poe2.alert_current_price", "Current")
                    purchases_lines.append(f"- {item_name}: {buy_label} {buy_price:.2f} Div | {current_label} {current_price:.2f} Div {profit_emoji}")
                else:
                    purchases_lines.append(f"- {item_name}: {buy_price:.2f} Div")
            purchases_block = "\n".join(purchases_lines)
        else:
            purchases_block = _treasure_text("poe2.no_purchases", "- No purchases recorded")

        # Extract label from current_league by removing the placeholder
        league_label = _treasure_text("poe2.current_league", "🏆 **Current League**: {league}").replace(": {league}", "")

        return "\n".join([
            _treasure_text("poe2.description", "Manage your POE2 tracked items and league preferences."),
            league_label,
            f"- {state['league']}",
            "",
            _treasure_text("poe2.tracked_items_label", "**Tracked items**"),
            items_block,
            "",
            _treasure_text("poe2.purchases_label", "**Purchases**"),
            purchases_block,
        ])

    if detail_name in {"league"}:
        state = _get_canvas_poe2_state(guild, author_id)
        return "\n".join([
            _treasure_text("poe2.current_league", "🏆 **Current League**: {league}").replace("{league}", state["league"]),
            _treasure_text("poe2.league_description", "Configure your POE2 league setting for item tracking"),
            "-"*45,
        ])

    if detail_name in {"admin", "setup"}:
        if not admin_visible:
            if callable(setup_not_available_builder):
                return setup_not_available_builder()
            return "❌ This setup is only available to administrators."

        state = _get_canvas_poe2_state(guild, author_id)
        # Check server_config for updated activation state first (per-server setting)
        try:
            from .server_config import get_role_config_value
            server_key = core.get_server_key(guild) if guild else None
            if server_key:
                poe2_activated = get_role_config_value(server_key, "treasure_hunter", "poe2_activated", default=None)
                if poe2_activated is not None:
                    state["activated"] = poe2_activated
        except Exception as e:
            logger.warning(f"Failed to read POE2 activation from server_config.json: {e}")
        return "\n".join([
            _treasure_text("title", "💎 Treasure Hunter Admin"),
            _treasure_text("description", "Configure POE2 tracking and automation settings"),
            _treasure_text("poe2.admin_activation_label", "**POE2 activation**"),
            f"- {_treasure_text('poe2.admin_current_state_label', 'Current state:')} {'On' if state['activated'] else 'Off'}",
            "",
            f"League: {state['league']}",
            "",
            _treasure_text("poe2.admin_concrete_choices_label", "**Concrete choices**"),
            f"- {_treasure_text('poe2.admin_toggle_selector', 'Toggle selector: POE2 on/off')}",
        ])

    return None
