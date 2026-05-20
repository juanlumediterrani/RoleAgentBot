"""Canvas Arena content builders."""

import discord
from discord_bot import discord_core_commands as core
from .content import _get_personality_descriptions

get_server_key = core.get_server_key
logger = core.logger
is_admin = core.is_admin
set_role_enabled = core.set_role_enabled


def _get_arena_messages(server_id: str, guild=None) -> dict:
    """Carga los mensajes de Arena de la personalidad del servidor."""
    try:
        personality_descriptions = _get_personality_descriptions(server_id)
        return personality_descriptions.get("role_descriptions", {}).get("arena", {})
    except Exception:
        return {}


def _text(messages: dict, key: str, fallback: str = "") -> str:
    """Obtiene un mensaje anidado por clave con dot notation."""
    if "." in key:
        keys = key.split(".")
        value = messages
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                value = None
                break
        return str(value).strip() if value else fallback
    return str(messages.get(key, fallback)).strip() if messages.get(key) else fallback


def build_canvas_role_arena(agent_config: dict, admin_visible: bool, guild=None, author_id: int = 0) -> str:
    """Build the Arena role overview for Canvas."""
    server_id = get_server_key(guild) if guild else None
    msgs = _get_arena_messages(server_id, guild)

    title = _text(msgs, "canvas_arena_overview_title", "**Combat Arena**")
    desc = _text(msgs, "canvas_arena_overview_description", "Battle and duel management.")
    sep = _text(msgs, "canvas_arena_overview_separator", "──────────────────────────────")

    parts = [title, "", desc, "", sep, ""]

    # Subroles disponibles
    subroles = _text(msgs, "canvas_arena_subrole_descriptions", {})
    if isinstance(subroles, dict):
        parts.append("**Combat modes:**")
        for sub_id, sub_desc in subroles.items():
            parts.append(f"• {sub_desc}")
        parts.append("")

    # Upcoming events and user's last duel
    if server_id:
        try:
            from roles.arena.arena_db import ArenaDatabase
            db = ArenaDatabase(server_id)
            
            # Active event (upcoming coliseo/torneo)
            event = db.events.get_active_event()
            if event:
                etype = event.get("type", "event").capitalize()
                status = event.get("status", "unknown")
                sched = event.get("scheduled_for", "")
                participants = event.get("participants", {})
                min_p = event.get("min_participants", 4)
                
                parts.append(f"**{etype} ({status})**")
                if sched:
                    parts.append(f"  📅 Scheduled: {sched}")
                parts.append(f"  👥 Participants: {len(participants)}/{min_p}")
                if participants:
                    names = [p.get("username", "???") for p in participants.values()][:5]
                    parts.append(f"  Registered: {', '.join(names)}" + ("..." if len(participants) > 5 else ""))
                parts.append("")
            
            # User's last duel (if author_id provided)
            if author_id:
                history = db.history.get_history(limit=50)  # Get more history to find user's duels
                user_duels = [battle for battle in history 
                             if battle.get("type") == "duelo" and 
                             str(author_id) in [battle.get("winner_id"), battle.get("loser_id")]]
                
                if user_duels:
                    last_duel = user_duels[0]  # Most recent
                    winner_id = last_duel.get("winner_id")
                    was_winner = str(author_id) == winner_id
                    opponent_id = last_duel.get("loser_id") if was_winner else last_duel.get("winner_id")
                    opponent_name = last_duel.get("loser_name") if was_winner else last_duel.get("winner_name")
                    timestamp = last_duel.get("timestamp", "")
                    
                    parts.append("**Your last duel:**")
                    parts.append(f"  {'🏆 Victory' if was_winner else '💀 Defeat'} vs **{opponent_name}**")
                    if timestamp:
                        parts.append(f"  🕐 {timestamp}")
                    parts.append("")
                else:
                    parts.append("**Your last duel:** No duels yet")
                    parts.append("")
                    
        except Exception as e:
            logger.debug(f"[ArenaCanvas] Error loading arena data: {e}")

    # Ranking top 5
    if server_id:
        try:
            from roles.arena.arena_db import ArenaDatabase
            db = ArenaDatabase(server_id)
            leaderboard = db.stats.get_leaderboard(limit=5)
            if leaderboard:
                parts.append("**Top 5 Ranking:**")
                for i, f in enumerate(leaderboard, 1):
                    wins = f.get("wins", 0)
                    xp = f.get("xp", 0)
                    uname = f.get("user_id", "???")[:20]
                    parts.append(f"  {i}. {uname} - {wins} wins, {xp:.1f} XP")
                parts.append("")
            else:
                parts.append("**Ranking:** No fighters yet.")
                parts.append("")
        except Exception as e:
            logger.debug(f"[ArenaCanvas] Error loading ranking: {e}")

    return "\n".join(parts)


def build_canvas_role_arena_detail(
    detail_name: str,
    admin_visible: bool,
    guild=None,
    author_id: int = 0,
    agent_config: dict = None,
) -> str | None:
    """Build Arena detail views."""
    if detail_name == "overview":
        return build_canvas_role_arena(agent_config, admin_visible, guild, author_id)

    server_id = get_server_key(guild) if guild else None
    msgs = _get_arena_messages(server_id, guild)

    if detail_name in ("duelo", "duel"):
        title = _text(msgs, "duelo.title", "Duel")
        desc = _text(msgs, "duelo.description", "1v1 challenge against another user.")
        return f"**{title}**\n\n{desc}\n\nUse the 'Challenge' button to challenge someone."

    if detail_name in ("coliseo", "coliseum"):
        title = _text(msgs, "coliseo.title", "Coliseum")
        desc = _text(msgs, "coliseo.description", "Free for all. Minimum 4.")
        lines = [f"**{title}**", "", desc, ""]
        if server_id:
            try:
                from roles.arena.arena_db import ArenaDatabase
                db = ArenaDatabase(server_id)
                event = db.events.get_active_event()
                if event and event.get("type") == "coliseo":
                    status = event.get("status", "???")
                    participants = event.get("participants", {})
                    min_p = event.get("min_participants", 4)
                    sched = event.get("scheduled_for", "")
                    lines.append(f"Status: **{status}**")
                    if sched:
                        lines.append(f"Scheduled for: {sched}")
                    lines.append(f"Participants: {len(participants)}/{min_p}")
                    if participants:
                        names = [p.get("username", "???") for p in participants.values()]
                        lines.append(f"Registered: {', '.join(names[:10])}")
                else:
                    lines.append("No active coliseum.")
            except Exception:
                pass
        return "\n".join(lines)

    if detail_name in ("torneo", "tournament"):
        title = _text(msgs, "torneo.title", "Tournament")
        desc = _text(msgs, "torneo.description", "Elimination. Minimum 8.")
        lines = [f"**{title}**", "", desc, ""]
        if server_id:
            try:
                from roles.arena.arena_db import ArenaDatabase
                db = ArenaDatabase(server_id)
                event = db.events.get_active_event()
                if event and event.get("type") == "torneo":
                    status = event.get("status", "???")
                    participants = event.get("participants", {})
                    min_p = event.get("min_participants", 8)
                    sched = event.get("scheduled_for", "")
                    lines.append(f"Status: **{status}**")
                    if sched:
                        lines.append(f"Scheduled for: {sched}")
                    lines.append(f"Participants: {len(participants)}/{min_p}")
                    if participants:
                        names = [p.get("username", "???") for p in participants.values()]
                        lines.append(f"Registered: {', '.join(names[:10])}")
                else:
                    lines.append("No active tournament.")
            except Exception:
                pass
        return "\n".join(lines)

    if detail_name in ("ranking", "leaderboard"):
        title = _text(msgs, "ranking.title", "Ranking")
        lines = [f"**{title}**", ""]
        if server_id:
            try:
                from roles.arena.arena_db import ArenaDatabase
                db = ArenaDatabase(server_id)
                leaderboard = db.stats.get_leaderboard(limit=10)
                if leaderboard:
                    for i, f in enumerate(leaderboard, 1):
                        wins = f.get("wins", 0)
                        part = f.get("participated", 0)
                        xp = f.get("xp", 0)
                        uname = f.get("user_id", "???")[:20]
                        fp = f.get("fighter_personality", "?")
                        lines.append(f"{i}. {uname} | {wins}W/{part}B | {xp:.1f}XP | {fp}")
                else:
                    lines.append(_text(msgs, "ranking.no_fighters", "No fighters yet."))
            except Exception as e:
                logger.debug(f"[ArenaCanvas] Error loading ranking: {e}")
                lines.append("Error loading ranking.")
        return "\n".join(lines)

    if detail_name in ("armas", "weapons"):
        title = _text(msgs, "weapons.title", "Arsenal")
        desc = _text(msgs, "weapons.description", "Unlocked weapons.")
        lines = [f"**{title}**", "", desc, ""]
        if server_id:
            try:
                from roles.arena.arena_catalogs import get_weapons, get_unlocked_weapons
                from roles.arena.arena_db import ArenaDatabase
                db = ArenaDatabase(server_id)
                fighter = db.stats.get_fighter(str(author_id))
                xp = fighter.get("xp", 0.0)
                active_w = fighter.get("active_weapon")
                all_weapons = get_weapons(server_id)
                unlocked = get_unlocked_weapons(server_id, xp)
                unlocked_ids = {w["id"] for w in unlocked}

                lines.append("**Unlocked:**")
                for w in unlocked:
                    marker = " (equipped)" if w["id"] == active_w else ""
                    lines.append(f"  • {w['name']}{marker} - {w['desc']}")

                lines.append("")
                lines.append("**Locked:**")
                for w in all_weapons:
                    if w["id"] not in unlocked_ids:
                        lines.append(f"  • {w['name']} - Requires {w['unlock_xp']} XP")
            except Exception as e:
                logger.debug(f"[ArenaCanvas] Error loading weapons: {e}")
        return "\n".join(lines)

    if detail_name in ("config", "admin"):
        if not admin_visible:
            return "Only administrators can view this section."
        title = _text(msgs, "admin.title", "Arena Settings")
        desc = _text(msgs, "admin.description", "Module settings.")
        lines = [f"**{title}**", "", desc, ""]
        try:
            from roles.arena.arena import get_arena_config
            cfg = get_arena_config(server_id) if server_id else {}
            lines.append(f"Coliseum minimum: {cfg.get('min_coliseo_participants', 4)}")
            lines.append(f"Tournament minimum: {cfg.get('min_tournament_participants', 8)}")
            lines.append(f"Registration time: {cfg.get('registration_timeout_hours', 24)}h")
            lines.append(f"Coliseum XP: {cfg.get('xp_per_coliseo', 1.0)}")
            lines.append(f"Tournament XP: {cfg.get('xp_per_tournament', 1.0)}")
            lines.append(f"Duel XP: {cfg.get('xp_per_duel', 0.2)}")
        except Exception:
            pass
        # Show active event info
        if server_id:
            try:
                from roles.arena.arena_db import ArenaDatabase
                db = ArenaDatabase(server_id)
                event = db.events.get_active_event()
                if event:
                    etype = event.get("type", "event").capitalize()
                    status = event.get("status", "???")
                    sched = event.get("scheduled_for", "")
                    participants = event.get("participants", {})
                    lines.append("")
                    lines.append(f"**Active event:** {etype} ({status})")
                    if sched:
                        lines.append(f"Scheduled for: {sched}")
                    lines.append(f"Participants: {len(participants)}/{event.get('min_participants', '?')}")
                else:
                    lines.append("")
                    lines.append("**No active event.**")
                    lines.append("Use 'Configure Arena' to propose a coliseum or tournament.")
            except Exception as e:
                logger.debug(f"[ArenaCanvas] Error admin event: {e}")
        return "\n".join(lines)

    # Admin variants of duelo, ranking, armas
    if detail_name == "duelo_admin":
        if not admin_visible:
            return "Only administrators can view this section."
        title = _text(msgs, "duelo.title", "Duel")
        desc = _text(msgs, "duelo.description", "1v1 challenge against another user.")
        lines = [f"**{title}**", "", desc, ""]
        lines.append("**--- Admin Section ---**")
        lines.append("From here you can manage duels.")
        lines.append("Use the dropdown below for admin actions.")
        return "\n".join(lines)

    if detail_name == "ranking_admin":
        if not admin_visible:
            return "Only administrators can view this section."
        title = _text(msgs, "ranking.title", "Ranking")
        lines = [f"**{title}**", ""]
        if server_id:
            try:
                from roles.arena.arena_db import ArenaDatabase
                db = ArenaDatabase(server_id)
                leaderboard = db.stats.get_leaderboard(limit=10)
                if leaderboard:
                    for i, f in enumerate(leaderboard, 1):
                        wins = f.get("wins", 0)
                        part = f.get("participated", 0)
                        xp = f.get("xp", 0)
                        uname = f.get("user_id", "???")[:20]
                        fp = f.get("fighter_personality", "?")
                        lines.append(f"{i}. {uname} | {wins}W/{part}B | {xp:.1f}XP | {fp}")
                else:
                    lines.append(_text(msgs, "ranking.no_fighters", "No fighters yet."))
            except Exception as e:
                logger.debug(f"[ArenaCanvas] Error loading ranking: {e}")
                lines.append("Error loading ranking.")
        lines.append("")
        lines.append("**--- Admin Section ---**")
        lines.append("Use the dropdown below for admin actions.")
        return "\n".join(lines)

    if detail_name == "armas_admin":
        if not admin_visible:
            return "Only administrators can view this section."
        title = _text(msgs, "weapons.title", "Arsenal")
        desc = _text(msgs, "weapons.description", "Unlocked weapons.")
        lines = [f"**{title}**", "", desc, ""]
        if server_id:
            try:
                from roles.arena.arena_catalogs import get_weapons, get_unlocked_weapons
                from roles.arena.arena_db import ArenaDatabase
                db = ArenaDatabase(server_id)
                fighter = db.stats.get_fighter(str(author_id))
                xp = fighter.get("xp", 0.0)
                active_w = fighter.get("active_weapon")
                all_weapons = get_weapons(server_id)
                unlocked = get_unlocked_weapons(server_id, xp)
                unlocked_ids = {w["id"] for w in unlocked}

                lines.append("**Unlocked:**")
                for w in unlocked:
                    marker = " (equipped)" if w["id"] == active_w else ""
                    lines.append(f"  • {w['name']}{marker} - {w['desc']}")

                lines.append("")
                lines.append("**Locked:**")
                for w in all_weapons:
                    if w["id"] not in unlocked_ids:
                        lines.append(f"  • {w['name']} - Requires {w['unlock_xp']} XP")
            except Exception as e:
                logger.debug(f"[ArenaCanvas] Error loading weapons: {e}")
        lines.append("")
        lines.append("**--- Admin Section ---**")
        lines.append("Use the dropdown below for admin actions.")
        return "\n".join(lines)

    return None
