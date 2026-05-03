"""Cron type definitions."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class CronSchedule:
    """Schedule definition for a cron job."""
    kind: Literal["at", "every", "cron"]
    at_ms: int | None = None       # Unix ms timestamp for "at" kind
    every_ms: int | None = None    # Interval ms for "every" kind
    expr: str | None = None        # Cron expression for "cron" kind
    tz: str | None = None          # IANA timezone for "cron" kind


@dataclass
class CronPayload:
    """What to do when the job runs."""
    kind: Literal["system_event", "agent_turn"] = "agent_turn"
    message: str = ""
    deliver: bool = True           # Whether to deliver result to user
    channel: str | None = None     # e.g. "cli", "feishu"
    to: str | None = None          # e.g. chat_id
    channel_meta: dict = field(default_factory=dict)
    session_key: str | None = None


@dataclass
class CronRunRecord:
    """A single execution record."""
    run_at_ms: int
    status: Literal["ok", "error", "skipped"]
    duration_ms: int = 0
    error: str | None = None


@dataclass
class CronJobState:
    """Runtime state of a job."""
    next_run_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_status: Literal["ok", "error", "skipped"] | None = None
    last_error: str | None = None
    run_history: list[CronRunRecord] = field(default_factory=list)


@dataclass
class CronJob:
    """A scheduled job."""
    id: str
    name: str
    enabled: bool = True
    schedule: CronSchedule = field(default_factory=lambda: CronSchedule(kind="every"))
    payload: CronPayload = field(default_factory=CronPayload)
    state: CronJobState = field(default_factory=CronJobState)
    created_at_ms: int = 0
    updated_at_ms: int = 0
    delete_after_run: bool = False

    @classmethod
    def from_dict(cls, kwargs: dict) -> "CronJob":
        state_raw = dict(kwargs.get("state", {}))
        state_raw["run_history"] = [
            r if isinstance(r, CronRunRecord) else CronRunRecord(**r)
            for r in state_raw.get("run_history", [])
        ]
        return cls(
            id=kwargs["id"],
            name=kwargs["name"],
            enabled=kwargs.get("enabled", True),
            schedule=CronSchedule(**kwargs.get("schedule", {"kind": "every"})),
            payload=CronPayload(**kwargs.get("payload", {})),
            state=CronJobState(**state_raw),
            created_at_ms=kwargs.get("created_at_ms", 0),
            updated_at_ms=kwargs.get("updated_at_ms", 0),
            delete_after_run=kwargs.get("delete_after_run", False),
        )


@dataclass
class CronStore:
    """Persistent store for cron jobs."""
    version: int = 1
    jobs: list[CronJob] = field(default_factory=list)
