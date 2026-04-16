"""Canvas Treasure Hunter content builders and UI handlers."""

import discord

from discord_bot import discord_core_commands as core
from .state import _get_canvas_poe2_state

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


class Poe2ItemModal(discord.ui.Modal):
    def __init__(self, action_name: str, author_id: int, guild, view):
        title = "Add POE2 Item" if action_name == "poe2_item_add" else "Remove POE2 Item"
        super().__init__(title=title)
        self.action_name = action_name
        self.author_id = author_id
        self.guild = guild
        self.view = view
        label = "Item name" if action_name == "poe2_item_add" else "Item name or item number"
        placeholder = "Ancient Rib" if action_name == "poe2_item_add" else "Ancient Rib or 1"
        self.value_input = discord.ui.TextInput(label=label, placeholder=placeholder, required=True, max_length=120)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        if get_poe2_manager is None:
            await interaction.response.send_message("❌ POE2 manager is not available.", ephemeral=True)
            return
        manager = get_poe2_manager()
        server_id = "" if self.guild is None else str(self.guild.id)
        user_id = str(self.author_id)
        item_value = str(self.value_input.value).strip()
        if not item_value:
            await interaction.response.send_message("❌ Enter a valid POE2 item.", ephemeral=True)
            return
        try:
            if self.action_name == "poe2_item_add":
                ok, message = manager.add_objective(server_id, user_id, item_value)
            else:
                ok, message = manager.remove_objective(server_id, user_id, item_value)
        except Exception as e:
            logger.exception(f"Canvas POE2 item update failed: {e}")
            await interaction.response.send_message("❌ Could not update POE2 items.", ephemeral=True)
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
        detail_embed = _build_canvas_role_embed(
            "treasure_hunter",
            content or "",
            self.view.admin_visible,
            "poe2",
            None,
            next_view.auto_response_preview,
        )
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


async def handle_canvas_treasure_hunter_action(interaction: discord.Interaction, action_name: str, view) -> None:
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    if get_poe2_manager is None:
        await interaction.followup.send("❌ POE2 manager is not available.", ephemeral=True)
        return

    manager = get_poe2_manager()
    server_id = "" if interaction.guild is None else str(interaction.guild.id)
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
            ok = manager.set_user_league(user_id, league, server_id)
            if ok:
                if manager.should_refresh_item_list(league):
                    await manager.download_item_list(league)
                manager._add_default_objectives(user_id, league)
                manager._download_default_objectives_history(user_id, league)
        except Exception as e:
            logger.exception(f"Canvas POE2 league update failed: {e}")
            ok = False
        if not ok:
            await interaction.followup.send("❌ Could not update POE2 league.", ephemeral=True)
            return

        target_detail = view.current_detail if view.current_detail == "poe2" else "league"
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
        embed = _build_canvas_role_embed("treasure_hunter", content, view.admin_visible, target_detail, None, next_view.auto_response_preview)
        next_view.current_embed = embed
        await _handle_canvas_followup_edit(interaction, embed, next_view, "for league update")
        return

    if not view.admin_visible or not is_admin(interaction):
        await interaction.followup.send("❌ This POE2 option is admin-only.", ephemeral=True)
        return

    try:
        if action_name == "poe2_on":
            league = manager.get_active_league(user_id, server_id)
            if manager.should_refresh_item_list(league):
                await manager.download_item_list(league)
            ok = manager.activate_subrole(server_id)
        else:
            ok = manager.deactivate_subrole(server_id)
    except Exception as e:
        logger.exception(f"Canvas POE2 activation toggle failed: {e}")
        ok = False

    if not ok:
        await interaction.followup.send("❌ Could not update POE2 activation state.", ephemeral=True)
        return

    target_detail = view.current_detail if view.current_detail in {"personal", "league"} else "admin"
    content = _build_canvas_role_detail_view(
        "treasure_hunter",
        target_detail,
        view.agent_config,
        view.admin_visible,
        view.guild,
        view.author_id,
    )
    next_view = CanvasRoleDetailView(view.author_id, view.role_name, view.agent_config, view.admin_visible, view.sections, current_detail=target_detail, guild=view.guild)
    next_view.auto_response_preview = f"POE2 {'enabled' if action_name == 'poe2_on' else 'disabled'}."
    embed = _build_canvas_role_embed("treasure_hunter", content, view.admin_visible, target_detail, None, next_view.auto_response_preview)
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
    """Build the Treasure Hunter role view."""
    _treasure_text = _get_treasure_text_factory(guild)

    interval = (agent_config or {}).get("roles", {}).get("treasure_hunter", {}).get("interval_hours", 1)
    state = _get_canvas_poe2_state(guild, author_id)
    objective_count = len(state.get("objectives", []))

    parts = [
        _treasure_text("title", "💎 Treasure Hunter Canvas"),
        _treasure_text("description", "Item-tracking and alerts setup for different games."),
        f"**{_treasure_text('user_flows_title', 'User flows')}**",
        f"- {_treasure_text('user_flows_1', 'Select the game that you want to track.')}",
        f"- {_treasure_text('user_flows_2', 'Navigate inside to configure the differents aspects and select the items.')}",
        f"**{_treasure_text('task_map_title', 'Task map')}**",
        f"- {_treasure_text('task_map_1', 'Items: maintain tracked objectives')}",
        f"- {_treasure_text('task_map_2', 'Alerts: Receive some alerts when the prize of the items touch som max/min prize')}",
        "",
        f"**{_treasure_text('available_subroles_title', 'Available Subroles')}**",
        f"**POE2 state:** {'On' if state.get('activated', False) else 'Off'} | league {state.get('league', 'Standard')} | {objective_count} tracked item(s)\n",
    ]
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
        items_block = "\n".join([f"- {item}" for item in state["objectives"]]) if state["objectives"] else "- No tracked items yet"
        return "\n".join([
            _treasure_text("poe2.title", "💎 Treasure Hunter POE2"),
            _treasure_text("poe2.description", "Manage your POE2 tracked items and league preferences."),
        "**Current league**",
        f"- {state['league']}",
        "",
        "**Tracked items**",
        items_block,])

    if detail_name in {"league"}:
        state = _get_canvas_poe2_state(guild, author_id)
        return "\n".join([
            _treasure_text("poe2.current_league", "🏆 **Curent League**: {league}").replace("{league}", state["league"]),
            _treasure_text("poe2.league_description", "Configure your POE2 league setting for item tracking"),
            "-"*45,
            _treasure_text("poe2.current_league", "Current League**: {league}").replace("{league}", state["league"]),

        ])

    if detail_name in {"admin", "setup"}:
        if not admin_visible:
            if callable(setup_not_available_builder):
                return setup_not_available_builder()
            return "❌ This setup is only available to administrators."

        state = _get_canvas_poe2_state(guild, author_id)
        interval = (AGENT_CFG or {}).get("roles", {}).get("treasure_hunter", {}).get("interval_hours", 1)
        return "\n".join([
            "💎 Treasure Hunter Admin",
            "Configure POE2 tracking and automation settings",
            "**POE2 activation**",
            f"- Current state: {'On' if state['activated'] else 'Off'}",
            "",
            "**Active league**",
            f"- {state['league']}",
            "",
            "**Execution frequency**",
            f"- Current interval: {interval}h",
            "",
            "**Concrete choices**",
            "- Toggle selector: POE2 on/off",
            "- Number input: hunter frequency in hours",
            "",
            "**Best next actions**",
            "- Enable POE2 only after confirming the active league",
            "- Adjust frequency after your tracked items are stable",
            "",
            "**Routing**",
            "- Activation and scheduler controls are admin-only",
            "- Use `!canvas role treasure_hunter` to return to the role overview",
        ])

    return None
