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


def _get_last_daily_memory_update_time() -> datetime | None:
    """Get the timestamp of the last daily memory update from the active server."""
    try:
        server_name = _get_active_server_name()
        if not server_name:
            return None
        
        from agent_mind import get_global_db
        db_instance = get_global_db(server_name=server_name)
        
        with db_instance._lock:
            import sqlite3
            conn = sqlite3.connect(db_instance.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT updated_at FROM daily_memory 
                WHERE summary IS NOT NULL AND summary != '' 
                ORDER BY updated_at DESC LIMIT 1
            """)
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0]:
                from datetime import datetime
                # Parse the datetime string
                return datetime.fromisoformat(result[0].replace('Z', '+00:00'))
                
    except Exception as e:
        logger.debug(f"Could not retrieve last daily memory update time: {e}")
    
    return None

def _get_active_server_name() -> str | None:
    if not ACTIVE_SERVER_FILE.exists():
        return None
    return ACTIVE_SERVER_FILE.read_text(encoding="utf-8").strip() or None

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

        # Propagate active server to subprocess if it exists
        try:
            if ACTIVE_SERVER_FILE.exists():
                active_server = ACTIVE_SERVER_FILE.read_text(encoding="utf-8").strip()
                if active_server:
                    env["ACTIVE_SERVER_NAME"] = active_server
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

async def _run_server_bound_task(task_name: str, task_func):
    try:
        server_name = _get_active_server_name()
        if not server_name:
            return
        result = await asyncio.to_thread(task_func, server_name)
        return server_name, result
    except Exception as e:
        logger.error(f"[run] ❌ Error running server-bound task '{task_name}': {e}")
        return None, None


async def execute_recent_memory_summary():
    server_name, refreshed = await _run_server_bound_task("recent_memory_summary", refresh_due_recent_memories)
    if server_name and refreshed:
        logger.info(f"[run] 🧠 Recent memory summary refreshed for '{server_name}'")


async def execute_daily_memory_summary():
    server_name, summary = await _run_server_bound_task("daily_memory_summary", generate_daily_memory_summary)
    if server_name and summary:
        logger.info(f"[run] 🧠 Daily memory summary refreshed for '{server_name}'")


async def execute_relationship_memory_refresh():
    server_name, refreshed = await _run_server_bound_task("relationship_memory_refresh", refresh_due_relationship_memories)
    if server_name and refreshed:
        logger.info(f"[run] 🧠 Relationship memories refreshed for '{server_name}': {refreshed}")


def _get_last_daily_memory_update_time(server_name: str | None = None) -> datetime | None:
    """Get the last time daily memory was updated from the database."""
    from agent_db import get_global_db
    resolved_server = server_name or _get_active_server_name()
    if not resolved_server:
        return None
    try:
        db_instance = get_global_db(server_name=resolved_server)
        # Get the most recent daily memory record by updated_at
        import sqlite3
        with db_instance._lock:
            conn = sqlite3.connect(db_instance.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT updated_at FROM daily_memory
                WHERE server_name = ? AND summary IS NOT NULL AND summary != ''
                ORDER BY updated_at DESC LIMIT 1
            ''', (resolved_server,))
            row = cursor.fetchone()
            conn.close()
            if row and row["updated_at"]:
                # Parse ISO format datetime string
                from datetime import datetime
                try:
                    return datetime.fromisoformat(row["updated_at"])
                except (ValueError, TypeError):
                    return None
        return None
    except Exception as e:
        logger.warning(f"[run] ⚠️ Could not get last daily memory time: {e}")
        return None


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
        ("daily_memory", execute_daily_memory_summary, timedelta(days=1), "Next daily memory summary"),
    ]
    for task_key, task_func, interval, log_label in task_specs:
        if now < next_non_role_run[task_key]:
            continue
        await task_func()
        next_non_role_run[task_key] = datetime.now() + interval
        logger.info(f"[run] 🧠 {log_label}: {next_non_role_run[task_key]:%Y-%m-%d %H:%M:%S}")
    await execute_recent_memory_summary()
    await execute_relationship_memory_refresh()


async def _wait_for_active_server_publish(next_run: dict[str, datetime]):
    if not next_run:
        return
    for _ in range(60):
        if ACTIVE_SERVER_FILE.exists() and ACTIVE_SERVER_FILE.stat().st_size > 0:
            break
        await asyncio.sleep(1)


# ── Role scheduler ────────────────────────────────────────────────────────────

async def scheduler(config: dict):
    roles_cfg = config.get("roles", {})
    logger.info(f"[run] 📋 Starting scheduler with {len(roles_cfg)} configured roles")
    next_run = _build_optional_role_schedule(config)

    if not next_run:
        logger.info("[run] ℹ️  No active roles. Only the main bot is running.")

    await _wait_for_active_server_publish(next_run)

    # Calculate next daily memory run based on last database update time
    # This prevents the timer from resetting on every bot restart
    last_daily_memory_time = _get_last_daily_memory_update_time()
    if last_daily_memory_time:
        next_daily_memory_run = last_daily_memory_time + timedelta(days=1)
        logger.info(f"[run] 🧠 Last daily memory was at {last_daily_memory_time:%Y-%m-%d %H:%M:%S}, next run scheduled for {next_daily_memory_run:%Y-%m-%d %H:%M:%S}")
    else:
        next_daily_memory_run = datetime.now()
        logger.info(f"[run] 🧠 No previous daily memory found, scheduling first run for {next_daily_memory_run:%Y-%m-%d %H:%M:%S}")

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
