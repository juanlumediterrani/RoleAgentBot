"""Canvas Trickster content builders."""

from discord_bot import discord_core_commands as core
from .state import (
    _get_canvas_dice_state,
    _get_canvas_dice_ranking,
    _get_canvas_ring_state,
    _get_canvas_beggar_state,
)

_personality_descriptions = core._personality_descriptions
_bot_display_name = core._bot_display_name
get_server_key = core.get_server_key

try:
    from roles.trickster.subroles.dice_game.db_dice_game import get_dice_game_db_instance
except Exception:
    get_dice_game_db_instance = None


def build_canvas_role_trickster(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the Trickster role view."""
    from .content import _build_canvas_intro_block
    roles_messages = {}
    trickster_messages = {}
    try:
        roles_messages = _personality_descriptions.get("roles_view_messages", {})
        trickster_messages = roles_messages.get("trickster", {})
    except Exception:
        pass

    def _trickster_text(key: str, fallback: str) -> str:
        value = trickster_messages.get(key)
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback

    subroles = (agent_config or {}).get("roles", {}).get("trickster", {}).get("subroles", {})
    active_subroles = [name for name, cfg in subroles.items() if isinstance(cfg, dict) and cfg.get("enabled", False)]
    dice_state = _get_canvas_dice_state(guild)
    ring_state = _get_canvas_ring_state(guild)
    beggar_state = _get_canvas_beggar_state(guild)

    separator = _trickster_text("canvas_trickster_overview_separator", "──────────────────────────────")
    subrole_descriptions = trickster_messages.get("canvas_trickster_subrole_descriptions", {})

    active_descriptions = []
    for subrole in active_subroles:
        if subrole in subrole_descriptions:
            active_descriptions.append(subrole_descriptions[subrole])

    parts = [
        _build_canvas_intro_block(
            _trickster_text("canvas_trickster_overview_title", "🎭Canvas - Trickster"),
            _trickster_text("description", "Description: Trickster is a minigame based role."),
        ),
    ]

    if active_descriptions:
        parts.append("**Available subroles**")
        parts.extend(active_descriptions)

    parts += [
        "",
        "**Live state**",
        f"**Live state:** dice bet {dice_state['bet']:,} | pot {dice_state['pot_balance']:,} | ring {'On' if ring_state['enabled'] else 'Off'} | beggar {'On' if beggar_state['enabled'] else 'Off'}",
    ]

    return "\n".join(parts)


def build_canvas_role_trickster_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Build a detailed Trickster view."""
    from .content import _build_canvas_intro_block
    roles_messages = _personality_descriptions.get("roles_view_messages", {})
    trickster_messages = roles_messages.get("trickster", {})

    def _trickster_text(key: str, fallback: str) -> str:
        value = trickster_messages.get(key)
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback

    if detail_name in {"dice", "game"}:
        dice_state = _get_canvas_dice_state(guild)
        descriptions = _personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("dice_game", {})
        title = descriptions.get("title", "🎲 DICE GAME")
        pot_title = descriptions.get("current_balance", "💎 **CURRENT POT:**")
        fixed_bet = descriptions.get("fixed_bet", "💎 **FIXED BET:**")
        game_description = descriptions.get("description", "Test your luck against the Dice POT! Roll the dice and win big prizes!")
        dice_rules = descriptions.get("rules", "-Triple Ones you won the POT!\n -n Hight Straight (4,5,6) you won x5 the bet.\n -Any Triple, you won x3 the bet.\n -The pairs will return you the bet.\n ")
        parts = [
            _build_canvas_intro_block(title, game_description),
            "**Rules**",
            dice_rules,
            "",
        ]

        ranking_data = _get_canvas_dice_ranking(guild, 10)
        ranking_title = descriptions.get("ranking", "**🏆 DICE RANKING**")
        parts.append(ranking_title)
        if ranking_data:
            for player in ranking_data:
                medal = "🥇" if player["position"] == 1 else "🥈" if player["position"] == 2 else "🥉" if player["position"] == 3 else "🏅"
                parts.append(f"{medal} **#{player['position']}** {player['player_name']} | 🏆 Prize: {player['prize']:,} | Games: {player['total_plays']}")
        else:
            parts.append(descriptions.get("rankingvoid", "📊 No ranked players yet. Be the first to play!"))

        parts.append("─" * 45)
        server_key = get_server_key(guild)
        server_id = str(guild.id) if guild else "0"
        if get_dice_game_db_instance is None:
            parts.append(descriptions.get("historyvoid", "📊 Any play in the game. Be the first!"))
            return "\n".join(parts)
        db_dice = get_dice_game_db_instance(server_key)
        history = db_dice.get_game_history(server_id, 10)
        history_title = descriptions.get("history", "**📜 DICE HISTORY**")
        parts.append(history_title)

        parts.append("─" * 45)
        if history:
            for record in history:
                user_name = record[2] if len(record) > 2 else "Unknown"
                dice = record[6] if len(record) > 6 else ""
                combination = record[7] if len(record) > 7 else ""
                prize = record[8] if len(record) > 8 else 0
                dice_display = "🎲".join(dice.split('-')) if dice else "???"
                prize_emoji = "💰" if prize > 0 else "💸"
                parts.append(f"👤 {user_name} | {dice_display} → {combination} | {prize_emoji} {prize:,}")
        else:
            parts.append(descriptions.get("historyvoid", "📊 Any play in the game. Be the first!"))
        
        parts.append("─" * 45)
        parts += {  
            "",    
            f"**{pot_title} {dice_state['pot_balance']:,}** :coin: ",
            f"{fixed_bet} {dice_state.get('bet', 1):,} :coin:",
        }
        return "\n".join(parts)

    if detail_name in {"dice_admin"}:
        dice_state = _get_canvas_dice_state(guild)
        hot_pot = int(dice_state["bet"] * 73)
        return "\n".join([
            _build_canvas_intro_block(
                f"🎲 {_bot_display_name} Canvas - Trickster / Dice / Admin",
                "Configure dice game settings and announcements",
            ),
            "**Current settings**",
            f"**Current fixed bet:** {dice_state['bet']:,} gold",
            f"**Current pot:** {dice_state['pot_balance']:,} gold",
            f"**Big pot threshold:** ~{hot_pot:,} gold",
            "",
            "**Controls**",
            f"- Announcements: {'On' if dice_state['announcements_active'] else 'Off'}",
            "- Editable fixed bet input",
            "- Editable pot value input",
            "- Announcement on/off selector",
            "",
            "**Routing**",
            "- Back only from here",
            "- No other subrole buttons are shown in this admin screen",
        ])

    if detail_name in {"beggar"}:
        beggar_state = _get_canvas_beggar_state(guild)
        return "\n".join([
            _build_canvas_intro_block(
                _trickster_text("canvas_beggar_title", f"🙏 {_bot_display_name} Canvas - Trickster / Beggar"),
                _trickster_text("canvas_beggar_description", "Donate gold to support the clan project"),
            ),
            beggar_state["message"].format(reason=beggar_state["last_reason"] or "the current clan project") if beggar_state["message"] else "",
            "",
            f"**Current fund:** {beggar_state['fund_balance']:,} gold",
            f"**Last reason:** {beggar_state['last_reason']}",
            "",
            "**Donate gold**",
            "- Enter the amount in the donation modal",
            "- Confirm to transfer gold from your wallet",
            "",
            "**Routing**",
            "- This is the user-facing beggar surface",
            "- Use `Admin` for enable/frequency controls",
        ])

    if detail_name in {"beggar_admin"}:
        beggar_state = _get_canvas_beggar_state(guild)
        return "\n".join([
            _build_canvas_intro_block(
                f"🙏 {_bot_display_name} Canvas - Trickster / Beggar / Admin",
                "Configure beggar functionality and frequency",
            ),
            f"**Status:** {'On' if beggar_state['enabled'] else 'Off'}",
            f"**Frequency:** every {beggar_state['frequency_hours']}h",
            "",
            "**Controls**",
            "- Enable or disable beggar",
            "- Editable frequency box",
            "- Users can donate from the personal beggar surface",
            "",
            "**Routing**",
            "- Back only from here",
        ])

    if detail_name in {"ring"}:
        ring_state = _get_canvas_ring_state(guild)
        ring_messages = roles_messages.get("trickster", {}).get("ring", {})

        title = _trickster_text("canvas_ring_title", f"👁️ **{_bot_display_name} Ring Hunter**")
        clean_title = title.replace("**", "")
        description = _trickster_text("canvas_ring_description", "🔍 Putre the ring hunter seeks the lost artifact. Your boss tasked you with finding that cursed jewel and you won't return until you have it. Interrogate suspects and make them talk.")

        current_target_label = ring_messages.get("current_target", "🎯 **CURRENT TARGET:**")
        target_unknown = ring_messages.get("target_unknown", "👤 No suspect selected")
        investigation_title = ring_messages.get("investigation_title", "🔍 **MAKE AN ACCUSATION:**")
        investigation_instructions = ring_messages.get("investigation_instructions", "• Use **Ring: Accuse** from the dropdown below\n• Enter: @username, user ID, or visible name\n• The AI will generate a threatening accusation\n• Accusation will be posted publicly in the channel")
        investigation_warning = ring_messages.get("investigation_warning", "⚠️ **IMPORTANT:**\n• You cannot accuse yourself\n• You cannot accuse bots\n• Ring must be enabled by an admin first")
        inactive_title = ring_messages.get("inactive_title", "⚠️ **THE HUNT IS INACTIVE**")
        inactive_instructions = ring_messages.get("inactive_instructions", "To enable ring functionality:\n• An admin must go to **Ring Admin**\n• Click **Ring: On** to activate\n• Set frequency for automatic investigations\n\nOnce enabled, you can accuse users of carrying the One Ring!")
        navigation_info = ring_messages.get("navigation_info", "📍 **NAVIGATION:**\n• You are at `trickster / ring / personal`\n• Use `Admin` for on/off and frequency controls\n• Select **Ring: Accuse** from the dropdown to make accusations")

        parts = [
            _build_canvas_intro_block(clean_title, description),
            f"**Status:** {'✅ Active' if ring_state['enabled'] else '❌ Inactive'}",
            f"**Frequency:** Every {ring_state['frequency_hours']} hours",
            "",
        ]
        if ring_state["enabled"]:
            parts.extend([
                current_target_label,
                f"👤 {ring_state['target_user_name']}" if ring_state['target_user_name'] != "Unknown bearer" else target_unknown,
                "",
                investigation_title,
                investigation_instructions,
                "",
                investigation_warning,
            ])
        else:
            parts.extend([inactive_title, "", inactive_instructions])

        parts.extend(["", navigation_info])
        return "\n".join(parts)

    if detail_name in {"ring_admin"}:
        ring_state = _get_canvas_ring_state(guild)
        return "\n".join([
            _build_canvas_intro_block(
                f"👁️ {_bot_display_name} Canvas - Trickster / Ring / Admin",
                "Configure ring hunt functionality and frequency",
            ),
            f"**Status:** {'On' if ring_state['enabled'] else 'Off'}",
            f"**Frequency:** every {ring_state['frequency_hours']}h",
            "",
            "**Controls**",
            "- Enable or disable ring",
            "- Editable frequency box",
            "",
            "**Routing**",
            "- Back only from here",
        ])

    if detail_name == "runes":
        runes_messages = roles_messages.get("trickster", {}).get("nordic_runes", {})
        title = runes_messages.get("canvas_runes_title", "🔮 **Nordic Runes Ancient Wisdom** 🔮")
        description = runes_messages.get("canvas_runes_description", "Ancient wisdom for modern guidance through Elder Futhark runes.")
        return "\n".join([
            _build_canvas_intro_block(title, description),
            "**Available readings**",
            "- Single rune: quick guidance",
            "- Three runes: past, present, future",
            "• **Three Rune Spread** - Past, Present, Future insights",
            "• **Five Rune Cross** - Comprehensive situation analysis",
            "",
            "**How to Use:**",
            "1. Choose a reading type from the dropdown",
            "2. Enter your question in the modal",
            "3. Receive personalized rune interpretation",
            "",
            "**The 24 Elder Futhark Runes:**",
            "Fehu • Uruz • Thurisaz • Ansuz • Raidho • Kenaz • Gebo • Wunjo",
            "Hagalaz • Nauthiz • Isa • Jera • Eiwaz • Perthro • Algiz • Sowilo",
            "Tiwaz • Berkano • Ehwaz • Mannaz • Laguz • Ingwaz • Dagaz • Othala",
            "",
            "**Features:**",
            "• Personalized interpretations based on your question",
            "• Reading history tracking",
            "• Contextual guidance for different life areas",
            "• Ancient Norse wisdom applied to modern life",
            "",
            "**Commands:**",
            "• `!runes cast [type] <question>` - Direct rune casting",
            "• `!runes history` - View your reading history",
            "• `!runes types` - Show reading types",
            "• `!runes help` - Detailed help",
        ])

    return None
