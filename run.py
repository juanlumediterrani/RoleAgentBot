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
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from agent_logging import get_logger

# Import subrole system
from agent_engine import get_active_subroles, execute_subrole_internal_task

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

# ── Subrole tasks system ─────────────────────────────────────────────────────

async def execute_subrole_tasks():
    """
    Execute internal tasks for active subroles (beggar, ring).
    This runs independently of the main role scheduler but only checks frequency.
    """
    try:
        active_subroles = get_active_subroles()
        
        if not active_subroles:
            return
        
        # Check which tasks actually need to run based on frequency from agent_config.json
        tasks_to_execute = []
        for subrole_name, subrole_config in active_subroles.items():
            # Get frequency from agent_config.json
            frequency = _get_subrole_frequency_from_config(subrole_name)
            
            # Import the frequency check function
            from agent_engine import should_execute_subrole_task
            if should_execute_subrole_task(subrole_name, frequency):
                tasks_to_execute.append((subrole_name, subrole_config))
        
        if not tasks_to_execute:
            # Don't log anything if no tasks need to run (avoid spam)
            return
        
        logger.info(f"[run] 🎭 Executing {len(tasks_to_execute)} subrole tasks: {[name for name, _ in tasks_to_execute]}")
        
        # Execute tasks in parallel
        await asyncio.gather(*[
            execute_subrole_internal_task(subrole_name, subrole_config)
            for subrole_name, subrole_config in tasks_to_execute
        ])
        
    except Exception as e:
        logger.error(f"[run] 🎭 Error in subrole tasks: {e}")


def _get_subrole_frequency_from_config(subrole_name: str) -> int:
    """Get subrole frequency from agent_config.json."""
    try:
        # Import BASE_DIR for path construction
        import os
        from pathlib import Path
        
        # Get the directory where run.py is located
        BASE_DIR = Path(__file__).parent
        
        # Load agent_config.json
        config_path = BASE_DIR / "agent_config.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Navigate to subrole frequency
        roles_cfg = config.get("roles", {})
        trickster_cfg = roles_cfg.get("trickster", {})
        subroles_cfg = trickster_cfg.get("subroles", {})
        subrole_cfg = subroles_cfg.get(subrole_name, {})
        
        return subrole_cfg.get("frequency_hours", 12)  # Default to 12 hours
        
    except Exception as e:
        logger.warning(f"Could not get frequency for {subrole_name} from config: {e}")
        return 12  # Default fallback

# ── Role scheduler ────────────────────────────────────────────────────────────

async def scheduler(config: dict):
    """
    Main loop that launches each active role according to its interval.
    Runs all enabled roles immediately on startup, then respects the interval.
    Also handles subrole internal tasks.
    """
    roles_cfg = config.get("roles", {})
    logger.info(f"[run] 📋 Starting scheduler with {len(roles_cfg)} configured roles")

    # State: next execution time per role
    next_run: dict[str, datetime] = {}
    now = datetime.now()

    for name, cfg in roles_cfg.items():
        # Use only agent_config.json as single source of truth
        enabled = cfg.get("enabled", False)
        logger.info(f"[run] 🔍 Config enabled={enabled} → '{name}' {'✅' if enabled else '❌'}")
            
        if enabled:
            # Special case for MC: check mode
            if name == "mc":
                from agent_engine import get_mc_mode
                mc_mode = get_mc_mode()
                logger.info(f"[run] 🎵 MC mode: '{mc_mode}'")
                
                if mc_mode == "integrated":
                    logger.info(f"[run] 🎵 MC integrated mode, skipping separate launch")
                    continue  # Don't launch as separate process
                elif mc_mode == "standalone":
                    logger.info(f"[run] 🎵 MC standalone mode, launching as process")
                else:
                    logger.info(f"[run] 🎵 MC mode '{mc_mode}' not recognized, skipping")
                    continue
            
            # First execution immediately on startup
            next_run[name] = now
            logger.info(f"[run] 📋 Role '{name}' enabled — every {cfg['interval_hours']}h")
        else:
            logger.info(f"[run] 💤 Role '{name}' disabled")

    if not next_run:
        logger.info("[run] ℹ️  No active roles. Only the main bot is running.")

    # Wait for the main bot to publish the active server, so roles
    # write to databases/<server>/... and logs/<server>/...
    if next_run:
        for _ in range(60):  # ~60s
            if ACTIVE_SERVER_FILE.exists() and ACTIVE_SERVER_FILE.stat().st_size > 0:
                break
            await asyncio.sleep(1)

    while True:
        now = datetime.now()
        pending = [
            name for name, t in next_run.items() if now >= t
        ]

        # Launch pending roles in parallel
        if pending:
            await asyncio.gather(*[
                launch_role(
                    name,
                    roles_cfg[name]["script"],
                    persistent=roles_cfg[name].get("persistent", False)
                )
                for name in pending
            ])
            # Reschedule after execution
            for name in pending:
                hours = roles_cfg[name]["interval_hours"]
                next_run[name] = datetime.now() + timedelta(hours=hours)
                logger.info(f"[run] ⏳ '{name}' next execution: {next_run[name]:%H:%M:%S}")

        # Execute subrole tasks
        await execute_subrole_tasks()

        await asyncio.sleep(30)   # check every 30s

# ── Main Discord bot ─────────────────────────────────────────────────────────

async def discord_bot():
    """
    Keeps the main bot (agent_discord.py) alive as a subprocess.
    If it dies, relaunches automatically after 10s.
    Only used when platform == "discord".
    """
    script = BASE_DIR / "discord_bot" / "agent_discord.py"
    while True:
        logger.info("[run] 🤖 Starting main Discord bot...")
        proc = await asyncio.create_subprocess_exec(
            PYTHON, str(script),
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

    tasks = []

    if platform == "discord":
        tasks.append(discord_bot())
        tasks.append(scheduler(config))
    elif platform == "telegram":
        # TODO: add bot_telegram() when implemented
        logger.info("[run] ℹ️  Telegram selected — main bot pending implementation")
    else:
        logger.error(f"[run] ❌ Unknown platform: {platform}")
        sys.exit(1)

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        logger.info("[run] 🚀 Starting RoleAgentBot...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n[run] 🛑 Stopped by user.")
