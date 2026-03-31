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
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None


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
        """Get text from trickster messages with dot notation support (e.g., 'ring.title')."""
        # Handle dot notation for nested keys
        if "." in key:
            keys = key.split(".")
            value = trickster_messages
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    value = None
                    break
        else:
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


def build_canvas_role_trickster_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None, agent_config: dict | None = None) -> str | None:
    """Build a detailed Trickster view."""
    from .content import _build_canvas_intro_block
    
    # Handle overview case
    if detail_name == "overview":
        # Use the main overview function
        return build_canvas_role_trickster({}, admin_visible, guild)
    
    roles_messages = _personality_descriptions.get("roles_view_messages", {})
    trickster_messages = roles_messages.get("trickster", {})

    def _trickster_text(key: str, fallback: str) -> str:
        """Get text from trickster messages with dot notation support (e.g., 'ring.title')."""
        # Handle dot notation for nested keys
        if "." in key:
            keys = key.split(".")
            value = trickster_messages
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    value = None
                    break
        else:
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
        server_id = str(guild.id) if guild else server_key
        if get_roles_db_instance is None:
            parts.append(descriptions.get("historyvoid", "📊 Any play in the game. Be the first!"))
            return "\n".join(parts)
        db_dice = get_roles_db_instance(server_key)
        history = db_dice.get_dice_game_history(server_id, 10)
        history_title = descriptions.get("history", "**📜 DICE HISTORY**")
        parts.append(history_title)

        parts.append("─" * 45)
        if history:
            for record in history:
                user_name = record.get('user_name', 'Unknown')
                dice = record.get('dice', '')
                combination = record.get('combination', '')
                prize = record.get('prize', 0)
                created_at = record.get('created_at', '')
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    date_str = dt.strftime("%d/%m %H:%M")
                except:
                    date_str = created_at[:16] if created_at else ''
                
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
        hot_pot = int(dice_state["bet"] * 72)
        
        # Get personality descriptions with English fallbacks
        descriptions = _personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("dice_game", {})
        
        return "\n".join([
            _build_canvas_intro_block(
                f"🎲 {_bot_display_name} Canvas - Trickster / Dice / Admin",
                descriptions.get("admin_description", "Configure dice game settings and announcements"),
            ),
            descriptions.get("current_settings", "**Current settings**"),
            f"{descriptions.get('current_fixed_bet', '**Current fixed bet:**')} {dice_state['bet']:,} {descriptions.get('gold_suffix', 'gold')}",
            f"{descriptions.get('current_pot', '**Current pot:**')} {dice_state['pot_balance']:,} {descriptions.get('gold_suffix', 'gold')}",
            f"{descriptions.get('big_pot_threshold', '**Big pot threshold:**')} ~{hot_pot:,} {descriptions.get('gold_suffix', 'gold')}",
            "",
            descriptions.get("controls_title", "**Controls**"),
            f"{descriptions.get('announcements_status', '- Announcements:')} {'On' if dice_state['announcements_active'] else 'Off'}",
            descriptions.get("editable_fixed_bet", "- Editable fixed bet input"),
            descriptions.get("editable_pot_value", "- Editable pot value input"),
            descriptions.get("announcement_selector", "- Announcement on/off selector"),
            "",
            descriptions.get("routing_title", "**Routing**"),
            descriptions.get("back_only", "- Back only from here"),
            descriptions.get("no_other_buttons", "- No other subrole buttons are shown in this admin screen"),
        ])

    if detail_name in {"beggar"}:
        beggar_state = _get_canvas_beggar_state(guild)
        descriptions = _personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("beggar", {})
        
        title = descriptions.get("title", "🙏 BEGGAR")
        fund_title = descriptions.get("current_fund", "💰 **CURRENT FUND:**")
        description = descriptions.get("description", "Help support the clan with your generous donations! Every gold piece counts towards our collective goals.")
        title_reason = descriptions.get("title_reason", "**Reason:**")
        title_campaing = descriptions.get("title_campaign", "**Current Campaign**")
        title_instructions = descriptions.get("title_instructions", "**How it works**")
        instructions = descriptions.get("instructions", "💝 Click the 'Donate' button below\n - Wait the weekly result at end of the week.\n - If you give whatever donation, the beggar will memory that.\n ")
        title_donations = descriptions.get("title_donations", "**Recent Donations**")
    
        parts = [
            _build_canvas_intro_block(title, description),
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
            no_donations = descriptions.get("no_donations", "📊 No donations yet. Be the first to contribute!")
            parts.append(no_donations)
        
        return "\n".join(parts)

    if detail_name in {"beggar_admin"}:
        beggar_state = _get_canvas_beggar_state(guild)
        descriptions = _personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("beggar", {})
        description = descriptions.get("description", "Help support the clan with your generous donations! Every gold piece counts towards our collective goals.")  
        title = descriptions.get("title", "🙏 BEGGAR")
        general_descriptions =  _personality_descriptions.get("general", {})
        return "\n".join([
            _build_canvas_intro_block(title, description),
            "-" * 45,
            general_descriptions.get("current_settings", "**Current Settings**"),
            "-" * 45,
            f"{general_descriptions.get('status_label', '**Status:**')} {_personality_descriptions.get('active', '✅ Enabled') if beggar_state['enabled'] else _personality_descriptions.get('inactive','❌ Disabled')}",
            f"{general_descriptions.get('frequency_label', '**Frequency:**')} {_personality_descriptions.get('every', 'every')} {beggar_state['frequency_hours']}h",
            f"{descriptions.get('current_fund', '**Current Fund:**')} {beggar_state['fund_balance']:,} :coin:",
            f"{descriptions.get('title_reason', '**Last Reason:**')} {beggar_state['last_reason'] or _personality_descriptions.get('none','None')}",
           
           ])

    if detail_name in {"ring"}:
        ring_state = _get_canvas_ring_state(guild)
        ring_messages = roles_messages.get("trickster", {}).get("ring", {})

        title = _trickster_text("ring.title", f"👁️ **{_bot_display_name} Ring Hunter**")
        clean_title = title.replace("**", "")
        description = _trickster_text("ring.description", f"🔍 {_bot_display_name} the ring hunter seeks the lost artifact. Your boss tasked you with finding that cursed jewel and you won't return until you have it. Interrogate suspects and make them talk.")

        current_target_label = ring_messages.get("current_target", "🎯 **CURRENT TARGET:**")
        target_unknown = ring_messages.get("target_unknown", "👤 No suspect selected")
        investigation_title = ring_messages.get("investigation_title", "🔍 **MAKE AN ACCUSATION:**")
        investigation_instructions = ring_messages.get("investigation_instructions", "• Use **Ring: Accuse** from the dropdown below\n• Enter: @username, user ID, or visible name\n• The AI will generate a threatening accusation\n• Accusation will be posted publicly in the channel")
        investigation_warning = ring_messages.get("investigation_warning", "⚠️ **IMPORTANT:**\n• You cannot accuse yourself\n• You cannot accuse bots\n• Ring must be enabled by an admin first")
        inactive_title = ring_messages.get("inactive_title", "⚠️ **THE HUNT IS INACTIVE**")
        inactive_instructions = ring_messages.get("inactive_instructions", "To enable ring functionality:\n• An admin must go to **Ring Admin**\n• Click **Ring: On** to activate\n• Set frequency for automatic investigations\n\nOnce enabled, you can accuse users of carrying the One Ring!")

        parts = [
            _build_canvas_intro_block(clean_title, description),
            "-" * 45,   
            ]
        
        parts.append("")
        if ring_state["enabled"]:
            parts.extend([
                investigation_title,
                investigation_instructions,
                "-" * 45,
                investigation_warning,
                "-" * 45,
                current_target_label,
                f"👤 {ring_state['target_user_name']}" if ring_state['target_user_name'] != "Unknown bearer" else target_unknown,
                "-" * 45,
            ])
        else:
            parts.extend([inactive_title, "", inactive_instructions])

        # Use general descriptions for status
        general = _personality_descriptions.get("general", {})
        status_label = general.get("status", "Status:")
        active_text = general.get("active", "✅  Active")
        inactive_text = general.get("inactive", "❌ Inactive")
        
        parts.append(f"**{status_label}** { active_text if ring_state['enabled'] else  inactive_text}")
        
        return "\n".join(parts)

    if detail_name in {"ring_admin"}:
        ring_state = _get_canvas_ring_state(guild)
        ring_messages = roles_messages.get("trickster", {}).get("ring", {})
        # Get title without newlines for admin
        title = _trickster_text("ring.title", f"👁️ **{_bot_display_name} Ring Hunter**")
        # Use general descriptions for admin panel
        general = _personality_descriptions.get("general", {})
        ring_descriptions = _personality_descriptions.get("roles_view_messages", {}).get("trickster", {}).get("ring", {})
        
        admin_status = general.get("status", "Status:")
        active_text = general.get("active", "Active")
        inactive_text = general.get("inactive", "Inactive")
        base_freq_label = general.get("base_frequency", "Base Frequency:")
        current_freq_label = general.get("current_frequency", "Current Frequency:")
        freq_format = general.get("frequency_format", "Every {hours}h")
        hot_potato_format = ring_descriptions.get("hot_potato", "🔥 **Hot Potato:** Iteration {iteration} (frequency reduced by {multiplier}x)")
        description = _trickster_text("ring.description", f"🔍 {_bot_display_name} the ring hunter seeks the lost artifact. Your boss tasked you with finding that cursed jewel and you won't return until you have it. Interrogate suspects and make them talk.")

        base_freq = ring_state.get('base_frequency_hours', ring_state['frequency_hours'])
        current_freq = ring_state.get('current_frequency_hours', ring_state['frequency_hours'])
        
        parts = [
            _build_canvas_intro_block(
                f"{title} Admin",
                description,
            ),
            f"**{admin_status}** {active_text if ring_state['enabled'] else inactive_text}",
            f"**{base_freq_label}** {freq_format.format(hours=base_freq)}",
            f"**{current_freq_label}** {freq_format.format(hours=current_freq)}",
        ]
        
        # Add hot potato information if active
        if ring_state.get('frequency_iteration', 0) > 0:
            iteration = ring_state.get('frequency_iteration', 0)
            multiplier = 2 ** iteration
            parts.append(hot_potato_format.format(iteration=iteration, multiplier=multiplier))
        
        controls = ring_descriptions.get("controls", "**Controls**\n- Enable or disable ring\n- Editable frequency box (sets base frequency and resets hot potato)")
        
        parts.extend(["", controls])
        
        return "\n".join(parts)

    if detail_name == "runes":
        runes_messages = roles_messages.get("trickster", {}).get("nordic_runes", {})
        title = runes_messages.get("title", "🔮 **Nordic Runes Ancient Wisdom** 🔮")
        description = runes_messages.get("description", "Ancient wisdom for modern guidance through Elder Futhark runes.")
        
        # Check if runes subrole is enabled
        runes_enabled = False
        if agent_config:
            runes_enabled = agent_config.get("roles", {}).get("trickster", {}).get("subroles", {}).get("nordic_runes", {}).get("enabled", False)
        
        how_to_use = runes_messages.get("how_to_use", "**How to Use:**\n 1. Choose a reading type from the dropdown\n 2. Enter your question in the modal\n 3. Receive personalized rune interpretation\n")
        runes_title = runes_messages.get("runes_title", "**The 24 Elder Futhark Runes:**")
        
        return "\n".join([
            _build_canvas_intro_block(title, description),
            "-"*45,
            how_to_use,
            "-"*45,
            "",
            runes_title,
            "-"*45,
            "ᚠ Fehu • ᚢ Uruz • ᚦ Thurisaz • ᚨ Ansuz • ᚱ Raidho • ᚲ Kenaz • ᚷ Gebo • ᚹ Wunjo",
            "ᚺ Hagalaz • ᚾ Nauthiz • ᛁ Isa • ᛃ Jera • ᛇ Eiwaz • ᛈ Perthro • ᛉ Algiz • ᛊ Sowilo",
            "ᛏ Tiwaz • ᛒ Berkano • ᛖ Ehwaz • ᛗ Mannaz • ᛚ Laguz • ᛜ Ingwaz • ᛞ Dagaz • ᛟ Othala",
            "",
            "-"*45,
            f"**Status:** {'✅ Enabled' if runes_enabled else '❌ Disabled'}",
        ])

    if detail_name == "runes_admin":
        runes_messages = roles_messages.get("trickster", {}).get("nordic_runes", {})
        title = runes_messages.get("title", "🔮 **Nordic Runes Ancient Wisdom** 🔮")
        
        # Get runes subrole status from agent config
        subroles = (agent_config or {}).get("roles", {}).get("trickster", {}).get("subroles", {})
        runes_enabled = subroles.get("nordic_runes", {}).get("enabled", False)
        
        return "\n".join([
            _build_canvas_intro_block(
                f"{title} Admin",
                "Configure Nordic Runes subrole settings and availability for this server."
            ),
            f"**Status:** {'✅ Enabled' if runes_enabled else '❌ Disabled'}",
            "",
            "**Controls**",
            "- Enable or disable Nordic Runes subrole",
            "- When enabled, users can cast runes and receive interpretations",
            "- All rune readings are tracked in the database",
            "",
            "**Available Reading Types:**",
            "• Single Rune - Quick guidance and insight",
            "• Three Rune Spread - Past, Present, Future",
            "• Five Rune Cross - Comprehensive situation analysis",
            "• Seven Rune Runic Cross - Deep spiritual guidance",
            "",
            "**Features when enabled:**",
            "• Personalized rune interpretations based on user questions",
            "• Reading history tracking for each user",
            "• Contextual guidance for different life areas",
            "• Ancient Norse wisdom applied to modern situations",
            "",
            "**Routing**",
            "- Back only from here",
            "- No other subrole buttons are shown in this admin screen",
        ])

    return None
