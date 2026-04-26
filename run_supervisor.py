"""Supervisor integration for run.py.

Provides a bridge between the existing run.py scheduler and the new Supervisor/JobScheduler
infrastructure. This allows gradual migration without breaking existing functionality.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from supervisor import Supervisor, JobScheduler, Schedule, RestartPolicy, RestartType
from agent_logging import get_logger

logger = get_logger("run_supervisor")


class RunSupervisor:
    """Bridges existing run.py scheduler with Supervisor infrastructure.

    This wrapper allows the existing run.py to continue working while gradually
    migrating to the new Supervisor/JobScheduler pattern.
    """

    def __init__(self):
        self.supervisor = Supervisor(logger=logger)
        self.job_scheduler = JobScheduler(tick_seconds=60.0, logger=logger)
        self._running = False

    async def start(self):
        """Start both supervisor and job scheduler."""
        if self._running:
            logger.warning("[RunSupervisor] Already running")
            return

        self._running = True
        logger.info("[RunSupervisor] Starting supervisor and job scheduler")

        # Start job scheduler in background
        asyncio.create_task(self.job_scheduler.run_forever())

        logger.info("[RunSupervisor] Started successfully")

    async def stop(self):
        """Stop both supervisor and job scheduler."""
        if not self._running:
            return

        logger.info("[RunSupervisor] Stopping...")
        await self.job_scheduler.stop()
        await self.supervisor.shutdown()
        self._running = False
        logger.info("[RunSupervisor] Stopped")

    def register_periodic_job(
        self,
        name: str,
        func: Callable,
        interval_hours: float,
        timeout_seconds: Optional[float] = None,
    ):
        """Register a periodic job with JobScheduler.

        This replaces the existing run.py scheduler's role task registration.
        """
        schedule = Schedule.every(hours=interval_hours)
        self.job_scheduler.register(
            name,
            func,
            schedule,
            timeout_seconds=timeout_seconds,
        )
        logger.info(f"[RunSupervisor] Registered periodic job '{name}' every {interval_hours}h")

    def register_memory_jobs(self, config: dict):
        """Register memory maintenance jobs from run.py.

        These replace the _execute_optional_non_role_tasks in run.py.
        """
        # Daily memory summary (24 hours)
        from run import execute_daily_memory_summary_all_servers
        self.job_scheduler.register(
            "daily_memory_summary",
            execute_daily_memory_summary_all_servers,
            Schedule.every(hours=24),
            timeout_seconds=600,
        )

        # Weekly personality evolution (7 days)
        from run import execute_weekly_personality_evolution_all_servers
        self.job_scheduler.register(
            "weekly_personality_evolution",
            execute_weekly_personality_evolution_all_servers,
            Schedule.every(days=7),
            timeout_seconds=600,
        )

        # GDPR retention (configurable, default 24 hours)
        gdpr_cfg = config.get("gdpr", {}) or {}
        gdpr_hours = int(gdpr_cfg.get("run_every_hours", 24))
        from run import execute_gdpr_retention_all_servers
        self.job_scheduler.register(
            "gdpr_retention",
            execute_gdpr_retention_all_servers,
            Schedule.every(hours=gdpr_hours),
            timeout_seconds=300,
        )

        # Recent memory summary (every 4 hours)
        from run import execute_recent_memory_summary_all_servers
        self.job_scheduler.register(
            "recent_memory_summary",
            execute_recent_memory_summary_all_servers,
            Schedule.every(hours=4),
            timeout_seconds=300,
        )

        # Relationship memory refresh (every 1 hour)
        from run import execute_relationship_memory_refresh_all_servers
        self.job_scheduler.register(
            "relationship_memory_refresh",
            execute_relationship_memory_refresh_all_servers,
            Schedule.every(hours=1),
            timeout_seconds=300,
        )

        logger.info("[RunSupervisor] Registered 5 memory maintenance jobs")

    def register_persistent_actor(
        self,
        name: str,
        factory: Callable,
        restart_policy: Optional[RestartPolicy] = None,
    ):
        """Register a persistent actor with Supervisor.

        This replaces the existing _persistent_processes tracking for roles like MC.
        """
        if restart_policy is None:
            restart_policy = RestartPolicy(max_retries=3, backoff_seconds=30)

        self.supervisor.register_actor(
            name,
            factory,
            restart_policy=restart_policy,
        )
        logger.info(f"[RunSupervisor] Registered persistent actor '{name}'")

    def register_mc_actor(self, config: dict):
        """Register MC role as a persistent actor.

        MC (Music Controller) is a persistent role that needs to run continuously.
        """
        # Check if MC is enabled in config
        mc_config = config.get("roles", {}).get("mc", {})
        if not mc_config.get("enabled", False):
            logger.info("[RunSupervisor] MC role disabled in config, skipping actor registration")
            return

        # Create factory for MC actor
        async def mc_actor_factory():
            """Factory for MC actor."""
            try:
                # Import MC role
                from roles.mc.mc import run_mc_loop

                # Run MC loop (this should be a long-running coroutine)
                await run_mc_loop()
            except Exception as e:
                logger.error(f"[RunSupervisor] MC actor error: {e}")
                raise

        # Register MC as persistent actor with aggressive restart policy
        restart_policy = RestartPolicy(max_retries=5, backoff_seconds=10)
        self.register_persistent_actor("mc", mc_actor_factory, restart_policy)
        logger.info("[RunSupervisor] Registered MC actor (persistent)")

    async def trigger_job(self, name: str) -> bool:
        """Manually trigger a job."""
        try:
            await self.job_scheduler.trigger_now(name)
            logger.info(f"[RunSupervisor] Triggered job '{name}'")
            return True
        except Exception as e:
            logger.error(f"[RunSupervisor] Failed to trigger job '{name}': {e}")
            return False

    def get_status(self) -> dict:
        """Get combined status of supervisor and job scheduler."""
        return {
            "supervisor": self.supervisor.status(),
            "job_scheduler": self.job_scheduler.status(),
        }


# Global instance
_run_supervisor_instance: Optional[RunSupervisor] = None


def get_run_supervisor() -> RunSupervisor:
    """Get or create the global RunSupervisor instance."""
    global _run_supervisor_instance
    if _run_supervisor_instance is None:
        _run_supervisor_instance = RunSupervisor()
    return _run_supervisor_instance
