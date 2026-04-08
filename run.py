#!/usr/bin/env python3
"""
RoleAgentBot - Main orchestrator
Starts the main Discord bot and launches each role as a subprocess
according to the interval configured in agent_config.json.
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from agent_logging import get_logger

from agent_engine import (
    _get_subrole_frequency_from_config,
    get_active_subroles,
    get_mc_mode,
    should_execute_subrole_task,
    execute_subrole_internal_task,
    generate_daily_memory_summary,
    refresh_due_recent_memories,
    refresh_due_relationship_memories,
)

logger = get_logger('run')

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.resolve()
CONFIG_FILE = BASE_DIR / "agent_config.json"
PYTHON     = sys.executable   # same interpreter from active venv

ACTIVE_SERVER_FILE = BASE_DIR / ".active_server"

# ── Configuration ─────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        logger.error(f"[run] ❌ Config file not found: {CONFIG_FILE}")
        sys.exit(1)
    with CONFIG_FILE.open(encoding="utf-8") as f:
        config = json.load(f)
        logger.info(f"[run] 📋 Configuration loaded successfully")
        return config

# ── Subprocess launcher ───────────────────────────────────────────────────────

_persistent_processes: dict = {}

async def launch_role(name: str, script_rel: str, persistent: bool = False):
    """Run the role script as a subprocess. Persistent roles are launched once and don't block."""
    script = BASE_DIR / script_rel
    if not script.exists():
        logger.warning(f"[run] ⚠️  Script not found for '{name}': {script}")
        return

    if persistent:
        current_proc = _persistent_processes.get(name)
        if current_proc and current_proc.returncode is None:
            logger.info(f"[run] 🔄 Persistent role '{name}' already active (PID {current_proc.pid}), skipping relaunch")
            return

    logger.info(f"[run] 🚀 Running role '{name}' → {script.name}")
    try:
        env = os.environ.copy()
        env["ROLE_AGENT_PROCESS"] = "1"

        # Propagate active server to subprocess if it exists (for compatibility)
        try:
            if ACTIVE_SERVER_FILE.exists():
                active_server = ACTIVE_SERVER_FILE.read_text(encoding="utf-8").strip()
                if active_server:
                    env["ACTIVE_SERVER_ID"] = active_server
        except Exception:
            pass

        proc = await asyncio.create_subprocess_exec(
            PYTHON, str(script),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR),
            env=env,
        )

        if persistent:
            _persistent_processes[name] = proc
            logger.info(f"[run] 🔄 Persistent role '{name}' launched in background (PID {proc.pid})")
            return

        stdout, _ = await proc.communicate()
        output = stdout.decode(errors="replace").strip()
        if output:
            for line in output.splitlines():
                match = re.match(r'^\s*\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}\s+(.+)$', line.strip())
                if match:
                    logger.info(f"  [{name}] {match.group(1)}")
                else:
                    logger.info(f"  [{name}] {line.strip()}")
        exit_code = proc.returncode
        status = "✅" if exit_code == 0 else f"⚠️  (code {exit_code})"
        logger.info(f"[run] {status} Role '{name}' finished")
    except Exception as e:
        logger.error(f"[run] ❌ Error launching '{name}': {e}")

async def execute_recent_memory_summary_all_servers():
    from agent_db import get_all_server_ids

    server_ids = get_all_server_ids()
    if not server_ids:
        logger.info("[run] 🧠 No servers found for recent memory refresh")
        return

    total_refreshed = 0
    for server_id in server_ids:
        try:
            refreshed = await asyncio.to_thread(refresh_due_recent_memories, server_id)
            if refreshed:
                total_refreshed += refreshed
                logger.info(f"[run] 🧠 Recent memory summary refreshed for '{server_id}' (PRIORITY: 1)")
        except Exception as e:
            logger.error(f"[run] ❌ Error refreshing recent memory for server '{server_id}': {e}")

    if total_refreshed:
        logger.info(f"[run] 🧠 Recent memory refresh completed across servers: {total_refreshed} update(s)")


async def execute_daily_memory_summary_all_servers():
    """Execute daily memory generation for ALL servers, not just active one."""
    from agent_db import get_all_server_ids
    from agent_mind import generate_daily_memory_summary
    
    server_ids = get_all_server_ids()
    if not server_ids:
        logger.info("[run] 🧠 No servers found for daily memory generation")
        return
    
    logger.info(f"[run] 🧠 Running daily memory generation for {len(server_ids)} servers")
    
    for server_id in server_ids:
        try:
            # Check if server needs daily memory generation
            from agent_db import get_global_db
            import sqlite3
            
            db_instance = get_global_db(server_id=server_id)
            with db_instance._lock:
                conn = sqlite3.connect(db_instance.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT summary, updated_at FROM daily_memory 
                    WHERE summary IS NOT NULL AND summary != '' AND summary != '[Error in internal task]'
                    ORDER BY updated_at DESC LIMIT 1
                """)
                result = cursor.fetchone()
                conn.close()
                
                should_generate = False
                if not result or not result[0] or not result[0].strip():
                    # No daily memory - generate immediately
                    should_generate = True
                    reason = "no existing memory"
                else:
                    # Check if it's been more than 24 hours
                    from datetime import datetime, timedelta
                    last_update = datetime.fromisoformat(result[1].replace('Z', '+00:00'))
                    if datetime.now().replace(tzinfo=last_update.tzinfo) - last_update > timedelta(hours=24):
                        should_generate = True
                        reason = "24+ hours since last update"
                
                if should_generate:
                    logger.info(f"[run] 🧠 Generating daily memory for server '{server_id}' ({reason})")
                    summary = await asyncio.to_thread(generate_daily_memory_summary, server_id)
                    if summary:
                        logger.info(f"[run] ✅ Daily memory generated for '{server_id}': {summary[:50]}...")
                    else:
                        logger.warning(f"[run] ⚠️ Failed to generate daily memory for '{server_id}'")
                else:
                    logger.debug(f"[run] 🧠 Daily memory up to date for '{server_id}'")
                    
        except Exception as e:
            logger.error(f"[run] ❌ Error processing daily memory for server '{server_id}': {e}")
    
    logger.info(f"[run] 🧠 Daily memory generation completed for all servers")


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


def _build_optional_role_schedule(config: dict) -> dict[str, datetime]:
    roles_cfg = config.get("roles", {})
    next_run: dict[str, datetime] = {}
    now = datetime.now()

    for name, cfg in roles_cfg.items():
        enabled = cfg.get("enabled", False)
        logger.info(f"[run] 🔍 Config enabled={enabled} → '{name}' {'✅' if enabled else '❌'}")
        if not enabled:
            logger.info(f"[run] 💤 Role '{name}' disabled")
            continue

        if name == "mc":
            mc_mode = get_mc_mode()
            logger.info(f"[run] 🎵 MC mode: '{mc_mode}'")
            if mc_mode == "integrated":
                logger.info("[run] 🎵 MC integrated mode, skipping separate launch")
                continue
            if mc_mode != "standalone":
                logger.info(f"[run] 🎵 MC mode '{mc_mode}' not recognized, skipping")
                continue
            logger.info("[run] 🎵 MC standalone mode, launching as process")

        next_run[name] = now
        logger.info(f"[run] 📋 Role '{name}' enabled — every {cfg['interval_hours']}h")

    return next_run


def _get_due_role_tasks(next_run: dict[str, datetime], now: datetime) -> list[str]:
    return [name for name, scheduled_for in next_run.items() if now >= scheduled_for]


async def _execute_optional_role_tasks(roles_cfg: dict, next_run: dict[str, datetime], now: datetime):
    pending_roles = _get_due_role_tasks(next_run, now)
    if not pending_roles:
        return

    await asyncio.gather(*[
        launch_role(
            name,
            roles_cfg[name]["script"],
            persistent=roles_cfg[name].get("persistent", False),
        )
        for name in pending_roles
    ])

    for name in pending_roles:
        hours = roles_cfg[name]["interval_hours"]
        next_run[name] = datetime.now() + timedelta(hours=hours)
        logger.info(f"[run] ⏳ '{name}' next execution: {next_run[name]:%H:%M:%S}")


def _get_due_subrole_tasks() -> list[tuple[str, dict]]:
    tasks_to_execute = []
    for subrole_name, subrole_config in get_active_subroles().items():
        frequency = _get_subrole_frequency_from_config(subrole_name)
        if should_execute_subrole_task(subrole_name, frequency):
            tasks_to_execute.append((subrole_name, subrole_config))
    return tasks_to_execute


async def _execute_optional_subrole_tasks():
    try:
        tasks_to_execute = _get_due_subrole_tasks()
        if not tasks_to_execute:
            return
        logger.info(f"[run] 🎭 Executing {len(tasks_to_execute)} subrole tasks: {[name for name, _ in tasks_to_execute]}")
        await asyncio.gather(*[
            execute_subrole_internal_task(subrole_name, subrole_config)
            for subrole_name, subrole_config in tasks_to_execute
        ])
    except Exception as e:
        logger.error(f"[run] 🎭 Error in subrole tasks: {e}")


async def _execute_optional_non_role_tasks(now: datetime, next_non_role_run: dict[str, datetime]):
    task_specs = [
        ("daily_memory", execute_daily_memory_summary_all_servers, timedelta(days=1), "Next daily memory summary"),
    ]
    for task_key, task_func, interval, log_label in task_specs:
        if now < next_non_role_run[task_key]:
            continue
        await task_func()
        next_non_role_run[task_key] = datetime.now() + interval
        logger.info(f"[run] 🧠 {log_label}: {next_non_role_run[task_key]:%Y-%m-%d %H:%M:%S}")
    await execute_recent_memory_summary_all_servers()
    # Small delay to avoid overlap and give priority to recent memory
    await asyncio.sleep(5)
    await execute_relationship_memory_refresh_all_servers()


# ── Role scheduler ────────────────────────────────────────────────────────────

async def scheduler(config: dict):
    roles_cfg = config.get("roles", {})
    logger.info(f"[run] 📋 Starting scheduler with {len(roles_cfg)} configured roles")
    next_run = _build_optional_role_schedule(config)

    if not next_run:
        logger.info("[run] ℹ️  No active roles. Only the main bot is running.")

    # No longer waiting for active server - process all servers immediately

    # Schedule daily memory 24h from now - the bootstrap in db_init.py handles the first
    # generation at startup so we avoid a race condition between the two.
    next_daily_memory_run = datetime.now() + timedelta(hours=24)
    logger.info(f"[run] 🧠 Next global daily memory sweep scheduled for {next_daily_memory_run:%Y-%m-%d %H:%M:%S}")

    next_non_role_run = {
        "daily_memory": next_daily_memory_run,
    }

    while True:
        now = datetime.now()
        await _execute_optional_role_tasks(roles_cfg, next_run, now)
        await _execute_optional_subrole_tasks()
        await _execute_optional_non_role_tasks(now, next_non_role_run)
        await asyncio.sleep(30)

# ── Main Discord bot ─────────────────────────────────────────────────────────

async def discord_bot():
    """
    Keeps the main bot (agent_discord.py) alive as a subprocess.
    If it dies, relaunches automatically after 10s.
    Only used when platform == "discord".
    """
    while True:
        logger.info("[run] 🤖 Starting main Discord bot...")
        proc = await asyncio.create_subprocess_exec(
            PYTHON, "-m", "discord_bot.agent_discord",
            cwd=str(BASE_DIR),
        )
        exit_code = await proc.wait()
        if exit_code == 0:
            logger.info("[run] 👋 Main bot terminated cleanly.")
            break
        logger.warning(f"[run] ⚠️  Main bot terminated with code {exit_code}. Relaunching in 10s...")
        await asyncio.sleep(10)

# ── Entry point ──────────────────────────────────────────────────────────────

async def main():
    config   = load_config()
    platform = config.get("platform", "discord")

    # Perform global RSS feed health check once at startup
    logger.info("[run] 📡 Performing global RSS feed health check...")
    try:
        from roles.news_watcher.global_feed_health import check_global_feed_health
        check_global_feed_health()
    except Exception as e:
        logger.error(f"[run] ❌ Error in global feed health check: {e}")

    logger.info(f"[run] 🌐 Platform: {platform}")
    logger.info(f"[run] 📋 Configuration loaded from: {CONFIG_FILE}")
    logger.info(f"[run] 🤖 Base directory: {BASE_DIR}")

    if platform == "discord":
        always_on_tasks = [discord_bot(), scheduler(config)]
    elif platform == "telegram":
        logger.info("[run] ℹ️  Telegram selected — main bot pending implementation")
        always_on_tasks = []
    else:
        logger.error(f"[run] ❌ Unknown platform: {platform}")
        sys.exit(1)

    await asyncio.gather(*always_on_tasks)

if __name__ == "__main__":
    try:
        logger.info("[run] 🚀 Starting RoleAgentBot...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n[run] 🛑 Stopped by user.")
