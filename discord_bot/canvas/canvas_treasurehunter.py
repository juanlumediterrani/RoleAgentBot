"""Canvas Treasure Hunter content builders."""

from discord_bot import discord_core_commands as core
from .state import _get_canvas_poe2_state

_bot_display_name = core._bot_display_name
_personality_answers = core._personality_answers
_personality_descriptions = core._personality_descriptions
AGENT_CFG = core.AGENT_CFG


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

        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback

    return _treasure_text


def build_canvas_role_treasure_hunter(agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str:
    """Build the Treasure Hunter role view."""
    from .content import _build_canvas_intro_block
    treasure_messages = _personality_answers.get("treasure_hunter_messages", {})
    treasure_descriptions = _personality_descriptions.get("roles_view_messages", {}).get("treasure_hunter", {})
    _treasure_text = _treasure_text_factory(treasure_messages, treasure_descriptions)

    interval = (agent_config or {}).get("roles", {}).get("treasure_hunter", {}).get("interval_hours", 1)
    state = _get_canvas_poe2_state(guild, author_id)
    objective_count = len(state.get("objectives", []))

    parts = [
        _build_canvas_intro_block(
            _treasure_text("title", f"💎 {_bot_display_name} Canvas - Treasure Hunter"),
            _treasure_text("description", "Item-tracking and alerts setup for different games."),
        ),
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
    from .content import _build_canvas_intro_block
    treasure_messages = _personality_answers.get("treasure_hunter_messages", {})
    treasure_descriptions = _personality_descriptions.get("roles_view_messages", {}).get("treasure_hunter", {})
    _treasure_text = _treasure_text_factory(treasure_messages, treasure_descriptions)
    if detail_name in {"personal", "poe2", "items"}:
        return build_canvas_role_treasure_hunter_poe2({}, admin_visible, guild, author_id)

    if detail_name in {"league"}:
        state = _get_canvas_poe2_state(guild, author_id)
        return "\n".join([
            _build_canvas_intro_block(
                _treasure_text("poe2.league.title", f"💎 {_bot_display_name} Canvas - Treasure Hunter League").replace("{league}", state["league"]),
                _treasure_text("poe2.league.description", "Configure your POE2 league setting for item tracking"),
            ),
            "**Current league**",
            f"- {state['league']}",
            "",
            "**League actions**",
            "- `!hunter poe2 league` - Show your current league",
            "- `!hunter poe2 league \"Standard\"` - Change to Standard",
            "- `!hunter poe2 league \"Fate of the Vaal\"` - Change to Fate of the Vaal",
            "- `!hunter poe2 league \"Hardcore\"` - Change to Hardcore if supported",
            "",
            "**Concrete choices**",
            "- Preferred selector options: `Standard` / `Fate of the Vaal`",
            "- Fallback: text input for a custom or future league",
            "",
            "**Routing**",
            "- League management is DM-oriented",
            "- Use `!canvas role treasure_hunter` to return to the role overview",
        ])

    if detail_name in {"admin", "setup"}:
        if not admin_visible:
            if callable(setup_not_available_builder):
                return setup_not_available_builder()
            return "❌ This setup is only available to administrators."

        state = _get_canvas_poe2_state(guild, author_id)
        interval = (AGENT_CFG or {}).get("roles", {}).get("treasure_hunter", {}).get("interval_hours", 1)
        return "\n".join([
            _build_canvas_intro_block(
                f"💎 {_bot_display_name} Canvas - Treasure Hunter Admin",
                "Configure POE2 tracking and automation settings",
            ),
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


def build_canvas_role_treasure_hunter_poe2(agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Build the POE2 subrole view within Treasure Hunter."""
    from .content import _build_canvas_intro_block
    treasure_messages = _personality_answers.get("treasure_hunter_messages", {})
    treasure_descriptions = _personality_descriptions.get("roles_view_messages", {}).get("treasure_hunter", {})
    _treasure_text = _treasure_text_factory(treasure_messages, treasure_descriptions)

    state = _get_canvas_poe2_state(guild, author_id)
    items_block = "\n".join([f"- {item}" for item in state["objectives"]]) if state["objectives"] else "- No tracked items yet"
    return "\n".join([
        _build_canvas_intro_block(
            _treasure_text("poe2.title", f"💎 {_bot_display_name} Canvas - Treasure Hunter POE2"),
            _treasure_text("poe2.description", "Manage your POE2 tracked items and league preferences."),
        ),
        "**Current league**",
        f"- {state['league']}",
        "",
        "**Tracked items**",
        items_block,
        "",
        "**Remove tracked items**",
        "- Use the remove action selector and confirm the item name or index",
        "",
        "**Add a new item**",
        "- Use the add action selector and submit the exact POE2 item name",
        "",
        "**Concrete choices**",
        "- Text input to add an exact POE2 item name",
        "- Text input to remove by item name or visible item number",
        "",
        "**Routing**",
        "- Personal POE2 management updates the current server-linked user profile",
        "- Use `!canvas role treasure_hunter` to return to the role overview",
    ])
