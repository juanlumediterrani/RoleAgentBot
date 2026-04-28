#!/usr/bin/env python3
"""
RoleAgentBot - Main orchestrator.

Responsibilities:
- Load and validate agent_config.json.
- Run the global RSS feed health check at startup.
- Start RunSupervisor (in-process Supervisor + JobScheduler infrastructure)
  which owns memory maintenance jobs and the MC actor.
- Run the Discord bot coroutine. The Discord bot itself owns DiscordScheduler
  (subrole ticker, news_watcher, treasure_hunter, banker, database_cleanup),
  so this entry point keeps zero per-role scheduling logic of its own.

All work runs in a single asyncio event loop; there are no subprocesses.
"""

import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from agent_logging import get_logger

# Import validation schema for agent_config
try:
    from validation.schemas import AgentConfig, ValidationError
    VALIDATION_AVAILABLE = True
except ImportError:
    VALIDATION_AVAILABLE = False
    ValidationError = Exception

from agent_engine import (
    refresh_due_recent_memories,
    refresh_due_relationship_memories,
)
from agent_mind import generate_weekly_personality_evolution

logger = get_logger('run')

# ── Paths ───────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.resolve()
CONFIG_FILE = BASE_DIR / "agent_config.json"


# ── Configuration ─────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        logger.error(f"[run] ❌ Config file not found: {CONFIG_FILE}")
        sys.exit(1)
    with CONFIG_FILE.open(encoding="utf-8") as f:
        config = json.load(f)
    
    # Validate configuration if validation module is available
    if VALIDATION_AVAILABLE:
        try:
            AgentConfig(**config)
            logger.info(f"[run] 📋 Configuration loaded and validated successfully")
        except Exception as e:
            logger.warning(
                f"[run] ⚠️  Configuration validation failed: {e}. "
                "Using configuration as-is (may have issues)."
            )
            # In fail-hard mode, we would sys.exit(1) here
            # For fail-soft mode, we continue with the potentially invalid config
    else:
        logger.info(f"[run] 📋 Configuration loaded (validation not available)")
    
    return config

# ── Memory maintenance jobs (called by RunSupervisor.JobScheduler) ──────────────


async def execute_daily_memory_summary_all_servers():
    """Execute daily memory generation for servers whose stagger window is due.

    Uses per-server `is_scheduled_task_due()` to distribute LLM load across
    the 24h period (hash-offset by server_id), avoiding thundering-herd
    saturation of Vertex/Groq/Mistral quotas.
    """
    from agent_db import get_all_server_ids, get_global_db
    from agent_mind import generate_daily_memory_summary

    server_ids = get_all_server_ids()
    if not server_ids:
        logger.debug("[run] 🧠 No servers found for daily memory generation")
        return

    DAILY_INTERVAL_HOURS = 24.0
    # 24h stagger window → each server fires on its own minute-of-the-day.
    STAGGER_WINDOW_HOURS = 24.0

    processed = 0
    skipped = 0
    for server_id in server_ids:
        try:
            db_instance = get_global_db(server_id=server_id)
            if not db_instance.is_scheduled_task_due(
                "daily_memory_summary",
                interval_hours=DAILY_INTERVAL_HOURS,
                stagger_window_hours=STAGGER_WINDOW_HOURS,
            ):
                skipped += 1
                await asyncio.sleep(0)
                continue

            # Yield briefly between LLM calls (in-window, not global burst)
            if processed > 0:
                await asyncio.sleep(3)

            logger.info(f"[run] 🧠 Generating daily memory for server '{server_id}' (due)")
            summary = await asyncio.to_thread(generate_daily_memory_summary, server_id)
            if summary:
                logger.info(f"[run] ✅ Daily memory generated for '{server_id}': {summary[:50]}...")
            else:
                logger.warning(f"[run] ⚠️ Failed to generate daily memory for '{server_id}'")

            # Mark done regardless of success so we don't retry in tight loop
            db_instance.mark_scheduled_task_done(
                "daily_memory_summary",
                interval_hours=DAILY_INTERVAL_HOURS,
                stagger_window_hours=STAGGER_WINDOW_HOURS,
            )
            processed += 1
        except Exception as e:
            logger.error(f"[run] ❌ Error processing daily memory for server '{server_id}': {e}")
            continue

    if processed:
        logger.info(
            f"[run] 🧠 Daily memory pass: {processed} processed, {skipped} not due"
        )
    else:
        logger.debug(f"[run] 🧠 Daily memory pass: 0 due (of {len(server_ids)} servers)")


async def execute_recent_memory_summary_all_servers():
    """Execute recent memory summary for all servers."""
    try:
        refreshed = await asyncio.to_thread(refresh_due_recent_memories)
        if refreshed:
            logger.info(f"[run] 🧠 Recent memory refresh: {refreshed} server(s) updated")
    except Exception as e:
        logger.error(f"[run] ❌ Error in recent memory refresh: {e}")


async def execute_relationship_memory_refresh_all_servers():
    """Execute relationship memory refresh for all servers."""
    try:
        refreshed = await asyncio.to_thread(refresh_due_relationship_memories)
        if refreshed:
            logger.info(f"[run] 🧠 Relationship memory refresh: {refreshed} user relationship(s) updated")
    except Exception as e:
        logger.error(f"[run] ❌ Error in relationship memory refresh: {e}")


async def execute_weekly_personality_evolution_all_servers():
    """Execute weekly personality evolution for servers whose stagger window is due.

    Uses per-server `is_scheduled_task_due()` with a 7-day stagger window to
    distribute LLM load evenly (hash-offset by server_id) across the week.
    """
    from agent_db import get_all_server_ids, get_global_db

    server_ids = get_all_server_ids()
    if not server_ids:
        logger.debug("[run] 🧬 No servers found for weekly personality evolution")
        return

    WEEKLY_INTERVAL_HOURS = 24.0 * 7
    STAGGER_WINDOW_HOURS = 24.0 * 7  # spread across the whole week

    processed = 0
    skipped = 0
    for server_id in server_ids:
        try:
            db_instance = get_global_db(server_id=server_id)
            if not db_instance.is_scheduled_task_due(
                "weekly_personality_evolution",
                interval_hours=WEEKLY_INTERVAL_HOURS,
                stagger_window_hours=STAGGER_WINDOW_HOURS,
            ):
                skipped += 1
                await asyncio.sleep(0)
                continue

            if processed > 0:
                await asyncio.sleep(3)

            result = await asyncio.to_thread(generate_weekly_personality_evolution, server_id)
            if result.get("success"):
                logger.info(f"[run] 🧬 Weekly personality evolution completed for '{server_id}'")
            else:
                logger.warning(
                    f"[run] ⚠️ Personality evolution skipped for '{server_id}': "
                    f"{result.get('error', 'Unknown')}"
                )

            db_instance.mark_scheduled_task_done(
                "weekly_personality_evolution",
                interval_hours=WEEKLY_INTERVAL_HOURS,
                stagger_window_hours=STAGGER_WINDOW_HOURS,
            )
            processed += 1
        except Exception as e:
            logger.error(f"[run] ❌ Error in personality evolution for '{server_id}': {e}")
            continue

    if processed:
        logger.info(
            f"[run] 🧬 Weekly personality evolution pass: {processed} processed, {skipped} not due"
        )


async def execute_gdpr_retention_all_servers():
    """Apply the configured GDPR retention policy on every server database."""
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"[run] 🧹 Could not load config for GDPR retention: {e}")
        return

    gdpr_cfg = config.get("gdpr", {}) or {}
    if not gdpr_cfg.get("retention_enabled", True):
        logger.debug("[run] 🧹 GDPR retention disabled in agent_config.json, skipping")
        return

    interactions_days = int(gdpr_cfg.get("interactions_days", 90))
    derived_memory_days = int(gdpr_cfg.get("derived_memory_days", 365))

    try:
        from agent_db import apply_retention_across_servers
        report = await asyncio.to_thread(
            apply_retention_across_servers,
            interactions_days,
            derived_memory_days,
        )
        if report:
            logger.info(
                f"[run] 🧹 GDPR retention sweep purged data on {len(report)} server(s) "
                f"(interactions≥{interactions_days}d, derived≥{derived_memory_days}d)"
            )
    except Exception as e:
        logger.error(f"[run] 🧹 GDPR retention sweep failed: {e}")

    # Prompt-log file retention — safety net against human error leaving
    # prompt_logging=true in production. Runs regardless of the prompt_logging
    # flag so stale files are cleaned up even after the flag is turned off.
    try:
        from prompts_logger import purge_old_prompt_logs
        prompt_retention_days = int(
            (config.get("dev_options") or {}).get("prompt_log_retention_days", 15)
        )
        purged = await asyncio.to_thread(purge_old_prompt_logs, prompt_retention_days)
        if purged:
            logger.info(f"[run] 🧹 Prompt log retention: deleted {purged} file(s) older than {prompt_retention_days}d")
    except Exception as e:
        logger.error(f"[run] 🧹 Prompt log retention failed: {e}")


# ── Main Discord bot ───────────────────────────────────────────────────────────────────

async def discord_bot():
    """
    Run the main Discord bot in-process with auto-restart on failure.

    Replaces the previous subprocess approach. The bot now runs as a
    coroutine in the same event loop as the scheduler and supervisor,
    eliminating IPC overhead and enabling shared state.

    On unhandled exceptions, waits 10s and restarts (legacy compatibility).
    For richer restart policies, use the Supervisor (run_supervisor.py).
    """
    from discord_bot.agent_discord import run_bot_async

    while True:
        logger.info("[run] 🤖 Starting main Discord bot (in-process)...")
        try:
            await run_bot_async()
            logger.info("[run] 👋 Main bot terminated cleanly.")
            break
        except asyncio.CancelledError:
            logger.info("[run] 👋 Main bot cancelled.")
            raise
        except Exception as e:
            logger.warning(f"[run] ⚠️  Main bot crashed: {e}. Relaunching in 10s...")
            await asyncio.sleep(10)

# ── Entry point ──────────────────────────────────────────────────────────────

async def main():
    config   = load_config()
    platform = config.get("platform", "discord")

    # Global RSS feed health check is now run by DiscordScheduler in background

    logger.info(f"[run] 🌐 Platform: {platform}")
    logger.info(f"[run] 📋 Configuration loaded from: {CONFIG_FILE}")
    logger.info(f"[run] 🤖 Base directory: {BASE_DIR}")

    # Initialize RunSupervisor for new infrastructure
    try:
        from run_supervisor import get_run_supervisor
        run_sup = get_run_supervisor()
        await run_sup.start()
        run_sup.register_memory_jobs(config)
        await run_sup.register_mc_actor(config)
        logger.info("[run] 🔄 RunSupervisor started with memory jobs and MC actor (new infrastructure)")
    except Exception as e:
        logger.error(f"[run] ❌ Failed to start RunSupervisor: {e}")
        logger.warning("[run] ⚠️ Continuing with legacy scheduler")
        run_sup = None

    if platform == "discord":
        # The Discord bot owns its own DiscordScheduler (started in on_ready) for
        # subrole ticker, news_watcher, treasure_hunter, banker, and database
        # cleanup. RunSupervisor (above) owns memory maintenance jobs and the
        # MC actor. There are no longer any role subprocesses or per-role
        # scheduling logic in this entry point.
        always_on_tasks = [discord_bot()]
    elif platform == "telegram":
        logger.info("[run] ℹ️  Telegram selected — main bot pending implementation")
        always_on_tasks = []
    else:
        logger.error(f"[run] ❌ Unknown platform: {platform}")
        sys.exit(1)

    try:
        await asyncio.gather(*always_on_tasks)
    finally:
        # Cleanup on shutdown
        if run_sup:
            await run_sup.stop()

if __name__ == "__main__":
    try:
        logger.info("[run] 🚀 Starting RoleAgentBot...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n[run] 🛑 Stopped by user.")
