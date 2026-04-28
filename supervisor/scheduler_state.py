"""Scheduler state persistence.

Persists JobScheduler state (next_run times, job status) to avoid double-trigger
after restarts. Uses JsonStore for atomic updates.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from persistence.json_store import JsonStore
from agent_logging import get_logger

logger = get_logger("scheduler_state")


class SchedulerState:
    """Persists and restores JobScheduler state."""

    def __init__(self, state_path: Optional[Path] = None):
        if state_path is None:
            state_path = Path(__file__).parent.parent.parent / "databases" / "scheduler_state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            state_path = Path(state_path)

        self._store = JsonStore(
            state_path,
            default_factory=lambda: {"version": 1, "jobs": {}, "last_shutdown": None},
            keep_backup=True,
        )
        logger.info(f"🗄️ [SchedulerState] Initialized at {state_path}")

    def save_job_next_run(self, job_name: str, next_run_monotonic: float):
        """Save next run time for a job."""
        self._store.set(f"jobs.{job_name}.next_run", next_run_monotonic)
        self._store.set(f"jobs.{job_name}.updated_at", datetime.now().isoformat())

    def get_job_next_run(self, job_name: str) -> Optional[float]:
        """Get next run time for a job."""
        return self._store.get(f"jobs.{job_name}.next_run")

    def save_job_status(self, job_name: str, status: str):
        """Save job status."""
        self._store.set(f"jobs.{job_name}.status", status)

    def get_job_status(self, job_name: str) -> Optional[str]:
        """Get job status."""
        return self._store.get(f"jobs.{job_name}.status")

    def save_last_shutdown(self):
        """Record last shutdown time."""
        self._store.set("last_shutdown", datetime.now().isoformat())

    def get_last_shutdown(self) -> Optional[str]:
        """Get last shutdown time."""
        return self._store.get("last_shutdown")

    def get_all_jobs_state(self) -> Dict:
        """Get state for all jobs."""
        return self._store.get("jobs") or {}

    def clear_job_state(self, job_name: str):
        """Clear state for a specific job."""
        self._store.update(lambda data: data["jobs"].pop(job_name, None))


# Global instance
_scheduler_state_instance: Optional[SchedulerState] = None


def get_scheduler_state(state_path: Optional[Path] = None) -> SchedulerState:
    """Get or create the global SchedulerState instance."""
    global _scheduler_state_instance
    if _scheduler_state_instance is None:
        _scheduler_state_instance = SchedulerState(state_path)
    return _scheduler_state_instance
