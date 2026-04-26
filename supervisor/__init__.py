"""Supervisor: actor + job scheduling layer for resilient process management.

Public API:
    Supervisor        - manages a set of Actors with restart policies
    Actor             - a long-lived supervised coroutine
    JobScheduler      - schedules recurring/one-shot jobs with timeout/retry
    Schedule          - schedule descriptor (every / at)
    RestartPolicy     - actor restart strategy
    RetryPolicy       - per-job retry strategy
    CircuitBreaker    - per-job circuit breaker
    Heartbeat         - liveness tracker
"""

from supervisor.policies import (
    BackoffStrategy,
    CircuitBreaker,
    CircuitBreakerOpen,
    RestartPolicy,
    RestartType,
    RetryPolicy,
)
from supervisor.heartbeat import Heartbeat, HeartbeatRegistry
from supervisor.scheduler import JobScheduler, Schedule, Job, JobStatus
from supervisor.supervisor import Actor, ActorState, Supervisor

__all__ = [
    "Supervisor",
    "Actor",
    "ActorState",
    "JobScheduler",
    "Schedule",
    "Job",
    "JobStatus",
    "RestartPolicy",
    "RestartType",
    "RetryPolicy",
    "CircuitBreaker",
    "CircuitBreakerOpen",
    "BackoffStrategy",
    "Heartbeat",
    "HeartbeatRegistry",
]
