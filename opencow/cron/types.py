"""Cron job type definitions."""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class CronSchedule:
    """Schedule definition for a cron job."""
    kind: Literal["at", "every", "cron"] = "every"
    at_ms: int | None = None       # Unix ms timestamp for "at" kind
    every_ms: int | None = None    # Interval ms for "every" kind
    expr: str | None = None        # Cron expression for "cron" kind
    tz: str | None = None          # IANA timezone for "cron" kind


@dataclass
class CronJob:
    """A scheduled job."""
    id: str
    schedule: CronSchedule
    prompt: str                    # What to tell the agent
    state: str = "active"          # active | paused | done
    created_at: float = 0.0        # Unix ms
    last_run_at: float | None = None
    next_run_at: float | None = None


@dataclass
class CronRunRecord:
    """Record of a cron job execution."""
    job_id: str
    run_at: float
    result: str | None = None      # Response text from the agent
    error: str | None = None


@dataclass
class CronStore:
    """Persisted state for the cron service."""
    jobs: dict[str, CronJob] = field(default_factory=dict)
    run_history: list[CronRunRecord] = field(default_factory=list)
