"""
Scheduler de eventos de Arena.

Revisa periodicamente los eventos activos (coliseo/torneo) en todos los servidores.
Cuando un evento expira su timer de registro:
- Si tiene suficientes participantes: ejecuta la batalla
- Si no: retraso o cancelacion segun las reglas
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from agent_logging import get_logger
from agent_db import get_all_server_ids

logger = get_logger("arena_scheduler")


async def check_arena_events_all_servers():
    """Check arena events across all servers. Registered with JobScheduler."""
    try:
        server_ids = get_all_server_ids()
        if not server_ids:
            return

        checked = 0
        for server_id in server_ids:
            try:
                result = await _check_server_arena_events(server_id)
                if result:
                    checked += 1
            except Exception as e:
                logger.error(f"[ArenaScheduler] Error checking server {server_id}: {e}")
            await asyncio.sleep(0.1)  # yield between servers

        if checked > 0:
            logger.debug(f"[ArenaScheduler] Checked arena events on {checked} servers")
    except Exception as e:
        logger.error(f"[ArenaScheduler] Error in global check: {e}")


async def _check_server_arena_events(server_id: str) -> bool:
    """Check and process arena events for a single server.

    Returns True if there was an active event to check.
    """
    from roles.arena.arena_db import ArenaDatabase
    from roles.arena.arena import (
        get_arena_config,
        execute_coliseo,
        can_create_event,
    )
    from discord_bot.canvas.server_config import is_role_enabled

    # Skip if Arena role is not enabled
    if not is_role_enabled(server_id, "arena", default_enabled=False):
        return False

    db = ArenaDatabase(server_id)
    event = db.events.get_active_event()
    if not event:
        return False

    status = event.get("status")
    if status not in ("registering", "ready"):
        return False

    scheduled_for = event.get("scheduled_for")
    if not scheduled_for:
        return False

    # Check if timer has expired
    try:
        scheduled_dt = datetime.fromisoformat(scheduled_for.replace("Z", "+00:00"))
    except Exception:
        return False

    now = datetime.now(timezone.utc)
    if scheduled_dt > now:
        return True  # Timer still running, nothing to do

    # Timer expired - evaluate participants
    event_type = event.get("type")
    participants = event.get("participants", {})
    participant_count = len(participants)

    cfg = get_arena_config(server_id)
    min_coliseo = cfg.get("min_coliseo_participants", 4)
    min_tournament = cfg.get("min_tournament_participants", 8)
    max_retries = cfg.get("max_retries", 3)

    required = min_coliseo if event_type == "coliseo" else min_tournament

    if participant_count >= required:
        # Enough participants - execute battle
        logger.info(f"[ArenaScheduler] {event_type} ready on {server_id} with {participant_count} participants. Executing...")
        event["status"] = "in_progress"
        db.events.set_active_event(event)

        # Build participant list
        participant_list = list(participants.values())

        if event_type == "coliseo":
            # Execute via LLM
            try:
                from agent_engine import _get_personality
                personality = _get_personality(server_id)
                bot_name = personality.get("name", "Bot") if personality else "Bot"
            except Exception:
                bot_name = "Bot"

            result = await execute_coliseo(server_id, participant_list, bot_name)
            if result.get("success"):
                winner_id = result.get("winner_id")
                xp = cfg.get("xp_per_coliseo", 1.0)

                # Update stats
                for pid in participants:
                    won = (pid == winner_id)
                    db.stats.record_battle_result(pid, won, "coliseo", xp if won else 0.0)

                # Save battle history
                db.history.save_battle({
                    "type": "coliseo",
                    "event_id": event.get("event_id"),
                    "participants": participant_list,
                    "winner": winner_id,
                    "narrative": result.get("narrative", ""),
                })

                # Publish result to Arena channel
                try:
                    import discord
                    from roles.arena.arena_discord import publish_battle_result, get_arena_channel
                    # Note: we can't access client here in the scheduler context
                    # The result should be published when the scheduler runs within the bot loop
                    # For now, mark as completed
                except Exception:
                    pass

                event["status"] = "completed"
                event["winner"] = winner_id
                event["narrative"] = result.get("narrative", "")
                db.events.set_active_event(event)
                logger.info(f"[ArenaScheduler] Coliseo completed on {server_id}. Winner: {winner_id}")
            else:
                logger.error(f"[ArenaScheduler] Coliseo execution failed on {server_id}: {result.get('error')}")
                event["status"] = "ready"  # retry later
                db.events.set_active_event(event)

        elif event_type == "torneo":
            # TODO: tournament execution (brackets)
            logger.info(f"[ArenaScheduler] Torneo execution not yet implemented on {server_id}")
            event["status"] = "cancelled"
            db.events.set_active_event(event)

    else:
        # Not enough participants - retry or cancel
        retries = event.get("retries", 0)
        if retries < max_retries:
            # Reschedule with 24h delay
            new_scheduled = (now.replace(tzinfo=None) + __import__("datetime").timedelta(hours=24)).isoformat()
            event["retries"] = retries + 1
            event["scheduled_for"] = new_scheduled
            db.events.set_active_event(event)
            logger.info(f"[ArenaScheduler] {event_type} on {server_id} rescheduled (retry {retries + 1}/{max_retries}). Participants: {participant_count}/{required}")
        else:
            # Cancel
            event["status"] = "cancelled"
            db.events.set_active_event(event)
            logger.info(f"[ArenaScheduler] {event_type} on {server_id} cancelled after {max_retries} retries.")

    return True
