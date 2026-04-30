"""JobScheduler integration for agent_discord.py.

Replaces discord.py @tasks.loop schedulers with the new JobScheduler infrastructure.
This provides better control, observability, and resilience for scheduled tasks.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from supervisor import JobScheduler, Schedule
from agent_logging import get_logger

logger = get_logger("discord_scheduler")


class DiscordScheduler:
    """Manages scheduled tasks for the Discord bot using JobScheduler.

    Hosts every Discord-context-bound periodic task; replaces both the legacy
    @tasks.loop schedulers in agent_discord.py and the old role-script
    dispatcher (run.py::launch_role).

    Registered jobs:
    - discord_task_scheduler (1 min) → subrole tasks (beggar, ring, ...)
    - treasure_hunter_global_scheduler (1 min, runs on interval_hours)
    - news_watcher_global_scheduler (1 min, runs on interval_hours)
    - news_watcher_subscription_processor (1 min, runs on interval_hours)
    - global_feed_health_scheduler (1 min, runs on interval_hours)
    - database_cleanup (24 h)
    - banker_global_scheduler (24 h) → banker_task() across all servers
    - recent_memory_summary (4 h) → refresh_due_recent_memories()
    - relationship_memory_refresh (1 h) → refresh_due_relationship_memories()
    """

    def __init__(
        self,
        bot_instance,
        agent_config: dict,
        external_scheduler: Optional[JobScheduler] = None,
    ):
        self.bot = bot_instance
        self.agent_config = agent_config

        # When `external_scheduler` is provided (typical: RunSupervisor.job_scheduler),
        # we register our jobs on the shared scheduler so the whole bot runs on a
        # single JobScheduler instance. When None we own a private scheduler
        # (used by tests / standalone scenarios).
        self._owns_scheduler = external_scheduler is None
        self.scheduler = external_scheduler or JobScheduler(tick_seconds=60.0, logger=logger)
        self._running = False

        # Track next run times for interval-based jobs
        self._treasure_hunter_next_run: Optional[datetime] = None
        self._news_watcher_next_run: Optional[datetime] = None
        self._subscription_processor_next_runs: dict = {}
        self._global_feed_health_next_run: Optional[datetime] = None

    async def start(self):
        """Register Discord-bound jobs and start the scheduler if we own it."""
        if self._running:
            logger.warning("[DiscordScheduler] Already running")
            return

        self._running = True
        mode = "standalone" if self._owns_scheduler else "shared (RunSupervisor)"
        logger.info(f"[DiscordScheduler] Registering jobs ({mode})")

        # Register all jobs on whatever scheduler we have
        self._register_jobs()

        # Only run a private scheduler when we own it; otherwise rely on the
        # external one (RunSupervisor) to drive ticks.
        if self._owns_scheduler:
            asyncio.create_task(self.scheduler.run_forever())

        logger.info("[DiscordScheduler] Started successfully")

    async def stop(self):
        """Stop the private scheduler (if any). Shared schedulers are stopped by their owner."""
        if not self._running:
            return

        logger.info("[DiscordScheduler] Stopping...")
        if self._owns_scheduler:
            await self.scheduler.stop()
        self._running = False
        logger.info("[DiscordScheduler] Stopped")

    def _register_jobs(self):
        """Register all scheduled jobs with JobScheduler."""

        # 1. Discord task scheduler (subrole tasks) - every 1 minute
        self.scheduler.register(
            "discord_task_scheduler",
            self._run_discord_task_scheduler,
            Schedule.every(minutes=1),
            timeout_seconds=300,
        )

        # 2. Treasure hunter global scheduler - every 1 minute (checks interval internally)
        self.scheduler.register(
            "treasure_hunter_global_scheduler",
            self._run_treasure_hunter_scheduler,
            Schedule.every(minutes=1),
            timeout_seconds=600,
        )

        # 3. News watcher global scheduler - every 1 minute (checks interval internally)
        self.scheduler.register(
            "news_watcher_global_scheduler",
            self._run_news_watcher_scheduler,
            Schedule.every(minutes=1),
            timeout_seconds=600,
        )

        # 4. News watcher subscription processor - every 1 minute (checks interval internally)
        self.scheduler.register(
            "news_watcher_subscription_processor",
            self._run_subscription_processor,
            Schedule.every(minutes=1),
            timeout_seconds=600,
        )

        # 5. Global feed health scheduler - every 1 minute (checks interval internally)
        self.scheduler.register(
            "global_feed_health_scheduler",
            self._run_global_feed_health_scheduler,
            Schedule.every(minutes=1),
            timeout_seconds=600,
        )

        # 6. Database cleanup - every 24 hours
        self.scheduler.register(
            "database_cleanup",
            self._run_database_cleanup,
            Schedule.every(hours=24),
            timeout_seconds=300,
        )

        # 7. Banker global task - every 24 hours (creates wallets, daily TAE, dice pot)
        banker_cfg = self.agent_config.get("roles", {}).get("banker", {})
        if banker_cfg.get("enabled", False):
            interval_hours = float(banker_cfg.get("interval_hours", 24))
            self.scheduler.register(
                "banker_global_scheduler",
                self._run_banker_task,
                Schedule.every(hours=interval_hours),
                timeout_seconds=600,
            )
            logger.info(f"[DiscordScheduler] Registered 7 jobs (banker every {interval_hours}h)")
        else:
            logger.info("[DiscordScheduler] Registered 6 jobs (banker disabled)")

        # 8. Recent memory summary - every 4 hours
        # Only register if not already registered by RunSupervisor (run.py case)
        if "recent_memory_summary" not in self.scheduler.status()["jobs"]:
            self.scheduler.register(
                "recent_memory_summary",
                self._run_recent_memory_summary,
                Schedule.every(hours=4),
                timeout_seconds=300,
            )
            logger.info("[DiscordScheduler] Registered recent_memory_summary job")
        else:
            logger.debug("[DiscordScheduler] recent_memory_summary already registered by RunSupervisor, skipping")

        # 9. Relationship memory refresh - every 1 hour
        # Only register if not already registered by RunSupervisor (run.py case)
        if "relationship_memory_refresh" not in self.scheduler.status()["jobs"]:
            self.scheduler.register(
                "relationship_memory_refresh",
                self._run_relationship_memory_refresh,
                Schedule.every(hours=1),
                timeout_seconds=300,
            )
            logger.info("[DiscordScheduler] Registered relationship_memory_refresh job")
        else:
            logger.debug("[DiscordScheduler] relationship_memory_refresh already registered by RunSupervisor, skipping")

    async def _run_discord_task_scheduler(self):
        """Run Discord-dependent subrole tasks.

        Replaces the original discord_task_scheduler @tasks.loop.
        """
        if not self.bot.is_ready():
            return

        try:
            from agent_db import get_all_server_ids
            from agent_engine import get_due_subrole_tasks_for_server, execute_subrole_internal_task

            server_ids = get_all_server_ids()
            if not server_ids:
                return

            for server_id in server_ids:
                tasks_to_execute = get_due_subrole_tasks_for_server(server_id)
                if not tasks_to_execute:
                    continue

                logger.info(f"[BOT_SCHEDULER] Server {server_id}: executing {len(tasks_to_execute)} subrole task(s)")

                for subrole_name, subrole_config in tasks_to_execute:
                    try:
                        await execute_subrole_internal_task(
                            subrole_name, subrole_config,
                            bot_instance=self.bot,
                            server_id=server_id
                        )
                    except Exception as e:
                        logger.error(f"[BOT_SCHEDULER] Error in {subrole_name} for {server_id}: {e}")
        except Exception as e:
            logger.error(f"[BOT_SCHEDULER] Error in task scheduler: {e}")

    async def _run_treasure_hunter_scheduler(self):
        """Run treasure hunter global task.

        Replaces the original treasure_hunter_global_scheduler @tasks.loop.
        """
        if not self.bot.is_ready():
            return

        try:
            th_config = self.agent_config.get("roles", {}).get("treasure_hunter", {})
            if not th_config.get("enabled", False):
                logger.debug("[TH_SCHEDULER] treasure_hunter disabled in agent_config, skipping")
                return

            interval_hours = th_config.get("interval_hours", 1)
            now = datetime.now()

            if self._treasure_hunter_next_run is None or now >= self._treasure_hunter_next_run:
                logger.info(f"[TH_SCHEDULER] Running treasure_hunter task (interval: {interval_hours}h)")

                try:
                    from roles.treasure_hunter.treasure_hunter import ejecutar_mision_treasure_hunter
                    await ejecutar_mision_treasure_hunter(self.agent_config, server_name=None)
                    logger.info("[TH_SCHEDULER] treasure_hunter task completed successfully")
                except Exception as e:
                    logger.error(f"[TH_SCHEDULER] Error executing treasure_hunter task: {e}")

                self._treasure_hunter_next_run = now + timedelta(hours=interval_hours)
                logger.info(f"[TH_SCHEDULER] Next treasure_hunter run scheduled for: {self._treasure_hunter_next_run}")
            else:
                time_until = self._treasure_hunter_next_run - now
                logger.debug(f"[TH_SCHEDULER] Next run in {time_until.total_seconds() // 60:.0f} minutes")
        except Exception as e:
            logger.error(f"[TH_SCHEDULER] Error in treasure_hunter scheduler: {e}")

    async def _run_news_watcher_scheduler(self):
        """Run news watcher global download task.

        Replaces the original news_watcher_global_scheduler @tasks.loop.
        """
        if not self.bot.is_ready():
            return

        try:
            nw_config = self.agent_config.get("roles", {}).get("news_watcher", {})
            if not nw_config.get("enabled", False):
                logger.debug("[NW_SCHEDULER] news_watcher disabled in agent_config, skipping")
                return

            interval_hours = nw_config.get("interval_hours", 1)
            now = datetime.now()

            if self._news_watcher_next_run is None or now >= self._news_watcher_next_run:
                logger.info(f"[NW_SCHEDULER] Running news download task (interval: {interval_hours}h)")

                try:
                    from roles.news_watcher.news_downloader import download_all_feeds_global
                    from roles.news_watcher.global_feed_health import get_healthy_feeds

                    healthy_feeds = get_healthy_feeds()
                    if healthy_feeds:
                        download_task = asyncio.create_task(download_all_feeds_global(healthy_feeds))
                        logger.info(f"[NW_SCHEDULER] Started background download for {len(healthy_feeds)} feeds")
                    else:
                        logger.warning("[NW_SCHEDULER] No healthy feeds found to download")

                    logger.info("[NW_SCHEDULER] News download task initiated")
                except Exception as e:
                    logger.error(f"[NW_SCHEDULER] Error executing news download task: {e}")

                self._news_watcher_next_run = now + timedelta(hours=interval_hours)
                logger.info(f"[NW_SCHEDULER] Next news download run scheduled for: {self._news_watcher_next_run}")
            else:
                time_until = self._news_watcher_next_run - now
                logger.debug(f"[NW_SCHEDULER] Next run in {time_until.total_seconds() // 60:.0f} minutes")
        except Exception as e:
            logger.error(f"[NW_SCHEDULER] Error in news_watcher scheduler: {e}")

    async def _run_subscription_processor(self):
        """Run news watcher subscription processor.

        Replaces the original news_watcher_subscription_processor @tasks.loop.
        """
        if not self.bot.is_ready():
            return

        try:
            nw_config = self.agent_config.get("roles", {}).get("news_watcher", {})
            if not nw_config.get("enabled", False):
                logger.debug("[NW_SUBSCRIPTION_PROCESSOR] news_watcher disabled in agent_config, skipping")
                return

            interval_hours = nw_config.get("interval_hours", 1)
            now = datetime.now()

            global_interval = self._subscription_processor_next_runs.get("global")
            if global_interval is None or now >= global_interval:
                logger.info(f"[NW_SUBSCRIPTION_PROCESSOR] Running subscription processor (interval: {interval_hours}h)")

                try:
                    from roles.news_watcher.news_watcher import process_subscriptions_for_all_servers
                    await process_subscriptions_for_all_servers(self.agent_config)
                    logger.info("[NW_SUBSCRIPTION_PROCESSOR] Subscription processing completed")
                except Exception as e:
                    logger.error(f"[NW_SUBSCRIPTION_PROCESSOR] Error processing subscriptions: {e}")

                self._subscription_processor_next_runs["global"] = now + timedelta(hours=interval_hours)
                logger.info(f"[NW_SUBSCRIPTION_PROCESSOR] Next global run scheduled for: {self._subscription_processor_next_runs['global']}")
            else:
                time_until = global_interval - now
                logger.debug(f"[NW_SUBSCRIPTION_PROCESSOR] Next global run in {time_until.total_seconds() // 60:.0f} minutes")
        except Exception as e:
            logger.error(f"[NW_SUBSCRIPTION_PROCESSOR] Error in subscription processor: {e}")

    async def _run_global_feed_health_scheduler(self):
        """Run global RSS feed health check task.

        Checks health of all RSS feeds periodically in background without blocking startup.
        """
        if not self.bot.is_ready():
            return

        try:
            nw_config = self.agent_config.get("roles", {}).get("news_watcher", {})
            if not nw_config.get("enabled", False):
                logger.debug("[GLOBAL_FEED_HEALTH] news_watcher disabled in agent_config, skipping")
                return

            interval_hours = nw_config.get("feed_health_interval_hours", 24)
            now = datetime.now()

            if self._global_feed_health_next_run is None or now >= self._global_feed_health_next_run:
                logger.info(f"[GLOBAL_FEED_HEALTH] Running feed health check (interval: {interval_hours}h)")

                try:
                    from roles.news_watcher.global_feed_health import check_global_feed_health_async
                    await check_global_feed_health_async()
                    logger.info("[GLOBAL_FEED_HEALTH] Feed health check completed")
                except Exception as e:
                    logger.error(f"[GLOBAL_FEED_HEALTH] Error executing feed health check: {e}")

                self._global_feed_health_next_run = now + timedelta(hours=interval_hours)
                logger.info(f"[GLOBAL_FEED_HEALTH] Next run scheduled for: {self._global_feed_health_next_run}")
            else:
                time_until = self._global_feed_health_next_run - now
                logger.debug(f"[GLOBAL_FEED_HEALTH] Next run in {time_until.total_seconds() // 60:.0f} minutes")
        except Exception as e:
            logger.error(f"[GLOBAL_FEED_HEALTH] Error in feed health scheduler: {e}")

    async def _run_database_cleanup(self):
        """Run database cleanup task.

        Replaces the original database_cleanup @tasks.loop.
        """
        try:
            from agent_db import get_server_id, get_db_for_server
            from discord_bot.discord_utils import get_server_key

            active_server_key = (get_server_id() or "").strip()
            target_guild = None
            if active_server_key:
                active_key_lower = active_server_key.lower()
                for g in self.bot.guilds:
                    if str(getattr(g, "id", "")) == active_server_key:
                        target_guild = g
                        break
                    if getattr(g, "name", "").lower() == active_key_lower:
                        target_guild = g
                        break
            if target_guild is None and self.bot.guilds:
                target_guild = self.bot.guilds[0]
            if target_guild is None:
                return

            db_instance = get_db_for_server(target_guild)
            rows = await asyncio.to_thread(db_instance.clean_old_interactions, 30)
            server_key = get_server_key(target_guild)
            logger.info(f"🧹 Cleanup in {target_guild.name} ({server_key}): {rows} records deleted.")
        except Exception as e:
            logger.error(f"Error in database cleanup: {e}")

    async def _run_banker_task(self):
        """Run banker global task across all servers.

        Replaces run.py::launch_role for banker. Calls roles.banker.banker.banker_task()
        which iterates server directories, creates wallets, initializes the dice game pot,
        and distributes daily TAE.
        """
        if not self.bot.is_ready():
            return

        try:
            from roles.banker.banker import banker_task
            await banker_task()
            logger.info("[BANKER_SCHEDULER] banker_task completed successfully")
        except Exception as e:
            logger.error(f"[BANKER_SCHEDULER] Error executing banker_task: {e}", exc_info=True)

    async def _run_recent_memory_summary(self):
        """Run recent memory summary for all servers.

        Replaces run.py::execute_recent_memory_summary_all_servers.
        """
        if not self.bot.is_ready():
            return

        try:
            from agent_engine import refresh_due_recent_memories
            refreshed = await asyncio.to_thread(refresh_due_recent_memories)
            if refreshed:
                logger.info(f"[MEMORY_SCHEDULER] Recent memory refresh: {refreshed} server(s) updated")
        except Exception as e:
            logger.error(f"[MEMORY_SCHEDULER] Error in recent memory refresh: {e}", exc_info=True)

    async def _run_relationship_memory_refresh(self):
        """Run relationship memory refresh for all servers.

        Replaces run.py::execute_relationship_memory_refresh_all_servers.
        """
        if not self.bot.is_ready():
            return

        try:
            from agent_engine import refresh_due_relationship_memories
            refreshed = await asyncio.to_thread(refresh_due_relationship_memories)
            if refreshed:
                logger.info(f"[MEMORY_SCHEDULER] Relationship memory refresh: {refreshed} user relationship(s) updated")
        except Exception as e:
            logger.error(f"[MEMORY_SCHEDULER] Error in relationship memory refresh: {e}", exc_info=True)

    def get_status(self) -> dict:
        """Get scheduler status."""
        return self.scheduler.status()


# Global instance
_discord_scheduler_instance: Optional[DiscordScheduler] = None


def get_discord_scheduler(
    bot_instance=None,
    agent_config: Optional[dict] = None,
    external_scheduler: Optional[JobScheduler] = None,
) -> DiscordScheduler:
    """Get or create the global DiscordScheduler instance.

    When `external_scheduler` is provided on first call, the DiscordScheduler
    will register its jobs on that shared JobScheduler instead of creating
    its own. This is how the production runtime consolidates everything on
    `RunSupervisor.job_scheduler`.
    """
    global _discord_scheduler_instance
    if _discord_scheduler_instance is None:
        if bot_instance is None or agent_config is None:
            raise ValueError("bot_instance and agent_config required for first initialization")
        _discord_scheduler_instance = DiscordScheduler(
            bot_instance, agent_config, external_scheduler=external_scheduler
        )
    return _discord_scheduler_instance
