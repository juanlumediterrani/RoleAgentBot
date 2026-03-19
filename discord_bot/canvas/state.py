"""Canvas state helpers."""

from agent_engine import PERSONALITY
from agent_logging import get_logger
from discord_bot.discord_core_commands import (
    _personality_answers,
    get_taboo_state,
    is_taboo_triggered,
    update_taboo_state,
)
from discord_bot.discord_utils import get_server_key

try:
    from roles.banker.db_role_banker import get_banker_db_instance
except Exception:
    get_banker_db_instance = None

try:
    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
except Exception:
    get_news_watcher_db_instance = None

try:
    from roles.trickster.subroles.dice_game.db_dice_game import get_dice_game_db_instance
except Exception:
    get_dice_game_db_instance = None

try:
    from roles.treasure_hunter.poe2.poe2_subrole_manager import get_poe2_manager
except Exception:
    get_poe2_manager = None

try:
    from roles.trickster.subroles.beggar.db_beggar import get_beggar_db_instance
except Exception:
    get_beggar_db_instance = None

logger = get_logger("discord_core")

def _get_canvas_watcher_method_label(guild_id: str) -> str:
    if get_news_watcher_db_instance is None:
        return "Unknown"
    try:
        db_watcher = get_news_watcher_db_instance(guild_id)
        method = db_watcher.get_method_config(guild_id)
    except Exception:
        return "Unknown"
    labels = {
        "flat": "Flat",
        "keyword": "Keyword",
        "general": "General",
    }
    return labels.get(method, str(method).title())


def _get_canvas_watcher_frequency_hours(guild_id: str) -> int:
    if get_news_watcher_db_instance is None:
        return 1
    try:
        db_watcher = get_news_watcher_db_instance(guild_id)
        return int(db_watcher.get_frequency_setting())
    except Exception:
        return 1


def _get_canvas_dice_state(guild) -> dict:
    state = {
        "pot_balance": 0,
        "bet": 1,
        "announcements_active": True,
        "title": _personality_answers.get("dice_game_balance_messages", {}).get("title", "💰 **THE POT - {servidor}** 💰\n"),
    }
    if guild is None or get_dice_game_db_instance is None or get_banker_db_instance is None:
        return state
    try:
        server_key = get_server_key(guild)
        db_dice_game = get_dice_game_db_instance(server_key)
        db_banker = get_banker_db_instance(server_key)
        server_id = str(guild.id)
        config = db_dice_game.get_server_config(server_id)
        db_banker.create_wallet("dice_game_pot", "Dice Game Pot", server_id, guild.name)
        state["pot_balance"] = db_banker.get_balance("dice_game_pot", server_id)
        state["bet"] = config.get("bet_fija", 1)
        state["announcements_active"] = config.get("announcements_active", True)
    except Exception as e:
        logger.warning(f"Could not load dice state for Canvas: {e}")
    return state


def _get_canvas_dice_ranking(guild, limit: int = 5) -> list[dict]:
    if guild is None or get_dice_game_db_instance is None:
        return []
    try:
        server_key = get_server_key(guild)
        db_dice_game = get_dice_game_db_instance(server_key)
        ranking = db_dice_game.get_player_ranking(str(guild.id), "total_won", limit)
        rows: list[dict] = []
        for position, row in enumerate(ranking, 1):
            user_id, _metric_value, total_plays, total_won, total_bet = row
            member = guild.get_member(int(user_id)) if str(user_id).isdigit() else None
            player_name = member.display_name if member is not None else str(user_id)
            balance = total_won - total_bet
            profitability = (total_won / total_bet * 100) if total_bet > 0 else 0
            rows.append({
                "position": position,
                "player_name": player_name,
                "total_plays": total_plays,
                "total_won": total_won,
                "total_bet": total_bet,
                "balance": balance,
                "profitability": profitability,
            })
        return rows
    except Exception as e:
        logger.warning(f"Could not load dice ranking for Canvas: {e}")
        return []


def _get_canvas_dice_history(guild, limit: int = 5) -> list[dict]:
    if guild is None or get_dice_game_db_instance is None:
        return []
    try:
        server_key = get_server_key(guild)
        db_dice_game = get_dice_game_db_instance(server_key)
        history = db_dice_game.get_game_history(str(guild.id), limit)
        rows: list[dict] = []
        for _id, user_id, user_name, _server_id, _server_name, bet, dice, combination, prize, pot_before, pot_after, date in history:
            rows.append({
                "user_id": user_id,
                "user_name": user_name,
                "bet": bet,
                "dice": dice,
                "combination": combination,
                "prize": prize,
                "pot_before": pot_before,
                "pot_after": pot_after,
                "date": str(date)[:16],
            })
        return rows
    except Exception as e:
        logger.warning(f"Could not load dice history for Canvas: {e}")
        return []


def _get_canvas_beggar_state(guild) -> dict:
    state = {
        "enabled": False,
        "frequency_hours": 6,
        "last_reason": "No reason recorded yet",
        "target_gold": 0,
        "fund_balance": 0,
        "title": "Beggar",
        "message": "",
    }
    if guild is None:
        return state
    try:
        beggar_cfg = (_personality_answers.get("subrole_messages", {}) or {})
        state["message"] = beggar_cfg.get("beggar_donation_request", "")
    except Exception:
        pass
    if get_beggar_db_instance is None:
        return state
    try:
        server_key = get_server_key(guild)
        server_id = str(guild.id)
        db_beggar = get_beggar_db_instance(server_key)
        state["enabled"] = db_beggar.is_subscribed(f"server_{server_id}", server_id)
        state["frequency_hours"] = db_beggar.get_frequency_hours(server_id)
        state["last_reason"] = db_beggar.get_last_reason(server_id) or state["last_reason"]
        state["target_gold"] = db_beggar.get_target_gold(server_id)
        if get_banker_db_instance is not None:
            db_banker = get_banker_db_instance(server_key)
            db_banker.create_wallet("beggar_fund", "Beggar Fund", server_id, guild.name)
            state["fund_balance"] = db_banker.get_balance("beggar_fund", server_id)
    except Exception as e:
        logger.warning(f"Could not load beggar state for Canvas: {e}")
    return state


def _get_canvas_ring_state(guild) -> dict:
    """Get ring state from trickster subrole."""
    state = {
        "enabled": False,
        "frequency_hours": 24,
        "target_user_name": "Unknown bearer",
        "title": "Ring",
        "description": "",
    }
    if guild is None:
        return state
    try:
        from roles.trickster.subroles.ring.ring_discord import _get_ring_state
        if _get_ring_state is None:
            return state
        current = _get_ring_state(str(guild.id))
        if current:
            state["enabled"] = current.get("enabled", False)
            state["frequency_hours"] = int(current.get("frequency_hours", 24))
            state["target_user_name"] = current.get("target_user_name", "Unknown bearer")
        # Load description from personality
        subrole_cfg = (PERSONALITY.get("role_system_prompts", {}).get("subroles", {}) or {}).get("ring", {})
        state["description"] = str(subrole_cfg.get("description", "")).strip()
    except Exception as e:
        logger.warning(f"Could not load ring state for Canvas: {e}")
    return state


def _get_canvas_poe2_state(guild, author_id: int | None = None) -> dict:
    state = {
        "activated": False,
        "league": "Standard",
        "objectives": [],
    }
    if guild is None or get_poe2_manager is None:
        return state
    try:
        manager = get_poe2_manager()
        server_id = str(guild.id)
        user_id = str(author_id) if author_id else ""
        state["activated"] = manager.is_activated(server_id)
        state["league"] = manager.get_user_league(user_id, server_id) if user_id else manager.get_active_league(server_id)
        ok, raw = manager.list_objectives(server_id, user_id) if user_id else (True, "")
        if ok and raw:
            items = []
            for line in raw.splitlines():
                stripped = line.strip()
                if ". " in stripped and ("**" in stripped or "*No data*" in stripped):
                    items.append(stripped)
            state["objectives"] = items
    except Exception as e:
        logger.warning(f"Could not load POE2 state for Canvas: {e}")
    return state


def _get_enabled_roles(agent_config: dict) -> list[str]:
    roles_cfg = (agent_config or {}).get("roles", {})
    enabled = []
    for role_name, cfg in roles_cfg.items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("enabled", False):
            enabled.append(role_name)
    return enabled


def _load_role_mission_prompts(role_names: list[str]) -> list[str]:
    prompts: list[str] = []
    role_prompts_cfg = PERSONALITY.get("role_system_prompts", {})

    for role_name in role_names:
        try:
            if role_name == "mc":
                from roles.mc.mc import get_mc_system_prompt
                prompts.append(get_mc_system_prompt())
                continue
            if role_name == "banker":
                from roles.banker.banker import get_banker_system_prompt
                prompts.append(get_banker_system_prompt())
                continue
            if role_name == "treasure_hunter":
                from roles.treasure_hunter.treasure_hunter import get_treasure_hunter_system_prompt
                prompts.append(get_treasure_hunter_system_prompt())
                continue
            if role_name == "trickster":
                from roles.trickster.trickster import get_trickster_system_prompt
                prompts.append(get_trickster_system_prompt())
                continue

            prompt = role_prompts_cfg.get(role_name)
            if prompt:
                prompts.append(prompt)
        except Exception as e:
            logger.warning(f"Could not load role prompt for {role_name}: {e}")
            prompt = role_prompts_cfg.get(role_name)
            if prompt:
                prompts.append(prompt)

    return [p for p in prompts if isinstance(p, str) and p.strip()]


def _build_mission_commentary_prompt(agent_config: dict, server_name: str = "default") -> str:
    """Build a comprehensive mission commentary prompt with personality, memories, and role prompts."""
    enabled_roles = _get_enabled_roles(agent_config)
    mission_prompts = _load_role_mission_prompts(enabled_roles)

    roles_text = "\n".join([f"- {r}" for r in enabled_roles]) if enabled_roles else "- none"
    missions_text = "\n\n".join(mission_prompts) if mission_prompts else "(no mission prompts found)"

    try:
        from agent_mind import generate_daily_memory_summary, generate_recent_memory_summary

        daily_memory = generate_daily_memory_summary(server_name) or ""
        recent_memory = generate_recent_memory_summary(server_name) or ""

        memories_section = ""
        if daily_memory and daily_memory.strip():
            memories_section += f"MEMORIA DIARIA:\n{daily_memory.strip()}\n\n"
        if recent_memory and recent_memory.strip():
            memories_section += f"RECUERDOS RECIENTES:\n{recent_memory.strip()}\n\n"
        if not memories_section:
            memories_section = "MEMORIAS: Sin recuerdos importantes recientes.\n\n"
    except Exception as e:
        logger.warning(f"Could not load memories for commentary: {e}")
        memories_section = "MEMORIAS: No disponibles temporalmente.\n\n"

    custom_cfg = PERSONALITY.get("prompts", {}).get("mission_commentary", {})
    if custom_cfg and isinstance(custom_cfg, dict):
        instructions = custom_cfg.get("instructions", [])
        closing = custom_cfg.get("closing", "")
        if instructions:
            rules_section = "\n".join(instructions) + "\n"
        else:
            rules_section = ""
        if closing:
            closing_section = f"\n{closing}"
        else:
            closing_section = ""
    else:
        rules_section = ""
        closing_section = ""

    return (
        f"**MISSION COMMENTARY TASK**\n\n"
        "You are the agent speaking in character. "
        "Your specific task is: **Make a comment about your active missions**. "
        "Be brief, entertaining, and don't repeat yourself. Incorporate context from your memories if relevant.\n\n"
        f"{rules_section}"
        f"ACTIVE ROLES:\n{roles_text}\n\n"
        f"MISSION CONTEXT:\n{missions_text}\n\n"
        f"{memories_section}"
        "**FINAL INSTRUCTION:** Now produce your commentary on the active missions, incorporating relevant memories if you have them."
        f"{closing_section}"
    )
