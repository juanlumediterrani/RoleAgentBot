"""
Core Discord bot commands.
Includes: help, insult, presence/welcome greetings, test, role control.

⚠️ **IMPORTANT - ROLE MAINTENANCE:**
When modifying roles (add/remove/rename), ALWAYS update:
1. 'valid_roles' list in _cmd_role_toggle (~line 125)
2. 'role_descriptions' dict in cmd_help (~line 237)
3. Help logic in cmd_help for each affected role
4. Verify all used variables are defined (e.g. role_descriptions vs role_display)

COMMON ERROR: NameError from using wrong variable after modifying roles.
"""

import os
import sys
import asyncio
import discord
from pathlib import Path

# Add parent directory to Python path to import root modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_db import AgentDatabase
from agent_logging import get_logger
from agent_engine import PERSONALIDAD, think, AGENT_CFG
from discord_bot.discord_utils import (
    is_admin, is_duplicate_command, send_dm_or_channel, send_embed_dm_or_channel,
    set_greeting_enabled, get_greeting_enabled,
    is_role_enabled_check,
    get_server_key,
    get_role_interval_hours,
    set_role_enabled,
)

try:
    from roles.banker.db_role_banker import get_banker_db_instance
except Exception:
    get_banker_db_instance = None

try:
    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
except Exception:
    get_news_watcher_db_instance = None

try:
    from roles.news_watcher.watcher_messages import get_watcher_messages
except Exception:
    get_watcher_messages = None

try:
    from roles.trickster.subroles.dice_game.db_dice_game import get_dice_game_db_instance
except Exception:
    get_dice_game_db_instance = None

try:
    from roles.trickster.subroles.dice_game.dice_game import DiceGame
except Exception:
    DiceGame = None

try:
    from roles.treasure_hunter.poe2.poe2_subrole_manager import get_poe2_manager
except Exception:
    get_poe2_manager = None

try:
    from roles.trickster.subroles.beggar.db_beggar import get_beggar_db_instance
except Exception:
    get_beggar_db_instance = None

try:
    from behavior.db_behavior import get_behavior_db_instance as get_behaviors_db_instance
except Exception:
    get_behaviors_db_instance = None

try:
    from behavior.taboo.db_taboo import get_taboo_db_instance
except Exception:
    get_taboo_db_instance = None

logger = get_logger('discord_core')

def _load_personality_answers() -> dict:
    try:
        personality_rel = AGENT_CFG.get("personality", "")
        personality_path = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), personality_rel))
        answers_path = personality_path.parent / "answers.json"
        if answers_path.exists():
            import json
            with open(answers_path, encoding="utf-8") as f:
                return json.load(f).get("discord", {})
    except Exception as e:
        logger.warning(f"Could not load personality answers.json: {e}")
    return {}


def _load_personality_descriptions() -> dict:
    try:
        personality_rel = AGENT_CFG.get("personality", "")
        personality_path = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), personality_rel))
        descriptions_path = personality_path.parent / "descriptions.json"
        if descriptions_path.exists():
            import json
            with open(descriptions_path, encoding="utf-8") as f:
                return json.load(f).get("discord", {})
    except Exception as e:
        logger.warning(f"Could not load personality descriptions.json: {e}")
    return {}


_discord_cfg = _load_personality_answers()
_personality_name = PERSONALIDAD.get("name", "bot").lower()
_bot_display_name = PERSONALIDAD.get("bot_display_name", PERSONALIDAD.get("name", "Bot"))
_insult_cfg = PERSONALIDAD.get("insult_command", {})  # Moved from discord.insult_command to prompts.json
_personality_answers = _load_personality_answers()
_personality_descriptions = _load_personality_descriptions()


_talk_state_by_guild_id: dict[int, dict] = {}
_taboo_state_by_guild_id: dict[int, dict] = {}


def get_taboo_state(guild_id: int) -> dict:
    """Get taboo state from database, initializing from prompts.json if needed."""
    state = _taboo_state_by_guild_id.get(guild_id)
    if state is None:
        # Try to get from database first
        if get_taboo_db_instance is not None:
            try:
                server_key = str(guild_id)
                db_taboo = get_taboo_db_instance(server_key)
                
                # Get default keywords from prompts.json
                role_cfg = PERSONALIDAD.get("role_system_prompts", {}).get("subroles", {})
                taboo_defaults = role_cfg.get("taboo", {}) if isinstance(role_cfg, dict) else {}
                default_keywords = list(taboo_defaults.get("keywords", [])) if isinstance(taboo_defaults.get("keywords", []), list) else []
                
                # Initialize database with defaults if empty
                db_taboo.initialize_from_defaults(default_keywords)
                
                # Get current state from database
                state = {
                    "enabled": db_taboo.is_enabled(),
                    "keywords": db_taboo.get_keywords(),
                    "response": taboo_defaults.get("response", "ADVERTENCIA: Esa palabra no es apropiada para este kampamento!")
                }
                
            except Exception as e:
                logger.warning(f"Error accessing taboo database for guild {guild_id}: {e}")
                # Fallback to in-memory state
                role_cfg = PERSONALIDAD.get("role_system_prompts", {}).get("subroles", {})
                taboo_defaults = role_cfg.get("taboo", {}) if isinstance(role_cfg, dict) else {}
                state = {
                    "enabled": False,
                    "keywords": list(taboo_defaults.get("keywords", [])) if isinstance(taboo_defaults.get("keywords", []), list) else [],
                    "response": taboo_defaults.get("response", "ADVERTENCIA: Esa palabra no es apropiada para este kampamento!")
                }
        else:
            # Fallback to prompts.json only
            role_cfg = PERSONALIDAD.get("role_system_prompts", {}).get("subroles", {})
            taboo_defaults = role_cfg.get("taboo", {}) if isinstance(role_cfg, dict) else {}
            state = {
                "enabled": False,
                "keywords": list(taboo_defaults.get("keywords", [])) if isinstance(taboo_defaults.get("keywords", []), list) else [],
                "response": taboo_defaults.get("response", "ADVERTENCIA: Esa palabra no es apropiada para este kampamento!")
            }
        
        _taboo_state_by_guild_id[guild_id] = state
    return state


def update_taboo_state(guild_id: int, enabled: bool = None, keywords: list = None) -> bool:
    """Update taboo state in database."""
    if get_taboo_db_instance is None:
        logger.warning("Taboo database not available, cannot update state")
        return False
    
    try:
        server_key = str(guild_id)
        db_taboo = get_taboo_db_instance(server_key)
        
        # Update enabled status if provided
        if enabled is not None:
            db_taboo.set_enabled(enabled)
            _taboo_state_by_guild_id[guild_id]["enabled"] = enabled
        
        # Update keywords if provided
        if keywords is not None:
            # Get current keywords
            current_keywords = set(db_taboo.get_keywords())
            new_keywords = set(kw.lower().strip() for kw in keywords if kw.strip())
            
            # Add new keywords
            for keyword in new_keywords - current_keywords:
                db_taboo.add_keyword(keyword, "admin_update")
            
            # Remove keywords not in new list
            for keyword in current_keywords - new_keywords:
                db_taboo.remove_keyword(keyword)
            
            _taboo_state_by_guild_id[guild_id]["keywords"] = list(new_keywords)
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating taboo state for guild {guild_id}: {e}")
        return False


def is_taboo_triggered(guild_id: int, content: str) -> tuple[bool, str | None]:
    state = get_taboo_state(guild_id)
    if not state.get("enabled", False):
        return False, None
    text = (content or "").lower()
    for keyword in state.get("keywords", []):
        kw = str(keyword).strip().lower()
        if kw and kw in text:
            return True, kw
    return False, None


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
        subrole_cfg = (PERSONALIDAD.get("role_system_prompts", {}).get("subroles", {}) or {}).get("ring", {})
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


def _build_canvas_sections(agent_config: dict, greet_name: str, nogreet_name: str, welcome_name: str, nowelcome_name: str,
                           role_cmd_name: str, talk_cmd_name: str, admin_visible: bool, server_name: str = "default",
                           author_id: int = 0, guild=None) -> dict[str, str]:
    """Build the top-level Canvas sections for the current user context."""
    return {
        "home": _build_canvas_home(
            agent_config, greet_name, nogreet_name, welcome_name, nowelcome_name, role_cmd_name, talk_cmd_name,
            admin_visible, server_name, author_id
        ),
        "behavior": _build_canvas_behavior(
            greet_name, nogreet_name, welcome_name, nowelcome_name, role_cmd_name, talk_cmd_name, admin_visible
        ),
        "roles": _build_canvas_roles(agent_config, admin_visible, guild),
        "personal": _build_canvas_personal(),
        "help": _build_canvas_help(),
    }


def _build_canvas_embed(section_name: str, content: str, admin_visible: bool) -> discord.Embed:
    # Get behavior title from personality descriptions for consistency
    if section_name == "behavior":
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        behavior_title = behavior_descriptions.get("canvas_conversation_title", f"💬 {_bot_display_name} Comportamiento General")
        # Replace {_bot} placeholder
        behavior_title = behavior_title.replace("{_bot}", _bot_display_name)
        # Remove ** for embed title
        behavior_title = behavior_title.replace("**", "")
        titles = {
            "home": f"🧭 {_bot_display_name} Canvas Hub",
            "behavior": behavior_title,
            "roles": "🎭 Roles de Putre 🎭",
            "personal": f"👤 {_bot_display_name} Canvas - Personal Space",
            "help": f"📚 {_bot_display_name} Canvas - Help & Troubleshooting",
        }
    else:
        titles = {
            "home": f"🧭 {_bot_display_name} Canvas Hub",
            "behavior": f"⚙️ {_bot_display_name} Canvas - General Behavior",
            "roles": "🎭 Roles de Putre 🎭",
            "personal": f"👤 {_bot_display_name} Canvas - Personal Space",
            "help": f"📚 {_bot_display_name} Canvas - Help & Troubleshooting",
        }
    colors = {
        "home": discord.Color.blurple(),
        "behavior": discord.Color.orange(),
        "roles": discord.Color.purple(),
        "personal": discord.Color.teal(),
        "help": discord.Color.gold(),
    }
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    description = ""

    if section_name == "home":
        personality_line = next((line for line in lines if line.startswith("**Personality:**")), "")
        roles_line = next((line for line in lines if line.startswith("**Active roles:**")), "")
        description_parts = [part for part in [personality_line.replace("**", ""), roles_line.replace("**", "")] if part]
        description = "\n".join(description_parts)
    elif section_name == "home_status":
        personality_line = next((line for line in lines if line.startswith("**Personality:**")), "")
        roles_line = next((line for line in lines if line.startswith("**Active roles:**")), "")
        description_parts = [part for part in [personality_line.replace("**", ""), roles_line.replace("**", "")] if part]
        description = "\n".join(description_parts)
    elif section_name == "roles":
        description = ""  # Empty description - title will be the main content
    elif section_name == "personal":
        description = "Focus on private or user-specific workflows that continue naturally in DM."
    elif section_name == "help":
        description = "Find command entry points, troubleshooting hints, and the fastest recovery paths."
    elif section_name == "behavior":
        description = "Shared bot behavior that sits above any individual role."

    embed = discord.Embed(
        title=titles.get(section_name, f"{_bot_display_name} Canvas"),
        description=description[:4096],
        color=colors.get(section_name, discord.Color.blurple()),
    )
    blocks = _split_canvas_blocks(content)
    for block_title, block_lines in blocks[:4]:
        filtered_lines = [
            line for line in block_lines
            if not (section_name in {"home", "home_status"} and (line.startswith("**Personality:**") or line.startswith("**Active roles:**")))
        ]
        value = "\n".join(filtered_lines)[:1024]
        if value:
            embed.add_field(name=block_title, value=value, inline=False)
    embed.set_footer(text=f"Canvas section: {section_name}")
    return embed


def _split_canvas_blocks(content: str) -> list[tuple[str, list[str]]]:
    """Split Canvas plain text into titled blocks for embed rendering."""
    blocks: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("**") and line.endswith("**") and len(line) > 4:
            if current_lines:
                blocks.append((current_title, current_lines))
            current_title = line.strip("*")
            current_lines = []
            continue
        current_lines.append(line)

    if current_lines:
        blocks.append((current_title, current_lines))
    return blocks


def _get_canvas_role_gui_controls(role_name: str, surface_name: str, admin_visible: bool) -> list[str]:
    controls_map: dict[str, dict[str, list[str]]] = {
        "news_watcher": {
            "overview": [
                "- Buttons: open `Personal` or `Admin`",
                "- Boolean toggle: quick alerts on/off (`watchernotify`)",
                "- Text input: category or feed to subscribe",
            ],
            "personal": [
                "- Select menu: subscription method (flat, keyword, general)",
                "- Select menu: category/feed selection before subscribing",
                "- Text input: feed id when a category requires a specific source",
                "- Boolean toggle: critical alerts on/off",
            ],
            "admin": [
                "- Select menu: filtering state `flat`, `keyword`, or `general`",
                "- Number input: watcher frequency in hours",
                "- Text input: category/feed for channel subscription",
                "- Boolean action: force one iteration now",
            ],
        },
        "treasure_hunter": {
            "overview": [
                "- Buttons: open `Items`, `League`, or `Admin`",
                "- Text input: tracked item name",
                "- Select menu: league selection",
            ],
            "personal": [
                "- Text input: item name to add/remove",
                "- Select menu: tracked items shortcuts",
                "- Select menu: open league management",
            ],
            "league": [
                "- Select menu: choose target league",
                "- Text input: custom league name if needed",
            ],
            "admin": [
                "- Boolean toggle: POE2 subrole on/off",
                "- Number input: execution frequency in hours",
            ],
        },
        "trickster": {
            "overview": [
                "- Buttons: open `Dice`, `Ring`, or `Beggar`",
                "- Boolean toggles: subrole enable/disable where applicable",
            ],
            "dice": [
                "- Number input: fixed bet amount",
                "- Boolean toggle: announcements on/off",
                "- Action button: play now",
            ],
            "ring": [
                "- Boolean toggle: ring on/off",
                "- Number input: ring frequency in hours",
                "- User picker/text input: accusation target",
            ],
            "beggar": [
                "- Boolean toggle: beggar on/off",
                "- Number input: beggar frequency in hours",
            ],
        },
        "banker": {
            "overview": [
                "- Buttons: open `Wallet`, `Guide`, or `Admin`",
                "- Number input: economy values for admin setup",
            ],
            "wallet": [
                "- Action button: refresh wallet view",
                "- Select menu: recent wallet/help shortcuts",
            ],
            "guide": [
                "- Select menu: choose `Wallet` or `Admin` focus",
            ],
            "admin": [
                "- Number input: daily allowance (`tae`)",
                "- Number input: opening bonus",
            ],
        },
        "mc": {
            "overview": [
                "- Text input: song/query to play or add",
                "- Select menu: queue/history actions",
                "- Boolean-style action buttons: pause/resume/stop",
            ],
        },
    }
    role_controls = controls_map.get(role_name, {})
    controls = role_controls.get(surface_name, [])
    if not admin_visible:
        controls = [line for line in controls if "admin" not in line.lower()]
    return controls


def _build_canvas_role_embed(role_name: str, content: str, admin_visible: bool, surface_name: str = "overview", user=None,
                             auto_response: str | None = None) -> discord.Embed:
    """Render a role/detail Canvas screen with a role-specific embed layout."""
    role_titles = {
        "news_watcher": "📡 News Watcher",
        "treasure_hunter": "💎 Treasure Hunter",
        "trickster": "🎭 Trickster",
        "banker": "💰 Banker",
        "mc": "🎵 MC",
    }
    role_colors = {
        "news_watcher": discord.Color.blue(),
        "treasure_hunter": discord.Color.dark_gold(),
        "trickster": discord.Color.magenta(),
        "banker": discord.Color.green(),
        "mc": discord.Color.purple(),
    }

    # Process all content as blocks, including intro
    blocks = _split_canvas_blocks(content)
    
    # Use the first block as title and description if available
    title = f"{_bot_display_name} Canvas"
    description = ""
    
    if blocks:
        first_block_title, first_block_lines = blocks[0]
        if first_block_lines:
            title = first_block_title
            # Use ALL lines from first block as description, not just the first one
            description = "\n".join(first_block_lines)
            # Skip the first block for field processing
        blocks_to_process = blocks[1:4]  # Take next 3 blocks
    else:
        blocks_to_process = []

    embed = discord.Embed(
        title=title.replace("**", ""),
        description=description,
        color=role_colors.get(role_name, discord.Color.blurple()),
    )

    last_block_index = len(blocks_to_process) - 1
    for index, (block_title, block_lines) in enumerate(blocks_to_process):
        value = _merge_canvas_block_with_auto_response(block_lines, auto_response) if index == last_block_index else _truncate_canvas_field_value("\n".join(block_lines))
        if value:
            embed.add_field(name=block_title, value=value, inline=False)

    embed.set_footer(text=f"{role_titles.get(role_name, role_name)} • {'admin' if admin_visible else 'user'} view")
    
    # Add user thumbnail for banker role (like !banker balance)
    if role_name == "banker" and user and hasattr(user, 'display_avatar'):
        embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)
    
    return embed


def _truncate_canvas_field_value(value: str, limit: int = 1024) -> str:
    value = (value or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _merge_canvas_block_with_auto_response(block_lines: list[str], auto_response: str | None) -> str:
    base_value = "\n".join(block_lines).strip()
    response_value = (auto_response or "").strip()
    if not response_value:
        return _truncate_canvas_field_value(base_value)
    merged = "\n".join([
        base_value,
        "",
        "**Automatic Response**",
        response_value,
    ]).strip()
    return _truncate_canvas_field_value(merged)


def _get_canvas_auto_response_preview(role_name: str | None = None, action_name: str | None = None) -> str | None:
    if not action_name:
        return None

    role_action_map: dict[str, dict[str, str]] = {
        "news_watcher": {
            "method_flat": "Watcher method set to `flat`.",
            "method_keyword": "Watcher method set to `keyword`.",
            "method_general": "Watcher method set to `general`.",
            "list_categories": "Showing the available watcher categories.",
            "list_feeds": "Showing the available watcher feeds.",
            "list_keywords": "Showing your configured watcher keywords.",
            "list_premises": "Showing your configured watcher premises.",
            "subscribe_categories": "The bot will ask for category details and create the watcher subscription after you confirm the modal.",
            "add_keywords": "The bot will ask for the keyword text and append it to your watcher filters.",
            "delete_keywords": "The bot will ask which keyword to remove from your watcher filters.",
            "add_premises": "The bot will ask for the premise text and store it for AI-based watcher filtering.",
            "delete_premises": "The bot will ask which premise to remove from your watcher configuration.",
            "channel_subscribe_categories": "The bot will ask for channel subscription details and publish future watcher alerts in this channel.",
            "channel_view_subscriptions": "Showing the current watcher channel subscriptions for this server.",
            "channel_unsubscribe": "The bot will ask for the subscription number to remove from this channel.",
            "watcher_frequency": "The bot will ask for the watcher frequency in hours and apply it server-wide.",
            "watcher_run_now": "The watcher will run immediately and publish any matching notifications.",
        },
        "treasure_hunter": {
            "poe2_item_add": "The bot will ask for an item name and add it to your tracked POE2 objectives.",
            "poe2_item_remove": "The bot will ask for an item name or visible number and remove it from your tracked objectives.",
            "league_standard": "League updated to `Standard`.",
            "league_fate_of_the_vaal": "League updated to `Fate of the Vaal`.",
            "league_hardcore": "League updated to `Hardcore`.",
            "poe2_on": "POE2 subrole enabled for this server.",
            "poe2_off": "POE2 subrole disabled for this server.",
            "hunter_frequency": "The bot will ask for the hunter execution frequency in hours and update the scheduler.",
        },
        "trickster": {
            "dice_play": "The bot will roll the dice for you and post the result.",
            "dice_ranking": "Showing the current dice ranking for this server.",
            "dice_history": "Showing the most recent dice results.",
            "dice_help": "Showing the dice help and rules.",
            "announcements_on": "Dice announcements enabled for this server.",
            "announcements_off": "Dice announcements disabled for this server.",
            "dice_fixed_bet": "The bot will ask for the fixed bet amount and update the dice game configuration.",
            "dice_pot_value": "The bot will ask for the new pot value and update the dice game balance.",
            "ring_accuse": "The bot will ask for a target user and generate a public ring accusation.",
            "ring_on": "Ring enabled for this server.",
            "ring_off": "Ring disabled for this server.",
            "ring_frequency": "The bot will ask for the ring frequency in hours and update the schedule.",
            "beggar_donate": "The bot will ask for the donation amount and transfer gold from your wallet.",
            "beggar_on": "Beggar enabled for this server.",
            "beggar_off": "Beggar disabled for this server.",
            "beggar_frequency": "The bot will ask for the beggar frequency in hours and update the schedule.",
        },
        "banker": {
            "config_tae": "The bot will ask for the daily TAE value and update the banker configuration.",
            "config_bonus": "The bot will ask for the opening bonus value and update the banker configuration.",
        },
        "mc": {
            "mc_play": "The bot will ask for a song or query and start playback.",
            "mc_add": "The bot will ask for a song or query and add it to the queue.",
            "mc_skip": "The bot will skip the current song.",
            "mc_pause": "Playback paused.",
            "mc_resume": "Playback resumed.",
            "mc_stop": "Playback stopped and the queue cleared.",
            "mc_queue": "Showing the current queue.",
            "mc_clear": "Queue cleared.",
            "mc_history": "Showing recent playback history.",
            "mc_volume": "The bot will ask for a new volume value.",
        },
    }
    behavior_action_map = {
        "greetings_on": "Presence greetings enabled for this server.",
        "greetings_off": "Presence greetings disabled for this server.",
        "welcome_on": "Welcome messages enabled for this server.",
        "welcome_off": "Welcome messages disabled for this server.",
        "commentary_on": "Mission commentary enabled for this server.",
        "commentary_off": "Mission commentary disabled for this server.",
        "commentary_now": "The bot will generate and post commentary immediately.",
        "commentary_frequency": "The bot will ask for the commentary interval in minutes and update the schedule.",
        "taboo_on": "Taboo enabled for this server.",
        "taboo_off": "Taboo disabled for this server.",
        "taboo_list": "Showing the current taboo keywords.",
        "taboo_add": "The bot will ask for a keyword and add it to the taboo list.",
        "taboo_del": "The bot will ask for a keyword and remove it from the taboo list.",
        "role_control_open": "The bot will ask which role to enable or disable for this server.",
    }

    if role_name:
        return role_action_map.get(role_name, {}).get(action_name)
    return behavior_action_map.get(action_name)


def _build_canvas_behavior_embed(content: str, admin_visible: bool, auto_response: str | None = None) -> discord.Embed:
    """Render a General Behavior Canvas screen with a specific embed layout."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    title_line = lines[0] if lines else f"{_bot_display_name} Canvas - General Behavior"
    embed = discord.Embed(
        title=title_line.replace("**", ""),
        color=discord.Color.orange() if admin_visible else discord.Color.dark_orange(),
    )
    blocks = _split_canvas_blocks(content)
    visible_blocks = blocks[:4]
    last_block_index = len(visible_blocks) - 1
    for index, (block_title, block_lines) in enumerate(visible_blocks):
        value = _merge_canvas_block_with_auto_response(block_lines, auto_response) if index == last_block_index else _truncate_canvas_field_value("\n".join(block_lines))
        if value:
            embed.add_field(name=block_title, value=value, inline=False)
    embed.set_footer(text=f"General Behavior • {'admin' if admin_visible else 'user'} view")
    return embed


def _get_canvas_behavior_action_items(admin_visible: bool) -> list[tuple[str, str, str]]:
    if not admin_visible:
        return []
    return [
        ("Greetings: On", "greetings_on", "Boolean toggle"),
        ("Greetings: Off", "greetings_off", "Boolean toggle"),
        ("Welcome: On", "welcome_on", "Boolean toggle"),
        ("Welcome: Off", "welcome_off", "Boolean toggle"),
        ("Commentary: On", "commentary_on", "Boolean toggle"),
        ("Commentary: Off", "commentary_off", "Boolean toggle"),
        ("Commentary: Now", "commentary_now", "Action"),
        ("Role Control", "role_control_open", "Select role and boolean state"),
    ]


def _get_canvas_behavior_action_items_for_detail(detail_name: str, admin_visible: bool) -> list[tuple[str, str, str]]:
    if not admin_visible:
        return []
    items_map: dict[str, list[tuple[str, str, str]]] = {
        "greetings": [
            ("Greetings: On", "greetings_on", "Boolean toggle"),
            ("Greetings: Off", "greetings_off", "Boolean toggle"),
        ],
        "welcome": [
            ("Welcome: On", "welcome_on", "Boolean toggle"),
            ("Welcome: Off", "welcome_off", "Boolean toggle"),
        ],
        "commentary": [
            ("Commentary: On", "commentary_on", "Boolean toggle"),
            ("Commentary: Off", "commentary_off", "Boolean toggle"),
            ("Commentary: Now", "commentary_now", "Action"),
            ("Commentary: Frequency", "commentary_frequency", "Number input target"),
        ],
        "taboo": [
            ("Taboo: On", "taboo_on", "Boolean toggle"),
            ("Taboo: Off", "taboo_off", "Boolean toggle"),
            ("Taboo: List", "taboo_list", "Action"),
            ("Taboo: Add Keyword", "taboo_add", "Text input target"),
            ("Taboo: Remove Keyword", "taboo_del", "Text input target"),
        ],
        "role_control": [
            ("Role Control", "role_control_open", "Select role and boolean state"),
        ],
    }
    return items_map.get(detail_name, [])


def _get_canvas_behavior_detail_items(admin_visible: bool) -> list[tuple[str, str]]:
    items = [("Conversation", "conversation")]
    if admin_visible:
        items.extend([
            ("Greetings", "greetings"),
            ("Welcome", "welcome"),
            ("Commentary", "commentary"),
            ("Taboo", "taboo"),
            ("Role Control", "role_control"),
        ])
    return items


def _get_canvas_role_detail_items(role_name: str, admin_visible: bool, current_detail: str | None = None) -> list[tuple[str, str]]:
    trickster_personal_map = {
        "dice": "dice",
        "dice_admin": "dice",
        "ring": "ring",
        "ring_admin": "ring",
        "beggar": "beggar",
        "beggar_admin": "beggar",
    }
    trickster_admin_map = {
        "dice": "dice_admin",
        "dice_admin": "dice_admin",
        "ring": "ring_admin",
        "ring_admin": "ring_admin",
        "beggar": "beggar_admin",
        "beggar_admin": "beggar_admin",
    }
    items_map: dict[str, list[tuple[str, str]]] = {
        "news_watcher": [
            ("Personal", "personal"),
        ] + ([("Admin", "admin")] if admin_visible else []),
        "treasure_hunter": [
            ("Items", "personal"),
            ("League", "league"),
        ] + ([("Admin", "admin")] if admin_visible else []),
        "trickster": (
            [("Personal", trickster_personal_map.get(current_detail or "dice", "dice"))]
            + ([("Admin", trickster_admin_map.get(current_detail or "dice", "dice_admin"))] if admin_visible else [])
        ) if current_detail in {"dice", "ring", "beggar", "dice_admin", "ring_admin", "beggar_admin"} else [
            ("Dice", "dice"),
            ("Ring", "ring"),
            ("Beggar", "beggar"),
        ],
        "banker": [
            ("Wallet", "overview"),  # Wallet maps to overview since they're the same view
        ] + ([("Admin", "admin")] if admin_visible else []),
        "mc": [
            ("Overview", "overview"),
        ],
    }
    return items_map.get(role_name, [])


def _get_canvas_role_action_items_for_detail(role_name: str, detail_name: str, admin_visible: bool) -> list[tuple[str, str, str]]:
    if role_name == "news_watcher":
        if detail_name in {"personal", "overview"}:  # Same view for both
            return [
                ("Method: Flat", "method_flat", "Set subscription method to flat"),
                ("Method: Keyword", "method_keyword", "Set subscription method to keyword"),
                ("Method: General", "method_general", "Set subscription method to general"),
                ("Subscribe: Categories", "subscribe_categories", "Browse and subscribe to categories"),
                ("List: Keywords", "list_keywords", "View your configured keywords"),
                ("List: Premises", "list_premises", "View your configured premises"),
            ]
        if detail_name == "admin" and admin_visible:
            return [
                ("Watcher: Frequency", "watcher_frequency", "Number input target"),
                ("Watcher: Run Now", "watcher_run_now", "Action"),
            ]
        return []

    if role_name == "treasure_hunter":
        if detail_name == "league":
            return [
                ("League: Standard", "league_standard", "Choose POE2 league"),
                ("League: Fate of the Vaal", "league_fate_of_the_vaal", "Choose POE2 league"),
                ("League: Hardcore", "league_hardcore", "Choose POE2 league"),
            ]
        if detail_name == "personal":
            return [
                ("Items: Add", "poe2_item_add", "Add a new POE2 item"),
                ("Items: Remove", "poe2_item_remove", "Remove a tracked POE2 item"),
            ]
        if detail_name == "admin" and admin_visible:
            return [
                ("POE2: On", "poe2_on", "Activate POE2 subrole"),
                ("POE2: Off", "poe2_off", "Deactivate POE2 subrole"),
                ("Hunter: Frequency", "hunter_frequency", "Number input target"),
            ]
        return []

    if role_name == "trickster":
        if detail_name == "dice":
            return [
                ("Dice: Play", "dice_play", "Play action"),
                ("Dice: Ranking", "dice_ranking", "Ranking action"),
                ("Dice: History", "dice_history", "History action"),
                ("Dice: Help", "dice_help", "Help action"),
            ]
        if detail_name == "dice_admin" and admin_visible:
            return [
                ("Announcements: On", "announcements_on", "Dice config"),
                ("Announcements: Off", "announcements_off", "Dice config"),
                ("Dice: Fixed Bet", "dice_fixed_bet", "Number input target"),
                ("Dice: Pot Value", "dice_pot_value", "Number input target"),
            ]
        if detail_name == "ring":
            return [
                ("Ring: Accuse", "ring_accuse", "User target input"),
            ]
        if detail_name == "ring_admin" and admin_visible:
            return [
                ("Ring: On", "ring_on", "Boolean toggle"),
                ("Ring: Off", "ring_off", "Boolean toggle"),
                ("Ring: Frequency", "ring_frequency", "Number input target"),
            ]
        if detail_name == "beggar":
            return [
                ("Beggar: Donate", "beggar_donate", "Number input target"),
            ]
        if detail_name == "beggar_admin" and admin_visible:
            return [
                ("Beggar: On", "beggar_on", "Boolean toggle"),
                ("Beggar: Off", "beggar_off", "Boolean toggle"),
                ("Beggar: Frequency", "beggar_frequency", "Number input target"),
            ]
        return []

    if role_name == "banker" and admin_visible and detail_name == "admin":
        return [
            ("Config: TAE", "config_tae", "Number input target"),
            ("Config: Bonus", "config_bonus", "Number input target"),
        ]
    
    if role_name == "mc":
        return [
            ("Play Now", "mc_play", "Text input target"),
            ("Add to Queue", "mc_add", "Text input target"),
            ("Skip Song", "mc_skip", "Action"),
            ("Pause", "mc_pause", "Action"),
            ("Resume", "mc_resume", "Action"),
            ("Stop", "mc_stop", "Action"),
            ("View Queue", "mc_queue", "Action"),
            ("Clear Queue", "mc_clear", "Action"),
            ("Show History", "mc_history", "Action"),
            ("Set Volume", "mc_volume", "Number input"),
        ] if detail_name == "overview" else []

    return []


def _get_canvas_role_action_items(role_name: str, admin_visible: bool) -> list[tuple[str, str, str]]:
    actions: list[tuple[str, str, str]] = []
    for _label, detail_name in _get_canvas_role_detail_items(role_name, admin_visible):
        actions.extend(_get_canvas_role_action_items_for_detail(role_name, detail_name, admin_visible))
    return actions


def _build_canvas_behavior_action_view(action_name: str, admin_visible: bool) -> str | None:
    if not admin_visible:
        return None
    action_map = {
        "greetings_on": ("Presence greetings", "On", f"`!greet{_personality_name}`", "Boolean toggle"),
        "greetings_off": ("Presence greetings", "Off", f"`!nogreet{_personality_name}`", "Boolean toggle"),
        "welcome_on": ("Welcome messages", "On", f"`!welcome{_personality_name}`", "Boolean toggle"),
        "welcome_off": ("Welcome messages", "Off", f"`!nowelcome{_personality_name}`", "Boolean toggle"),
        "commentary_on": ("Mission commentary", "On", f"`!talk{_personality_name} on`", "Boolean toggle"),
        "commentary_off": ("Mission commentary", "Off", f"`!talk{_personality_name} off`", "Boolean toggle"),
        "commentary_now": ("Mission commentary", "Run now", f"`!talk{_personality_name} now`", "Action button"),
        "commentary_frequency": ("Mission commentary", "Frequency", f"`!talk{_personality_name} frequency <minutes>`", "Number input"),
        "taboo_on": ("Taboo", "On", "`!taboo on`", "Boolean toggle"),
        "taboo_off": ("Taboo", "Off", "`!taboo off`", "Boolean toggle"),
        "taboo_list": ("Taboo", "List", "`!taboo list`", "Action"),
        "taboo_add": ("Taboo", "Add keyword", "`!taboo add <keyword>`", "Text input"),
        "taboo_del": ("Taboo", "Remove keyword", "`!taboo del <keyword>`", "Text input"),
        "role_control_open": ("Role control", "Choose role + on/off", f"`!role{_personality_name} <role> <on|off>`", "Select menu + boolean toggle"),
    }
    selected = action_map.get(action_name)
    if not selected:
        return None
    surface, state, command_name, input_type = selected
    return "\n".join([
        f"⚙️ **{_bot_display_name} Canvas - General Behavior Action Choice**\n",
        "**Selected option**",
        f"- Surface: {surface}",
        f"- State or action: {state}",
        f"- Command: {command_name}",
        "",
        "**GUI input model**",
        f"- Input type: {input_type}",
        "",
        "**Next step**",
        "- Apply the change only if you want to affect the whole server behavior",
    ])


def _build_canvas_role_action_view(role_name: str, action_name: str, admin_visible: bool) -> str | None:
    if role_name == "news_watcher":
        # Method selection actions
        method_map = {
            "method_flat": ("Flat Method", "`!watcher method flat`", "All news with AI opinions.", "Server-wide method selection"),
            "method_keyword": ("Keyword Method", "`!watcher method keyword`", "News filtered by keywords.", "Server-wide method selection"),
            "method_general": ("General Method", "`!watcher method general`", "AI critical news analysis.", "Server-wide method selection"),
        }
        
        # Subscription and listing actions
        subscription_map = {
            "subscribe_categories": ("Subscribe Categories", "`!watcher subscribe <method> <category> [feed_id]`", "Browse and subscribe to news categories.", "Category selection + method"),
            "list_keywords": ("List Keywords", "`!watcher keywords list`", "View your configured keywords.", "Display current keywords"),
            "list_premises": ("List Premises", "`!watcher premises list`", "View your AI analysis premises.", "Display current premises"),
        }
        
        # Check subscription/listing actions first
        selected = subscription_map.get(action_name)
        if selected:
            label, command_name, explanation, input_type = selected
            return "\n".join([
                f"📡 **{_bot_display_name} Canvas - News Watcher: {label}**\n",
                "**Selected option**",
                f"- Command: {command_name}",
                f"- Meaning: {explanation}",
                "",
                "**GUI input model**",
                f"- Input type: {input_type}",
                "- Best use: manage your subscriptions and configuration",
                "",
                "**Next step**",
                "- Browse available options and make selections",
                "- Configure your filtering preferences",
            ])
        
        # Check method actions
        selected = method_map.get(action_name)
        if selected:
            label, command_name, explanation, input_type = selected
            return "\n".join([
                f"📡 **{_bot_display_name} Canvas - News Watcher: {label}**\n",
                "**Selected option**",
                f"- Command: {command_name}",
                f"- Meaning: {explanation}",
                "",
                "**GUI input model**",
                f"- Input type: {input_type}",
                "- Best use: set default behavior for new subscriptions",
                "",
                "**Next step**",
                "- Choose method that matches your news preferences",
                "- Configure specific filtering if needed",
            ])

    if role_name == "treasure_hunter":
        league_map = {
            "league_standard": "Standard",
            "league_fate_of_the_vaal": "Fate of the Vaal",
            "league_hardcore": "Hardcore",
        }
        selected_league = league_map.get(action_name)
        if selected_league:
            return "\n".join([
                f"💎 **{_bot_display_name} Canvas - Treasure Hunter League Choice**\n",
                "**Selected option**",
                f"- League: `{selected_league}`",
                f"- Command: `!hunter poe2 league \"{selected_league}\"`",
                "",
                "**GUI input model**",
                "- Input type: select menu with league options",
                "- Fallback: text input for a custom league name if needed",
                "",
                "**Next step**",
                "- Apply the league and then review your tracked items",
            ])
        if action_name == "poe2_item_add":
            return "\n".join([
                f"💎 **{_bot_display_name} Canvas - Treasure Hunter Add Item**\n",
                "**Selected option**",
                "- Command: `!hunter poe2 add \"Item Name\"`",
                "",
                "**GUI input model**",
                "- Input type: text input",
                "- Validation: exact POE2 item name",
            ])
        if action_name == "poe2_item_remove":
            return "\n".join([
                f"💎 **{_bot_display_name} Canvas - Treasure Hunter Remove Item**\n",
                "**Selected option**",
                "- Command: `!hunter poe2 del \"Item Name\"`",
                "",
                "**GUI input model**",
                "- Input type: text input",
                "- Validation: item name or visible item number",
            ])
        if action_name in {"poe2_on", "poe2_off"} and admin_visible:
            state = "On" if action_name == "poe2_on" else "Off"
            return "\n".join([
                f"💎 **{_bot_display_name} Canvas - Treasure Hunter POE2 Toggle**\n",
                "**Selected option**",
                f"- State: {state}",
                f"- Command: `!hunter poe2 {'on' if action_name == 'poe2_on' else 'off'}`",
                "",
                "**GUI input model**",
                "- Input type: boolean selector",
            ])
        if action_name == "hunter_frequency" and admin_visible:
            return "\n".join([
                f"💎 **{_bot_display_name} Canvas - Treasure Hunter Frequency**\n",
                "**Selected option**",
                "- Command: `!hunterfrequency <hours>`",
                "- Meaning: adjust how often treasure hunter runs automatically",
                "",
                "**GUI input model**",
                "- Input type: number input",
                "- Valid range: 1 to 168 hours",
                "",
                "**Next step**",
                "- Choose a stable interval before enabling more tracked items",
            ])

    if role_name == "trickster":
        action_map = {
            "ring_on": ("Ring", "On", "`!trickster ring enable`", "Boolean toggle"),
            "ring_off": ("Ring", "Off", "`!trickster ring disable`", "Boolean toggle"),
            "ring_frequency": ("Ring", "Frequency", "`!trickster ring frequency <hours>`", "Number input"),
            "ring_accuse": ("Ring", "Accuse", "`!accuse @user`", "User input"),
            "beggar_on": ("Beggar", "On", "`!trickster beggar enable`", "Boolean toggle"),
            "beggar_off": ("Beggar", "Off", "`!trickster beggar disable`", "Boolean toggle"),
            "beggar_frequency": ("Beggar", "Frequency", "`!trickster beggar frequency <hours>`", "Number input"),
            "beggar_donate": ("Beggar", "Donate", "`!trickster beggar donate <gold>`", "Number input"),
            "announcements_on": ("Dice announcements", "On", "`!dice config announcements on`", "Boolean toggle"),
            "announcements_off": ("Dice announcements", "Off", "`!dice config announcements off`", "Boolean toggle"),
            "dice_fixed_bet": ("Dice fixed bet", "Set", "`!dice config bet <amount>`", "Number input"),
            "dice_pot_value": ("Dice pot", "Set", "Banker wallet update", "Number input"),
            "dice_play": ("Dice", "Play", "`!dice play`", "Action"),
            "dice_ranking": ("Dice", "Ranking", "`!dice ranking`", "Action"),
            "dice_history": ("Dice", "History", "`!dice history`", "Action"),
            "dice_help": ("Dice", "Help", "`!dice help`", "Action"),
        }
        selected = action_map.get(action_name)
        if selected:
            surface, value, command_name, input_type = selected
            return "\n".join([
                f"🎭 **{_bot_display_name} Canvas - Trickster Action Choice**\n",
                "**Selected option**",
                f"- Surface: {surface}",
                f"- State: {value}",
                f"- Command: {command_name}",
                "",
                "**GUI input model**",
                f"- Input type: {input_type}",
                "",
                "**Next step**",
                "- Apply the change and observe the subrole behavior on the server",
            ])

    if role_name == "banker" and admin_visible:
        config_map = {
            "config_tae": ("Daily allowance", "Configure daily TAE from unified view"),
            "config_bonus": ("Opening bonus", "Configure opening bonus from unified view"),
        }
        selected = config_map.get(action_name)
        if selected:
            label, command_name = selected
            return "\n".join([
                f"💰 **{_bot_display_name} Canvas - Banker Config Target**\n",
                "**Selected option**",
                f"- Target: {label}",
                f"- Command pattern: {command_name}",
                "",
                "**GUI input model**",
                "- Input type: number input",
                "- Validation: accept only positive numeric values",
                "",
                "**Next step**",
                "- Inspect the current value before changing it",
            ])

    if role_name == "mc":
        playback_map = {
            "playback_play": ("Play", "`!mc play \"song name\"`", "Text input"),
            "playback_add": ("Add", "`!mc add \"song name\"`", "Text input"),
            "queue_show": ("Queue", "`!mc queue`", "Action button"),
        }
        selected = playback_map.get(action_name)
        if selected:
            label, command_name, input_type = selected
            return "\n".join([
                f"🎵 **{_bot_display_name} Canvas - MC Action Choice**\n",
                "**Selected option**",
                f"- Action: {label}",
                f"- Command: {command_name}",
                "",
                "**GUI input model**",
                f"- Input type: {input_type}",
                "",
                "**Next step**",
                "- Use this action from a server voice-channel context",
            ])

    if role_name == "mc":
        action_map = {
            "mc_play": ("Play Now", "`!mc play <song>`", "Immediately play a song (replaces current)", "Text input with song name/URL"),
            "mc_add": ("Add to Queue", "`!mc add <song>`", "Add song to end of queue", "Text input with song name/URL"),
            "mc_skip": ("Skip", "`!mc skip`", "Skip current song", "Action button"),
            "mc_pause": ("Pause", "`!mc pause`", "Pause current playback", "Action button"),
            "mc_resume": ("Resume", "`!mc resume`", "Resume paused playback", "Action button"),
            "mc_stop": ("Stop", "`!mc stop`", "Stop playback and clear queue", "Action button"),
            "mc_queue": ("View Queue", "`!mc queue`", "Show current playback queue", "Action button"),
            "mc_clear": ("Clear Queue", "`!mc clear`", "Clear entire queue (DJ only)", "Action button"),
            "mc_history": ("History", "`!mc history`", "Show recently played songs", "Action button"),
            "mc_volume": ("Volume", "`!mc volume <0-100>`", "Adjust playback volume", "Number input 0-100"),
        }
        selected = action_map.get(action_name)
        if selected:
            label, command_name, explanation, input_type = selected
            return "\n".join([
                f"🎵 **{_bot_display_name} Canvas - MC Action: {label}**\n",
                "**Selected option**",
                f"- Command: {command_name}",
                f"- Meaning: {explanation}",
                "",
                "**GUI input model**",
                f"- Input type: {input_type}",
                "",
                "**Next step**",
                "- Use this action from a server voice-channel context",
            ])

    return None


def _get_canvas_role_action_surface_name(role_name: str, action_name: str) -> str:
    if role_name == "news_watcher" and action_name.startswith("method_"):
        return "overview"  # Same view for both overview and personal
    if role_name == "news_watcher" and action_name.startswith("subscribe_"):
        return "overview"  # Same view for both overview and personal
    if role_name == "news_watcher" and action_name.startswith("list_"):
        return "overview"  # Same view for both overview and personal
    if role_name == "treasure_hunter" and action_name.startswith("league_"):
        return "league"
    if role_name == "treasure_hunter" and action_name.startswith("poe2_item_"):
        return "personal"
    if role_name == "treasure_hunter" and action_name.startswith("poe2_"):
        return "admin"
    if role_name == "trickster":
        if action_name.startswith("ring_"):
            return "ring" if action_name == "ring_accuse" else "ring_admin"
        if action_name.startswith("beggar_"):
            return "beggar" if action_name == "beggar_donate" else "beggar_admin"
        if action_name.startswith("announcements_"):
            return "dice_admin"
        if action_name.startswith("dice_"):
            return "dice_admin" if action_name in {"dice_fixed_bet", "dice_pot_value"} else "dice"
    if role_name == "banker" and action_name.startswith("config_"):
        return "admin"
    if role_name == "mc":
        return "overview"
    return "overview"


class CanvasSectionSelect(discord.ui.Select):
    def __init__(self, admin_visible: bool):
        options = [
            discord.SelectOption(label="Home", value="home", description="Canvas hub and overview"),
            discord.SelectOption(label="Roles", value="roles", description="Browse role surfaces"),
            discord.SelectOption(label="Behavior", value="behavior", description="Shared bot behavior"),
            discord.SelectOption(label="Personal", value="personal", description="Private and user flows"),
            discord.SelectOption(label="Help", value="help", description="Troubleshooting and commands"),
        ]
        if admin_visible:
            options.append(discord.SelectOption(label="Setup", value="setup", description="Server administration"))
        super().__init__(placeholder="Choose a Canvas surface...", min_values=1, max_values=1, options=options, row=3)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasNavigationView):
            await interaction.response.send_message("❌ Canvas section navigation is not available.", ephemeral=True)
            return
        selected = self.values[0]
        if selected == "roles":
            roles_content = view.sections.get("roles")
            if not roles_content:
                await interaction.response.send_message("❌ This Canvas section is not available.", ephemeral=True)
                return
            roles_view = CanvasRolesView(view.author_id, view.agent_config, view.admin_visible, view.sections)
            roles_embed = _build_canvas_embed("roles", roles_content, view.admin_visible)
            await interaction.response.edit_message(content=None, embed=roles_embed, view=roles_view)
            # Set the message reference for timeout deletion
            roles_view.message = interaction.message
            return
        if selected == "behavior":
            behavior_content = view.sections.get("behavior")
            if not behavior_content:
                await interaction.response.send_message("❌ This Canvas section is not available.", ephemeral=True)
                return
            behavior_view = CanvasBehaviorView(view.author_id, view.sections, view.admin_visible, view.agent_config, current_detail="conversation", guild=interaction.guild)
            behavior_embed = _build_canvas_behavior_embed(behavior_content, view.admin_visible)
            await interaction.response.edit_message(content=None, embed=behavior_embed, view=behavior_view)
            # Set the message reference for timeout deletion
            behavior_view.message = interaction.message
            return
        await view._show_section(interaction, selected)


class CanvasRoleSelect(discord.ui.Select):
    def __init__(self, agent_config: dict):
        role_labels = {
            "news_watcher": ("Watcher", "Alerts and subscriptions"),
            "treasure_hunter": ("Treasure Hunter", "Tracked item opportunities"),
            "trickster": ("Trickster", "Subroles and player surfaces"),
            "banker": ("Banker", "Wallet and economy"),
            "mc": ("MC", "Music and queue controls"),
        }
        options = []
        for role_name in _get_enabled_roles(agent_config):
            label, description = role_labels.get(role_name, (role_name.replace("_", " ").title(), "Role surface"))
            options.append(discord.SelectOption(label=label, value=role_name, description=description))
        if (agent_config or {}).get("roles", {}).get("mc", {}).get("enabled", False) and not any(option.value == "mc" for option in options):
            options.append(discord.SelectOption(label="MC", value="mc", description="Music and queue controls"))
        # Add list option to show all available roles
        options.append(discord.SelectOption(label="List All Roles", value="list", description="Show complete list of available roles"))
        super().__init__(placeholder="Choose a role surface...", min_values=1, max_values=1, options=options[:25], row=3)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRolesView):
            await interaction.response.send_message("❌ Canvas role navigation is not available.", ephemeral=True)
            return
        role_name = self.values[0]
        
        # Handle list option
        if role_name == "list":
            await self._handle_list_option(interaction, view)
            return
            
        content = _build_canvas_role_view(role_name, view.agent_config, view.admin_visible, interaction.guild, view.author_id)
        if not content:
            await interaction.response.send_message("❌ This role is not available.", ephemeral=True)
            return
        detail_view = CanvasRoleDetailView(view.author_id, role_name, view.agent_config, view.admin_visible, view.sections, guild=interaction.guild)
        role_embed = _build_canvas_role_embed(role_name, content, view.admin_visible, "overview", interaction.user, detail_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=role_embed, view=detail_view)
        # Set the message reference for timeout deletion
        detail_view.message = interaction.message

    async def _handle_list_option(self, interaction: discord.Interaction, view):
        """Handle the 'list' option to show all available roles."""
        all_roles = ["news_watcher", "treasure_hunter", "trickster", "banker", "mc"]
        enabled_roles = _get_enabled_roles(view.agent_config)
        
        role_labels = {
            "news_watcher": ("Watcher", "Alerts and subscriptions"),
            "treasure_hunter": ("Treasure Hunter", "Tracked item opportunities"),
            "trickster": ("Trickster", "Subroles and player surfaces"),
            "banker": ("Banker", "Wallet and economy"),
            "mc": ("MC", "Music and queue controls"),
        }
        
        embed = discord.Embed(
            title=f"📋 {_bot_display_name} - All Available Roles",
            description="Complete list of available roles and their status",
            color=discord.Color.blue()
        )
        
        for role_name in all_roles:
            label, description = role_labels.get(role_name, (role_name.replace("_", " ").title(), "Role surface"))
            status = "✅ Enabled" if role_name in enabled_roles else "❌ Disabled"
            embed.add_field(
                name=f"{label} {status}",
                value=description,
                inline=False
            )
        
        await interaction.response.edit_message(embed=embed, view=view)


class CanvasRoleDetailSelect(discord.ui.Select):
    def __init__(self, role_name: str, admin_visible: bool):
        options = [
            discord.SelectOption(label=label, value=detail_name, description=f"Focus on {label.lower()} tasks")
            for label, detail_name in _get_canvas_role_detail_items(role_name, admin_visible)
        ]
        super().__init__(placeholder="Choose a role surface...", min_values=1, max_values=1, options=options[:25], row=3)
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRoleDetailView):
            await interaction.response.send_message("❌ Canvas role detail navigation is not available.", ephemeral=True)
            return
        detail_name = self.values[0]
        content = _build_canvas_role_detail_view(self.role_name, detail_name, view.agent_config, view.admin_visible, view.guild, view.author_id)
        if not content:
            await interaction.response.send_message("❌ This role detail is not available.", ephemeral=True)
            return
        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail=detail_name,
            guild=view.guild,
            message=interaction.message  # Add message reference
        )
        detail_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, detail_name, None, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


class CanvasWatcherMethodSelect(discord.ui.Select):
    """Dynamic method selection dropdown for News Watcher."""
    
    def __init__(self, view: "CanvasRoleDetailView"):
        options = [
            discord.SelectOption(label="Method: Flat", value="method_flat", description="All news with AI opinions", emoji="📰"),
            discord.SelectOption(label="Method: Keyword", value="method_keyword", description="News filtered by keywords", emoji="🔍"),
            discord.SelectOption(label="Method: General", value="method_general", description="AI critical news analysis", emoji="🤖"),
        ]
        super().__init__(placeholder="🔧 Select method...", options=options, min_values=1, max_values=1, row=0)
        self.canvas_view = view

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        self.canvas_view.watcher_selected_method = action_name.replace("method_", "")
        self.canvas_view.watcher_last_action = None
        self.canvas_view.auto_response_preview = _get_canvas_auto_response_preview(self.canvas_view.role_name, action_name)
        for child in self.canvas_view.children:
            if isinstance(child, CanvasWatcherSubscriptionSelect):
                child.set_method(self.canvas_view.watcher_selected_method)
        content = _build_canvas_role_news_watcher_detail(
            self.canvas_view.current_detail,
            self.canvas_view.admin_visible,
            self.canvas_view.guild,
            self.canvas_view.author_id,
            selected_method=self.canvas_view.watcher_selected_method,
            last_action=self.canvas_view.watcher_last_action,
        )
        embed = _build_canvas_role_embed(
            self.canvas_view.role_name,
            content or "",
            self.canvas_view.admin_visible,
            self.canvas_view.current_detail,
            None,
            self.canvas_view.auto_response_preview,
        )
        await interaction.response.edit_message(content=None, embed=embed, view=self.canvas_view)


class CanvasWatcherSubscriptionSelect(discord.ui.Select):
    """Dynamic subscription dropdown for News Watcher based on selected method."""
    
    def __init__(self, view: "CanvasRoleDetailView"):
        super().__init__(placeholder="📋 Select action...", options=self._build_options(view.watcher_selected_method), min_values=1, max_values=1, row=1)
        self.canvas_view = view

    def _build_options(self, method: str | None) -> list[discord.SelectOption]:
        # Fixed options for listing categories and feeds
        options = [
            discord.SelectOption(label="Categories", value="list_categories", description="List available categories", emoji="📂"),
            discord.SelectOption(label="Feeds", value="list_feeds", description="List available feeds", emoji="🔗"),
        ]
        # Add method-specific options for subscription
        if method:
            options.append(discord.SelectOption(label="Subscribe Categories", value="subscribe_categories", description=f"Subscribe to categories with {method} method", emoji="➕"))
        # Add method-specific configuration options
        if method == "keyword":
            options.append(discord.SelectOption(label="Keywords", value="list_keywords", description="View your configured keywords", emoji="🔍"))
            options.append(discord.SelectOption(label="Add Keywords", value="add_keywords", description="Add new keywords", emoji="➕"))
            options.append(discord.SelectOption(label="Delete Keywords", value="delete_keywords", description="Remove keywords", emoji="🗑️"))
        elif method == "general":
            options.append(discord.SelectOption(label="Premises", value="list_premises", description="View your AI analysis premises", emoji="🤖"))
            options.append(discord.SelectOption(label="Add Premises", value="add_premises", description="Add new premises", emoji="➕"))
            options.append(discord.SelectOption(label="Delete Premises", value="delete_premises", description="Remove premises", emoji="🗑️"))
        return options

    def set_method(self, method: str | None) -> None:
        self.options = self._build_options(method)

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        self.canvas_view.watcher_last_action = action_name
        
        # Handle subscription actions with modal
        if action_name == "subscribe_categories":
            await interaction.response.send_modal(CanvasWatcherSubscribeModal(action_name, self.canvas_view, interaction.client))
            return
        
        # Handle add actions with modal
        if action_name in {"add_keywords", "add_premises"}:
            await interaction.response.send_modal(CanvasWatcherAddModal(action_name, self.canvas_view, interaction.client))
            return
        
        # Handle delete actions with modal
        if action_name in {"delete_keywords", "delete_premises"}:
            await interaction.response.send_modal(CanvasWatcherDeleteModal(action_name, self.canvas_view, interaction.client))
            return
        
        # Handle listing actions by updating the view
        if action_name in {"list_categories", "list_feeds", "list_keywords", "list_premises"}:
            content = _build_canvas_role_news_watcher_detail(
                self.canvas_view.current_detail,
                self.canvas_view.admin_visible,
                self.canvas_view.guild,
                self.canvas_view.author_id,
                selected_method=self.canvas_view.watcher_selected_method,
                last_action=action_name,
            )
            embed = _build_canvas_role_embed(
                self.canvas_view.role_name,
                content or "",
                self.canvas_view.admin_visible,
                self.canvas_view.current_detail,
                None,
                self.canvas_view.auto_response_preview,
            )
            await interaction.response.edit_message(content=None, embed=embed, view=self.canvas_view)


class CanvasWatcherAdminMethodSelect(discord.ui.Select):
    """Dynamic method selection dropdown for News Watcher Admin."""
    
    def __init__(self, view: "CanvasRoleDetailView"):
        options = [
            discord.SelectOption(label="Method: Flat", value="method_flat", description="All news with AI opinions (server default)", emoji="📰"),
            discord.SelectOption(label="Method: Keyword", value="method_keyword", description="News filtered by keywords (server default)", emoji="🔍"),
            discord.SelectOption(label="Method: General", value="method_general", description="AI critical news analysis (server default)", emoji="🤖"),
        ]
        super().__init__(placeholder="🔧 Set server method...", options=options, min_values=1, max_values=1, row=0)
        self.canvas_view = view

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        self.canvas_view.watcher_selected_method = action_name.replace("method_", "")
        self.canvas_view.watcher_last_action = None
        self.canvas_view.auto_response_preview = _get_canvas_auto_response_preview(self.canvas_view.role_name, action_name)
        await _handle_canvas_watcher_action(interaction, action_name, self.canvas_view)


class CanvasWatcherAdminActionSelect(discord.ui.Select):
    """Dynamic admin action dropdown for News Watcher."""
    
    def __init__(self, view: "CanvasRoleDetailView"):
        options = [
            # Fixed listing options at the top
            discord.SelectOption(label="Categories", value="list_categories", description="List available categories", emoji="📂"),
            discord.SelectOption(label="Feeds", value="list_feeds", description="List available feeds", emoji="🔗"),
            # Channel management options
            discord.SelectOption(label="Channel: Subscribe", value="channel_subscribe_categories", description="Add channel subscription", emoji="➕"),
            discord.SelectOption(label="Channel: View Subs", value="channel_view_subscriptions", description="View current channel subs", emoji="📋"),
            discord.SelectOption(label="Channel: Unsubscribe", value="channel_unsubscribe", description="Cancel channel sub by number", emoji="🗑️"),
            # Server management options
            discord.SelectOption(label="Server: Set Frequency", value="watcher_frequency", description="Set news check frequency", emoji="⏰"),
            discord.SelectOption(label="Server: Force Run", value="watcher_run_now", description="Run news check immediately", emoji="▶️"),
        ]
        super().__init__(placeholder="⚙️ Select admin action...", options=options, min_values=1, max_values=1, row=1)
        self.canvas_view = view

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        self.canvas_view.watcher_last_action = action_name
        
        # Handle listing actions by updating the view
        if action_name in {"list_categories", "list_feeds"}:
            content = _build_canvas_role_news_watcher_detail(
                "admin",
                self.canvas_view.admin_visible,
                self.canvas_view.guild,
                self.canvas_view.author_id,
                selected_method=self.canvas_view.watcher_selected_method,
                last_action=action_name,
            )
            embed = _build_canvas_role_embed(
                self.canvas_view.role_name,
                content or "",
                self.canvas_view.admin_visible,
                "admin",
                None,
                self.canvas_view.auto_response_preview,
            )
            try:
                await interaction.response.edit_message(content=None, embed=embed, view=self.canvas_view)
            except discord.InteractionResponded:
                # If interaction was already responded to, use followup
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self.canvas_view)
            except discord.NotFound:
                # Message was deleted, send a new one
                await interaction.followup.send(embed=embed, view=self.canvas_view, ephemeral=True)
            except Exception as e:
                logger.exception(f"Failed to edit canvas watcher admin message: {e}")
                await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
            return
        
        # Handle other actions through the main handler
        await _handle_canvas_watcher_action(interaction, action_name, self.canvas_view)


class CanvasRoleActionSelect(discord.ui.Select):
    def __init__(self, role_name: str, detail_name: str, admin_visible: bool):
        options = [
            discord.SelectOption(label=label, value=value, description=description)
            for label, value, description in _get_canvas_role_action_items_for_detail(role_name, detail_name, admin_visible)
        ]
        super().__init__(placeholder="Choose a concrete option...", min_values=1, max_values=1, options=options[:25], row=2)
        self.role_name = role_name
        self.detail_name = detail_name

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRoleDetailView):
            await interaction.response.send_message("❌ Canvas role action selection is not available.", ephemeral=True)
            return
        action_name = self.values[0]
        view.auto_response_preview = _get_canvas_auto_response_preview(self.role_name, action_name)
        if self.role_name == "banker" and action_name in {"config_tae", "config_bonus"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This banker option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(BankerConfigModal(action_name))
            return
        if action_name in {"watcher_frequency", "hunter_frequency"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This role option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(RoleFrequencyModal(self.role_name, action_name, view.agent_config, view))
            return
        if self.role_name == "treasure_hunter" and action_name in {"poe2_item_add", "poe2_item_remove"}:
            if not interaction.guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return
            await interaction.response.send_modal(Poe2ItemModal(action_name, view.author_id, interaction.guild, view))
            return
        if self.role_name == "treasure_hunter" and action_name in {"league_standard", "league_fate_of_the_vaal", "league_hardcore", "poe2_on", "poe2_off"}:
            if not interaction.guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return
            await _handle_canvas_treasure_hunter_action(interaction, action_name, view)
            return
        if self.role_name == "trickster" and action_name in {"dice_fixed_bet", "dice_pot_value", "ring_frequency", "beggar_frequency", "beggar_donate", "ring_accuse"}:
            if not interaction.guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return
            await interaction.response.send_modal(TricksterActionModal(action_name, view.author_id, interaction.guild, view.admin_visible))
            return
        if self.role_name == "trickster" and action_name in {"dice_play", "dice_ranking", "dice_history", "dice_help"}:
            if not interaction.guild:
                await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
                return
            await _handle_canvas_dice_action(interaction, action_name, view)
            return
        if self.role_name == "news_watcher" and action_name in {"method_flat", "method_keyword", "method_general", "watcher_run_now"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This watcher option is admin-only.", ephemeral=True)
                return
            await _handle_canvas_watcher_action(interaction, action_name, view)
            return
        if self.role_name == "trickster" and action_name in {"announcements_on", "announcements_off", "ring_on", "ring_off", "beggar_on", "beggar_off"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This trickster option is admin-only.", ephemeral=True)
                return
            await _handle_canvas_trickster_action(interaction, action_name, view)
            return
        if self.role_name == "mc":
            if not interaction.guild:
                await interaction.response.send_message("❌ MC actions are only available in a server.", ephemeral=True)
                return
            await _handle_canvas_mc_action(interaction, action_name, view)
            return
        content = _build_canvas_role_action_view(self.role_name, action_name, view.admin_visible)
        if not content:
            await interaction.response.send_message("❌ This role option is not available.", ephemeral=True)
            return
        surface_name = _get_canvas_role_action_surface_name(self.role_name, action_name)
        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail=surface_name,
            guild=view.guild,
        )
        next_view.message = interaction.message
        next_view.auto_response_preview = view.auto_response_preview
        action_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, surface_name, None, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=action_embed, view=next_view)




class CanvasMCActionSelect(discord.ui.Select):
    """MC (Music Controller) action selection dropdown."""
    
    def __init__(self, view: "CanvasRoleDetailView"):
        # Get MC action items
        mc_actions = _get_canvas_role_action_items_for_detail("mc", "overview", view.admin_visible)
        options = [
            discord.SelectOption(label=label, value=value, description=description)
            for label, value, description in mc_actions
        ]
        super().__init__(placeholder="🎵 Select MC action...", min_values=1, max_values=1, options=options[:25], row=1)
        self.canvas_view = view

    async def callback(self, interaction: discord.Interaction):
        action_name = self.values[0]
        view = self.canvas_view
        
        if not interaction.guild:
            await interaction.response.send_message("❌ MC actions are only available in a server.", ephemeral=True)
            return
            
        await _handle_canvas_mc_action(interaction, action_name, view)


class CanvasBehaviorActionSelect(discord.ui.Select):
    def __init__(self, detail_name: str, admin_visible: bool):
        options = [
            discord.SelectOption(label=label, value=value, description=description)
            for label, value, description in _get_canvas_behavior_action_items_for_detail(detail_name, admin_visible)
        ]
        super().__init__(placeholder="Choose a concrete option...", min_values=1, max_values=1, options=options[:25], row=2)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasBehaviorView):
            await interaction.response.send_message("❌ Canvas behavior action selection is not available.", ephemeral=True)
            return
        action_name = self.values[0]
        view.auto_response_preview = _get_canvas_auto_response_preview(action_name=action_name)
        if action_name == "commentary_frequency":
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(CommentaryFrequencyModal(view))
            return
        if action_name in {"taboo_add", "taboo_del"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            await interaction.response.send_modal(TabooKeywordModal(action_name, int(interaction.guild.id), view))
            return
        if action_name in {"taboo_on", "taboo_off"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            guild_id = int(interaction.guild.id)
            enabled = action_name == "taboo_on"
            if update_taboo_state(guild_id, enabled=enabled):
                content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config)
                view.auto_response_preview = f"Taboo {'enabled' if enabled else 'disabled'} for this server."
                behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
            else:
                await interaction.response.send_message("❌ Failed to update taboo state. Check logs for details.", ephemeral=True)
            return
        
        # Handle greetings toggle
        if action_name in {"greetings_on", "greetings_off"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            enabled = action_name == "greetings_on"
            try:
                from discord_bot.discord_utils import set_greeting_enabled
                set_greeting_enabled(interaction.guild, enabled)
                content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config)
                view.auto_response_preview = f"Greetings {'enabled' if enabled else 'disabled'} for this server."
                behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
            except Exception as e:
                logger.error(f"Error updating greetings state: {e}")
                await interaction.response.send_message("❌ Failed to update greetings state. Check logs for details.", ephemeral=True)
            return
        
        # Handle welcome toggle
        if action_name in {"welcome_on", "welcome_off"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            enabled = action_name == "welcome_on"
            try:
                # Update in-memory config
                greeting_cfg = _discord_cfg.get("member_greeting", {})
                greeting_cfg["enabled"] = enabled

                # Save to behaviors database
                if get_behaviors_db_instance is not None:
                    guild_id = str(interaction.guild.id)
                    db = get_behaviors_db_instance(guild_id)
                    db.set_welcome_enabled(enabled, f"{interaction.user.name}")
                
                content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config)
                view.auto_response_preview = f"Welcome messages {'enabled' if enabled else 'disabled'} for this server."
                behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
            except Exception as e:
                logger.error(f"Error updating welcome state: {e}")
                await interaction.response.send_message("❌ Failed to update welcome state. Check logs for details.", ephemeral=True)
            return
        
        # Handle commentary toggle
        if action_name in {"commentary_on", "commentary_off"}:
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            enabled = action_name == "commentary_on"
            try:
                guild_id = int(interaction.guild.id)
                state = _talk_state_by_guild_id.get(guild_id, {})
                state["enabled"] = enabled
                
                # Save to behaviors database
                if get_behaviors_db_instance is not None:
                    db = get_behaviors_db_instance(str(guild_id))
                    config = {
                        "channel_id": state.get("channel_id"),
                        "interval_minutes": state.get("interval_minutes", 180)
                    }
                    db.set_commentary_state(enabled, config, f"{interaction.user.name}")
                
                content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config)
                view.auto_response_preview = f"Commentary {'enabled' if enabled else 'disabled'} for this server."
                behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
            except Exception as e:
                logger.error(f"Error updating commentary state: {e}")
                await interaction.response.send_message("❌ Failed to update commentary state. Check logs for details.", ephemeral=True)
            return
        # Handle commentary now action
        if action_name == "commentary_now":
            if not interaction.guild or not view.admin_visible:
                await interaction.response.send_message("❌ This behavior option is admin-only.", ephemeral=True)
                return
            try:
                server_name = get_server_key(interaction.guild) if interaction.guild else "default"
                prompt = _build_mission_commentary_prompt(view.agent_config, server_name)
                res = await asyncio.to_thread(
                    think,
                    role_context=_bot_display_name,
                    user_content=prompt,
                    logger=logger,
                    server_name=server_name,
                    interaction_type="mission",
                )
                if res and str(res).strip():
                    content = _build_canvas_behavior_detail(view.current_detail, view.admin_visible, view.guild, view.agent_config)
                    view.auto_response_preview = str(res).strip()
                    behavior_embed = _build_canvas_behavior_embed(content or "", view.admin_visible, view.auto_response_preview)
                    await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)
                else:
                    await interaction.response.send_message("⚠️ Could not generate commentary right now.", ephemeral=True)
            except Exception as e:
                logger.error(f"Error generating commentary: {e}")
                await interaction.response.send_message("❌ Failed to generate commentary. Check logs for details.", ephemeral=True)
            return
        
        # Fallback for other behavior actions
        content = _build_canvas_behavior_action_view(action_name, view.admin_visible)
        if not content:
            await interaction.response.send_message("❌ This behavior option is not available.", ephemeral=True)
            return
        behavior_embed = _build_canvas_behavior_embed(content, view.admin_visible, view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=behavior_embed, view=view)


class CanvasNavigationView(discord.ui.View):
    """Interactive button-based Canvas navigation for top-level sections."""

    def __init__(self, author_id: int, sections: dict[str, str], admin_visible: bool, agent_config: dict, message=None, show_dropdown=True):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.sections = sections
        self.admin_visible = admin_visible
        self.agent_config = agent_config
        self.message = message  # Store the message to delete it later
        if show_dropdown:
            self.add_item(CanvasSectionSelect(admin_visible))

    async def on_timeout(self) -> None:
        """Called when the view times out - delete the entire message."""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if self.message:
                    await self.message.delete()
                self.stop()
                return  # Success, exit the method
            except discord.NotFound:
                # Message already deleted, just stop the view
                self.stop()
                return
            except discord.Forbidden:
                # If we can't delete the message, at least disable the buttons
                for child in self.children:
                    child.disabled = True
                self.stop()
                return
            except Exception as e:
                if attempt == max_attempts - 1:  # Last attempt
                    logger.warning(f"Could not delete Canvas message on timeout after {max_attempts} attempts: {e}")
                    # Fallback: disable buttons
                    for child in self.children:
                        child.disabled = True
                    self.stop()
                else:
                    # Brief delay before retry
                    await asyncio.sleep(0.1)

    async def _show_section(self, interaction: discord.Interaction, section_name: str):
        content = self.sections.get(section_name)
        if not content:
            await interaction.response.send_message("❌ This Canvas section is not available.", ephemeral=True)
            return
        embed = _build_canvas_embed(section_name, content, self.admin_visible)
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive Canvas to its original user."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Home", style=discord.ButtonStyle.secondary)
    async def home_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show_section(interaction, "home")


    @discord.ui.button(label="Roles", style=discord.ButtonStyle.success)
    async def roles_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles_content = self.sections.get("roles")
        if not roles_content:
            await interaction.response.send_message("❌ This Canvas section is not available.", ephemeral=True)
            return
        roles_view = CanvasRolesView(self.author_id, self.agent_config, self.admin_visible, self.sections)
        roles_view.message = interaction.message
        roles_embed = _build_canvas_embed("roles", roles_content, self.admin_visible)
        await interaction.response.edit_message(content=None, embed=roles_embed, view=roles_view)
        # Set the message reference for timeout deletion
        roles_view.message = interaction.message

    @discord.ui.button(label="Behavior", style=discord.ButtonStyle.success)
    async def behavior_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        behavior_content = self.sections.get("behavior")
        if not behavior_content:
            await interaction.response.send_message("❌ This Canvas section is not available.", ephemeral=True)
            return
        behavior_view = CanvasBehaviorView(self.author_id, self.sections, self.admin_visible, self.agent_config, current_detail="conversation", guild=interaction.guild)
        behavior_embed = _build_canvas_behavior_embed(behavior_content, self.admin_visible)
        await interaction.response.edit_message(content=None, embed=behavior_embed, view=behavior_view)
        behavior_view.message = interaction.message

    
    @discord.ui.button(label="Help", style=discord.ButtonStyle.primary)
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show_section(interaction, "help")

    def update_visibility(self):
        """Hide or disable admin-only controls according to current permissions."""
        if not self.admin_visible:
            for child in self.children:
                if getattr(child, "label", "") == "Setup":
                    child.disabled = True
                    break


class CanvasRolesView(discord.ui.View):
    """Interactive role navigation for enabled roles."""

    def __init__(self, author_id: int, agent_config: dict, admin_visible: bool, sections: dict[str, str], message=None):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.agent_config = agent_config
        self.admin_visible = admin_visible
        self.sections = sections
        self.message = message  # Store the message to delete it later
        self._add_role_buttons()

    async def on_timeout(self) -> None:
        """Called when the view times out - delete the entire message."""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if self.message:
                    await self.message.delete()
                self.stop()
                return  # Success, exit the method
            except discord.NotFound:
                # Message already deleted, just stop the view
                self.stop()
                return
            except discord.Forbidden:
                # If we can't delete the message, at least disable the buttons
                for child in self.children:
                    child.disabled = True
                self.stop()
                return
            except Exception as e:
                if attempt == max_attempts - 1:  # Last attempt
                    logger.warning(f"Could not delete Canvas message on timeout after {max_attempts} attempts: {e}")
                    # Fallback: disable buttons
                    for child in self.children:
                        child.disabled = True
                    self.stop()
                else:
                    # Brief delay before retry
                    await asyncio.sleep(0.1)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive Canvas to its original user."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True

    def _add_role_buttons(self):
        """Add a button for each enabled role."""
        role_labels = {
            "news_watcher": "Watcher",
            "treasure_hunter": "Hunter",
            "trickster": "Trickster",
            "banker": "Banker",
            "mc": "MC",
        }
        for role_name in _get_enabled_roles(self.agent_config):
            label = role_labels.get(role_name, role_name.replace("_", " ").title())
            self.add_item(CanvasRoleButton(label=label, role_name=role_name))
        if (self.agent_config or {}).get("roles", {}).get("mc", {}).get("enabled", False) and "mc" not in _get_enabled_roles(self.agent_config):
            self.add_item(CanvasRoleButton(label="MC", role_name="mc"))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.primary, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        home_content = self.sections.get("home")
        if not home_content:
            await interaction.response.send_message("❌ The Canvas home is not available.", ephemeral=True)
            return
        nav_view = CanvasNavigationView(self.author_id, self.sections, self.admin_visible, self.agent_config, show_dropdown=False)
        nav_view.update_visibility()
        nav_view.message = interaction.message
        home_embed = _build_canvas_embed("home", home_content, self.admin_visible)
        await interaction.response.edit_message(content=None, embed=home_embed, view=nav_view)


class CanvasRoleButton(discord.ui.Button):
    """Button that opens one Canvas role view."""

    def __init__(self, label: str, role_name: str):
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRolesView):
            await interaction.response.send_message("❌ Canvas role navigation is not available.", ephemeral=True)
            return

        content = _build_canvas_role_view(
            self.role_name,
            view.agent_config,
            view.admin_visible,
            interaction.guild,
            view.author_id,
        )
        if not content:
            await interaction.response.send_message("❌ This role is not available.", ephemeral=True)
            return

        detail_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=self.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            guild=interaction.guild,
        )
        detail_view.message = interaction.message
        role_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, "overview", None, detail_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=role_embed, view=detail_view)
        # Set the message reference for timeout deletion
        detail_view.message = interaction.message


class CanvasRoleDetailButton(discord.ui.Button):
    """Button that opens one detail view inside a role."""

    def __init__(self, label: str, role_name: str, detail_name: str):
        # Admin buttons should be red, others green
        if "admin" in detail_name.lower():
            button_style = discord.ButtonStyle.danger  # Red for admin
        else:
            button_style = discord.ButtonStyle.success  # Green for others
        super().__init__(label=label, style=button_style)
        self.role_name = role_name
        self.detail_name = detail_name

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasRoleDetailView):
            await interaction.response.send_message("❌ Canvas role detail navigation is not available.", ephemeral=True)
            return

        content = _build_canvas_role_detail_view(
            self.role_name,
            self.detail_name,
            view.agent_config,
            view.admin_visible,
            view.guild,
            view.author_id,
        )
        if not content:
            await interaction.response.send_message("❌ This role detail is not available.", ephemeral=True)
            return

        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail=self.detail_name,
            guild=view.guild,
        )
        next_view.message = interaction.message
        detail_embed = _build_canvas_role_embed(self.role_name, content, view.admin_visible, self.detail_name, None, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


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
        if get_banker_db_instance is None:
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
            db_banker = get_banker_db_instance(str(interaction.guild.id))
            if self.action_name == "config_tae":
                ok = db_banker.configurar_tae(
                    str(interaction.guild.id),
                    interaction.guild.name,
                    amount,
                    str(interaction.user.id),
                )
                label = "TAE"
            else:
                ok = db_banker.configurar_bono(
                    str(interaction.guild.id),
                    interaction.guild.name,
                    amount,
                    str(interaction.user.id),
                )
                label = "Bonus"
        except Exception as e:
            logger.exception(f"Canvas banker config failed: {e}")
            await interaction.response.send_message("❌ Could not update banker configuration.", ephemeral=True)
            return

        if not ok:
            await interaction.response.send_message("❌ Could not update banker configuration.", ephemeral=True)
            return

        try:
            current_tae = db_banker.obtener_tae(str(interaction.guild.id))
            current_bonus = db_banker.obtener_opening_bonus(str(interaction.guild.id))
        except Exception:
            current_tae = amount if label == "TAE" else "Unknown"
            current_bonus = amount if label == "Bonus" else "Unknown"

        await interaction.response.send_message(
            f"✅ {label} updated to `{amount}`.\nCurrent config: TAE {current_tae}% | opening bonus {current_bonus}",
            ephemeral=True,
        )


class RoleFrequencyModal(discord.ui.Modal):
    def __init__(self, role_name: str, action_name: str, agent_config: dict, view):
        title = "Watcher Frequency" if action_name == "watcher_frequency" else "Hunter Frequency"
        super().__init__(title=title)
        self.role_name = role_name
        self.action_name = action_name
        self.agent_config = agent_config
        self.view = view
        placeholder = "1-24 hours" if action_name == "watcher_frequency" else "1-168 hours"
        self.value_input = discord.ui.TextInput(label="Hours", placeholder=placeholder, required=True, max_length=10)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ This option is only available in a server.", ephemeral=True)
            return
        if not is_admin(interaction):
            await interaction.response.send_message("❌ This option is admin-only.", ephemeral=True)
            return
        try:
            hours = int(str(self.value_input.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number of hours.", ephemeral=True)
            return

        applied_text = ""
        if self.action_name == "watcher_frequency":
            if hours < 1 or hours > 24:
                await interaction.response.send_message("❌ Watcher frequency must be between 1 and 24 hours.", ephemeral=True)
                return
            if get_news_watcher_db_instance is None:
                await interaction.response.send_message("❌ Watcher database is not available.", ephemeral=True)
                return
            try:
                db_watcher = get_news_watcher_db_instance(str(interaction.guild.id))
                ok = db_watcher.set_frequency_setting(hours)
            except Exception as e:
                logger.exception(f"Canvas watcher frequency update failed: {e}")
                ok = False
            if not ok:
                await interaction.response.send_message("❌ Could not update watcher frequency.", ephemeral=True)
                return
            current_method = _get_canvas_watcher_method_label(str(interaction.guild.id))
            applied_text = f"Watcher frequency updated to `{hours}` hours.\nCurrent method: {current_method}"
        else:  # hunter_frequency
            if hours < 1 or hours > 168:
                await interaction.response.send_message("❌ Hunter frequency must be between 1 and 168 hours.", ephemeral=True)
                return
            roles_cfg = self.agent_config.setdefault("roles", {})
            hunter_cfg = roles_cfg.setdefault("treasure_hunter", {})
            hunter_cfg["interval_hours"] = hours
            applied_text = f"Hunter frequency updated to `{hours}` hours.\nCurrent admin interval now matches the Canvas setting."

        # Rebuild the Canvas role detail view with updated state
        content = _build_canvas_role_action_view(self.role_name, self.action_name, self.view.admin_visible)
        next_view = CanvasRoleDetailView(
            author_id=self.view.author_id,
            role_name=self.view.role_name,
            agent_config=self.view.agent_config,
            admin_visible=self.view.admin_visible,
            sections=self.view.sections,
            current_detail="admin",
            guild=self.view.guild,
        )
        next_view.auto_response_preview = applied_text
        role_embed = _build_canvas_role_embed(self.role_name, content, self.view.admin_visible, "admin", None, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)


class CommentaryFrequencyModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Commentary Frequency")
        self.view = view
        self.value_input = discord.ui.TextInput(label="Minutes", placeholder="e.g. 180", required=True, max_length=10)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Commentary settings are only available in a server.", ephemeral=True)
            return
        if not is_admin(interaction):
            await interaction.response.send_message("❌ This option is admin-only.", ephemeral=True)
            return
        try:
            minutes = int(str(self.value_input.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number of minutes.", ephemeral=True)
            return
        if minutes < 1:
            await interaction.response.send_message("❌ Minutes must be greater than zero.", ephemeral=True)
            return
        guild_id = int(interaction.guild.id)
        state = _talk_state_by_guild_id.get(guild_id) or {}
        state["interval_minutes"] = minutes
        _talk_state_by_guild_id[guild_id] = state
        if state.get("enabled", False):
            task = state.get("task")
            if task and not task.done():
                task.cancel()
            state["task"] = asyncio.create_task(_start_talk_loop_for_guild(guild_id))
        enabled_text = "On" if state.get("enabled", False) else "Off"
        
        # Rebuild the Canvas behavior view with updated state
        content = _build_canvas_behavior_detail(self.view.current_detail, self.view.admin_visible, self.view.guild)
        next_view = CanvasBehaviorView(
            author_id=self.view.author_id,
            sections=self.view.sections,
            admin_visible=self.view.admin_visible,
            agent_config=self.view.agent_config,
            current_detail=self.view.current_detail,
            guild=self.view.guild,
        )
        next_view.auto_response_preview = f"Mission commentary interval set to `{minutes}` minutes.\nCurrent state: {enabled_text}"
        behavior_embed = _build_canvas_behavior_embed(content or "", self.view.admin_visible, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=behavior_embed, view=next_view)


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
        server_id = str(self.guild.id)
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
        try:
            league = manager.get_user_league(user_id, server_id)
            list_ok, raw = manager.list_objectives(server_id, user_id)
            if list_ok and raw:
                visible_lines = [line.strip() for line in raw.splitlines() if line.strip() and line.strip()[0].isdigit()]
            else:
                visible_lines = []
        except Exception:
            league = "Unknown"
            visible_lines = []
        summary = "\n".join([f"- {line}" for line in visible_lines[:5]]) if visible_lines else "- No tracked items yet"
        content = _build_canvas_role_detail_view(
            "treasure_hunter",
            "personal",
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
            current_detail="personal",
            guild=self.view.guild,
            message=interaction.message,
        )
        next_view.auto_response_preview = f"✅ {message}\nLeague: {league}\nTracked items now:\n{summary}"
        detail_embed = _build_canvas_role_embed(
            "treasure_hunter",
            content or "",
            self.view.admin_visible,
            "personal",
            None,
            next_view.auto_response_preview,
        )
        await interaction.response.edit_message(content=None, embed=detail_embed, view=next_view)


class TabooKeywordModal(discord.ui.Modal):
    def __init__(self, action_name: str, guild_id: int, view):
        super().__init__(title="Taboo Keyword")
        self.action_name = action_name
        self.guild_id = guild_id
        self.view = view
        self.value_input = discord.ui.TextInput(label="Keyword", placeholder="forbidden word", required=True, max_length=80)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        keyword = str(self.value_input.value).strip().lower()
        if not keyword:
            await interaction.response.send_message("❌ Enter a valid keyword.", ephemeral=True)
            return
        
        # Get current keywords from database
        state = get_taboo_state(self.guild_id)
        current_keywords = state.get("keywords", [])
        
        applied_text = ""
        success = False
        
        if self.action_name == "taboo_add":
            if keyword not in current_keywords:
                if update_taboo_state(self.guild_id, keywords=current_keywords + [keyword]):
                    applied_text = f"Added taboo keyword `{keyword}`."
                    success = True
                else:
                    applied_text = f"Failed to add keyword `{keyword}`. Check logs for details."
            else:
                applied_text = f"Keyword `{keyword}` was already in the list."
                success = True
        else:  # taboo_del
            if keyword in current_keywords:
                new_keywords = [kw for kw in current_keywords if kw != keyword]
                if update_taboo_state(self.guild_id, keywords=new_keywords):
                    applied_text = f"Removed taboo keyword `{keyword}`."
                    success = True
                else:
                    applied_text = f"Failed to remove keyword `{keyword}`. Check logs for details."
            else:
                applied_text = f"Keyword `{keyword}` was not in the list."
                success = True
        
        # Rebuild the Canvas behavior view with updated state
        content = _build_canvas_behavior_detail(self.view.current_detail, self.view.admin_visible, self.view.guild, self.view.agent_config)
        next_view = CanvasBehaviorView(
            author_id=self.view.author_id,
            sections=self.view.sections,
            admin_visible=self.view.admin_visible,
            agent_config=self.view.agent_config,
            current_detail=self.view.current_detail,
            guild=self.view.guild,
        )
        next_view.auto_response_preview = applied_text
        behavior_embed = _build_canvas_behavior_embed(content or "", self.view.admin_visible, next_view.auto_response_preview)
        
        if success:
            await interaction.response.edit_message(content=None, embed=behavior_embed, view=next_view)
        else:
            await interaction.response.send_message(applied_text, ephemeral=True)


class TricksterActionModal(discord.ui.Modal):
    def __init__(self, action_name: str, author_id: int, guild, admin_visible: bool):
        titles = {
            "dice_fixed_bet": "Dice Fixed Bet",
            "dice_pot_value": "Dice Pot Value",
            "ring_frequency": "Ring Frequency",
            "beggar_frequency": "Beggar Frequency",
            "beggar_donate": "Beggar Donation",
            "ring_accuse": "Accuse User",
        }
        super().__init__(title=titles.get(action_name, "Trickster Action"))
        self.action_name = action_name
        self.author_id = author_id
        self.guild = guild
        self.admin_visible = admin_visible
        label_map = {
            "dice_fixed_bet": "Gold amount",
            "dice_pot_value": "New pot balance",
            "ring_frequency": "Hours",
            "beggar_frequency": "Hours",
            "beggar_donate": "Gold amount",
            "ring_accuse": "User mention, id, or name",
        }
        placeholder_map = {
            "dice_fixed_bet": "15",
            "dice_pot_value": "500",
            "ring_frequency": "24",
            "beggar_frequency": "6",
            "beggar_donate": "25",
            "ring_accuse": "@user",
        }
        self.value_input = discord.ui.TextInput(
            label=label_map.get(action_name, "Value"),
            placeholder=placeholder_map.get(action_name, ""),
            required=True,
            max_length=120,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        await _handle_canvas_trickster_modal_submit(interaction, self.action_name, str(self.value_input.value).strip(), self.guild, self.author_id, self.admin_visible)


async def _handle_canvas_trickster_modal_submit(interaction: discord.Interaction, action_name: str, raw_value: str, guild, author_id: int, admin_visible: bool) -> None:
    server_key = get_server_key(guild)
    server_id = str(guild.id)
    server_name = guild.name

    # Build canvas sections for navigation
    from discord_bot.agent_discord import AGENT_CFG
    sections = _build_canvas_sections(
        AGENT_CFG,
        "greetputre",
        "nogreetputre", 
        "welcomeputre",
        "nowelcomeputre",
        "roleputre",
        "talkputre",
        admin_visible,
        server_name,
        author_id
    )

    if action_name == "ring_accuse":
        try:
            from roles.trickster.subroles.ring.ring_discord import _get_ring_state, execute_ring_accusation
            state = _get_ring_state(server_id)
            if not state.get("enabled", False):
                await interaction.response.send_message("❌ Ring is not enabled on this server.", ephemeral=True)
                return

            raw_target = raw_value.strip()
            mentioned_user = None
            if guild is not None:
                # Try mention/ID format first
                cleaned = raw_target.replace("<@", "").replace("!", "").replace(">", "").strip()
                if cleaned.isdigit():
                    mentioned_user = guild.get_member(int(cleaned))
                
                # If mention/ID lookup failed, try name matching
                if mentioned_user is None:
                    lowered = raw_target.lower()
                    for member in getattr(guild, "members", []) or []:
                        if getattr(member, "bot", False) or member.id == interaction.user.id:
                            continue
                        names = {member.name.lower(), member.display_name.lower()}
                        if lowered in names:
                            mentioned_user = member
                            break
                
                # If still not found, try fetching by ID using fetch_user for offline members
                if mentioned_user is None and cleaned.isdigit():
                    try:
                        mentioned_user = await interaction.client.fetch_user(int(cleaned))
                    except:
                        pass
                
                # Final fallback: try partial name matching
                if mentioned_user is None:
                    lowered = raw_target.lower()
                    for member in getattr(guild, "members", []) or []:
                        if getattr(member, "bot", False) or member.id == interaction.user.id:
                            continue
                        names = {member.name.lower(), member.display_name.lower()}
                        # Check if any name contains the search term
                        if any(lowered in name for name in names):
                            mentioned_user = member
                            break
            if mentioned_user is None:
                await interaction.response.send_message("❌ Enter a valid user mention, id, or visible name.", ephemeral=True)
                return
            
            # Update the target in state (no immediate accusation)
            target_name = mentioned_user.display_name if hasattr(mentioned_user, 'display_name') else mentioned_user.name
            state["target_user_id"] = str(mentioned_user.id)
            state["target_user_name"] = target_name
            
            # Log the target change
            db_instance = AgentDatabase(server_name=server_name)
            await asyncio.to_thread(
                db_instance.registrar_interaccion,
                interaction.user.id,
                interaction.user.name,
                "RING_TARGET_CHANGE",
                f"Changed ring target to {target_name}",
                interaction.channel.id if interaction.channel else None,
                guild.id,
                {"target_user_id": mentioned_user.id, "target_user_name": target_name},
            )
            
            # Rebuild the view with updated target
            content = _build_canvas_role_trickster_detail("ring", admin_visible, guild, author_id)
            next_view = CanvasRoleDetailView(
                author_id=author_id,
                role_name="trickster",
                agent_config=AGENT_CFG,  # Use actual agent config
                admin_visible=admin_visible,
                sections=sections,  # ← Use the built sections
                current_detail="ring",
                guild=guild,
                message=interaction.message
            )
            next_view.auto_response_preview = f"New target: {target_name}\nThe next investigation will focus on this user."
            role_embed = _build_canvas_role_embed("trickster", content or "", admin_visible, "ring", None, next_view.auto_response_preview)
            await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)
        except Exception as e:
            logger.exception(f"Canvas ring accuse failed: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Could not submit accusation.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Could not submit accusation.", ephemeral=True)
        return

    if action_name == "beggar_donate":
        if get_banker_db_instance is None or get_beggar_db_instance is None:
            await interaction.response.send_message("❌ Beggar donation systems are not available.", ephemeral=True)
            return
        try:
            amount = int(raw_value)
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid gold amount.", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("❌ Donation amount must be positive.", ephemeral=True)
            return
        db_banker = get_banker_db_instance(server_key)
        db_beggar = get_beggar_db_instance(server_key)
        donor_id = str(author_id)
        donor_name = interaction.user.display_name
        db_banker.create_wallet(donor_id, donor_name, server_id, server_name)
        db_banker.create_wallet("beggar_fund", "Beggar Fund", server_id, server_name)
        current_balance = db_banker.get_balance(donor_id, server_id)
        if current_balance < amount:
            await interaction.response.send_message(f"❌ You only have {current_balance:,} gold available.", ephemeral=True)
            return
        reason = db_beggar.get_last_reason(server_id) or "the current clan project"
        target_gold = db_beggar.get_target_gold(server_id)
        db_banker.update_balance(donor_id, donor_name, server_id, server_name, -amount, "BEGGAR_DONATION_OUT", "Donation sent to beggar")
        db_banker.update_balance("beggar_fund", "Beggar Fund", server_id, server_name, amount, "BEGGAR_DONATION_IN", f"Donation received from {donor_name}")
        fund_balance = db_banker.get_balance("beggar_fund", server_id)
        await interaction.response.send_message(
            f"✅ Donation accepted: {amount:,} gold.\n🪙 Fund: {fund_balance:,}\n🎯 Target: {target_gold:,}\n📣 Reason: {reason}",
            ephemeral=True,
        )
        return

    if not admin_visible or not is_admin(interaction):
        await interaction.response.send_message("❌ This trickster option is admin-only.", ephemeral=True)
        return

    if action_name in {"ring_frequency", "beggar_frequency"}:
        try:
            hours = int(raw_value)
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number of hours.", ephemeral=True)
            return
        if hours < 1 or hours > 168:
            await interaction.response.send_message("❌ Frequency must be between 1 and 168 hours.", ephemeral=True)
            return
        try:
            if action_name == "ring_frequency":
                from roles.trickster.subroles.ring.ring_discord import _get_ring_state
                state = _get_ring_state(server_id)
                state["frequency_hours"] = hours
                message = (
                    f"✅ Ring frequency updated to `{hours}` hours.\n"
                    f"Current state: {'On' if state.get('enabled', False) else 'Off'}"
                )
            else:
                db_beggar = get_beggar_db_instance(server_key)
                ok = db_beggar.set_frequency_hours(server_id, hours)
                if not ok:
                    raise RuntimeError("Could not update beggar frequency")
                target_gold = db_beggar.get_target_gold(server_id)
                message = (
                    f"✅ Beggar frequency updated to `{hours}` hours.\n"
                    f"Current target: {target_gold:,} gold"
                )
        except Exception as e:
            logger.exception(f"Canvas trickster frequency update failed: {e}")
            await interaction.response.send_message("❌ Could not update frequency.", ephemeral=True)
            return
        await interaction.response.send_message(message, ephemeral=True)
        return

    if action_name in {"dice_fixed_bet", "dice_pot_value"}:
        if get_dice_game_db_instance is None or get_banker_db_instance is None:
            await interaction.response.send_message("❌ Dice game systems are not available.", ephemeral=True)
            return
        try:
            amount = int(raw_value)
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid gold amount.", ephemeral=True)
            return
        if amount < 0:
            await interaction.response.send_message("❌ Amount must be zero or greater.", ephemeral=True)
            return
        try:
            if action_name == "dice_fixed_bet":
                if amount < 1 or amount > 1000:
                    await interaction.response.send_message("❌ Fixed bet must be between 1 and 1000 gold.", ephemeral=True)
                    return
                db_dice_game = get_dice_game_db_instance(server_key)
                ok = db_dice_game.configure_server(server_id, bet_fija=amount)
                if not ok:
                    raise RuntimeError("Could not update fixed bet")
                state = _get_canvas_dice_state(guild)
                message = (
                    f"✅ Dice fixed bet updated to `{amount}` gold.\n"
                    f"Current pot: {state['pot_balance']:,} gold"
                )
            else:
                db_banker = get_banker_db_instance(server_key)
                db_banker.create_wallet("dice_game_pot", "Dice Game Pot", server_id, server_name)
                current_balance = db_banker.get_balance("dice_game_pot", server_id)
                delta = amount - current_balance
                ok = db_banker.update_balance("dice_game_pot", "Dice Game Pot", server_id, server_name, delta, "DICE_POT_ADMIN_SET", "Canvas pot update", str(interaction.user.id), interaction.user.display_name)
                if not ok:
                    raise RuntimeError("Could not update pot balance")
                state = _get_canvas_dice_state(guild)
                message = (
                    f"✅ Dice pot balance updated to `{amount}` gold.\n"
                    f"Current fixed bet: {state['bet']:,} gold"
                )
        except Exception as e:
            logger.exception(f"Canvas trickster dice update failed: {e}")
            await interaction.response.send_message("❌ Could not update dice settings.", ephemeral=True)
            return
        await interaction.response.send_message(message, ephemeral=True)
        return


async def _handle_canvas_watcher_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    if get_news_watcher_db_instance is None:
        await interaction.response.send_message("❌ Watcher database is not available.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)

    # Handle method selection
    if action_name in {"method_flat", "method_keyword", "method_general"}:
        method_name = action_name.replace("method_", "")
        try:
            db_watcher = get_news_watcher_db_instance(guild_id)
            ok = db_watcher.set_method_config(guild_id, method_name)
        except Exception as e:
            logger.exception(f"Canvas watcher method update failed: {e}")
            ok = False
        if not ok:
            await interaction.response.send_message("❌ Could not update watcher method.", ephemeral=True)
            return

        view.watcher_selected_method = method_name
        view.watcher_last_action = None
        current_detail = "admin" if view.current_detail == "admin" else "personal"
        content = _build_canvas_role_news_watcher_detail(
            current_detail,
            view.admin_visible,
            view.guild,
            view.author_id,
            selected_method=view.watcher_selected_method,
            last_action=view.watcher_last_action,
        )
        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail=current_detail,
            guild=view.guild,
        )
        next_view.message = interaction.message
        next_view.watcher_selected_method = view.watcher_selected_method
        next_view.watcher_last_action = view.watcher_last_action
        next_view.auto_response_preview = f"Method set to `{method_name}`."
        action_embed = _build_canvas_role_embed("news_watcher", content or "", view.admin_visible, current_detail, None, next_view.auto_response_preview)
        try:
            await interaction.response.edit_message(content=None, embed=action_embed, view=next_view)
        except discord.InteractionResponded:
            # If interaction was already responded to, use followup
            await interaction.followup.edit_message(interaction.message.id, embed=action_embed, view=next_view)
        except discord.NotFound:
            # Message was deleted, send a new one
            await interaction.followup.send(embed=action_embed, view=next_view, ephemeral=True)
        except Exception as e:
            logger.exception(f"Failed to edit canvas watcher message: {e}")
            await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
        return

    # Handle subscription actions
    if action_name == "subscribe_categories":
        # Show subscription modal
        await interaction.response.send_modal(CanvasWatcherSubscribeModal(action_name, view, interaction.client))
        return

    # Handle list actions
    if action_name in {"list_keywords", "list_premises"}:
        list_type = action_name.replace("list_", "")
        
        # Show list modal
        await interaction.response.send_modal(CanvasWatcherListModal(list_type, view, interaction.client))
        return

    if action_name == "channel_subscribe_categories":
        await interaction.response.send_modal(CanvasWatcherChannelSubscribeModal(action_name, view, interaction.client))
        return

    if action_name == "channel_unsubscribe":
        await interaction.response.send_modal(CanvasWatcherChannelUnsubscribeModal(view, interaction.client))
        return

    if action_name == "channel_view_subscriptions":
        view.watcher_last_action = action_name
        content = _build_canvas_role_news_watcher_detail(
            "admin",
            view.admin_visible,
            view.guild,
            view.author_id,
            selected_method=view.watcher_selected_method,
            last_action=view.watcher_last_action,
        )
        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail="admin",
            guild=view.guild,
        )
        next_view.message = interaction.message
        next_view.watcher_selected_method = view.watcher_selected_method
        next_view.watcher_last_action = view.watcher_last_action
        action_embed = _build_canvas_role_embed("news_watcher", content or "", view.admin_visible, "admin", None)
        try:
            await interaction.response.edit_message(content=None, embed=action_embed, view=next_view)
        except discord.InteractionResponded:
            # If interaction was already responded to, use followup
            await interaction.followup.edit_message(interaction.message.id, embed=action_embed, view=next_view)
        except discord.NotFound:
            # Message was deleted, send a new one
            await interaction.followup.send(embed=action_embed, view=next_view, ephemeral=True)
        except Exception as e:
            logger.exception(f"Failed to edit canvas watcher message: {e}")
            await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
        return

    # Handle admin actions
    if action_name == "watcher_frequency":
        await interaction.response.send_modal(CanvasWatcherFrequencyModal(view, interaction.client))
        return

    if action_name == "watcher_run_now":
        try:
            from roles.news_watcher.news_watcher import process_channel_subscriptions
            from roles.news_watcher.global_news_db import get_global_news_db
            from discord_bot.discord_http import DiscordHTTP
            from agent_engine import get_discord_token

            if not view.guild:
                await interaction.response.send_message("❌ Guild context is required to run watcher now.", ephemeral=True)
                return
            db_watcher = get_news_watcher_db_instance(guild_id)
            http = DiscordHTTP(get_discord_token())
            global_db = get_global_news_db()
            server_name = str(view.guild.id)
            await process_channel_subscriptions(http, db_watcher, global_db, server_name)
        except Exception as e:
            logger.exception(f"Canvas force watcher failed: {e}")
            await interaction.response.send_message("❌ Could not run watcher now.", ephemeral=True)
            return

        current_detail = "admin" if view.current_detail == "admin" else "personal"
        view.watcher_last_action = action_name
        content = _build_canvas_role_news_watcher_detail(
            current_detail,
            view.admin_visible,
            view.guild,
            view.author_id,
            selected_method=view.watcher_selected_method,
            last_action=view.watcher_last_action,
        )
        next_view = CanvasRoleDetailView(
            author_id=view.author_id,
            role_name=view.role_name,
            agent_config=view.agent_config,
            admin_visible=view.admin_visible,
            sections=view.sections,
            current_detail=current_detail,
            guild=view.guild,
        )
        next_view.message = interaction.message
        next_view.watcher_selected_method = view.watcher_selected_method
        next_view.watcher_last_action = view.watcher_last_action
        next_view.auto_response_preview = "Watcher iteration completed."
        action_embed = _build_canvas_role_embed("news_watcher", content or "", view.admin_visible, current_detail, None, next_view.auto_response_preview)
        try:
            await interaction.response.edit_message(content=None, embed=action_embed, view=next_view)
        except discord.InteractionResponded:
            # If interaction was already responded to, use followup
            try:
                await interaction.followup.edit_message(interaction.message.id, embed=action_embed, view=next_view)
            except (discord.NotFound, discord.HTTPException) as e:
                logger.warning(f"Failed to edit message via followup: {e}")
                return  # Silently fail - user can try again
        except (discord.NotFound, discord.HTTPException) as e:
            # Message was deleted or interaction expired
            logger.warning(f"Interaction not found for watcher action: {e}")
            return  # Silently fail - user can try again
        except Exception as e:
            logger.exception(f"Unexpected error in canvas watcher interaction: {e}")
            return  # Silently fail - user can try again
        return
    await interaction.response.send_message("❌ Unknown watcher action.", ephemeral=True)


async def _handle_canvas_trickster_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    try:
        server_key = get_server_key(interaction.guild)
        server_id = str(interaction.guild.id)
        if action_name in {"announcements_on", "announcements_off"}:
            if get_dice_game_db_instance is None:
                await interaction.response.send_message("❌ Dice game database is not available.", ephemeral=True)
                return
            db_dice_game = get_dice_game_db_instance(server_key)
            enabled = action_name == "announcements_on"
            ok = db_dice_game.configure_server(server_id, announcements_active=enabled)
            current_detail = "dice_admin"
            applied_text = f"Dice announcements {'enabled' if enabled else 'disabled'}."
        elif action_name in {"ring_on", "ring_off"}:
            from roles.trickster.subroles.ring.ring_discord import _get_ring_state
            state = _get_ring_state(server_id)
            state["enabled"] = action_name == "ring_on"
            ok = True
            current_detail = "ring_admin"
            applied_text = f"Ring {'enabled' if state['enabled'] else 'disabled'}."
        elif action_name in {"beggar_on", "beggar_off"}:
            if get_beggar_db_instance is None:
                await interaction.response.send_message("❌ Beggar database is not available.", ephemeral=True)
                return
            db_beggar = get_beggar_db_instance(server_key)
            server_user_id = f"server_{server_id}"
            if action_name == "beggar_on":
                ok = db_beggar.add_subscription(server_user_id, interaction.guild.name, server_id)
            else:
                ok = db_beggar.remove_subscription(server_user_id, server_id)
            current_detail = "beggar_admin"
            applied_text = f"Beggar {'enabled' if action_name == 'beggar_on' else 'disabled'}."
        else:
            await interaction.response.send_message("❌ Unknown trickster action.", ephemeral=True)
            return
    except Exception as e:
        logger.exception(f"Canvas trickster action failed: {e}")
        ok = False

    if not ok:
        await interaction.response.send_message("❌ Could not update trickster settings.", ephemeral=True)
        return

    content = _build_canvas_role_action_view("trickster", action_name, view.admin_visible)
    next_view = CanvasRoleDetailView(
        author_id=view.author_id,
        role_name=view.role_name,
        agent_config=view.agent_config,
        admin_visible=view.admin_visible,
        sections=view.sections,
        current_detail=current_detail,
        guild=view.guild,
    )
    next_view.auto_response_preview = applied_text
    action_embed = _build_canvas_role_embed("trickster", content or "", view.admin_visible, current_detail, None, next_view.auto_response_preview)
    try:
        await interaction.response.edit_message(content=None, embed=action_embed, view=next_view)
    except discord.InteractionResponded:
        # If interaction was already responded to, use followup
        await interaction.followup.edit_message(interaction.message.id, embed=action_embed, view=next_view)
    except discord.NotFound:
        # Message was deleted, send a new one
        await interaction.followup.send(embed=action_embed, view=next_view, ephemeral=True)
    except Exception as e:
        logger.exception(f"Failed to edit canvas trickster message: {e}")
        await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)


async def _handle_canvas_dice_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    """Handle dice game actions with dynamic content display."""
    if get_dice_game_db_instance is None or get_banker_db_instance is None or DiceGame is None:
        await interaction.response.send_message("❌ Dice game systems are not available.", ephemeral=True)
        return

    server_key = get_server_key(interaction.guild)
    server_id = str(interaction.guild.id)
    server_name = interaction.guild.name
    
    # Get current dice state and personality messages
    dice_state = _get_canvas_dice_state(interaction.guild)
    personality = _personality_answers.get("dice_game_messages", {})
    balance_messages = _personality_answers.get("dice_game_balance_messages", {})
    
    # Build the base content with personality title and pot balance
    title = personality.get("invitation", "🎲 **DICE GAME** 🎲")
    pot_title = balance_messages.get("current_pot_title", "💎 **CURRENT POT:**")
    
    content_parts = [
        title,
        f"{pot_title} {dice_state['pot_balance']:,} gold",
        f"💰 **Fixed bet:** {dice_state['bet']:,} gold",
        "",
        "─" * 30,
        ""
    ]
    
    # Handle different actions
    if action_name == "dice_play":
        # Execute a dice play
        try:
            db_dice = get_dice_game_db_instance(server_key)
            db_banker = get_banker_db_instance(server_key)
            
            # Get or create player wallet
            player_id = str(interaction.user.id)
            player_name = interaction.user.display_name
            db_banker.create_wallet(player_id, player_name, server_id, server_name)
            db_banker.create_wallet("dice_game_pot", "Dice Game Pot", server_id, server_name)
            
            # Check balance
            player_balance = db_banker.get_balance(player_id, server_id)
            bet_amount = dice_state["bet"]
            
            if player_balance < bet_amount:
                insufficient_msg = personality.get("insufficient_balance", "❌ Insufficient balance!")
                content_parts.extend([
                    "**🎲 DICE PLAY RESULT**",
                    insufficient_msg.format(apuesta=bet_amount, saldo=player_balance),
                    "",
                    f"Your balance: {player_balance:,} gold",
                    f"Required: {bet_amount:,} gold",
                ])
            else:
                # Create dice game instance and play
                dice_game = DiceGame(fixed_bet=bet_amount)
                result = dice_game.play_game(player_id, player_name, server_id, server_name, dice_state['pot_balance'])
                
                if result.get('success', False):
                    # Parse result
                    dice_str = result.get("dice", "")
                    combination = result.get("combination", "")
                    prize = result.get("prize", 0)
                    new_pot_balance = result.get("new_pot_balance", dice_state['pot_balance'])
                    
                    # Format dice roll
                    dice_values = dice_str.split('-') if dice_str else []
                    dice_display = "🎲".join(dice_values)
                    roll_title = personality.get("roll_title", "🎲 **YOUR ROLL:**")
                    result_title = personality.get("combination_title", "📊 **RESULT:**")
                    prize_title = personality.get("prize_title", "💰 **PRIZE:**")
                    
                    content_parts.extend([
                        "**🎲 DICE PLAY RESULT**",
                        f"{roll_title} {dice_display}",
                        f"{result_title} {combination}",
                        "",
                    ])
                    
                    if prize > 0:
                        winner_msg = personality.get("winner", "🎉 **WINNER!!!**")
                        content_parts.append(f"{prize_title} {prize:,} gold")
                        content_parts.append(f"🎉 {winner_msg}")
                    else:
                        loser_msg = personality.get("loser", "😢 **LOSER!**")
                        content_parts.append(f"{prize_title} {prize:,} gold")
                        content_parts.append(f"😢 {loser_msg}")
                    
                    # Update balances in database (single transaction)
                    db_banker.update_balance(player_id, player_name, server_id, server_name, -bet_amount, "DICE_PLAY_BET", "Dice game bet")
                    if prize > 0:
                        db_banker.update_balance(player_id, player_name, server_id, server_name, prize, "DICE_PLAY_WIN", "Dice game win")
                    else:
                        db_banker.update_balance("dice_game_pot", "Dice Game Pot", server_id, server_name, bet_amount, "DICE_PLAY_ADD", "Dice game lost bet")
                    
                    # Register the game in database
                    db_dice.register_game(
                        player_id, player_name, server_id, server_name,
                        bet_amount, dice_str, combination, prize,
                        dice_state['pot_balance'], new_pot_balance
                    )
                    
                    content_parts.extend([
                        "",
                        f"New balance: {db_banker.get_balance(player_id, server_id):,} gold",
                        f"New pot: {new_pot_balance:,} gold",
                    ])
                else:
                    error_msg = personality.get("error_jugada", "❌ **ERROR!**")
                    content_parts.extend([
                        "**🎲 DICE PLAY RESULT**",
                        error_msg.format(error="Game execution failed"),
                    ])
        except Exception as e:
            logger.exception(f"Canvas dice play failed: {e}")
            content_parts.extend([
                "**🎲 DICE PLAY RESULT**",
                "❌ **ERROR!** Game execution failed.",
            ])
    
    elif action_name == "dice_ranking":
        # Show ranking
        try:
            db_dice = get_dice_game_db_instance(server_key)
            ranking = db_dice.get_player_ranking(server_id, "total_won", 10)
            
            content_parts.append("**🏆 DICE RANKING**")
            
            if ranking:
                for position, record in enumerate(ranking, 1):
                    # Parse tuple: (user_id, metric_value, total_plays, total_won, total_bet)
                    user_id = record[0] if len(record) > 0 else ""
                    total_won = record[3] if len(record) > 3 else 0
                    total_plays = record[2] if len(record) > 2 else 0
                    
                    # Try to get user name
                    try:
                        member = interaction.guild.get_member(int(user_id))
                        player_name = member.display_name if member else f"User {user_id}"
                    except:
                        player_name = f"User {user_id}"
                    
                    medal = "🥇" if position == 1 else "🥈" if position == 2 else "🥉" if position == 3 else "🏅"
                    content_parts.append(
                        f"{medal} **#{position}** {player_name} | Won: {total_won:,} | Games: {total_plays}"
                    )
            else:
                content_parts.append("📊 No ranked players yet. Be the first to play!")
        except Exception as e:
            logger.exception(f"Canvas dice ranking failed: {e}")
            content_parts.extend([
                "**🏆 DICE RANKING**",
                "❌ **ERROR!** Could not load ranking.",
            ])
    
    elif action_name == "dice_history":
        # Show recent history
        try:
            db_dice = get_dice_game_db_instance(server_key)
            history = db_dice.get_game_history(server_id, 10)
            
            content_parts.append("**📜 DICE HISTORY**")
            
            if history:
                for record in history:
                    # Parse tuple: (id, user_id, user_name, server_id, server_name, bet, dice, combination, prize, pot_before, pot_after, date)
                    user_name = record[2] if len(record) > 2 else "Unknown"
                    dice = record[6] if len(record) > 6 else ""
                    combination = record[7] if len(record) > 7 else ""
                    prize = record[8] if len(record) > 8 else 0
                    
                    dice_display = "🎲".join(dice.split('-')) if dice else "???"
                    prize_emoji = "💰" if prize > 0 else "💸"
                    
                    content_parts.append(
                        f"👤 {user_name} | {dice_display} → {combination} | {prize_emoji} {prize:,}"
                    )
            else:
                content_parts.append("📊 No recent games yet. Be the first to play!")
        except Exception as e:
            logger.exception(f"Canvas dice history failed: {e}")
            content_parts.extend([
                "**📜 DICE HISTORY**",
                "❌ **ERROR!** Could not load history.",
            ])
    
    elif action_name == "dice_help":
        # Show help
        content_parts.extend([
            "**🎲 DICE GAME HELP**",
            "",
            "**How to play:**",
            "• Click **Dice: Play** to roll the dice",
            "• Cost: Fixed bet amount per game",
            "• Win: Get prizes based on dice combinations",
            "",
            "**Commands:**",
            "• `!dice play` - Play a game",
            "• `!dice ranking` - Show top players",
            "• `!dice history` - Show recent games",
            "• `!dice balance` - Check your gold",
            "",
            "**Prizes:**",
            "• Special combinations = Big prizes!",
            "• Regular combinations = Small prizes",
            "• No match = No prize (bet goes to pot)",
            "",
            f"**Current bet:** {dice_state['bet']:,} gold",
            f"**Current pot:** {dice_state['pot_balance']:,} gold",
        ])
    
    # Rebuild the view with dynamic content
    content = "\n".join(content_parts)
    next_view = CanvasRoleDetailView(
        author_id=view.author_id,
        role_name=view.role_name,
        agent_config=view.agent_config,
        admin_visible=view.admin_visible,
        sections=view.sections,
        current_detail="dice",
        guild=view.guild,
    )
    next_view.auto_response_preview = f"Executed {action_name.replace('_', ' ').title()}"
    role_embed = _build_canvas_role_embed("trickster", content, view.admin_visible, "dice", None, next_view.auto_response_preview)
    try:
        await interaction.response.edit_message(content=None, embed=role_embed, view=next_view)
    except discord.InteractionResponded:
        # If interaction was already responded to, use followup
        await interaction.followup.edit_message(interaction.message.id, embed=role_embed, view=next_view)
    except discord.NotFound:
        # Message was deleted, send a new one
        await interaction.followup.send(embed=role_embed, view=next_view, ephemeral=True)
    except Exception as e:
        logger.exception(f"Failed to edit canvas dice message: {e}")
        await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)


async def _handle_canvas_treasure_hunter_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    if get_poe2_manager is None:
        await interaction.response.send_message("❌ POE2 manager is not available.", ephemeral=True)
        return

    manager = get_poe2_manager()
    server_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)

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
            await interaction.response.send_message("❌ Could not update POE2 league.", ephemeral=True)
            return
        content = _build_canvas_role_action_view("treasure_hunter", action_name, view.admin_visible)
        next_view = CanvasRoleDetailView(view.author_id, view.role_name, view.agent_config, view.admin_visible, view.sections, current_detail="league", guild=view.guild)
        next_view.auto_response_preview = f"League changed to `{league}` and default items were synced."
        embed = _build_canvas_role_embed("treasure_hunter", content or "", view.admin_visible, "league", None, next_view.auto_response_preview)
        try:
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        except discord.InteractionResponded:
            # If interaction was already responded to, use followup
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=next_view)
        except discord.NotFound:
            # Message was deleted, send a new one
            await interaction.followup.send(embed=embed, view=next_view, ephemeral=True)
        except Exception as e:
            logger.exception(f"Failed to edit canvas treasure hunter message: {e}")
            await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
        return

    if not view.admin_visible or not is_admin(interaction):
        await interaction.response.send_message("❌ This POE2 option is admin-only.", ephemeral=True)
        return

    try:
        if action_name == "poe2_on":
            league = manager.get_active_league(server_id)
            if manager.should_refresh_item_list(league):
                await manager.download_item_list(league)
            ok = manager.activate_subrole(server_id)
        else:
            ok = manager.deactivate_subrole(server_id)
    except Exception as e:
        logger.exception(f"Canvas POE2 activation toggle failed: {e}")
        ok = False

    if not ok:
        await interaction.response.send_message("❌ Could not update POE2 activation state.", ephemeral=True)
        return

    content = _build_canvas_role_action_view("treasure_hunter", action_name, view.admin_visible)
    next_view = CanvasRoleDetailView(view.author_id, view.role_name, view.agent_config, view.admin_visible, view.sections, current_detail="admin", guild=view.guild)
    next_view.auto_response_preview = f"POE2 {'enabled' if action_name == 'poe2_on' else 'disabled'}."
    embed = _build_canvas_role_embed("treasure_hunter", content or "", view.admin_visible, "admin", None, next_view.auto_response_preview)
    try:
        await interaction.response.edit_message(content=None, embed=embed, view=next_view)
    except discord.InteractionResponded:
        # If interaction was already responded to, use followup
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=next_view)
    except discord.NotFound:
        # Message was deleted, send a new one
        await interaction.followup.send(embed=embed, view=next_view, ephemeral=True)
    except Exception as e:
        logger.exception(f"Failed to edit canvas treasure hunter message: {e}")
        await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)


async def _handle_canvas_mc_action(interaction: discord.Interaction, action_name: str, view: "CanvasRoleDetailView") -> None:
    """Handle MC (Music Controller) canvas actions."""
    try:
        # Import MC commands if available
        from roles.mc.mc_discord import get_mc_commands_instance
        from agent_engine import get_mc_feature
        
        # Get the global MC commands instance
        mc_commands = get_mc_commands_instance()
        if not mc_commands:
            await interaction.response.send_message("❌ MC commands are not initialized.", ephemeral=True)
            return
        
        # Check if MC is enabled and available
        mc_enabled = get_mc_feature("voice_commands") if get_mc_feature else False
        if not mc_enabled:
            await interaction.response.send_message("❌ MC voice commands are not enabled.", ephemeral=True)
            return
            
        # Create a mock message for the MC command
        class MockMessage:
            def __init__(self, channel, author, guild):
                self.channel = channel
                self.author = author
                self.guild = guild
                
        mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
        
        # Handle different actions
        if action_name == "mc_play":
            # Show modal for song input
            await interaction.response.send_modal(CanvasMCSongModal("mc_play", view, mc_commands))
            return
        elif action_name == "mc_add":
            # Show modal for song input
            await interaction.response.send_modal(CanvasMCSongModal("mc_add", view, mc_commands))
            return
        elif action_name == "mc_volume":
            await interaction.response.send_modal(CanvasMCVolumeModal(view, mc_commands))
            return
        
        # For non-modal actions, execute immediately and update view
        captured_messages = []
        last_action = None
        queue_info = None
        
        # Set up message callback to capture MC messages
        async def message_callback(content, **kwargs):
            captured_messages.append(content)
        
        # Set callback before executing command
        original_callback = mc_commands._message_callback
        mc_commands.set_message_callback(message_callback)
        
        # Store callback reference for cleanup
        if not hasattr(view, '_mc_callbacks'):
            view._mc_callbacks = []
        view._mc_callbacks.append((mc_commands, original_callback))
        
        try:
            if action_name == "mc_skip":
                await mc_commands.cmd_skip(mock_message, [])
                last_action = "⏭️ Song skipped"
            elif action_name == "mc_pause":
                await mc_commands.cmd_pause(mock_message, [])
                last_action = "⏸️ Playback paused"
            elif action_name == "mc_resume":
                await mc_commands.cmd_resume(mock_message, [])
                last_action = "▶️ Playback resumed"
            elif action_name == "mc_stop":
                await mc_commands.cmd_stop(mock_message, [])
                last_action = "⏹️ Playback stopped and queue cleared"
            elif action_name == "mc_queue":
                await mc_commands.cmd_queue(mock_message, [])
                last_action = "📋 Queue displayed"
                # Try to get queue info
                try:
                    from roles.mc.db_role_mc import get_mc_db_instance
                    db_mc = get_mc_db_instance(str(interaction.guild.id))
                    queue_data = db_mc.obtener_queue(str(interaction.guild.id), str(interaction.channel.id))
                    queue_info = [(title, artist, duration, user) for pos, title, url, duration, artist, user_id, fecha in queue_data]
                except:
                    pass
            elif action_name == "mc_clear":
                await mc_commands.cmd_clear(mock_message, [])
                last_action = "🗑️ Queue cleared"
            elif action_name == "mc_history":
                await mc_commands.cmd_history(mock_message, [])
                last_action = "📜 History displayed"
            else:
                await interaction.response.send_message("❌ Unknown MC action.", ephemeral=True)
                return
        finally:
            # Don't restore callback immediately - let it persist for the lifetime of the view
            pass
        
        # Update the current Canvas view with dynamic content (no transition)
        # Small delay to allow async messages to be captured
        await asyncio.sleep(0.5)
        
        mc_content = _build_canvas_role_mc(
            last_action=last_action,
            queue_info=queue_info,
            mc_messages=captured_messages
        )
        
        # Update current view state
        view.auto_response_preview = last_action
        embed = _build_canvas_role_embed("mc", mc_content, view.admin_visible, "overview", None, view.auto_response_preview)
        
        # Update the same view without creating a new one
        # Note: We pass the same view to maintain all components including the dropdown
        try:
            await interaction.response.edit_message(content=None, embed=embed, view=view)
        except discord.InteractionResponded:
            # If interaction was already responded to, use followup
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
        except discord.NotFound:
            # Message was deleted, send a new one
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            logger.exception(f"Failed to edit canvas MC message: {e}")
            await interaction.followup.send("❌ Failed to update view. Please try again.", ephemeral=True)
            
    except ImportError:
        await interaction.response.send_message("❌ MC commands are not available. Install yt-dlp and PyNaCl.", ephemeral=True)
    except Exception as e:
        logger.exception(f"Error handling MC canvas action {action_name}: {e}")
        try:
            await interaction.followup.send(f"❌ Error updating configuration: {e}", ephemeral=True)
        except discord.NotFound:
            # Interaction expired, can't send followup
            logger.info(f"Could not send error followup for MC action {action_name}: interaction expired")
        except discord.HTTPException:
            # Other HTTP errors, can't send followup
            logger.warning(f"Could not send error followup for MC action {action_name}: HTTP error")


class CanvasMCSongModal(discord.ui.Modal):
    """Modal for MC song input (play or add)."""
    
    def __init__(self, action_name: str, view: "CanvasRoleDetailView", mc_commands):
        self.action_name = action_name
        self.view = view
        self.mc_commands = mc_commands
        title = "Play Song Now" if action_name == "mc_play" else "Add Song to Queue"
        super().__init__(title=title, timeout=300)
        
        self.song_input = discord.ui.TextInput(
            label="Song Name or URL",
            placeholder="Enter song name, YouTube URL, or search query...",
            style=discord.TextStyle.long,
            required=True,
            max_length=200
        )
        self.add_item(self.song_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Respond immediately to prevent modal timeout
            await interaction.response.send_message("🎵 Processing song request...", ephemeral=True, delete_after=5)
            
            # Create mock message
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild
                    
            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            
            # Set up message callback to capture MC messages
            captured_messages = []
            
            async def message_callback(content, **kwargs):
                captured_messages.append(content)
                # Don't send to channel, capture for Canvas display
            
            # Set callback before executing command
            original_callback = self.mc_commands._message_callback
            self.mc_commands.set_message_callback(message_callback)
            
            # Store callback reference for cleanup
            if not hasattr(self.view, '_mc_callbacks'):
                self.view._mc_callbacks = []
            self.view._mc_callbacks.append((self.mc_commands, original_callback))
            
            try:
                # Execute command
                song_query = str(self.song_input.value).strip()
                args = song_query.split()
                
                if self.action_name == "mc_play":
                    await self.mc_commands.cmd_play(mock_message, args)
                    result_msg = f"🎵 Now playing: {song_query}"
                else:  # mc_add
                    await self.mc_commands.cmd_add(mock_message, args)
                    result_msg = f"🎵 Added to queue: {song_query}"
                
                # Get current queue and now playing info
                queue_info = None
                try:
                    # Small delay to ensure DB is updated after playback starts
                    import asyncio
                    await asyncio.sleep(0.5)
                    
                    from roles.mc.db_role_mc import get_mc_db_instance
                    db_mc = get_mc_db_instance(str(interaction.guild.id))
                    queue_data = db_mc.obtener_queue(str(interaction.guild.id), str(interaction.channel.id))
                    
                    # Convert queue data to display format
                    queue_info = []
                    for pos, title, url, duration, artist, user_id, fecha in queue_data:
                        try:
                            # Get user name from Discord
                            user = interaction.guild.get_member(int(user_id))
                            user_name = user.display_name if user else "Unknown User"
                            queue_info.append((title, artist, duration, user_name))
                        except:
                            queue_info.append((title, artist, duration, "Unknown User"))
                except Exception as e:
                    logger.warning(f"Error getting queue info: {e}")
                    pass
                
            finally:
                # Don't restore callback immediately - let it persist for the lifetime of the view
                pass
            
            # Try to update the Canvas interface
            try:
                # Small delay to allow async messages to be captured
                await asyncio.sleep(0.5)
                
                # Build dynamic MC view with captured messages
                mc_content = _build_canvas_role_mc(
                    last_action=result_msg,
                    queue_info=queue_info,
                    mc_messages=captured_messages
                )
                
                # Update current view state (no transition)
                self.view.auto_response_preview = result_msg
                embed = _build_canvas_role_embed("mc", mc_content, self.view.admin_visible, "overview", None)
                
                # Try to update the Canvas view separately using followup
                try:
                    await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self.view)
                except:
                    pass  # If we can't update Canvas, the initial message is enough
            except Exception as e:
                logger.exception(f"Error updating Canvas after modal submission: {e}")
                pass  # Don't show errors to user since action worked
            
        except Exception as e:
            logger.exception(f"Error in MC song modal: {e}")
            try:
                await interaction.followup.send("❌ Error processing song request", ephemeral=True)
            except (discord.NotFound, discord.InteractionResponded):
                # Interaction already responded or expired
                pass


class CanvasMCVolumeModal(discord.ui.Modal):
    """Modal for MC volume input."""
    
    def __init__(self, view: "CanvasRoleDetailView", mc_commands):
        self.view = view
        self.mc_commands = mc_commands
        super().__init__(title="Set Volume", timeout=300)
        
        self.volume_input = discord.ui.TextInput(
            label="Volume (0-100)",
            placeholder="Enter volume level between 0 and 100...",
            style=discord.TextStyle.short,
            required=True,
            max_length=3
        )
        self.add_item(self.volume_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Create mock message
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild
                    
            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            
            # Execute command
            volume_str = str(self.volume_input.value).strip()
            args = [volume_str]
            await self.mc_commands.cmd_volume(mock_message, args)
            
            result_msg = f"🔊 Volume set to {volume_str}%"
            
            # Try to update the Canvas interface
            try:
                # Build dynamic MC view with volume result
                mc_content = _build_canvas_role_mc(
                    last_action=result_msg,
                    queue_info=None,
                    mc_messages=None
                )
                
                # Update current view state (no transition)
                self.view.auto_response_preview = result_msg
                embed = _build_canvas_role_embed("mc", mc_content, self.view.admin_visible, "overview", None)
                
                # Update the Canvas view directly
                if self.view and not self.view.is_finished():
                    await interaction.response.edit_message(content=None, embed=embed, view=self.view)
                else:
                    # If view is invalid, just confirm the action
                    await interaction.response.send_message(f"✅ {result_msg}", ephemeral=True, delete_after=3)
            except discord.NotFound:
                # Interaction expired - the action was successful
                logger.info(f"MC Canvas volume action completed but interaction expired")
            except discord.HTTPException as e:
                # Other HTTP errors - respond with success message since the action worked
                logger.warning(f"Could not update Canvas for MC volume action: {e}")
                try:
                    await interaction.response.send_message(f"✅ {result_msg}", ephemeral=True, delete_after=3)
                except:
                    pass  # If we can't respond, just log it
            
        except Exception as e:
            logger.exception(f"Error in MC volume modal: {e}")
            # Don't try to respond on error - the interaction is likely expired anyway


class CanvasWatcherSubscribeModal(discord.ui.Modal):
    """Modal for News Watcher subscription with unified interface."""
    
    def __init__(self, action_name: str, view: "CanvasRoleDetailView", bot):
        self.action_name = action_name
        self.view = view
        self.bot = bot
        
        if action_name == "subscribe_categories":
            title = "Subscribe to Categories"
        else:  # This should not happen since we removed subscribe_feeds
            title = "Subscribe to Categories"
            
        super().__init__(title=title, timeout=300)
        
        self.category_input = discord.ui.TextInput(
            label="Category",
            placeholder="Enter category (economy, technology, international, general, crypto)...",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        self.add_item(self.category_input)
        
        # Add optional feed_id input for subscribe_categories
        self.feed_id_input = discord.ui.TextInput(
            label="Feed ID (Optional)",
            placeholder="Enter specific feed ID number (optional - leave empty to subscribe to all feeds in category)...",
            style=discord.TextStyle.short,
            required=False,  # Make it optional
            max_length=10,
            default=""  # Empty by default
        )
        self.add_item(self.feed_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands
            
            # Create mock message
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild
                    
            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            watcher_commands = WatcherCommands(self.bot)
            
            # Build command arguments
            method = (self.view.watcher_selected_method or "flat").strip().lower()
            category = str(self.category_input.value).strip()
            
            args = [method, category]
            
            # Add optional feed_id if provided
            feed_id = str(self.feed_id_input.value).strip()
            if feed_id:  # Only add if not empty
                args.append(feed_id)
            
            # Execute subscription command
            await watcher_commands.cmd_unified_subscribe(mock_message, args)
            
            method_titles = {
                "flat": "Flat Subscription (All News)",
                "keyword": "Keyword Subscription (Filtered)",
                "general": "General Subscription (AI Analysis)"
            }
            
            result_msg = f"✅ {method_titles.get(method, 'Subscription')} created for {category}"
            if feed_id:
                result_msg += f" (feed #{feed_id})"
            else:
                result_msg += " (all feeds in category)"
            
            # Try to respond, but handle expired interaction gracefully
            try:
                self.view.watcher_last_action = self.action_name
                content = _build_canvas_role_news_watcher_detail(
                    "personal",
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = CanvasRoleDetailView(
                    author_id=self.view.author_id,
                    role_name=self.view.role_name,
                    agent_config=self.view.agent_config,
                    admin_visible=self.view.admin_visible,
                    sections=self.view.sections,
                    current_detail="personal",
                    guild=self.view.guild
                )
                next_view.watcher_selected_method = self.view.watcher_selected_method
                next_view.watcher_last_action = self.view.watcher_last_action
                next_view.auto_response_preview = result_msg
                embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, "personal", None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                # Interaction expired - the action was successful, so just acknowledge silently
                logger.info(f"Watcher Canvas subscription {self.action_name} completed but interaction expired")
            except discord.HTTPException as e:
                # Other HTTP errors - log but don't send followup to keep Canvas clean
                logger.warning(f"Could not update Canvas for Watcher subscription {self.action_name}: {e}")
            
        except Exception as e:
            logger.exception(f"Error in Watcher subscription modal: {e}")
            # Don't try to respond on error - the interaction is likely expired anyway


class CanvasWatcherAddModal(discord.ui.Modal):
    """Modal for adding keywords and premises."""
    
    def __init__(self, action_name: str, view: "CanvasRoleDetailView", bot):
        self.action_name = action_name
        self.view = view
        self.bot = bot
        
        if action_name == "add_keywords":
            title = "Add Keywords"
            label = "Keywords"
            placeholder = "Enter keywords separated by commas (e.g., bitcoin, ethereum, crypto)..."
        else:  # add_premises
            title = "Add Premises"
            label = "Premise"
            placeholder = "Enter your AI analysis premise (e.g., Focus on market impact)..."
            
        super().__init__(title=title, timeout=300)
        
        self.content_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            style=discord.TextStyle.paragraph if action_name == "add_premises" else discord.TextStyle.short,
            required=True,
            max_length=500 if action_name == "add_premises" else 200
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands
            
            # Create mock message
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild
                    
            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            watcher_commands = WatcherCommands(self.bot)
            
            content = str(self.content_input.value).strip()
            
            # Execute appropriate command
            if self.action_name == "add_keywords":
                await watcher_commands.cmd_keywords_add(mock_message, [content])
                result_msg = f"✅ Keywords added: {content}"
            else:  # add_premises
                await watcher_commands.cmd_premises_add(mock_message, [content])
                result_msg = f"✅ Premise added: {content}"
            
            # Try to respond, but handle expired interaction gracefully
            try:
                self.view.watcher_last_action = "list_keywords" if self.action_name == "add_keywords" else "list_premises"
                content = _build_canvas_role_news_watcher_detail(
                    self.view.current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = CanvasRoleDetailView(
                    author_id=self.view.author_id,
                    role_name=self.view.role_name,
                    agent_config=self.view.agent_config,
                    admin_visible=self.view.admin_visible,
                    sections=self.view.sections,
                    current_detail=self.view.current_detail,
                    guild=self.view.guild
                )
                next_view.watcher_selected_method = self.view.watcher_selected_method
                next_view.watcher_last_action = self.view.watcher_last_action
                next_view.auto_response_preview = result_msg
                embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, self.view.current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                # Interaction expired - the action was successful, so just acknowledge silently
                logger.info(f"Watcher Canvas add {self.action_name} completed but interaction expired")
            except discord.HTTPException as e:
                # Other HTTP errors - log but don't send followup to keep Canvas clean
                logger.warning(f"Could not update Canvas for Watcher add {self.action_name}: {e}")
            
        except Exception as e:
            logger.exception(f"Error in Watcher add modal: {e}")
            # Don't try to respond on error - the interaction is likely expired anyway


class CanvasWatcherDeleteModal(discord.ui.Modal):
    """Modal for deleting keywords and premises."""
    
    def __init__(self, action_name: str, view: "CanvasRoleDetailView", bot):
        self.action_name = action_name
        self.view = view
        self.bot = bot
        
        if action_name == "delete_keywords":
            title = "Delete Keywords"
            label = "Keyword to Delete"
            placeholder = "Enter keyword to remove (e.g., bitcoin)..."
        else:  # delete_premises
            title = "Delete Premises"
            label = "Premise Number"
            placeholder = "Enter premise number to delete (e.g., 1, 2, 3)..."
            
        super().__init__(title=title, timeout=300)
        
        self.content_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            style=discord.TextStyle.short,
            required=True,
            max_length=100
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands
            
            # Create mock message
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild
                    
            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            watcher_commands = WatcherCommands(self.bot)
            
            content = str(self.content_input.value).strip()
            
            # Execute appropriate command
            if self.action_name == "delete_keywords":
                await watcher_commands.cmd_keywords_del(mock_message, [content])
                result_msg = f"✅ Keyword deleted: {content}"
            else:  # delete_premises
                await watcher_commands.cmd_premises_del(mock_message, [content])
                result_msg = f"✅ Premise #{content} deleted"
            
            # Try to respond, but handle expired interaction gracefully
            try:
                self.view.watcher_last_action = "list_keywords" if self.action_name == "delete_keywords" else "list_premises"
                content = _build_canvas_role_news_watcher_detail(
                    self.view.current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = CanvasRoleDetailView(
                    author_id=self.view.author_id,
                    role_name=self.view.role_name,
                    agent_config=self.view.agent_config,
                    admin_visible=self.view.admin_visible,
                    sections=self.view.sections,
                    current_detail=self.view.current_detail,
                    guild=self.view.guild
                )
                next_view.watcher_selected_method = self.view.watcher_selected_method
                next_view.watcher_last_action = self.view.watcher_last_action
                next_view.auto_response_preview = result_msg
                embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, self.view.current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                # Interaction expired - the action was successful, so just acknowledge silently
                logger.info(f"Watcher Canvas delete {self.action_name} completed but interaction expired")
            except discord.HTTPException as e:
                # Other HTTP errors - log but don't send followup to keep Canvas clean
                logger.warning(f"Could not update Canvas for Watcher delete {self.action_name}: {e}")
            
        except Exception as e:
            logger.exception(f"Error in Watcher delete modal: {e}")
            # Don't try to respond on error - the interaction is likely expired anyway


class CanvasWatcherListModal(discord.ui.Modal):
    """Modal for listing keywords and premises."""
    
    def __init__(self, list_type: str, view: "CanvasRoleDetailView", bot):
        self.list_type = list_type
        self.view = view
        self.bot = bot
        
        titles = {
            "keywords": "View Keywords",
            "premises": "View Premises"
        }
        
        super().__init__(title=titles.get(list_type, "View Configuration"), timeout=300)
        
        self.action_input = discord.ui.TextInput(
            label="Action",
            placeholder="Enter: list (to view), add (to add), or del (to delete)",
            style=discord.TextStyle.short,
            required=True,
            max_length=10
        )
        self.add_item(self.action_input)
        
        if list_type == "keywords":
            self.value_input = discord.ui.TextInput(
                label="Keywords",
                placeholder="Enter keyword(s) separated by commas (for add/del)...",
                style=discord.TextStyle.short,
                required=False,
                max_length=200
            )
        else:  # premises
            self.value_input = discord.ui.TextInput(
                label="Premise Text",
                placeholder="Enter premise text (for add/del)...",
                style=discord.TextStyle.long,
                required=False,
                max_length=500
            )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands
            
            # Create mock message
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild
                    
            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            watcher_commands = WatcherCommands(self.bot)
            
            # Build command arguments
            action = str(self.action_input.value).strip().lower()
            value = str(self.value_input.value).strip() if self.value_input.value else ""
            
            if self.list_type == "keywords":
                if action == "add" and value:
                    args = ["add"] + [kw.strip() for kw in value.split(",")]
                    await watcher_commands.cmd_keywords_add(mock_message, args)
                    result_msg = f"✅ Keywords added: {value}"
                elif action == "list":
                    await watcher_commands.cmd_keywords_list(mock_message, [])
                    result_msg = "📋 Keywords list sent by DM"
                elif action == "del" and value:
                    args = ["del"] + [kw.strip() for kw in value.split(",")]
                    await watcher_commands.cmd_keywords_del(mock_message, args)
                    result_msg = f"🗑️ Keywords deleted: {value}"
                else:
                    result_msg = "❌ Invalid action or missing keywords"
                    
            else:  # premises
                if action == "add" and value:
                    args = ["add", value]
                    await watcher_commands.cmd_premises_add(mock_message, args)
                    result_msg = "✅ Premise added successfully"
                elif action == "list":
                    await watcher_commands.cmd_premises_list(mock_message, [])
                    result_msg = "📋 Premises list sent by DM"
                elif action == "del" and value:
                    args = ["del", value]
                    await watcher_commands.cmd_premises_del(mock_message, args)
                    result_msg = "🗑️ Premise deleted successfully"
                else:
                    result_msg = "❌ Invalid action or missing premise text"
            
            # Try to respond, but handle expired interaction gracefully
            try:
                content = _build_canvas_role_action_view("news_watcher", f"list_{self.list_type}", self.view.admin_visible)
                next_view = CanvasRoleDetailView(
                    author_id=self.view.author_id,
                    role_name=self.view.role_name,
                    agent_config=self.view.agent_config,
                    admin_visible=self.view.admin_visible,
                    sections=self.view.sections,
                    current_detail="overview",
                    guild=self.view.guild
                )
                next_view.auto_response_preview = result_msg
                embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, "overview", None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                # Interaction expired - the action was successful, so just acknowledge silently
                logger.info(f"Watcher Canvas list {self.list_type} completed but interaction expired")
            except discord.HTTPException as e:
                # Other HTTP errors - log but don't send followup to keep Canvas clean
                logger.warning(f"Could not update Canvas for Watcher list {self.list_type}: {e}")
            
        except Exception as e:
            logger.exception(f"Error in Watcher list modal: {e}")
            # Don't try to respond on error - the interaction is likely expired anyway


class CanvasWatcherChannelSubscribeModal(discord.ui.Modal):
    """Modal for channel subscriptions using the selected watcher method."""

    def __init__(self, action_name: str, view: "CanvasRoleDetailView", bot):
        self.action_name = action_name
        self.view = view
        self.bot = bot
        title = "Channel Subscribe Categories" if action_name == "channel_subscribe_categories" else "Channel Subscribe Feeds"
        super().__init__(title=title, timeout=300)

        self.category_input = discord.ui.TextInput(
            label="Category",
            placeholder="Enter category (economy, technology, international, general, crypto)...",
            style=discord.TextStyle.short,
            required=True,
            max_length=50,
        )
        self.add_item(self.category_input)

        if action_name == "channel_subscribe_feeds":
            self.feed_id_input = discord.ui.TextInput(
                label="Feed ID",
                placeholder="Enter specific feed ID number...",
                style=discord.TextStyle.short,
                required=True,
                max_length=10,
            )
            self.add_item(self.feed_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if get_news_watcher_db_instance is None or not interaction.guild:
                await interaction.response.send_message("❌ Watcher database is not available.", ephemeral=True)
                return

            db = get_news_watcher_db_instance(str(interaction.guild.id))
            method = (self.view.watcher_selected_method or "flat").strip().lower()
            category = str(self.category_input.value).strip().lower()
            feed_id = None
            if self.action_name == "channel_subscribe_feeds":
                feed_id = int(str(self.feed_id_input.value).strip())

            channel_id = str(interaction.channel.id)
            channel_name = interaction.channel.name
            server_id = str(interaction.guild.id)
            server_name = interaction.guild.name

            ok = False
            if method == "flat":
                ok = db.subscribe_channel_category(channel_id, channel_name, server_id, server_name, category, feed_id)
            elif method == "general":
                premises, _ = db.get_channel_premises_with_context(channel_id)
                premises_str = ",".join(premises) if premises else ""
                ok = db.subscribe_channel_category_ai(channel_id, channel_name, server_id, server_name, category, feed_id, premises_str)
            elif method == "keyword":
                await interaction.response.send_message("❌ Channel keyword subscriptions are not available in Canvas yet.", ephemeral=True)
                return

            if not ok:
                await interaction.response.send_message("❌ Could not create channel subscription.", ephemeral=True)
                return

            self.view.watcher_last_action = self.action_name
            content = _build_canvas_role_news_watcher_detail(
                "admin",
                self.view.admin_visible,
                self.view.guild,
                self.view.author_id,
                selected_method=self.view.watcher_selected_method,
                last_action=self.view.watcher_last_action,
            )
            next_view = CanvasRoleDetailView(
                author_id=self.view.author_id,
                role_name=self.view.role_name,
                agent_config=self.view.agent_config,
                admin_visible=self.view.admin_visible,
                sections=self.view.sections,
                current_detail="admin",
                guild=self.view.guild,
            )
            feed_suffix = f" (feed #{feed_id})" if feed_id is not None else ""
            next_view.watcher_selected_method = self.view.watcher_selected_method
            next_view.watcher_last_action = self.view.watcher_last_action
            next_view.auto_response_preview = f"✅ {method.title()} channel subscription created for `{category}`{feed_suffix}."
            embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, "admin", None, next_view.auto_response_preview)
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        except ValueError:
            logger.warning("Invalid Feed ID in channel subscription modal")
        except Exception as e:
            logger.exception(f"Error in Watcher channel subscription modal: {e}")


class CanvasWatcherChannelUnsubscribeModal(discord.ui.Modal):
    """Modal to unsubscribe a channel subscription by numbered entry."""

    def __init__(self, view: "CanvasRoleDetailView", bot):
        self.view = view
        self.bot = bot
        super().__init__(title="Channel Unsubscribe", timeout=300)
        self.number_input = discord.ui.TextInput(
            label="Subscription Number",
            placeholder="Enter the numbered subscription from block 2...",
            style=discord.TextStyle.short,
            required=True,
            max_length=5,
        )
        self.add_item(self.number_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if get_news_watcher_db_instance is None or not interaction.guild:
                logger.warning("Watcher database not available for channel unsubscribe")
                return

            db = get_news_watcher_db_instance(str(interaction.guild.id))
            channel_id = str(interaction.channel.id)
            index = int(str(self.number_input.value).strip())

            all_subs = [("channel", category, feed_id) for category, feed_id, _ in db.get_channel_subscriptions(channel_id)]

            if index < 1 or index > len(all_subs):
                logger.warning(f"Invalid subscription number: {index}")
                return

            method, category, feed_id = all_subs[index - 1]
            ok = db.cancel_channel_subscription(channel_id, category, feed_id)
            if not ok:
                ok = db.cancel_category_subscription(f"channel_{channel_id}", category, feed_id)

            if not ok:
                logger.warning("Could not cancel channel subscription")
                return

            self.view.watcher_last_action = "channel_unsubscribe"
            content = _build_canvas_role_news_watcher_detail(
                "admin",
                self.view.admin_visible,
                self.view.guild,
                self.view.author_id,
                selected_method=self.view.watcher_selected_method,
                last_action=self.view.watcher_last_action,
            )
            next_view = CanvasRoleDetailView(
                author_id=self.view.author_id,
                role_name=self.view.role_name,
                agent_config=self.view.agent_config,
                admin_visible=self.view.admin_visible,
                sections=self.view.sections,
                current_detail="admin",
                guild=self.view.guild,
            )
            next_view.watcher_selected_method = self.view.watcher_selected_method
            next_view.watcher_last_action = self.view.watcher_last_action
            next_view.auto_response_preview = f"✅ Removed channel subscription #{index} from `{category}`."
            embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, "admin", None, next_view.auto_response_preview)
            await interaction.response.edit_message(content=None, embed=embed, view=next_view)
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in Watcher channel unsubscribe modal: {e}")


class CanvasWatcherFrequencyModal(discord.ui.Modal):
    """Modal for setting watcher frequency."""
    
    def __init__(self, view: "CanvasRoleDetailView", bot):
        self.view = view
        self.bot = bot
        
        super().__init__(title="Set Watcher Frequency", timeout=300)
        
        self.hours_input = discord.ui.TextInput(
            label="Hours",
            placeholder="Enter number of hours (1-24)...",
            style=discord.TextStyle.short,
            required=True,
            max_length=5
        )
        self.add_item(self.hours_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from roles.news_watcher.watcher_commands import WatcherCommands
            
            # Create mock message
            class MockMessage:
                def __init__(self, channel, author, guild):
                    self.channel = channel
                    self.author = author
                    self.guild = guild
                    
            mock_message = MockMessage(interaction.channel, interaction.user, interaction.guild)
            watcher_commands = WatcherCommands(self.bot)
            
            # Build command arguments
            hours = str(self.hours_input.value).strip()
            args = [hours]
            
            # Execute frequency command
            await watcher_commands.cmd_frequency(mock_message, args)
            
            result_msg = f"✅ Watcher frequency set to {hours} hours"
            
            # Try to respond, but handle expired interaction gracefully
            try:
                self.view.watcher_last_action = "watcher_frequency"
                current_detail = "admin" if self.view.current_detail == "admin" else "personal"
                content = _build_canvas_role_news_watcher_detail(
                    current_detail,
                    self.view.admin_visible,
                    self.view.guild,
                    self.view.author_id,
                    selected_method=self.view.watcher_selected_method,
                    last_action=self.view.watcher_last_action,
                )
                next_view = CanvasRoleDetailView(
                    author_id=self.view.author_id,
                    role_name=self.view.role_name,
                    agent_config=self.view.agent_config,
                    admin_visible=self.view.admin_visible,
                    sections=self.view.sections,
                    current_detail=current_detail,
                    guild=self.view.guild
                )
                next_view.watcher_selected_method = self.view.watcher_selected_method
                next_view.watcher_last_action = self.view.watcher_last_action
                next_view.auto_response_preview = result_msg
                embed = _build_canvas_role_embed("news_watcher", content or "", self.view.admin_visible, current_detail, None, next_view.auto_response_preview)
                await interaction.response.edit_message(content=None, embed=embed, view=next_view)
            except discord.NotFound:
                # Interaction expired - the action was successful, so just acknowledge silently
                logger.info(f"Watcher Canvas frequency completed but interaction expired")
            except discord.HTTPException as e:
                # Other HTTP errors - log but don't send followup to keep Canvas clean
                logger.warning(f"Could not update Canvas for Watcher frequency: {e}")
            
        except Exception as e:
            logger.exception(f"Error in Watcher frequency modal: {e}")
            # Don't try to respond on error - the interaction is likely expired anyway


class CanvasRoleDetailView(discord.ui.View):
    """Interactive navigation for role-specific details."""

    def __init__(self, author_id: int, role_name: str, agent_config: dict, admin_visible: bool,
                 sections: dict[str, str], current_detail: str = "overview", guild=None, message=None):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.role_name = role_name
        self.agent_config = agent_config
        self.admin_visible = admin_visible
        self.sections = sections
        self.current_detail = current_detail
        self.guild = guild
        self.message = message  # Store the message to delete it later
        
        # Dynamic state for News Watcher
        self.watcher_selected_method = None  # Will store "flat", "keyword", or "general"
        self.watcher_last_action = None  # Track last action for dynamic updates
        self.auto_response_preview = None
        
        role_details = _get_canvas_role_detail_items(role_name, admin_visible, current_detail)
        current_actions = _get_canvas_role_action_items_for_detail(role_name, current_detail, admin_visible)
        if current_actions:
            # For News Watcher, create dynamic dropdowns
            if role_name == "news_watcher" and current_detail in {"personal", "overview"}:
                self.add_item(CanvasWatcherMethodSelect(self))
                self.add_item(CanvasWatcherSubscriptionSelect(self))
            elif role_name == "news_watcher" and current_detail == "admin":
                self.add_item(CanvasWatcherAdminMethodSelect(self))
                self.add_item(CanvasWatcherAdminActionSelect(self))
            # For MC, create action dropdown
            elif role_name == "mc" and current_detail == "overview":
                self.add_item(CanvasMCActionSelect(self))
            else:
                self.add_item(CanvasRoleActionSelect(role_name, current_detail, admin_visible))
        for label, detail_name in role_details:
            self.add_item(CanvasRoleDetailButton(label=label, role_name=role_name, detail_name=detail_name))
        self._add_role_buttons()

    def _add_role_buttons(self):
        return

    async def on_timeout(self) -> None:
        """Called when the view times out - delete the entire message and cleanup callbacks."""
        # Cleanup MC callbacks before stopping
        if hasattr(self, '_mc_callbacks'):
            for mc_commands, original_callback in self._mc_callbacks:
                try:
                    mc_commands.set_message_callback(original_callback)
                except:
                    pass  # Ignore errors during cleanup
            self._mc_callbacks.clear()
        
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if self.message:
                    await self.message.delete()
                self.stop()
                return  # Success, exit the method
            except discord.NotFound:
                # Message already deleted, just stop the view
                self.stop()
                return
            except discord.Forbidden:
                for child in self.children:
                    child.disabled = True
                self.stop()
                return
            except Exception as e:
                if attempt == max_attempts - 1:  # Last attempt
                    logger.warning(f"Could not delete Canvas message on timeout after {max_attempts} attempts: {e}")
                    for child in self.children:
                        child.disabled = True
                    self.stop()
                else:
                    # Brief delay before retry
                    await asyncio.sleep(0.1)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the interactive Canvas to its original user."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True

    def _add_behavior_buttons(self):
        """Add available shared behavior buttons."""
        items = _get_canvas_behavior_detail_items(self.admin_visible)
        for label, detail_name in items:
            self.add_item(CanvasBehaviorDetailButton(label=label, detail_name=detail_name))

    def _get_watcher_block3_content(self, action_name: str) -> str:
        """Get dynamic content for block 3 based on selected action."""
        if action_name == "subscribe_categories":
            return "\n".join([
                "**📂 Browse & Subscribe**",
                "",
                f"Selected: {action_name.replace('_', ' ').title()}",
                "",
                "**Available Categories**",
                "- 🏦 **Economy**: Financial markets, business news, economic policies",
                "- 💻 **Technology**: AI, software, hardware, tech innovations", 
                "- 🌍 **International**: Global politics, world events, diplomacy",
                "- 📰 **General**: Breaking news, general current events",
                "- 🪙 **Crypto**: Cryptocurrency, blockchain, DeFi news",
                "",
                "**How to subscribe**",
                f"- Use the dropdown to select `{action_name.replace('_', ' ').title()}`",
                "- Fill in the modal with your preferences",
                "- Choose method: flat (all), keyword (filtered), or general (AI-critical)",
                "",
                "**Current subscriptions**",
                "- You can have up to 3 active subscriptions",
                "- Use `!watcher subscriptions` to see your current subscriptions",
                "- Use `!watcher unsubscribe <number>` to cancel",
            ])
        elif action_name == "list_keywords":
            return "\n".join([
                "**🔍 Keywords Management**",
                "",
                "Selected: List Keywords",
                "",
                "**Your Keywords Configuration**",
                "- Keywords filter news for keyword subscriptions",
                "- Only news containing your keywords will be delivered",
                "- You can add multiple keywords per subscription",
                "",
                "**How to manage keywords**",
                "- **List**: View all your configured keywords",
                "- **Add**: Add new keywords for filtering",
                "- **Delete**: Remove keywords you no longer need",
                "",
                "**Example keywords**",
                "- Technology: AI, blockchain, machine learning, software",
                "- Finance: bitcoin, stocks, inflation, trading",
                "- Science: research, discovery, space, medicine",
                "",
                "**Current status**",
                "- Select `list` from the dropdown to see your keywords",
                "- Keywords are sent by private message for privacy",
            ])
        elif action_name == "list_premises":
            return "\n".join([
                "**🤖 AI Premises Management**",
                "",
                "Selected: List Premises",
                "",
                "**Your AI Analysis Premises**",
                "- Premises guide AI in selecting globally critical news",
                "- AI evaluates news importance based on your criteria",
                "- Only news matching your premises will be delivered",
                "",
                "**How to manage premises**",
                "- **List**: View all your configured premises",
                "- **Add**: Add new premises for AI analysis",
                "- **Delete**: Remove premises you no longer need",
                "",
                "**Example premises**",
                "- \"I care about technological advances that affect society\"",
                "- \"Focus on economic policies that impact global markets\"",
                "- \"Prioritize climate change and environmental news\"",
                "",
                "**Current status**",
                "- Select `list` from the dropdown to see your premises",
                "- Premises are sent by private message for privacy",
            ])
        else:
            return "\n".join([
                "**Interactive Selection**",
                "- Use the dropdowns below to manage your subscriptions",
                "- Method dropdown: Choose filtering approach",
                "- Subscriptions dropdown: Subscribe or view configuration",
                "- This block will update based on your selections",
                "",
                "**Available categories**",
                "- Economy, Technology, International, General, Crypto",
                "- Use interactive dropdowns to browse and subscribe",
            ])

    def _get_watcher_admin_block3_content(self, action_name: str) -> str:
        """Get dynamic content for admin block 3 based on selected action."""
        if action_name == "channel_subscribe_categories":
            return "\n".join([
                "**📂 Channel Subscription Management**",
                "",
                f"Selected: {action_name.replace('_', ' ').title()}",
                "",
                "**Channel Subscription Impact**",
                "- News will be delivered to this channel for all members",
                "- Channel subscriptions count towards server limit (max 5)",
                "- All channel members will see the news notifications",
                "",
                "**Available Categories**",
                "- 🏦 **Economy**: Financial markets, business news, economic policies",
                "- 💻 **Technology**: AI, software, hardware, tech innovations", 
                "- 🌍 **International**: Global politics, world events, diplomacy",
                "- 📰 **General**: Breaking news, general current events",
                "- 🪙 **Crypto**: Cryptocurrency, blockchain, DeFi news",
                "",
                "**Admin Subscription Process**",
                f"- Select `{action_name.replace('_', ' ').title()}` from dropdown",
                "- Choose method: flat (all), keyword (filtered), or general (AI-critical)",
                "- Specify category and optionally feed ID",
                "- News will be delivered directly to this channel",
                "",
                "**Channel vs Personal**",
                "- **Channel**: Everyone in channel sees notifications",
                "- **Personal**: Only user gets notifications via DM",
            ])
        elif action_name == "channel_view_subscriptions":
            return "\n".join([
                "**📋 Channel Subscriptions Overview**",
                "",
                "Selected: View Channel Subscriptions",
                "",
                "**Current Channel Subscriptions**",
                "- Lists all active subscriptions for this channel",
                "- Shows subscription method, category, and feed details",
                "- Displays subscription numbers for management",
                "",
                "**Management Options**",
                "- **View**: See all current channel subscriptions",
                "- **Unsubscribe**: Cancel by subscription number",
                "- **Add**: Create new channel subscriptions",
                "",
                "**Channel Subscription Limits**",
                "- Maximum 5 channel subscriptions per server",
                "- Each subscription can have different filtering method",
                "- Admin can manage all channel subscriptions",
                "",
                "**Notification Behavior**",
                "- Channel subscriptions notify in this channel",
                "- All channel members receive notifications",
                "- Uses server-wide method configuration by default",
            ])
        elif action_name == "channel_unsubscribe":
            return "\n".join([
                "**🗑️ Channel Unsubscribe Management**",
                "",
                "Selected: Channel Unsubscribe",
                "",
                "**Unsubscribe Process**",
                "- Cancel channel subscriptions by number",
                "- View current subscriptions to get numbers",
                "- Immediate cancellation - no waiting period",
                "",
                "**Steps to Unsubscribe**",
                "1. First use 'View Subscriptions' to see current list",
                "2. Note the subscription number you want to cancel",
                "3. Select 'Channel Unsubscribe' and enter the number",
                "4. Confirmation will be shown in this channel",
                "",
                "**Impact of Cancellation**",
                "- No more news notifications for that subscription",
                "- Frees up channel subscription slot",
                "- Affects all channel members equally",
                "",
                "**Admin Responsibility**",
                "- Only admins can manage channel subscriptions",
                "- Consider impact on all channel members",
                "- Can re-subscribe later if needed",
            ])
        elif action_name == "watcher_frequency":
            return "\n".join([
                "**⏰ Watcher Frequency Configuration**",
                "",
                "Selected: Set Check Frequency",
                "",
                "**Frequency Impact**",
                "- Controls how often watcher checks for new news",
                "- Affects all subscriptions server-wide",
                "- Balance between timeliness and server resources",
                "",
                "**Recommended Settings**",
                "- **1-3 hours**: Breaking news, time-sensitive topics",
                "- **6-12 hours**: Regular updates, balanced approach",
                "- **24 hours**: Daily summaries, resource-efficient",
                "",
                "**Current Server Load**",
                "- More frequent checks = more server resource usage",
                "- Consider number of active subscriptions",
                "- Adjust based on news importance and timing needs",
                "",
                "**Configuration Process**",
                "- Enter frequency in hours (1-24)",
                "- Changes apply immediately to next check",
                "- Can be adjusted anytime by admin",
                "",
                "**Default Setting**",
                "- If not configured, uses system default",
                "- Recommended starting point: 6 hours",
            ])
        elif action_name == "watcher_run_now":
            return "\n".join([
                "**▶️ Force Watcher Run**",
                "",
                "Selected: Run News Check Immediately",
                "",
                "**Immediate News Check**",
                "- Bypasses normal frequency schedule",
                "- Checks all active subscriptions now",
                "- Delays next scheduled check accordingly",
                "",
                "**When to Use Force Run**",
                "- **Breaking news**: Important events happening now",
                "- **Testing**: Verify subscriptions are working",
                "- **Schedule changes**: After adding new subscriptions",
                "- **Manual refresh**: Get latest updates immediately",
                "",
                "**Process**",
                "- Checks all user and channel subscriptions",
                "- Processes news through configured methods",
                "- Delivers notifications according to subscriptions",
                "- Updates subscription timestamps",
                "",
                "**Admin Impact**",
                "- Affects all subscriptions server-wide",
                "- May generate multiple notifications",
                "- Consider timing for channel members",
                "",
                "**Resource Usage**",
                "- Temporary increase in server activity",
                "- Normal frequency resumes after completion",
                "- Safe to use occasionally, not continuously",
            ])
        else:
            return "\n".join([
                "**Admin Interactive Selection**",
                "- Use the dropdowns below to manage channel settings",
                "- Frequency control: Set how often watcher checks for news",
                "- Force run: Trigger immediate news check",
                "- This block will update based on your selections",
                "",
                "**Channel Management**",
                "- Channel subscriptions affect all users in this channel",
                "- Server method affects new subscriptions by default",
                "- Use admin controls to manage server-wide settings",
            ])

    async def disable_all_items(self):
        """Disable buttons when the view expires."""
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.primary, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_detail == "overview":
            roles_content = self.sections.get("roles")
            if not roles_content:
                await interaction.response.send_message("❌ The Canvas roles view is not available.", ephemeral=True)
                return
            roles_view = CanvasRolesView(self.author_id, self.agent_config, self.admin_visible, self.sections)
            roles_view.message = interaction.message
            roles_embed = _build_canvas_embed("roles", roles_content, self.admin_visible)
            await interaction.response.edit_message(content=None, embed=roles_embed, view=roles_view)
            return

        content = _build_canvas_role_view(self.role_name, self.agent_config, self.admin_visible, self.guild, self.author_id)
        if not content:
            await interaction.response.send_message("❌ This role is not available.", ephemeral=True)
            return

        detail_view = CanvasRoleDetailView(
            author_id=self.author_id,
            role_name=self.role_name,
            agent_config=self.agent_config,
            admin_visible=self.admin_visible,
            sections=self.sections,
            current_detail="overview",
            guild=self.guild,
        )
        detail_view.message = interaction.message
        role_embed = _build_canvas_role_embed(self.role_name, content, self.admin_visible, "overview")
        await interaction.response.edit_message(content=None, embed=role_embed, view=detail_view)

    @discord.ui.button(label="Home", style=discord.ButtonStyle.secondary, row=4)
    async def home_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        home_content = self.sections.get("home")
        if not home_content:
            await interaction.response.send_message("❌ The Canvas home is not available.", ephemeral=True)
            return
        nav_view = CanvasNavigationView(self.author_id, self.sections, self.admin_visible, self.agent_config, show_dropdown=False)
        nav_view.update_visibility()
        nav_view.message = interaction.message
        home_embed = _build_canvas_embed("home", home_content, self.admin_visible)
        await interaction.response.edit_message(content=None, embed=home_embed, view=nav_view)


class CanvasBehaviorView(discord.ui.View):
    def __init__(self, author_id: int, sections: dict[str, str], admin_visible: bool, agent_config: dict,
                 current_detail: str = "conversation", guild=None, message=None):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.sections = sections
        self.admin_visible = admin_visible
        self.agent_config = agent_config
        self.current_detail = current_detail
        self.guild = guild
        self.message = message
        self.auto_response_preview = None

        current_actions = _get_canvas_behavior_action_items_for_detail(current_detail, admin_visible)
        if current_actions:
            self.add_item(CanvasBehaviorActionSelect(current_detail, admin_visible))
        self._add_behavior_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True

    def _add_behavior_buttons(self):
        items = _get_canvas_behavior_detail_items(self.admin_visible)
        for label, detail_name in items:
            if detail_name != self.current_detail:
                self.add_item(CanvasBehaviorDetailButton(label=label, detail_name=detail_name))

    async def on_timeout(self) -> None:
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if self.message:
                    await self.message.delete()
                self.stop()
                return  # Success, exit the method
            except discord.NotFound:
                # Message already deleted, just stop the view
                self.stop()
                return
            except discord.Forbidden:
                for child in self.children:
                    child.disabled = True
                self.stop()
                return
            except Exception as e:
                if attempt == max_attempts - 1:  # Last attempt
                    logger.warning(f"Could not delete Canvas message on timeout after {max_attempts} attempts: {e}")
                    for child in self.children:
                        child.disabled = True
                    self.stop()
                else:
                    # Brief delay before retry
                    await asyncio.sleep(0.1)

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.primary, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Since conversation is now the behavior overview, back always goes to home
        home_content = self.sections.get("home")
        if not home_content:
            await interaction.response.send_message("❌ The Canvas home is not available.", ephemeral=True)
            return
        nav_view = CanvasNavigationView(self.author_id, self.sections, self.admin_visible, self.agent_config, show_dropdown=False)
        nav_view.update_visibility()
        nav_view.message = interaction.message
        home_embed = _build_canvas_embed("home", home_content, self.admin_visible)
        await interaction.response.edit_message(content=None, embed=home_embed, view=nav_view)

    @discord.ui.button(label="Home", style=discord.ButtonStyle.secondary, row=4)
    async def home_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        home_content = self.sections.get("home")
        if not home_content:
            await interaction.response.send_message("❌ The Canvas home is not available.", ephemeral=True)
            return
        nav_view = CanvasNavigationView(self.author_id, self.sections, self.admin_visible, self.agent_config, show_dropdown=False)
        nav_view.update_visibility()
        nav_view.message = interaction.message
        home_embed = _build_canvas_embed("home", home_content, self.admin_visible)
        await interaction.response.edit_message(content=None, embed=home_embed, view=nav_view)


class CanvasBehaviorDetailButton(discord.ui.Button):
    """Button that opens one General Behavior detail view."""

    def __init__(self, label: str, detail_name: str):
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self.detail_name = detail_name

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CanvasBehaviorView):
            await interaction.response.send_message("❌ Canvas behavior navigation is not available.", ephemeral=True)
            return

        content = _build_canvas_behavior_detail(self.detail_name, view.admin_visible, view.guild, view.agent_config)
        if not content:
            await interaction.response.send_message("❌ This behavior detail is not available.", ephemeral=True)
            return

        next_view = CanvasBehaviorView(
            author_id=view.author_id,
            sections=view.sections,
            admin_visible=view.admin_visible,
            agent_config=view.agent_config,
            current_detail=self.detail_name,
            guild=view.guild,
        )
        next_view.message = interaction.message
        behavior_embed = _build_canvas_behavior_embed(content, view.admin_visible, next_view.auto_response_preview)
        await interaction.response.edit_message(content=None, embed=behavior_embed, view=next_view)


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
    role_prompts_cfg = PERSONALIDAD.get("role_system_prompts", {})

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

    # Load general memories for context
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

    # Try to load custom prompt from personality JSON, fallback to default
    custom_cfg = PERSONALIDAD.get("prompts", {}).get("mission_commentary", {})
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






def _build_canvas_home(agent_config: dict, greet_name: str, nogreet_name: str, welcome_name: str, nowelcome_name: str,
                       role_cmd_name: str, talk_cmd_name: str, admin_visible: bool, server_name: str = "default",
                       author_id: int = 0) -> str:
    """Build the main Canvas hub view with status information."""
    enabled_roles = _get_enabled_roles(agent_config)
    roles_text = ", ".join(enabled_roles) if enabled_roles else "none"
    
    # Get home messages from personality with fallback
    home_messages = _personality_descriptions.get("canvas_home_messages", {})
    
    def _home_text(key: str, fallback: str) -> str:
        value = home_messages.get(key)
        return str(value).strip() if value else fallback
    
    # Build status content
    status_lines: list[str] = []
    
    try:
        database = AgentDatabase(server_name=server_name)
        daily_record = database.get_daily_memory_record()
        recent_record = database.get_recent_memory_record()
        relationship_record = database.get_user_relationship_memory(author_id)
    except Exception as e:
        logger.warning(f"Canvas status could not load memory data for server={server_name}: {e}")
        daily_record = None
        recent_record = None
        relationship_record = {"summary": "", "updated_at": None, "last_interaction_at": None, "metadata": {}}
    
    mission_prompt_lines = _load_role_mission_prompts(enabled_roles)
    mission_prompt_count = len(mission_prompt_lines)
    
    daily_summary = (daily_record or {}).get("summary", "").strip()
    recent_summary = (recent_record or {}).get("summary", "").strip()
    relationship_summary = (relationship_record or {}).get("summary", "").strip()
    
    status_lines.extend([
        f"**Personality:** `{_personality_name}`",
        f"**Active roles:** {roles_text}",
        "",
        "──────────────────────────────",
        "",
        "**Status**",
        f"- Mission prompt paragraphs active: {mission_prompt_count}",
        f"- Recent memory: {'available' if recent_summary else 'empty'}",
        f"- Daily memory: {'available' if daily_summary else 'empty'}",
        f"- Personal memory with you: {'available' if relationship_summary else 'empty'}",
    ])
    
    if recent_summary:
        status_lines.extend([
            "",
            "──────────────────────────────",
            "",
            "**Recent synthesis**",
            f"- {recent_summary[:900]}",
        ])
    
    if relationship_summary:
        status_lines.extend([
            "",
            "──────────────────────────────",
            "",
            "**Personal synthesis with you**",
            f"- {relationship_summary[:900]}",
        ])
    
    # Add final separator
    status_lines.extend([
        "",
        "──────────────────────────────"
    ])
    
    return "\n".join(status_lines)


def _build_canvas_behavior(greet_name: str, nogreet_name: str, welcome_name: str, nowelcome_name: str,
                           role_cmd_name: str, talk_cmd_name: str, admin_visible: bool) -> str:
    """Build the shared non-role behavior view - now shows conversation as default."""
    # Return the conversation view as the behavior overview
    return _build_canvas_behavior_detail("conversation", admin_visible, None, None) or f"**💬 {_bot_display_name} Comportamiento General**\n**Conversation surface**\n- Mention the bot in a server channel to talk\n- Send a DM to the bot for private interaction\n- Replies are shaped by the active personality and roles\n\n**Routing**\n- This is a shared global behavior, not a role-specific one\n- Use `!canvas roles` for role-specific flows"


def _build_canvas_behavior_detail(detail_name: str, admin_visible: bool, guild=None, agent_config: dict = None) -> str | None:
    """Build a detailed General Behavior view."""
    if detail_name in {"conversation", "chat"}:
        # Get conversation title from personality descriptions with fallback
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        conversation_title = behavior_descriptions.get("canvas_conversation_title", f"💬 {_bot_display_name} Canvas - General Behavior Conversation")
        
        # Replace {_bot} placeholder
        conversation_title = conversation_title.replace("{_bot}", _bot_display_name)
        
        return "\n".join([
            f"{conversation_title}\n",
            "**Conversation surface**",
            "- Mention the bot in a server channel to talk",
            "- Send a DM to the bot for private interaction",
            "- Replies are shaped by the active personality and roles",
            "",
            "**Routing**",
            "- This is a shared global behavior, not a role-specific one",
            "- Use `!canvas roles` for role-specific flows",
        ])
    if detail_name in {"greetings"}:
        from behavior.greet import clear_greeting_cache
        # Get greeting state from behaviors database first, fallback to memory
        greeting_enabled = False
        guild_id = "unknown"
        if guild:
            if hasattr(guild, 'id'):
                # guild is a guild object
                guild_id = str(guild.id)
                greeting_enabled = get_greeting_enabled(guild)
        else:
            greeting_enabled = False
            guild_id = "unknown"
        
        # Get title from personality descriptions with fallback
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        greetings_title = behavior_descriptions.get("canvas_greetings_title", f"👋 {_bot_display_name} Canvas - General Behavior Greetings")
        
        # Replace {_bot} placeholder
        greetings_title = greetings_title.replace("{_bot}", _bot_display_name)
        
        # Debug info
        from discord_bot.discord_utils import _greeting_config
        debug_config = _greeting_config.get(guild_id, {})
        
        return "\n".join([
            f"{greetings_title}\n",
            "**Admin controls**",
            f"- `!greet{_personality_name}` - Enable presence greetings",
            f"- `!nogreet{_personality_name}` - Disable presence greetings",
            "",
            "**Current status**",
            f"- {'✅ Enabled' if greeting_enabled else '❌ Disabled'}",
            "",
            "**Debug info**",
            f"- Guild ID: {guild_id}",
            f"- Behaviors DB available: {get_behaviors_db_instance is not None}",
            f"- Config exists: {guild_id in _greeting_config}",
            f"- Raw config: {debug_config}",
            f"- Final state: {greeting_enabled}",
            "",
            "**Routing**",
            "- Presence greetings are global server behavior",
            "- Uses behavior/greet.py module",
            "- Greets users when they come online (offline → online)",
            "- 5-minute cooldown between greetings per user",
        ])
    if detail_name in {"welcome"}:
        if not admin_visible:
            return _build_canvas_setup_not_available()
        
        # Get welcome state from behaviors database first, fallback to memory
        welcome_enabled = False
        if guild and get_behaviors_db_instance is not None:
            try:
                if hasattr(guild, 'id'):
                    guild_id = str(guild.id)
                else:
                    guild_id = str(guild)
                
                db = get_behaviors_db_instance(guild_id)
                welcome_enabled = db.get_welcome_enabled()
            except Exception as e:
                logger.warning(f"Error loading welcome state from behaviors database: {e}")
                # Fallback to memory config
                greeting_cfg = _discord_cfg.get("member_greeting", {})
                welcome_enabled = greeting_cfg.get("enabled", False)
        else:
            # Fallback to memory config
            greeting_cfg = _discord_cfg.get("member_greeting", {})
            welcome_enabled = greeting_cfg.get("enabled", False)
        
        # Get title from personality descriptions with fallback
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        welcome_title = behavior_descriptions.get("canvas_welcome_title", f"👋 {_bot_display_name} Canvas - General Behavior Welcome Messages")
        
        # Replace {_bot} placeholder
        welcome_title = welcome_title.replace("{_bot}", _bot_display_name)
        
        # Debug info
        guild_id = str(guild.id) if hasattr(guild, 'id') else str(guild) if guild else "unknown"
        
        return "\n".join([
            f"{welcome_title}\n",
            "**Admin controls**",
            "- `!welcome{_personality_name}` - Enable member welcome messages",
            "- `!nowelcome{_personality_name}` - Disable member welcome messages",
            "",
            "**Current status**",
            f"- {'✅ Enabled' if welcome_enabled else '❌ Disabled'}",
            "",
            "**Debug info**",
            f"- Guild ID: {guild_id}",
            f"- Behaviors DB available: {get_behaviors_db_instance is not None}",
            f"- Memory cfg: {greeting_cfg.get('enabled', False) if 'greeting_cfg' in locals() else 'N/A'}",
            f"- Final state: {welcome_enabled}",
            "",
            "**Concrete choices**",
            "- Boolean toggle: welcome messages on/off",
            "",
            "**Routing**",
            "- Welcome behavior is global to the server",
            "- Uses behavior/welcome.py module",
            "- Welcomes new members when they join the server",
            "- Only administrators can change it",
        ])
    if detail_name in {"commentary", "talk"}:
        if not admin_visible:
            return _build_canvas_setup_not_available()
        
        # Handle both guild object and guild ID
        if guild:
            if hasattr(guild, 'id'):
                guild_id = int(guild.id)
                guild_id_str = str(guild.id)
            else:
                guild_id = int(guild)
                guild_id_str = str(guild)
        else:
            guild_id = 0
            guild_id_str = "0"
        
        # Try to get state from behaviors database first
        enabled = False
        interval_minutes = 180
        channel_id = None
        
        if get_behaviors_db_instance is not None:
            try:
                db = get_behaviors_db_instance(guild_id_str)
                db_state = db.get_commentary_state()
                enabled = db_state['enabled']
                config = db_state.get('config', {})
                interval_minutes = config.get('interval_minutes', 180)
                channel_id = config.get('channel_id')
            except Exception as e:
                logger.warning(f"Error loading commentary from behaviors DB: {e}")
        
        # Fallback to memory if DB not available or no state found
        if not enabled and not channel_id:
            state = _talk_state_by_guild_id.get(guild_id) or {}
            enabled = state.get("enabled", False)
            interval_minutes = state.get("interval_minutes", 180)
            channel_id = state.get("channel_id")
        
        # Get title from personality descriptions with fallback
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        commentary_title = behavior_descriptions.get("canvas_commentary_title", f"🗣️ {_bot_display_name} Canvas - General Behavior Mission Commentary")
        
        # Replace {_bot} placeholder
        commentary_title = commentary_title.replace("{_bot}", _bot_display_name)
        
        return "\n".join([
            f"{commentary_title}\n",
            "**Admin controls**",
            f"- `!talk{_personality_name} on` - Enable commentary",
            f"- `!talk{_personality_name} off` - Disable commentary",
            f"- `!talk{_personality_name} now` - Trigger commentary now",
            f"- `!talk{_personality_name} status` - Inspect current status",
            f"- `!talk{_personality_name} frequency <minutes>` - Set frequency",
            "",
            "**Current status**",
            f"- {'✅ Enabled' if enabled else '❌ Disabled'}",
            f"- Interval: {interval_minutes} minutes",
            f"- Channel: {f'<#{channel_id}>' if channel_id else 'Not set'}" if enabled else "- Channel: N/A (disabled)",
            "",
            "**Debug info**",
            f"- Guild ID: {guild_id_str}",
            f"- Behaviors DB available: {get_behaviors_db_instance is not None}",
            f"- Memory state: {_talk_state_by_guild_id.get(guild_id, 'None')}",
            "",
            "**Concrete choices**",
            "- Boolean toggle: commentary on/off",
            "- Action button: run commentary now",
            "- Number input: frequency in minutes",
            "",
            "**Routing**",
            "- Commentary is global behavior driven by active roles",
            "- Only administrators can configure it",
        ])
    if detail_name in {"taboo"}:
        if not admin_visible:
            return _build_canvas_setup_not_available()
        
        # Handle both guild object and guild ID
        if guild:
            if hasattr(guild, 'id'):
                guild_id = int(guild.id)
            else:
                guild_id = int(guild)
        else:
            guild_id = 0
        
        state = get_taboo_state(guild_id)
        keywords = ", ".join(state.get("keywords", [])) or "(none)"
        
        # Get title from personality descriptions with fallback
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        taboo_title = behavior_descriptions.get("canvas_taboo_title", f"🚫 {_bot_display_name} Canvas - General Behavior Taboo")
        
        # Replace {_bot} placeholder
        taboo_title = taboo_title.replace("{_bot}", _bot_display_name)
        
        return "\n".join([
            f"{taboo_title}\n",
            "**Admin controls**",
            "- `!taboo on` - Enable taboo responses",
            "- `!taboo off` - Disable taboo responses",
            "- `!taboo add <keyword>` - Add a forbidden keyword",
            "- `!taboo del <keyword>` - Remove a forbidden keyword",
            "- `!taboo list` - Inspect the current keyword list",
            "",
            "**Current status**",
            f"- {'On' if state.get('enabled', False) else 'Off'}",
            "",
            "**Current keywords**",
            f"- {keywords}",
            "",
            "**Debug info**",
            f"- Guild ID: {guild_id}",
            f"- Taboo DB available: {get_taboo_db_instance is not None}",
            f"- Keywords count: {len(state.get('keywords', []))}",
            f"- Default from prompts: {'orco' in state.get('keywords', [])}",
            "",
            "**Routing**",
            "- Taboo watches normal server chat and can trigger an in-character reply",
            "- Only administrators can configure it",
        ])
    if detail_name in {"role_control", "roles"}:
        if not admin_visible:
            return _build_canvas_setup_not_available()
        enabled_roles = _get_enabled_roles(agent_config) if agent_config else []
        all_roles = ["news_watcher", "treasure_hunter", "trickster", "banker", "mc"]
        role_labels = {
            "news_watcher": "News Watcher",
            "treasure_hunter": "Treasure Hunter", 
            "trickster": "Trickster",
            "banker": "Banker",
            "mc": "MC",
        }
        
        # Debug info - check actual config
        roles_cfg = (agent_config or {}).get("roles", {})
        
        status_lines = []
        for role_name in all_roles:
            label = role_labels.get(role_name, role_name.replace("_", " ").title())
            # Check both methods for consistency
            method1_status = role_name in enabled_roles
            method2_status = roles_cfg.get(role_name, {}).get("enabled", False)
            status = "✅ Enabled" if method1_status else "❌ Disabled"
            # Add debug info if there's a mismatch
            debug_info = f" (cfg:{method2_status})" if method1_status != method2_status else ""
            status_lines.append(f"- {label}: {status}{debug_info}")
        
        # Add debug section
        debug_lines = [
            "**Debug Info**",
            f"- Total roles in config: {len(roles_cfg)}",
            f"- Enabled roles found: {len(enabled_roles)}",
            f"- Config keys: {list(roles_cfg.keys())}",
            f"- Enabled list: {enabled_roles}",
            ""
        ]
        
        # Get title from personality descriptions with fallback
        behavior_descriptions = _personality_descriptions.get("behavior_messages", {})
        role_control_title = behavior_descriptions.get("canvas_role_control_title", f"🎛️ {_bot_display_name} Canvas - General Behavior Role Control")
        
        # Replace {_bot} placeholder
        role_control_title = role_control_title.replace("{_bot}", _bot_display_name)
        
        return "\n".join([
            f"{role_control_title}\n",
            "**Admin controls**",
            f"- `!role{_personality_name} <role> on` - Activate a role",
            f"- `!role{_personality_name} <role> off` - Deactivate a role",
            "",
            *debug_lines,
            "**Current status**",
            *status_lines,
            "",
            "**Concrete choices**",
            "- Select menu: choose role",
            "- Boolean toggle: on/off",
            "",
            "**Routing**",
            "- Role activation is global server behavior",
            "- Detailed per-role work continues in `!canvas roles`",
        ])
    return None


def _build_canvas_roles(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the role navigation Canvas view."""
    roles_config = (agent_config or {}).get("roles", {})
    
    # Get roles view messages from personality with fallback
    roles_messages = _personality_descriptions.get("roles_view_messages", {})
    role_descriptions = roles_messages.get("role_descriptions", {})
    server_name = "Server"  # We don't have guild context here
    
    # Title and description from descriptions.json with fallback
    title = roles_messages.get("title", f"🎭 PUTRE ROLE MANAGER - {server_name} 🎭\n")
    description = roles_messages.get("description", "🌟 Putre the role manager oversees all aspects of the clan. Each role has unique abilities to serve the tribe. Explore different specializations and choose your path.")
    
    # Helper messages
    enabled_status = roles_messages.get("enabled_status", "ACTIVE")
    interval_info = roles_messages.get("interval_info", "⏰ Every {interval}h")
    inactive_status = roles_messages.get("inactive_status", "❌ INACTIVE")
    
    parts = [
        description,
        "──────────────────────────────",
        ""
    ]
    
    # Track active and inactive roles
    active_roles = []
    inactive_roles = []
    
    # Helper function to get role info with fallback
    def get_role_info(role_key):
        role_info = role_descriptions.get(role_key, {})
        fallback_titles = {
            "news_watcher": "News Watcher",
            "treasure_hunter": "Treasure Hunter", 
            "trickster": "Trickster",
            "banker": "Banker",
            "mc": "MC"
        }
        fallback_descriptions = {
            "news_watcher": "News monitoring for the clan",
            "treasure_hunter": "Treasure hunting and POE2 monitoring",
            "trickster": "Games, tricks, and accusations",
            "banker": "Clan economy and personal wallets",
            "mc": "Music playback and queue management"
        }
        
        return {
            "title": role_info.get("title", fallback_titles.get(role_key, role_key)),
            "description": role_info.get("description", fallback_descriptions.get(role_key, "Role functionality"))
        }
    
    # News Watcher
    if is_role_enabled_check("news_watcher", agent_config, guild):
        active_roles.append("news_watcher")
        interval = get_role_interval_hours("news_watcher", agent_config, guild, 1)
        role_info = get_role_info("news_watcher")
        parts.append(
            f"📡 **{role_info['title']}** {enabled_status} {interval_info.format(interval=interval)}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # Treasure Hunter
    if is_role_enabled_check("treasure_hunter", agent_config, guild):
        active_roles.append("treasure_hunter")
        interval = get_role_interval_hours("treasure_hunter", agent_config, guild, 1)
        role_info = get_role_info("treasure_hunter")
        parts.append(
            f"💎 **{role_info['title']}** {enabled_status} {interval_info.format(interval=interval)}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # Trickster
    if is_role_enabled_check("trickster", agent_config, guild):
        active_roles.append("trickster")
        role_info = get_role_info("trickster")
        parts.append(
            f"🎭 **{role_info['title']}** {enabled_status}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # Banker
    if is_role_enabled_check("banker", agent_config, guild):
        active_roles.append("banker")
        interval = get_role_interval_hours("banker", agent_config, guild, 24)
        role_info = get_role_info("banker")
        parts.append(
            f"💰 **{role_info['title']}** {enabled_status} {interval_info.format(interval=interval)}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # MC
    mc_cfg = roles_config.get("mc", {})
    if mc_cfg.get("enabled", False):
        active_roles.append("mc")
        role_info = get_role_info("mc")
        parts.append(
            f"🎵 **{role_info['title']}** {enabled_status}\n"
            f"• {role_info['description']}\n"
            ""
        )
    
    # Check for inactive roles
    all_possible_roles = ["news_watcher", "treasure_hunter", "trickster", "banker", "mc"]
    for role in all_possible_roles:
        if role not in active_roles:
            inactive_roles.append(role)
    
    # Add inactive roles section if any exist
    if inactive_roles:
        parts.extend([
            "",
            "**DEACTIVATE ROLES:**",
            ""
        ])
        
        for role in inactive_roles:
            role_info = get_role_info(role)
            role_icons = {
                "news_watcher": "📡",
                "treasure_hunter": "💎", 
                "trickster": "🎭",
                "banker": "💰",
                "mc": "🎵"
            }
            icon = role_icons.get(role, "📋")
            parts.append(f"{icon} {role_info['title']} {inactive_status}")
    
    # If no roles are active, show helpful message
    if not active_roles:
        no_roles_msg = roles_messages.get("no_roles_active", 
            "🌫️ **NO ACTIVE ROLES**\n\nNo specialized roles are currently active. Ask an administrator to activate some roles using `!canvas setup`.\n\n**Available roles to activate:**\n• 📡 News Watcher - News monitoring\n• 💎 Treasure Hunter - Treasure hunting\n• 🎭 Trickster - Games and tricks\n• 💰 Banker - Clan economy\n• 🎵 MC - Music and entertainment"
        )
        parts.append(no_roles_msg)
    
    # Add final separator if there are roles
    if active_roles or inactive_roles:
        parts.append("──────────────────────────────")
    
    return "\n".join(parts)


def _build_canvas_personal() -> str:
    """Build the personal/DM-oriented Canvas view."""
    return (
        f"👤 **{_bot_display_name} Canvas - Personal Space**\n\n"
        "**Personal workflows**\n"
        "- News Watcher personal subscriptions: `!watcherhelp`\n"
        "- POE2 objectives and league: `!hunter poe2 help`\n"
        "- Wallet and recent transactions: `!banker balance` (unified in Canvas)\n"
        "- Dice game stats and balance: `!dice stats`, `!dice balance`\n\n"
        "**DM-oriented flows**\n"
        "- Some Watcher responses are delivered by private message\n"
        "- POE2 personal management is DM-only for some commands\n"
        "- Banker balance is designed to answer privately\n\n"
        "**Concrete choices**\n"
        "- Text input: tracked item names, watcher keywords, watcher premises\n"
        "- Select menu: league choices such as `Standard` or `Fate of the Vaal`\n"
        "- Boolean toggle: critical watcher alerts on/off\n\n"
        "**Fast path**\n"
        "- `!watchernotify` - Subscribe to critical watcher alerts\n"
        "- `!hunter poe2 list` - Show tracked POE2 objectives\n"
        "- `!banker balance` - Show your wallet (unified in Canvas)\n"
        "- `!dice ranking` - View the current ranking"
    )


def _build_canvas_help() -> str:
    """Build the help and troubleshooting Canvas view."""
    return (
        f"📚 **{_bot_display_name} Canvas - Help & Troubleshooting**\n\n"
        "**Command lookup**\n"
        "- `!agenthelp` - Full command summary\n"
        "- `!readme` - Complete guide by private message\n"
        "- `!watcherhelp` - News Watcher user guide\n"
        "- `!watcherchannelhelp` - News Watcher channel/admin guide\n"
        "- `!hunter help` / `!hunter poe2 help`\n"
        "- `!trickster help`\n"
        "- `!banker help`\n"
        "- `!mc help`\n\n"
        "**Common issues**\n"
        "- If a command fails in DM, retry it in a server channel\n"
        "- If a command fails in a server, check whether it is DM-only\n"
        "- If setup commands fail, verify administrator permissions\n"
        "- If a role command is missing, verify the role is enabled in configuration\n\n"
        "**Concrete choices**\n"
        "- Use role surfaces when you need command-specific options\n"
        "- Use setup/behavior surfaces when you need server-wide toggles\n"
        "- Use personal surfaces when you need DM-oriented text or list management\n\n"
        "**Navigation**\n"
        "- `!canvas home`\n"
        "- `!canvas setup`\n"
        "- `!canvas roles`\n"
        "- `!canvas role <name>`\n"
        "- `!canvas role news_watcher personal`\n"
        "- `!canvas role trickster dice`\n"
        "- `!canvas role treasure_hunter personal`\n"
        "- `!canvas role banker wallet`\n"
        "- `!canvas personal`"
    )


def _build_canvas_role_news_watcher(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the News Watcher role view (same as personal view)."""
    # Use the personal view content directly
    return _build_canvas_role_news_watcher_detail("personal", admin_visible, guild, 0)


def _get_canvas_channel_subscriptions_info(guild) -> str:
    """Get formatted channel subscriptions information for canvas display."""
    try:
        if get_news_watcher_db_instance is None:
            return "**Channel subscriptions**\n- Unable to load channel subscription data"
        
        db = get_news_watcher_db_instance(str(guild.id))
        channel_id = str(guild.id)  # Using guild ID as channel ID for server-wide subscriptions
        
        # Get channel subscription count
        current_count = db.count_channel_subscriptions(channel_id)
        max_subs = 5  # Channel subscriptions limit
        usage_info = f"**Channel subscriptions** ({current_count}/{max_subs})\n"
        
        if current_count == 0:
            usage_info += "- No active channel subscriptions\n"
        else:
            subscriptions_info = "- **Channel subscriptions:**\n"
            channel_subs = db.get_channel_subscriptions(channel_id)
            for i, (category, feed_id, _) in enumerate(channel_subs, 1):
                if feed_id:
                    subscriptions_info += f"  {i}. 📡 {category} (feed #{feed_id})\n"
                else:
                    subscriptions_info += f"  {i}. 📡 {category} (all feeds)\n"
            usage_info += subscriptions_info
        
        # Add server configuration info
        config_info = "\n──────────────────────────────\n\n**Server configuration**\n"
        
        # Get frequency
        try:
            frequency = db.get_frequency_config(str(guild.id))
            config_info += f"- ⏰ **Check frequency**: Every {frequency} hours\n"
        except:
            config_info += "- ⏰ **Check frequency**: Not configured\n"
        
        # Get method
        method = db.get_method_config(str(guild.id))
        method_labels = {
            "flat": "Flat (All news)",
            "keyword": "Keyword (Filtered)",
            "general": "General (AI-critical)"
        }
        config_info += f"- 🔧 **Default method**: {method_labels.get(method, 'Unknown')}\n"
        config_info += "──────────────────────────────\n"
        
        return usage_info + config_info
        
    except Exception as e:
        logger.warning(f"Could not load channel subscriptions for Canvas: {e}")
        return "**Channel subscriptions**\n- Error loading channel subscription data"


def _get_canvas_user_subscriptions_info(guild, author_id: int) -> str:
    """Get formatted user subscriptions information for canvas display."""
    try:
        if get_news_watcher_db_instance is None:
            return "**Active subscriptions**\n- Unable to load subscription data"
        
        db = get_news_watcher_db_instance(str(guild.id))
        user_id = str(author_id)
        
        # Get subscription count and limits
        current_count = db.count_user_subscriptions(user_id)
        max_subs = 3
        usage_info = f"**Active subscriptions** ({current_count}/{max_subs})\n"
        
        if current_count == 0:
            usage_info += "- No active subscriptions\n"
        else:
            # Get all subscriptions with their methods
            subscriptions_info = "- **Your subscriptions:**\n"
            
            # Get flat subscriptions
            flat_subs = db.get_user_subscriptions(user_id)
            for i, (category, feed_id, _) in enumerate(flat_subs, 1):
                if feed_id:
                    subscriptions_info += f"  {i}. 📰 Flat: {category} (feed #{feed_id})\n"
                else:
                    subscriptions_info += f"  {i}. 📰 Flat: {category} (all feeds)\n"
            
            # Get keyword subscriptions
            keyword_subs = db.get_user_keyword_subscriptions(user_id)
            for i, (category, keywords, _) in enumerate(keyword_subs, len(flat_subs) + 1):
                subscriptions_info += f"  {i}. 🔍 Keywords: {category} - {keywords}\n"
            
            # Get AI subscriptions
            ai_subs = db.get_user_ai_subscriptions(user_id)
            for i, (category, feed_id, _) in enumerate(ai_subs, len(flat_subs) + len(keyword_subs) + 1):
                if feed_id:
                    subscriptions_info += f"  {i}. 🤖 AI: {category} (feed #{feed_id})\n"
                else:
                    subscriptions_info += f"  {i}. 🤖 AI: {category} (all feeds)\n"
            
            usage_info += subscriptions_info
        
        # Add configuration info
        config_info = "\n──────────────────────────────\n\n**Configuration status**\n"
        
        # Check keywords
        keywords = db.get_user_keywords(user_id)
        if keywords:
            config_info += f"- 🔍 **Keywords**: {', '.join(keywords[:3])}"
            if len(keywords) > 3:
                config_info += f" (+{len(keywords) - 3} more)"
            config_info += "\n"
        else:
            config_info += "- 🔍 **Keywords**: None configured\n"
        
        # Check premises
        premises, _ = db.get_premises_with_context(user_id)
        if premises:
            config_info += f"- 🤖 **Premises**: {len(premises)} configured"
            if premises:
                preview = premises[0][:50] + "..." if len(premises[0]) > 50 else premises[0]
                config_info += f" - \"{preview}\""
            config_info += "\n"
        else:
            config_info += "- 🤖 **Premises**: None configured\n"
        
        return usage_info + config_info
        
    except Exception as e:
        logger.warning(f"Could not load user subscriptions for Canvas: {e}")
        return "**Active subscriptions**\n- Error loading subscription data"


def _build_canvas_role_news_watcher_detail(
    detail_name: str,
    admin_visible: bool,
    guild=None,
    author_id: int = 0,
    selected_method: str | None = None,
    last_action: str | None = None,
) -> str | None:
    """Build a detailed News Watcher view with 3-block structure."""
    watcher_messages = get_watcher_messages() if get_watcher_messages else {}
    watcher_descriptions = _personality_descriptions.get("watcher_messages", {})

    def _watcher_text(key: str, fallback: str) -> str:
        value = watcher_descriptions.get(key, watcher_messages.get(key))
        return str(value).strip() if value else fallback

    def _get_watcher_personal_intro_block() -> str:
        """Get the standard watcher personal introduction block."""
        return "\n".join([
            f"**{_watcher_text('canvas_personal_title', 'News Watcher Personal')}**",
            _watcher_text('canvas_personal_description', 'Build and maintain your personal news subscriptions. Choose a method first, then subscribe to categories or feeds, or review your keywords and premises.'),
            "──────────────────────────────",
        ])

    def _get_watcher_admin_intro_block() -> str:
        """Get the standard watcher admin introduction block."""
        return "\n".join([
            f"**{_watcher_text('canvas_admin_title', '📡 News Watcher')} Admin**",
            "",
            _watcher_text("canvas_admin_description", "Manage channel subscriptions with the same flow as personal view, but applied to channels. Choose a method, then manage categories, feeds, and server actions."),
            "──────────────────────────────",
        ])

    def _format_categories() -> str:
        if not guild or get_news_watcher_db_instance is None:
            return "- Economy\n- Technology\n- International\n- General\n- Crypto"
        try:
            db = get_news_watcher_db_instance(str(guild.id))
            categories = db.get_available_categories()
            if not categories:
                return "- No categories available"
            return "\n".join([
                f"- {str(category).title()} ({count} feeds)"
                for category, count in categories
            ])
        except Exception as e:
            logger.warning(f"Could not load watcher categories for Canvas: {e}")
            return "- Error loading categories"

    def _format_feeds() -> str:
        if not guild or get_news_watcher_db_instance is None:
            return "- No feed data available"
        try:
            db = get_news_watcher_db_instance(str(guild.id))
            feeds = db.get_active_feeds()
            if not feeds:
                return "- No feeds available"
            lines = []
            for feed_id, name, _url, category, country, language, _priority, _keywords, feed_type in feeds[:12]:
                meta = []
                if category:
                    meta.append(str(category).title())
                if feed_type:
                    meta.append(str(feed_type))
                if country:
                    meta.append(str(country).upper())
                if language:
                    meta.append(str(language))
                meta_text = " | ".join(meta) if meta else "Feed"
                lines.append(f"- #{feed_id} {name} ({meta_text})")
            if len(feeds) > 12:
                lines.append(f"- ... and {len(feeds) - 12} more feeds")
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Could not load watcher feeds for Canvas: {e}")
            return "- Error loading feeds"

    def _format_keywords() -> str:
        if not guild or not author_id or get_news_watcher_db_instance is None:
            return "- No keywords configured"
        try:
            db = get_news_watcher_db_instance(str(guild.id))
            raw_keywords = db.get_user_keywords(str(author_id))
            if not raw_keywords:
                return "- No keywords configured"
            parts = [item.strip() for item in str(raw_keywords).split(",") if item.strip()]
            return "\n".join([f"- {keyword}" for keyword in parts[:15]])
        except Exception as e:
            logger.warning(f"Could not load watcher keywords for Canvas: {e}")
            return "- Error loading keywords"

    def _format_premises() -> str:
        if not guild or not author_id or get_news_watcher_db_instance is None:
            return "- No premises configured"
        try:
            db = get_news_watcher_db_instance(str(guild.id))
            premises, scope = db.get_premises_with_context(str(author_id))
            if not premises:
                return "- No premises configured"
            lines = [f"- Scope: {scope}"]
            lines.extend([f"- {premise}" for premise in premises[:8]])
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Could not load watcher premises for Canvas: {e}")
            return "- Error loading premises"

    method_labels = {
        "flat": "Flat",
        "keyword": "Keyword",
        "general": "General",
        None: "Not selected",
    }
    method_label = method_labels.get(selected_method, str(selected_method).title() if selected_method else "Not selected")

    if detail_name in {"personal", "overview"}:
        block1 = _get_watcher_personal_intro_block()

        subscriptions_info = _get_canvas_user_subscriptions_info(guild, author_id) if guild and author_id else "**Active subscriptions**\n- No subscription data available"
        block2 = "\n".join([
            f"**Selected Method**: {method_label}",
            "",
            subscriptions_info,
        ])
        
        # Add separator after block2
        block2 += "\n──────────────────────────────"

        if last_action == "list_feeds":
            block3_title = "**Available Feeds**"
            block3_body = _format_feeds()
        elif last_action == "list_keywords":
            block3_title = "**Configured Keywords**"
            block3_body = _format_keywords()
        elif last_action == "list_premises":
            block3_title = "**Configured Premises**"
            block3_body = _format_premises()
        elif last_action == "list_categories":
            block3_title = "**Available Categories**"
            block3_body = _format_categories()
        else:
            block3_title = "**Available Categories**"
            block3_body = _format_categories()

        block3 = "\n".join([
            block3_title,
            "",
            block3_body,
        ])

        return "\n".join([block1, "", block2, "", block3])

    if detail_name == "admin" and admin_visible:
        block1 = _get_watcher_admin_intro_block()

        channel_subscriptions = _get_canvas_channel_subscriptions_info(guild) if guild else "**Channel subscriptions**\n- No channel data available"
        block2 = "\n".join([
            f"**Selected Method**: {method_label}",
            "",
            channel_subscriptions,
            "──────────────────────────────"
        ])

        if last_action == "list_feeds":
            block3_title = "**Available Feeds**"
            block3_body = _format_feeds()
        elif last_action == "channel_view_subscriptions":
            block3_title = "**Current Channel Subscriptions**"
            block3_body = channel_subscriptions
        elif last_action == "channel_unsubscribe":
            block3_title = "**Channel Unsubscribe**"
            block3_body = "\n".join([
                "- Use the numbered list from block 2",
                "- Choose the subscription number to remove",
                "- The change affects this channel",
            ])
        elif last_action == "watcher_frequency":
            block3_title = "**Watcher Frequency**"
            block3_body = "\n".join([
                "- Set how often the watcher checks for news",
                "- Recommended range: 1 to 24 hours",
                "- This affects the server-wide watcher schedule",
            ])
        elif last_action == "watcher_run_now":
            block3_title = "**Force Watcher Run**"
            block3_body = "\n".join([
                "- Runs the watcher immediately",
                "- Useful after adding or changing channel subscriptions",
                "- May generate notifications in subscribed channels",
            ])
        elif last_action == "list_categories":
            block3_title = "**Available Categories**"
            block3_body = _format_categories()
        elif last_action == "list_feeds":
            block3_title = "**Available Feeds**"
            block3_body = _format_feeds()
        else:
            block3_title = "**Available Categories**"
            block3_body = _format_categories()

        block3 = "\n".join([
            block3_title,
            "",
            block3_body,
        ])

        return "\n".join([block1, "", block2, "", block3])
    if detail_name in {"keywords", "filters"}:
        return "\n".join([
            f"**📡 {_bot_display_name} Canvas - News Watcher Keywords**",
            "**Main goal**",
            "- Shape what the watcher considers relevant for you",
            "",
            "**Keyword management**",
            "- `!watcher keywords add <word>` - Add a keyword",
            "- `!watcher keywords del <word>` - Remove a keyword",
            "- `!watcher keywords list` - Review your active keywords",
            "",
            "**AI premises**",
            "- `!watcher premises add \"text\"` - Add a premise",
            "- `!watcher premises del <number>` - Remove a premise",
            "- `!watcher premises list` - Review premises",
            "",
            "**Best next actions**",
            "- Add only a few strong keywords first",
            "- Use premises when raw keywords are too noisy",
            "",
            "**Concrete choices**",
            "- Text input: keyword or premise text",
            "- Number input: premise index to delete",
            "",
            "**Routing**",
            "- These settings shape your personal watcher filtering",
            "- Use `!canvas role news_watcher` to return to the role overview",
        ])
    if detail_name in {"admin", "channel", "setup"}:
        if not admin_visible:
            return _build_canvas_setup_not_available()
        current_method = _get_canvas_watcher_method_label(str(guild.id)) if guild else "Unknown"
        current_frequency = _get_canvas_watcher_frequency_hours(str(guild.id)) if guild else 1
        return "\n".join([
            f"**{_watcher_text('canvas_admin_title', '📡 News Watcher')} Admin**",
            "**Main goal**",
            "- Configure how the server receives and filters watcher output",
            "",
            "**Channel and server setup**",
            "- `!watcherchannelhelp` - Open the channel/admin help surface",
            "- `!watcherchannel subscribe <category> [feed_id]` - Subscribe the current channel",
            "- `!watcherchannel unsubscribe <category>` - Remove a channel subscription",
            "- `watcherchannel status` - Inspect the current channel state",
            "",
            "**Server filtering state**",
            f"- Current method: {current_method}",
            "- `Method: Flat` - all news with opinions",
            "- `Method: Keyword` - filtered by keywords",
            "- `Method: General` - AI-based critical news",
            "",
            "**Operations**",
            f"- Current frequency: every {current_frequency}h",
            "- `Watcher: Frequency` - Adjust watcher frequency",
            "- `Watcher: Run Now` - Force one watcher iteration",
            "",
            "**Best next actions**",
            "- Confirm channel status before changing filtering state",
            "- Use `!forcewatcher` after setup to verify the pipeline",
            "",
            "**Concrete choices**",
            "- Selector options: `flat` / `keyword` / `general`",
            "- Number input: watcher frequency in hours",
            "- Text input: category or feed id for channel routing",
            "",
            "**Routing**",
            "- These actions are server-only and admin-only",
            "- Use `!canvas role news_watcher` to return to the role overview",
        ])
    return None


def _build_canvas_role_treasure_hunter(agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str:
    """Build the Treasure Hunter role view."""
    treasure_messages = _personality_answers.get("treasure_hunter_messages", {})
    treasure_descriptions = _personality_descriptions.get("treasure_hunter_messages", {})
    
    def _treasure_text(key: str, fallback: str) -> str:
        value = treasure_descriptions.get(key, treasure_messages.get(key))
        # Replace {_bot} placeholder
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback
    
    def _get_treasure_overview_intro_block() -> str:
        return "\n".join([
            _treasure_text("canvas_th_overview_title", f"💎 {_bot_display_name} Canvas - Treasure Hunter"),
        ])
    
    def _get_treasure_poe2_intro_block() -> str:
        return "\n".join([
            _treasure_text("canvas_th_poe2_title", f"💎 {_bot_display_name} Canvas - Treasure Hunter POE2"),
        ])
    
    interval = (agent_config or {}).get("roles", {}).get("treasure_hunter", {}).get("interval_hours", 1)
    state = _get_canvas_poe2_state(guild, author_id)
    objective_count = len(state.get("objectives", []))
    parts = [
        _get_treasure_overview_intro_block(),
        "**Role type:** item-tracking surface with personal and admin paths\n",
        f"**Status:** enabled | every {interval}h\n",
        f"**POE2 state:** {'On' if state.get('activated', False) else 'Off'} | league {state.get('league', 'Standard')} | {objective_count} tracked item(s)\n",
        "**User flows**",
        "- `!hunter help` - General role help",
        "- `!hunter poe2 help` - POE2 help",
        "- `!hunter poe2 list` - Show tracked objectives",
        "- `!hunter poe2 add \"Item Name\"` - Add an objective",
        "- `!hunter poe2 del \"Item Name\"` - Remove an objective",
        "- `!hunter poe2 league \"Standard\"` - Show or change your league in DM",
        "",
        "**Task map**",
        "- Items: maintain tracked objectives",
        "- League: align search scope with your economy through concrete league options",
        "- Admin: enable and schedule the subrole",
        "",
        "**Concrete choices**",
        "- League selector: `Standard`, `Fate of the Vaal`, or another supported league",
    ]
    if admin_visible:
        parts.extend([
            "",
            "**Admin flows**",
            "- `!hunter poe2 on` - Activate the POE2 subrole",
            "- `!hunter poe2 off` - Deactivate the POE2 subrole",
            "- `!hunterfrequency <hours>` - Set execution frequency",
        ])
    parts.extend([
        "",
        "**Routing**",
        "- Personal POE2 management is DM-oriented",
        "- Server activation and frequency are admin-only",
        "- Detail views: `!canvas role treasure_hunter personal`",
    ])
    if admin_visible:
        parts[-1] += "\n- Admin detail: `!canvas role treasure_hunter admin`"
    return "\n".join(parts)


def _build_canvas_role_treasure_hunter_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Build a detailed Treasure Hunter view."""
    treasure_messages = _personality_answers.get("treasure_hunter_messages", {})
    treasure_descriptions = _personality_descriptions.get("treasure_hunter_messages", {})
    
    def _treasure_text(key: str, fallback: str) -> str:
        value = treasure_descriptions.get(key, treasure_messages.get(key))
        # Replace {_bot} placeholder
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback
    
    def _get_treasure_overview_intro_block() -> str:
        return "\n".join([
            _treasure_text("canvas_th_overview_title", f"💎 {_bot_display_name} Canvas - Treasure Hunter"),
        ])
    
    def _get_treasure_poe2_intro_block() -> str:
        return "\n".join([
            _treasure_text("canvas_th_poe2_title", f"💎 {_bot_display_name} Canvas - Treasure Hunter POE2"),
        ])
    if detail_name in {"personal", "poe2", "items"}:
        state = _get_canvas_poe2_state(guild, author_id)
        items_block = "\n".join([f"- {item}" for item in state["objectives"]]) if state["objectives"] else "- No tracked items yet"
        return "\n".join([
            _get_treasure_poe2_intro_block(),
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
    if detail_name in {"league"}:
        state = _get_canvas_poe2_state(guild, author_id)
        return "\n".join([
            f"**💎 {_bot_display_name} Canvas - Treasure Hunter League**",
            "Configure your POE2 league setting for item tracking",
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
            return _build_canvas_setup_not_available()
        state = _get_canvas_poe2_state(guild, author_id)
        interval = (AGENT_CFG or {}).get("roles", {}).get("treasure_hunter", {}).get("interval_hours", 1)
        return "\n".join([
            f"**💎 {_bot_display_name} Canvas - Treasure Hunter Admin**",
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


def _build_canvas_role_trickster(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the Trickster role view."""
    # Try to get trickster messages, fallback to empty dict
    trickster_messages = {}
    try:
        trickster_messages = _personality_descriptions.get("ring_view_messages", {})
    except Exception:
        pass
    
    def _trickster_text(key: str, fallback: str) -> str:
        value = trickster_messages.get(key)
        # Replace {_bot} placeholder
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback
    
    def _get_trickster_overview_intro_block() -> str:
        return "\n".join([
            _trickster_text("canvas_trickster_overview_title", f"🎭Trilero de Putre"),
        ])
    
    subroles = (agent_config or {}).get("roles", {}).get("trickster", {}).get("subroles", {})
    active_subroles = [name for name, cfg in subroles.items() if isinstance(cfg, dict) and cfg.get("enabled", False)]
    subroles_text = ", ".join(active_subroles) if active_subroles else "none"
    dice_state = _get_canvas_dice_state(guild)
    ring_state = _get_canvas_ring_state(guild)
    beggar_state = _get_canvas_beggar_state(guild)
    
    # Get separator and subrole descriptions
    separator = _trickster_text("canvas_trickster_overview_separator", "──────────────────────────────")
    subrole_descriptions = trickster_messages.get("canvas_trickster_subrole_descriptions", {})
    
    # Build subrole descriptions for active subroles
    active_descriptions = []
    for subrole in active_subroles:
        if subrole in subrole_descriptions:
            active_descriptions.append(subrole_descriptions[subrole])
    
    parts = [
        _get_trickster_overview_intro_block(),
        separator,
        "**Role type:** multi-surface role with subroles",
        f"**Active subroles:** {subroles_text}",
        f"**Live state:** dice bet {dice_state['bet']:,} | pot {dice_state['pot_balance']:,} | ring {'On' if ring_state['enabled'] else 'Off'} | beggar {'On' if beggar_state['enabled'] else 'Off'}",
        separator,
    ]
    
    # Add subrole descriptions if available
    if active_descriptions:
        parts.extend(active_descriptions)
        parts.append(separator)
    
    parts.append("🎭 Trickster • admin/user view")
    
    return "\n".join(parts)


def _build_canvas_role_trickster_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Build a detailed Trickster view."""
    # Try to get trickster messages, fallback to empty dict
    trickster_messages = {}
    try:
        trickster_messages = _personality_descriptions.get("ring_view_messages", {})
    except Exception:
        pass
    
    def _trickster_text(key: str, fallback: str) -> str:
        value = trickster_messages.get(key)
        # Replace {_bot} placeholder
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback
    
    def _get_dice_intro_block() -> str:
        return "\n".join([
            _trickster_text("canvas_dice_title", f"🎭 {_bot_display_name} Canvas - Trickster Dice Game"),
        ])
    
    def _get_ring_intro_block() -> str:
        return "\n".join([
            _trickster_text("canvas_ring_title", f"🎭 {_bot_display_name} Canvas - Trickster Ring"),
        ])
    
    def _get_beggar_intro_block() -> str:
        return "\n".join([
            _trickster_text("canvas_beggar_title", f"🎭 {_bot_display_name} Canvas - Trickster Beggar"),
        ])
    
    if detail_name in {"dice", "game"}:
        dice_state = _get_canvas_dice_state(guild)
        personality = _personality_answers.get("dice_game_messages", {})
        balance_messages = _personality_answers.get("dice_game_balance_messages", {})
        
        # Use personality messages for title
        title = personality.get("invitation", "🎲 **DICE GAME** 🎲")
        pot_title = balance_messages.get("current_pot_title", "💎 **CURRENT POT:**")
        
        parts = [
            _get_dice_intro_block(),
            f"{pot_title} {dice_state['pot_balance']:,} gold",
            f"💰 **Fixed bet:** {dice_state['bet']:,} gold",
            "",
            "─" * 30,
            "",
            "**🎲 Choose an action below:**",
            "",
            "**Available Actions:**",
            "• **Dice: Play** - Roll the dice and try your luck!",
            "• **Dice: Ranking** - View top players and their winnings",
            "• **Dice: History** - See recent game results",
            "• **Dice: Help** - Learn how to play and win",
            "",
            "─" * 30,
            "",
            "**📊 Quick Stats:**",
        ]
        
        # Add some quick stats
        ranking_rows = _get_canvas_dice_ranking(guild, 3)
        if ranking_rows:
            parts.append("🏆 **Top Players:**")
            for row in ranking_rows[:3]:
                medal = "🥇" if row['position'] == 1 else "🥈" if row['position'] == 2 else "🥉"
                parts.append(f"{medal} #{row['position']} {row['player_name']} - {row['total_won']:,} gold")
        else:
            parts.append("🏆 No ranked players yet. Be the first!")
        
        parts.extend([
            "",
            "**📜 Recent Activity:**",
        ])
        
        history_rows = _get_canvas_dice_history(guild, 3)
        if history_rows:
            for row in history_rows[:3]:
                dice_str = row.get("dice", "")
                dice_display = "🎲".join(dice_str.split('-')) if dice_str else "???"
                prize_emoji = "💰" if row.get("prize", 0) > 0 else "💸"
                parts.append(f"👤 {row['user_name']} | {dice_display} → {row['combination']} | {prize_emoji} {row['prize']:,}")
        else:
            parts.append("📜 No recent games. Start playing to see history here!")
        
        parts.extend([
            "",
            "**📍 Navigation:**",
            "• This is `trickster / dice / personal`",
            "• Use `Admin` for bet, pot and announcement controls",
            "• Select actions from the dropdown menu below",
        ])
        
        return "\n".join(parts)
    if detail_name in {"dice_admin"}:
        dice_state = _get_canvas_dice_state(guild)
        hot_pot = int(dice_state["bet"] * 73)
        return "\n".join([
            f"**🎲 {_bot_display_name} Canvas - Trickster / Dice / Admin**",
            "Configure dice game settings and announcements",
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
            _trickster_text("canvas_beggar_title", f"**🙏 {_bot_display_name} Canvas - Trickster / Beggar**"),
            _trickster_text("canvas_beggar_description", "Donate gold to support the clan project"),
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
            f"**🙏 {_bot_display_name} Canvas - Trickster / Beggar / Admin**",
            "Configure beggar functionality and frequency",
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
        
        # Get ring view messages from personality with fallback
        ring_messages = _personality_descriptions.get("ring_view_messages", {})
        server_name = guild.name if guild else "Server"
        
        # Title and description from personality files with fallback
        title = _trickster_text("canvas_ring_title", f"👁️ **{_bot_display_name} Cazador del Anillo**")
        # Remove ** from title for embed title
        clean_title = title.replace("**", "")
        description = _trickster_text("canvas_ring_description", "🔍 Putre the ring hunter seeks the lost artifact. Your boss tasked you with finding that cursed jewel and you won't return until you have it. Interrogate suspects and make them talk.")
        
        # Status messages
        status_active = ring_messages.get("status_active", "✅ **HUNT ACTIVE** - Putre is seeking the ring")
        status_inactive = ring_messages.get("status_inactive", "❌ **HUNT INACTIVE** - Putre is resting")
        
        # Target messages
        current_target_label = ring_messages.get("current_target", "🎯 **CURRENT TARGET:**")
        target_unknown = ring_messages.get("target_unknown", "👤 No suspect selected")
        
        # Investigation messages
        investigation_title = ring_messages.get("investigation_title", "🔍 **MAKE AN ACCUSATION:**")
        investigation_instructions = ring_messages.get("investigation_instructions", 
            "• Use **Ring: Accuse** from the dropdown below\n"
            "• Enter: @username, user ID, or visible name\n"
            "• The AI will generate a threatening accusation\n"
            "• Accusation will be posted publicly in the channel"
        )
        investigation_warning = ring_messages.get("investigation_warning",
            "⚠️ **IMPORTANT:**\n"
            "• You cannot accuse yourself\n"
            "• You cannot accuse bots\n"
            "• Ring must be enabled by an admin first"
        )
        
        # Inactive messages
        inactive_title = ring_messages.get("inactive_title", "⚠️ **THE HUNT IS INACTIVE**")
        inactive_instructions = ring_messages.get("inactive_instructions",
            "To enable ring functionality:\n"
            "• An admin must go to **Ring Admin**\n"
            "• Click **Ring: On** to activate\n"
            "• Set frequency for automatic investigations\n\n"
            "Once enabled, you can accuse users of carrying the One Ring!"
        )
        
        # Navigation messages
        navigation_info = ring_messages.get("navigation_info",
            "📍 **NAVIGATION:**\n"
            "• You are at `trickster / ring / personal`\n"
            "• Use `Admin` for on/off and frequency controls\n"
            "• Select **Ring: Accuse** from the dropdown to make accusations"
        )
        
        parts = [
            f"**{clean_title}**",
            description,
            f"**Status:** {'✅ Active' if ring_state['enabled'] else '❌ Inactive'}",
            f"**Frequency:** Every {ring_state['frequency_hours']} hours",
            "",
        ]
        
        if ring_state['enabled']:
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
            parts.extend([
                inactive_title,
                "",
                inactive_instructions,
            ])
        
        parts.extend([
            "",
            navigation_info,
        ])
        
        return "\n".join(parts)
    if detail_name in {"ring_admin"}:
        ring_state = _get_canvas_ring_state(guild)
        return "\n".join([
            f"**👁️ {_bot_display_name} Canvas - Trickster / Ring / Admin**",
            "Configure ring hunt functionality and frequency",
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
    return None


def _build_canvas_role_banker(agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str:
    """Build the unified Banker role view with wallet information."""
    banker_messages = _personality_answers.get("banker_messages", {})
    banker_descriptions = _personality_descriptions.get("banker_messages", {})
    
    def _banker_text(key: str, fallback: str) -> str:
        value = banker_descriptions.get(key, banker_messages.get(key))
        # Replace {_bot} placeholder
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback
    
    # Get banker data
    balance = 0
    tae = 1
    bonus = 10
    user_name = "Unknown"
    server_name = "Unknown Server"
    history = []
    dice_game_ready = False
    
    if guild is not None and get_banker_db_instance is not None:
        try:
            server_key = get_server_key(guild)
            db_banker = get_banker_db_instance(server_key)
            server_id = str(guild.id)
            
            # Get server info
            from agent_db import get_active_server_name
            server_name = get_active_server_name() or guild.name
            
            if author_id is not None:
                user_id = str(author_id)
                user_name = guild.get_member(author_id).display_name if guild.get_member(author_id) else "Unknown User"
                
                # Create wallet if needed
                was_created, initial_balance = db_banker.create_wallet(user_id, user_name, server_id, server_name)
                
                # Initialize dice game account
                try:
                    from roles.banker.banker_discord import _initialize_dice_game_account
                    dice_game_ready = _initialize_dice_game_account(user_id, user_name, server_id, server_key, server_name)
                except:
                    pass
                
                # Get balance and history
                balance = db_banker.get_balance(user_id, server_id)
                history = db_banker.get_transaction_history(user_id, server_id, limit=5)
            
            tae = db_banker.obtener_tae(server_id)
            bonus = db_banker.obtener_opening_bonus(server_id)
        except Exception as e:
            logger.warning(f"Could not load banker state for Canvas: {e}")
    
    # Build the unified view with clean format - title as first line
    title = _banker_text('canvas_title', '💰 El Gran Kofre de Putre')
    content_parts = [
        f"**{title}**",
        "──────────────────────────────",
        f":coin: {balance:,} gold coins",
        f":bank: {server_name}",
        f":bust_in_silhouette: {user_name}",
        _banker_text('canvas_description', '¡mira tu montaña de oro o iora por zer probe umano!'),
        "──────────────────────────────",
        "- Recent Transactions",
    ]
    
    # Add recent transactions
    if history:
        for trans in history[:3]:  # Show only last 3 transactions
            trans_type, amount, balance_before, balance_after, description, date, admin = trans
            emoji = ":inbox_tray:" if amount > 0 else ":outbox_tray:"
            content_parts.append(f"{emoji} {amount:,} ({trans_type})")
    else:
        content_parts.append("No transactions yet")
    
    # Return content with properly formatted title for embed
    return "\n".join(content_parts)


def _build_canvas_role_banker_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Redirect all banker details to the unified main view."""
    # All banker details (including 'wallet' and 'overview') redirect to the same unified view
    return _build_canvas_role_banker({}, admin_visible, guild, author_id)


def _build_canvas_role_mc(last_action=None, queue_info=None, mc_messages=None) -> str:
    """Build the MC role view with dynamic state."""
    # Try to get MC messages, fallback to empty dict
    mc_messages_dict = {}
    try:
        mc_messages_dict = _personality_descriptions.get("mc_messages", {})
    except Exception:
        pass
    
    def _mc_text(key: str, fallback: str) -> str:
        value = mc_messages_dict.get(key)
        # Replace {_bot} placeholder
        if value:
            value = str(value).replace("{_bot}", _bot_display_name)
        return str(value).strip() if value else fallback
    
    # Title as first line (will become embed title)
    parts = [_mc_text("canvas_mc_title", f"**🎵 {_bot_display_name} Canvas - MC (Master of Ceremonies)**")]
    
    # Add subtitle and separator as separate lines
    parts.append(_mc_text("canvas_mc_subtitle", "Klavijas de kontrol"))
    parts.append(_mc_text("canvas_mc_separator", "──────────────────────────────"))
    
    # Show last action if available
    if last_action:
        parts.append(f"✅ **Last Action:** {last_action}")
    
    # Add description from JSON or fallback
    if not (last_action or queue_info or mc_messages):
        parts.append(_mc_text("canvas_mc_description", "**Music Control Center**\nUse the dropdown below to control music playback\n🎵 Play Now - ➕ Add to Queue - ⏭️ Skip\n⏸️ Pause - ▶️ Resume - ⏹️ Stop\n📋 View Queue - 🔊 Volume"))
        parts.append(_mc_text("canvas_mc_voice_required", "**Voice Channel Required**\nYou must be in a voice channel to use MC\nBot will auto-connect to your channel"))
    
    # Show queue information
    if queue_info:
        parts.append("\n📋 **Current Queue:**")
        if queue_info and len(queue_info) > 0:
            for i, (title, artist, duration, user) in enumerate(queue_info[:5], 1):
                parts.append(f"  {i}. {title}")
                if artist:
                    parts.append(f"     👤 {artist}")
                if duration and duration != "Desconocida":
                    parts.append(f"     ⏱️ {duration}")
            if len(queue_info) > 5:
                parts.append(f"  ... and {len(queue_info) - 5} more songs")
        else:
            parts.append("  📭 Queue is empty")
    
    # Show MC messages if available
    if mc_messages:
        parts.append("\n📋 **MC Status:**")
        for msg in mc_messages[-3:]:  # Show last 3 messages
            parts.append(f"  {msg}")
    
    return "\n".join(parts)


def _build_canvas_role_view(role_name: str, agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Build a role-specific Canvas view."""
    if role_name == "news_watcher" and is_role_enabled_check("news_watcher", agent_config, guild):
        return _build_canvas_role_news_watcher(agent_config, admin_visible, guild)
    if role_name == "treasure_hunter" and is_role_enabled_check("treasure_hunter", agent_config, guild):
        return _build_canvas_role_treasure_hunter(agent_config, admin_visible, guild, author_id)
    if role_name == "trickster" and is_role_enabled_check("trickster", agent_config, guild):
        return _build_canvas_role_trickster(agent_config, admin_visible, guild)
    if role_name == "banker" and is_role_enabled_check("banker", agent_config, guild):
        return _build_canvas_role_banker(agent_config, admin_visible, guild, author_id)
    if role_name == "mc" and (agent_config or {}).get("roles", {}).get("mc", {}).get("enabled", False):
        return _build_canvas_role_mc()
    return None


def _build_canvas_role_detail_view(role_name: str, detail_name: str, agent_config: dict, admin_visible: bool, guild=None, author_id: int | None = None) -> str | None:
    """Build a role detail Canvas view."""
    if role_name == "news_watcher" and is_role_enabled_check("news_watcher", agent_config, guild):
        return _build_canvas_role_news_watcher_detail(detail_name, admin_visible, guild, author_id or 0)
    if role_name == "treasure_hunter" and is_role_enabled_check("treasure_hunter", agent_config, guild):
        return _build_canvas_role_treasure_hunter_detail(detail_name, admin_visible, guild, author_id)
    if role_name == "trickster" and is_role_enabled_check("trickster", agent_config, guild):
        return _build_canvas_role_trickster_detail(detail_name, admin_visible, guild, author_id)
    if role_name == "banker" and is_role_enabled_check("banker", agent_config, guild):
        return _build_canvas_role_banker_detail(detail_name, admin_visible, guild, author_id)
    if role_name == "mc" and (agent_config or {}).get("roles", {}).get("mc", {}).get("enabled", False):
        return _build_canvas_role_mc()
    return None


def register_core_commands(bot, agent_config):
    """Register all base bot commands."""

    # --- Dynamic names based on personality ---
    greet_name = f"greet{_personality_name}"
    nogreet_name = f"nogreet{_personality_name}"
    welcome_name = f"welcome{_personality_name}"
    nowelcome_name = f"nowelcome{_personality_name}"
    insult_name = f"insult{_personality_name}"
    role_cmd_name = f"role{_personality_name}"
    talk_cmd_name = f"talk{_personality_name}"

    # --- PRESENCE GREETINGS ---

    async def _cmd_saluda_toggle(ctx, enabled: bool):
        """Generic command to enable/disable presence greetings."""
        role_cfg = _personality_answers.get("role_messages", {})
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can modify presence greetings."))
            return

        set_greeting_enabled(ctx.guild, enabled)

        presence_cfg = _discord_cfg.get("member_presence")
        if not isinstance(presence_cfg, dict):
            _discord_cfg["member_presence"] = {}
            presence_cfg = _discord_cfg["member_presence"]
        presence_cfg["enabled"] = enabled

        greeting_cfg = _personality_answers.get("member_greeting", {})
        mensaje_activado = greeting_cfg.get("greetings_enabled", "GRRR {_bot_name} will watch for humans! {_bot_name} will greet when humans appear!")
        mensaje_desactivado = greeting_cfg.get("greetings_disabled", "BRRR {_bot_name} will no longer watch humans! {_bot_name} will stop greeting, too much work!")

        mensaje = mensaje_activado.format(_bot_name=_bot_display_name) if enabled else mensaje_desactivado.format(_bot_name=_bot_display_name)
        await ctx.send(mensaje)

        action = "enabled" if enabled else "disabled"
        logger.info(f"{ctx.author.name} {action} presence greetings in {ctx.guild.name}")

    # --- GREETING CONTROL COMMANDS ---
    try:
        @bot.command(name=greet_name)
        async def cmd_greet_enable(ctx):
            await _cmd_saluda_toggle(ctx, True)
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {greet_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {greet_name}: {e}")

    try:
        @bot.command(name=nogreet_name)
        async def cmd_greet_disable(ctx):
            await _cmd_saluda_toggle(ctx, False)
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {nogreet_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {nogreet_name}: {e}")

    # --- WELCOME ---

    async def _cmd_bienvenida_toggle(ctx, enabled: bool):
        """Generic command to enable/disable welcome greetings with persistence."""
        role_cfg = _personality_answers.get("role_messages", {})
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can modify welcome greetings."))
            return

        # Update in-memory config
        greeting_cfg = _discord_cfg.get("member_greeting", {})
        greeting_cfg["enabled"] = enabled

        # Save to behaviors database
        if get_behaviors_db_instance is not None and ctx.guild:
            try:
                guild_id = str(ctx.guild.id)
                db = get_behaviors_db_instance(guild_id)
                db.set_welcome_enabled(enabled, f"{ctx.author.name}")
                logger.info(f"Welcome greetings {'enabled' if enabled else 'disabled'} and saved to behaviors database for {ctx.guild.name}")
            except Exception as e:
                logger.error(f"Failed to save welcome state to behaviors database for {ctx.guild.name}: {e}")
        else:
            logger.warning(f"Behaviors database not available, welcome state not persisted for {ctx.guild.name}")

        greeting_messages_cfg = _personality_answers.get("member_greeting", {})
        if enabled:
            mensaje = greeting_messages_cfg.get("greetings_enabled", "✅ Welcome greetings enabled on this server.")
        else:
            mensaje = greeting_messages_cfg.get("greetings_disabled", "✅ Welcome greetings disabled on this server.")

        logger.info(f"{ctx.author.name} {'enabled' if enabled else 'disabled'} welcome greetings in {ctx.guild.name}")
        await ctx.send(mensaje)

    try:
        @bot.command(name=welcome_name)
        async def cmd_welcome_enable(ctx):
            await _cmd_bienvenida_toggle(ctx, True)
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {welcome_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {welcome_name}: {e}")

    try:
        @bot.command(name=nowelcome_name)
        async def cmd_welcome_disable(ctx):
            await _cmd_bienvenida_toggle(ctx, False)
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {nowelcome_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {nowelcome_name}: {e}")

    # --- INSULT ---

    async def _cmd_insult(ctx, obj=""):
        target = obj if obj else ctx.author.mention
        if "@everyone" in target or "@here" in target:
            prompt = _insult_cfg.get("prompt_everyone", "Lanza un insulto breve a TODO EL MUNDO, maximo 1 frase")
        else:
            prompt = _insult_cfg.get("prompt_target", "Lanza un insulto breve a una persona especifica, maximo 1 frase")
        server_name = get_server_key(ctx.guild) if ctx.guild else "default"
        res = await asyncio.to_thread(
            think,
            role_context=_bot_display_name,
            user_content=prompt,
            logger=logger,
            server_name=server_name,
            interaction_type="command",
        )
        await ctx.send(f"{target} {res}")

    try:
        bot.command(name=insult_name)(_cmd_insult)
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {insult_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {insult_name}: {e}")

    # --- TEST ---

    try:
        @bot.command(name="test")
        async def cmd_test(ctx):
            """Test command to verify the bot works."""
            role_cfg = _personality_answers.get("role_messages", {})
            logger.info(f"Test command executed by {ctx.author.name}")
            await ctx.send(role_cfg.get("test_command", "✅ Test command works!"))
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info("Command test already registered, skipping...")
        else:
            logger.error(f"Error registering test: {e}")

    async def _start_talk_loop_for_guild(guild_id: int):
        state = _talk_state_by_guild_id.get(guild_id)
        if not state:
            return

        interval_minutes = int(state.get("interval_minutes", 180))
        if interval_minutes < 5:
            interval_minutes = 5
            state["interval_minutes"] = interval_minutes

        while state.get("enabled", False):
            try:
                channel_id = state.get("channel_id")
                channel = bot.get_channel(int(channel_id)) if channel_id else None
                if channel is None:
                    state["enabled"] = False
                    break

                server_name = get_server_key(channel.guild) if channel.guild else "default"
                prompt = _build_mission_commentary_prompt(agent_config, server_name)
                res = await asyncio.to_thread(
                    think,
                    role_context=_bot_display_name,
                    user_content=prompt,
                    logger=logger,
                    server_name=server_name,
                    interaction_type="mission",
                )
                if res and str(res).strip():
                    await channel.send(str(res).strip())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in talk loop for guild_id={guild_id}: {e}")

            await asyncio.sleep(interval_minutes * 60)

    async def _talk_enable(ctx, interval_minutes: int | None = None):
        role_cfg = _personality_answers.get("role_messages", {})
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can modify this feature."))
            return

        guild_id = int(ctx.guild.id)
        state = _talk_state_by_guild_id.get(guild_id) or {}
        state["enabled"] = True
        state["channel_id"] = int(ctx.channel.id)
        if interval_minutes is not None:
            try:
                state["interval_minutes"] = int(interval_minutes)
            except Exception:
                pass
        if "interval_minutes" not in state:
            state["interval_minutes"] = 180

        task = state.get("task")
        if task and not task.done():
            task.cancel()

        state["task"] = asyncio.create_task(_start_talk_loop_for_guild(guild_id))
        _talk_state_by_guild_id[guild_id] = state

        await ctx.send(
            f"✅ Mission commentary enabled in this channel (every {state['interval_minutes']} minutes)."
        )

    async def _talk_disable(ctx):
        role_cfg = _personality_answers.get("role_messages", {})
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can modify this feature."))
            return

        guild_id = int(ctx.guild.id)
        state = _talk_state_by_guild_id.get(guild_id)
        if not state or not state.get("enabled", False):
            await ctx.send("ℹ️ Mission commentary is already disabled for this server.")
            return

        state["enabled"] = False
        task = state.get("task")
        if task and not task.done():
            task.cancel()
        await ctx.send("✅ Mission commentary disabled for this server.")

    async def _talk_now(ctx):
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return

        server_name = get_server_key(ctx.guild) if ctx.guild else "default"
        prompt = _build_mission_commentary_prompt(agent_config, server_name)
        res = await asyncio.to_thread(
            think,
            role_context=_bot_display_name,
            user_content=prompt,
            logger=logger,
            server_name=server_name,
            interaction_type="mission",
        )
        if res and str(res).strip():
            await ctx.send(str(res).strip())
        else:
            await ctx.send("⚠️ Could not generate a commentary right now.")

    async def _talk_status(ctx):
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return

        guild_id = int(ctx.guild.id)
        state = _talk_state_by_guild_id.get(guild_id) or {}
        enabled = bool(state.get("enabled", False))
        channel_id = state.get("channel_id")
        interval_minutes = state.get("interval_minutes", 180)
        channel_mention = f"<#{channel_id}>" if channel_id else "(not set)"
        await ctx.send(
            f"Mission commentary: {'ON' if enabled else 'OFF'} | channel={channel_mention} | interval={interval_minutes} minutes"
        )

    async def _talk_frequency(ctx, minutes: int):
        role_cfg = _personality_answers.get("role_messages", {})
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Only administrators can modify this feature."))
            return

        guild_id = int(ctx.guild.id)
        state = _talk_state_by_guild_id.get(guild_id) or {}
        state["interval_minutes"] = int(minutes)
        _talk_state_by_guild_id[guild_id] = state

        if state.get("enabled", False):
            task = state.get("task")
            if task and not task.done():
                task.cancel()
            state["task"] = asyncio.create_task(_start_talk_loop_for_guild(guild_id))

        await ctx.send(f"✅ Mission commentary interval set to {state['interval_minutes']} minutes.")

    try:
        @bot.command(name=talk_cmd_name)
        async def cmd_talk(ctx, action: str = "", value: str = ""):
            if not action:
                await ctx.send(
                    f"❌ Usage: `!{talk_cmd_name} on/off/now/status/frequency <minutes>`"
                )
                return

            action_lower = action.lower()
            if action_lower in ["on", "enable", "true", "1"]:
                interval = None
                if value:
                    try:
                        interval = int(value)
                    except Exception:
                        interval = None
                await _talk_enable(ctx, interval_minutes=interval)
                return
            if action_lower in ["off", "disable", "false", "0"]:
                await _talk_disable(ctx)
                return
            if action_lower in ["now", "say", "ping"]:
                await _talk_now(ctx)
                return
            if action_lower in ["status", "info"]:
                await _talk_status(ctx)
                return
            if action_lower in ["frequency", "interval"]:
                if not value:
                    await ctx.send(f"❌ Usage: `!{talk_cmd_name} frequency <minutes>`")
                    return
                try:
                    minutes = int(value)
                except Exception:
                    await ctx.send("❌ Minutes must be an integer.")
                    return
                await _talk_frequency(ctx, minutes)
                return

            await ctx.send(
                f"❌ Unknown action `{action}`. Use: on/off/now/status/frequency."
            )

    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {talk_cmd_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {talk_cmd_name}: {e}")

    async def _taboo_status(ctx):
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        state = get_taboo_state(int(ctx.guild.id))
        keywords = ", ".join(state.get("keywords", [])) or "(none)"
        await ctx.send(f"🚫 Taboo: {'ON' if state.get('enabled', False) else 'OFF'} | keywords: {keywords}")

    try:
        @bot.command(name="taboo")
        async def cmd_taboo(ctx, action: str = "", *, value: str = ""):
            if not ctx.guild:
                await ctx.send("❌ This command only works on servers, not in private messages.")
                return
            if not action:
                await _taboo_status(ctx)
                return
            if not is_admin(ctx):
                await ctx.send("❌ Only administrators can modify taboo behavior.")
                return
            
            guild_id = int(ctx.guild.id)
            action_lower = action.lower().strip()
            keyword = str(value).strip().lower()

            if action_lower in {"on", "enable"}:
                if update_taboo_state(guild_id, enabled=True):
                    await ctx.send("✅ Taboo enabled for this server.")
                else:
                    await ctx.send("❌ Failed to enable taboo. Check logs for details.")
                return
            if action_lower in {"off", "disable"}:
                if update_taboo_state(guild_id, enabled=False):
                    await ctx.send("✅ Taboo disabled for this server.")
                else:
                    await ctx.send("❌ Failed to disable taboo. Check logs for details.")
                return
            if action_lower == "list":
                await _taboo_status(ctx)
                return
            if action_lower == "add":
                if not keyword:
                    await ctx.send("❌ Usage: `!taboo add <keyword>`")
                    return
                
                # Get current state and add keyword
                state = get_taboo_state(guild_id)
                current_keywords = state.get("keywords", [])
                
                if keyword not in current_keywords:
                    if update_taboo_state(guild_id, keywords=current_keywords + [keyword]):
                        await ctx.send(f"✅ Added taboo keyword `{keyword}`.")
                    else:
                        await ctx.send("❌ Failed to add keyword. Check logs for details.")
                else:
                    await ctx.send(f"⚠️ Keyword `{keyword}` already exists.")
                return
            if action_lower in {"del", "remove"}:
                if not keyword:
                    await ctx.send("❌ Usage: `!taboo del <keyword>`")
                    return
                
                # Get current state and remove keyword
                state = get_taboo_state(guild_id)
                current_keywords = state.get("keywords", [])
                
                if keyword in current_keywords:
                    new_keywords = [kw for kw in current_keywords if kw != keyword]
                    if update_taboo_state(guild_id, keywords=new_keywords):
                        await ctx.send(f"✅ Removed taboo keyword `{keyword}`.")
                    else:
                        await ctx.send("❌ Failed to remove keyword. Check logs for details.")
                else:
                    await ctx.send(f"❌ Keyword `{keyword}` is not configured.")
                return

            await ctx.send("❌ Unknown taboo action. Use: `on`, `off`, `add`, `del`, or `list`.")
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info("Command taboo already registered, skipping...")
        else:
            logger.error(f"Error registering taboo: {e}")

    # --- ROLE CONTROL ---

    async def _cmd_role_toggle(ctx, role_name: str, enabled: bool):
        """Generic command to enable/disable roles dynamically."""
        role_cfg = _personality_answers.get("role_messages", {})
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("role_no_permission", "❌ Only administrators can modify roles."))
            return

        valid_roles = ["news_watcher", "treasure_hunter", "trickster", "banker"]
        if role_name not in valid_roles:
            await ctx.send(role_cfg.get("role_not_found", "❌ Role '{role}' not valid.").format(role=role_name))
            return

        env_var_name = f"{role_name.upper()}_ENABLED"
        env_value = "true" if enabled else "false"
        os.environ[env_var_name] = env_value

        set_role_enabled(ctx.guild, role_name, enabled, agent_config, getattr(ctx.author, "name", "admin_command"))

        # Register role commands if activating
        if enabled:
            from discord_bot.discord_role_loader import register_single_role
            await register_single_role(bot, role_name, agent_config, PERSONALIDAD)

        if enabled:
            await ctx.send(role_cfg.get("role_activated", "✅ Role '{role}' activated successfully.").format(role=role_name))
            logger.info(f"{ctx.author.name} activated role {role_name} in {ctx.guild.name}")
        else:
            await ctx.send(role_cfg.get("role_deactivated", "✅ Role '{role}' deactivated successfully.").format(role=role_name))
            logger.info(f"{ctx.author.name} deactivated role {role_name} in {ctx.guild.name}")

    try:
        @bot.command(name=role_cmd_name)
        async def cmd_role_control(ctx, role_name: str = "", action: str = ""):
            """Role control. Usage: !role<name> <role> <on/off>"""
            if not role_name:
                await ctx.send("❌ Usage: `!{}<role> <action>` where <action> is on/off, true/false, 1/0, enable/disable".format(_personality_name))
                return

            if not action:
                await ctx.send("❌ Usage: `!{}<role> <action>` where <action> is on/off, true/false, 1/0, enable/disable".format(_personality_name))
                return

            action_lower = action.lower()
            if action_lower in ["on", "true", "1", "enable"]:
                await _cmd_role_toggle(ctx, role_name, True)
            elif action_lower in ["off", "false", "0", "disable"]:
                await _cmd_role_toggle(ctx, role_name, False)
            else:
                await ctx.send("❌ Invalid action. Use: on/off, true/false, 1/0, enable/disable")

    except Exception as e:
        if "already an existing command" in str(e):
            logger.info(f"Command {role_cmd_name} already registered, skipping...")
        else:
            logger.error(f"Error registering {role_cmd_name}: {e}")

    # --- ENGLISH HELP COMMAND WITH PERSONALITY SUPPORT ---
    try:
        @bot.command(name="agenthelp")
        async def cmd_help(ctx, personality_name: str = ""):
            """Show all available commands for this agent (English)."""
            if is_duplicate_command(ctx, "agenthelp"):
                return

            # If personality name provided, check if it matches this agent
            if personality_name:
                if personality_name.lower() != _personality_name:
                    return  # Don't respond to help for other personalities
                
                # Show help for this specific personality
                await _show_agent_help(ctx, personality_name)
                return
            
            # No personality specified: always show help.
            # NOTE: ctx.guild can be None (DMs, some edge cases). Avoid accessing ctx.guild.members.
            await _show_agent_help(ctx, personality_name)

    except Exception as e:
        if "already an existing command" in str(e):
            logger.info("Command agenthelp already registered, skipping...")
        else:
            logger.error(f"Error registering agenthelp: {e}")

    async def _show_agent_help(ctx, requested_personality):
        """Internal function to show agent help - replicates Spanish help behavior with English commands."""
        roles_config = AGENT_CFG.get("roles", {})
        
        # Use requested personality name or current personality
        display_name = requested_personality or _personality_name
        help_msg = f"🤖 **Available Commands for {bot.user.name} ({display_name})** 🤖\n\n"

        # STATIC PART - Control commands 
        help_msg += "🎛️ **CONTROL COMMANDS**\n"
        help_msg += f"• `!{greet_name}` - Enable presence greetings (DM)\n"
        help_msg += f"• `!{nogreet_name}` - Disable presence greetings\n"
        help_msg += f"• `!{welcome_name}` - Enable new member welcome\n"
        help_msg += f"• `!{nowelcome_name}` - Disable new member welcome\n"
        help_msg += f"• `!{insult_name}` - Send orc insult\n"
        help_msg += f"• `!{role_cmd_name} <role> <on/off>` - Enable/disable roles dynamically\n"
        help_msg += f"• `!agenthelp {display_name}` - Show help for this personality\n"
        help_msg += "• `!readme` - Get complete command reference by private message\n\n"

        # DYNAMIC PART - Role commands
        help_msg += "🎭 **ROLE COMMANDS**\n"

        # News Watcher - 
        if is_role_enabled_check("news_watcher", agent_config, ctx.guild):
            interval = get_role_interval_hours("news_watcher", agent_config, ctx.guild, 1)
            help_msg += f"📡 **News Watcher** - Smart alerts (every {interval}h)\n"
            help_msg += "  • **Main:** `!watcher` | `!nowatcher` | `!watchernotify`\n"
            help_msg += "  • **Help:** `!watcherhelp` (users) | `!watcherchannelhelp` (admins)\n"
            help_msg += "  • **Channel:** `!watcherchannel` group (subscribe, unsubscribe, status, keywords, premises)\n"
            help_msg += "  • **Subscription:** `!watcher feeds/categories/status/subscribe/unsubscribe/keywords/general/reset`\n\n"
        # Treasure Hunter - 
        if is_role_enabled_check("treasure_hunter", agent_config, ctx.guild):
            interval = get_role_interval_hours("treasure_hunter", agent_config, ctx.guild, 1)
            help_msg += f"💎 **Treasure Hunter** - POE2 item alerts (every {interval}h)\n"
            help_msg += "  • **Admin:** `!hunter poe2 on//off`, `!hunterfrequency <h>` In a Channel for admins\n"
            help_msg += "  • **League:**`!hunter poe2 league \"Standard\"` | `!hunter poe2 \"Fate of the Vaal\"`\n"
            help_msg += "  • **Items:** `!hunteradd/ \"item\"` | `!hunterdel \"item\"` | `!hunterdel <number>` | `!hunterlist`\n"
            help_msg += "  • **Help:** `!hunterhelp` | `!hunter poe2 help` \n\n"
        # Trickster - 
        if is_role_enabled_check("trickster", agent_config, ctx.guild):
            trickster_config = roles_config.get("trickster", {})
            interval = trickster_config.get("interval_hours", 12)
            subroles = trickster_config.get("subroles", {})
            
            help_msg += f"🎭 **Trickster** - Multiple subroles:\n"
            
            if subroles.get("beggar", {}).get("enabled", False):
                help_msg += "  • 🙏 **Beggar:** `!trickster beggar enable/disable/frequency <h>/status/help`\n"
            
            if subroles.get("ring", {}).get("enabled", False):
                help_msg += "  • 👁️ **Ring:** `!accuse @user` | `!trickster ring enable/disable/frequency <h>/help`\n"
            
            if subroles.get("dice_game", {}).get("enabled", False):
                help_msg += "  • 🎲 **Dice Game:** `!dice play/help/balance/stats/ranking/history` | `!dice config bet <amount>` | `!dice config announcements on/off`\n"
            
            help_msg += "  • **Main:** `!trickster help`\n\n"
        # Banker - 
        if is_role_enabled_check("banker", agent_config, ctx.guild):
            help_msg += f"💰 **Banker** - Economic management\n"
            help_msg += "  • **Main:** `!banker help`\n"
            help_msg += "  • **Balance:** `!banker balance` (unified in Canvas)\n"
            help_msg += "  • **Config:**  | `!banker bonus <amount>`(admins)\n\n"
        # Music - Always available 
        help_msg += f"🎵  **MC** - Music Bot request a song in a voice channel\n"
        help_msg += "  • **Common use** `!mc play \"ADCD TNT\"`,`!mc add \"Queen Bycicle\"`,`!mc queue`\n"
        help_msg += "  • **Main:** `!mc help`\n    \n" # Jumpline for max characters in discord fix

        # Multiple agents info (only when no specific personality requested)
        if not requested_personality: 
            help_msg += "🔀 **MULTIPLE AGENTS**\n"
            help_msg += f"• Use `!agenthelp {display_name}` for help specific to this agent\n"
            help_msg += "• Each agent has its own personality and commands\n\n"

        # Basic conversation 
        help_msg += "💬 **BASIC CONVERSATION**\n"
        help_msg += "• Mention the bot to talk\n"
        help_msg += "• Responds using the agent's personality\n"
        help_msg += f"• Bot will respond as its character ({_bot_display_name})\n\n"
        
        # Active and inactive roles (exact same logic as Spanish help)
        help_msg += "🎭 **ACTIVE AND INACTIVE ROLES**\n"
        role_descriptions = {
            "mc": "🎵 **Music** - Always available (no activation required)",
            "news_watcher": "📡 **News Watcher** - Critical news alerts",
            "treasure_hunter": "💎 **Treasure Hunter** - Purchase opportunity alerts",
            "trickster": "🎭 **Trickster** - Beggar, ring, and dice game subroles",
            "banker": "💰 **Banker** - Economic management and daily TAE",
        }

        for role_name_key, role_cfg_val in roles_config.items():
            enabled = is_role_enabled_check(role_name_key, agent_config, ctx.guild)
            if role_name_key == "mc":
                status_emoji = "✅"
            else:
                status_emoji = "✅" if enabled else "❌"
            # Same logic as Spanish help - use role_descriptions
            display = role_descriptions.get(role_name_key, f"**{role_name_key.replace('_', ' ').title()}**")
            help_msg += f"• {status_emoji} {display}\n"

        # Send help (use personality message with fallback)
        help_sent_msg = _personality_answers.get("general_messages", {}).get("help_sent_private", "📩 Help sent by private message.")
        await send_dm_or_channel(ctx, help_msg, help_sent_msg)


    # --- CANVAS HUB COMMAND ---
    try:
        @bot.command(name="canvas")
        async def cmd_canvas(ctx, section: str = "home", target: str = "", detail: str = ""):
            """Show the guided Canvas-style navigation hub for this bot."""
            logger.info(
                f"Canvas command entered by {ctx.author.name}: raw_section={section!r}, raw_target={target!r}, raw_detail={detail!r}, "
                f"in_guild={bool(ctx.guild)}"
            )

            section_name = (section or "home").strip().lower()
            target_name = (target or "").strip().lower()
            detail_name = (detail or "").strip().lower()
            admin_visible = bool(ctx.guild and is_admin(ctx))

            if section_name == "role":
                if detail_name:
                    role_detail_view = _build_canvas_role_detail_view(
                        target_name,
                        detail_name,
                        agent_config,
                        admin_visible,
                        ctx.guild,
                        int(ctx.author.id),
                    )
                    if role_detail_view is not None:
                        # For banker role details, send as embed with user thumbnail
                        if target_name == "banker":
                            role_embed = _build_canvas_role_embed("banker", role_detail_view, admin_visible, detail_name, ctx.author)
                            canvas_sent_msg = _personality_answers.get("general_messages", {}).get(
                                "canvas_sent_private",
                                "📩 Canvas guide sent by private message."
                            )
                            await send_embed_dm_or_channel(ctx, role_embed, canvas_sent_msg)
                        else:
                            canvas_sent_msg = _personality_answers.get("general_messages", {}).get(
                                "canvas_sent_private",
                                "📩 Canvas guide sent by private message."
                            )
                            await send_dm_or_channel(ctx, role_detail_view, canvas_sent_msg)
                        return

                role_view = _build_canvas_role_view(
                    target_name,
                    agent_config,
                    admin_visible,
                    ctx.guild,
                    int(ctx.author.id),
                )
                if role_view is None:
                    await ctx.send(
                        "❌ Unknown or unavailable role. Use: `!canvas role news_watcher`, `!canvas role treasure_hatcher`, `!canvas role trickster`, `!canvas role banker`, `!canvas role mc`, or detailed views like `!canvas role trickster dice`."
                    )
                    return

                # For banker role, send as embed with user thumbnail
                if target_name == "banker":
                    role_embed = _build_canvas_role_embed("banker", role_view, admin_visible, "overview", ctx.author)
                    canvas_sent_msg = _personality_answers.get("general_messages", {}).get(
                        "canvas_sent_private",
                        "📩 Canvas guide sent by private message."
                    )
                    await send_embed_dm_or_channel(ctx, role_embed, canvas_sent_msg)
                else:
                    canvas_sent_msg = _personality_answers.get("general_messages", {}).get(
                        "canvas_sent_private",
                        "📩 Canvas guide sent by private message."
                    )
                    await send_dm_or_channel(ctx, role_view, canvas_sent_msg)
                return

            sections = _build_canvas_sections(
                agent_config,
                greet_name,
                nogreet_name,
                welcome_name,
                nowelcome_name,
                role_cmd_name,
                talk_cmd_name,
                admin_visible,
                get_server_key(ctx.guild) if ctx.guild else "default",
                ctx.author.id,
                ctx.guild,
            )

            if section_name not in sections:
                await ctx.send(
                    "❌ Unknown canvas section. Use: `!canvas home`, `!canvas roles`, `!canvas role <name>`, `!canvas personal`, or `!canvas help`."
                )
                return

            view = CanvasNavigationView(ctx.author.id, sections, admin_visible, agent_config, show_dropdown=(section_name not in {"home", "behavior"}))
            view.update_visibility()
            logger.info(
                f"Canvas top-level view prepared for {ctx.author.name}: section={section_name}, "
                f"admin_visible={admin_visible}, buttons={len(view.children)}, in_guild={bool(ctx.guild)}"
            )
            if section_name == "home":
                # For home section, show as embed like the Home button does
                home_embed = _build_canvas_embed("home", sections[section_name], admin_visible)
                message = await ctx.send(embed=home_embed, view=view)
            elif section_name == "behavior":
                # For behavior section, also show as embed for consistency
                behavior_embed = _build_canvas_embed("behavior", sections[section_name], admin_visible)
                message = await ctx.send(embed=behavior_embed, view=view)
            else:
                message = await ctx.send(sections[section_name], view=view)
            # Pass the message to the view so it can be deleted on timeout
            view.message = message
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                logger.debug("Could not delete original !canvas command message due to missing permissions.")
            except discord.HTTPException as e:
                logger.debug(f"Could not delete original !canvas command message: {e}")
            logger.info(
                f"Canvas top-level view sent: message_id={message.id}, components={len(getattr(message, 'components', []))}"
            )

    except Exception as e:
        if "already an existing command" in str(e):
            logger.info("Command canvas already registered, skipping...")
        else:
            logger.error(f"Error registering canvas: {e}")


    # --- README COMMAND ---
    try:
        @bot.command(name="readme")
        async def cmd_readme(ctx):
            """Send user-friendly README content privately to user."""
            try:
                # Read the README_USER.md file
                readme_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README_USER.md")
                with open(readme_path, 'r', encoding='utf-8') as f:
                    readme_content = f.read()
                
                # Discord has a 2000 character limit, so we need to split long content
                max_length = 1900  # Leave some buffer for formatting
                
                if len(readme_content) <= max_length:
                    # Send as single message if short enough
                    await ctx.author.send(f"📖 **RoleAgentBot - Complete User Guide**\n\n{readme_content}")
                else:
                    # Split into multiple messages
                    await ctx.author.send("📖 **RoleAgentBot - Complete User Guide**")
                    
                    # Split content into chunks
                    chunks = []
                    current_chunk = ""
                    
                    for line in readme_content.split('\n'):
                        # If adding this line would exceed limit, start new chunk
                        if len(current_chunk) + len(line) + 1 > max_length:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                                current_chunk = line
                            else:
                                # Line itself is too long, force split
                                while len(line) > max_length:
                                    chunks.append(line[:max_length])
                                    line = line[max_length:]
                                current_chunk = line
                        else:
                            if current_chunk:
                                current_chunk += '\n' + line
                            else:
                                current_chunk = line
                    
                    # Add the last chunk
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    
                    # Send chunks with part numbers
                    for i, chunk in enumerate(chunks, 1):
                        header = f"**Part {i}/{len(chunks)}**\n\n" if len(chunks) > 1 else ""
                        await ctx.author.send(f"{header}```md\n{chunk}\n```")
                
                # Confirm in channel (use personality message with fallback)
                readme_sent_msg = _personality_answers.get("general_messages", {}).get("readme_sent_private", "📩 Complete user guide sent by private message.")
                await ctx.send(readme_sent_msg)
                
                logger.info(f"README command executed by {ctx.author.name} in {ctx.guild.name if ctx.guild else 'DM'}")
                
            except FileNotFoundError:
                await ctx.send("❌ User guide file not found.")
                logger.error("README_USER.md file not found")
            except Exception as e:
                await ctx.send("❌ Error sending user guide.")
                logger.error(f"Error in README command: {e}")
                
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info("Command readme already registered, skipping...")
        else:
            logger.error(f"Error registering readme: {e}")

    # --- Log registered commands ---
    logger.info(f"Core commands registered: {greet_name}, {nogreet_name}, {welcome_name}, {nowelcome_name}, {insult_name}, agenthelp, canvas, {role_cmd_name}, test, readme")
