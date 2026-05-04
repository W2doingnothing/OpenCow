"""Cron management tools — schedule reminders and recurring tasks."""

from contextvars import ContextVar
from datetime import datetime

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from opencow.cron.service import CronService
from opencow.cron.types import CronSchedule

# Global reference + context set by OpenCow
_cron_service: CronService | None = None
_channel: ContextVar[str] = ContextVar("cron_channel", default="")
_chat_id: ContextVar[str] = ContextVar("cron_chat_id", default="")
_session_key: ContextVar[str] = ContextVar("cron_session_key", default="")
_metadata: ContextVar[dict] = ContextVar("cron_metadata", default={})
_in_cron_context: ContextVar[bool] = ContextVar("cron_in_context", default=False)


def set_cron_service(service: CronService) -> None:
    global _cron_service
    _cron_service = service


def set_context(channel: str, chat_id: str, session_key: str = "", metadata: dict | None = None) -> None:
    _channel.set(channel)
    _chat_id.set(chat_id)
    _session_key.set(session_key or f"{channel}:{chat_id}")
    _metadata.set(metadata or {})


def enter_cron_context() -> object:
    """Mark that we're inside a cron callback. Returns a token for reset."""
    return _in_cron_context.set(True)


def leave_cron_context(token: object) -> None:
    _in_cron_context.reset(token)


class AddCronInput(BaseModel):
    action: str = Field(default="add", description="Must be 'add'")
    message: str = Field(description="Instruction for the agent when the job triggers (e.g. reminder text)")
    name: str = Field(default="", description="Optional short label (e.g. 'daily-standup'). Defaults to first 30 chars of message")
    every_seconds: int = Field(default=0, description="Interval in seconds for repeating tasks")
    every_minutes: int = Field(default=0, description="Interval in minutes for repeating tasks")
    every_hours: int = Field(default=0, description="Interval in hours for repeating tasks")
    cron_expr: str = Field(default="", description="Cron expression like '0 9 * * *' for scheduled tasks")
    at: str = Field(default="", description="ISO datetime for ONE-SHOT execution (e.g. '2026-05-03T21:01:00'). Naive times use Asia/Shanghai.")
    deliver: bool = Field(default=True, description="Whether to deliver result to user (default true)")
    tz: str = Field(default="", description="IANA timezone for cron expressions (e.g. 'Asia/Shanghai')")


class ListCronInput(BaseModel):
    action: str = Field(default="list", description="Must be 'list'")


class RemoveCronInput(BaseModel):
    action: str = Field(default="remove", description="Must be 'remove'")
    job_id: str = Field(description="Job ID to remove (use list to find IDs)")


@tool(args_schema=AddCronInput)
async def add_cron(
    action: str = "add",
    message: str = "",
    name: str = "",
    every_seconds: int = 0,
    every_minutes: int = 0,
    every_hours: int = 0,
    cron_expr: str = "",
    at: str = "",
    deliver: bool = True,
    tz: str = "",
) -> str:
    """Schedule a reminder or recurring task. Once created, do NOT remove it
    unless the user explicitly asks you to. If the user asks to modify or
    replace a job, you must first ask for confirmation before removing any
    existing job.

    For ONE-TIME reminders (e.g. "remind me at 3pm"), use the 'at' parameter
    with an ISO datetime like '2026-05-03T15:00:00'.

    For REPEATING tasks, use every_seconds / every_minutes / every_hours.

    Use 'cron_expr' for complex schedules like '0 9 * * 1-5' (weekdays at 9am).
    """
    if _cron_service is None:
        return "Error: cron service not available"

    if _in_cron_context.get():
        return (
            "Error: cannot create new cron jobs from within a cron job execution. "
            "Just respond with the current time or the message the user asked for. "
            "Do NOT call add_cron again."
        )

    if not message.strip():
        return "Error: 'message' is required (what should the agent do when the job triggers?)"

    channel = _channel.get()
    chat_id = _chat_id.get()
    if not channel or not chat_id:
        return "Error: no session context available"

    # Build schedule
    delete_after = False
    schedule: CronSchedule

    total_ms = (every_seconds + every_minutes * 60 + every_hours * 3600) * 1000

    if at:
        try:
            dt = datetime.fromisoformat(at)
        except ValueError:
            return f"Error: invalid ISO datetime '{at}'. Use format '2026-05-03T21:01:00'"
        if dt.tzinfo is None:
            from zoneinfo import ZoneInfo
            tz_name = tz or "Asia/Shanghai"
            try:
                dt = dt.replace(tzinfo=ZoneInfo(tz_name))
            except Exception:
                return f"Error: unknown timezone '{tz_name}'"
        at_ms = int(dt.timestamp() * 1000)
        now_ms = int(datetime.now().timestamp() * 1000)
        if at_ms <= now_ms:
            return f"Error: 'at' time '{at}' is in the past"
        schedule = CronSchedule(kind="at", at_ms=at_ms)
        delete_after = True
    elif cron_expr:
        effective_tz = tz or "Asia/Shanghai"
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(effective_tz)
        except Exception:
            return f"Error: unknown timezone '{effective_tz}'"
        schedule = CronSchedule(kind="cron", expr=cron_expr, tz=effective_tz)
    elif total_ms > 0:
        schedule = CronSchedule(kind="every", every_ms=total_ms)
    else:
        return "Error: specify 'at' (one-shot), 'every_seconds/minutes/hours' (repeating), or 'cron_expr' (cron schedule)"

    job_name = name or message[:30]
    job = _cron_service.add_job(
        name=job_name,
        schedule=schedule,
        message=message,
        deliver=deliver,
        channel=channel,
        to=chat_id,
        delete_after_run=delete_after,
        channel_meta=_metadata.get(),
        session_key=_session_key.get() or None,
    )

    if schedule.kind == "at":
        return f"One-shot job created: '{job.name}' (id: {job.id}) at {at}"
    elif schedule.kind == "cron":
        return f"Cron job created: '{job.name}' (id: {job.id}) schedule: {cron_expr}"
    else:
        secs = total_ms // 1000
        return f"Repeating job created: '{job.name}' (id: {job.id}) every {secs}s"


@tool(args_schema=ListCronInput)
def list_cron(action: str = "list") -> str:
    """List all active scheduled cron jobs."""
    if _cron_service is None:
        return "Error: cron service not available"

    jobs = _cron_service.list_jobs()
    if not jobs:
        return "No scheduled jobs."

    lines = []
    for j in jobs:
        kind = j.schedule.kind
        if kind == "at":
            dt = datetime.fromtimestamp((j.schedule.at_ms or 0) / 1000)
            timing = f"at {dt.strftime('%Y-%m-%d %H:%M:%S')}"
        elif kind == "cron":
            timing = f"cron: {j.schedule.expr}"
        elif j.schedule.every_ms:
            ms = j.schedule.every_ms
            if ms % 3600000 == 0:
                timing = f"every {ms // 3600000}h"
            elif ms % 60000 == 0:
                timing = f"every {ms // 60000}m"
            else:
                timing = f"every {ms // 1000}s"
        else:
            timing = kind

        next_run = ""
        if j.state.next_run_at_ms:
            dt = datetime.fromtimestamp(j.state.next_run_at_ms / 1000)
            next_run = f" next at {dt.strftime('%H:%M:%S')}"

        lines.append(f"  {j.id} ({timing}): {j.name}{next_run}")

    return "\n".join(["Scheduled jobs:"] + lines)


@tool(args_schema=RemoveCronInput)
async def remove_cron(action: str = "remove", job_id: str = "") -> str:
    """Remove a scheduled cron job by its ID. Do NOT call this unless the
    user has explicitly confirmed they want to remove the job. Always ask
    for confirmation first."""
    if _cron_service is None:
        return "Error: cron service not available"

    if not job_id:
        return "Error: job_id is required"

    result = _cron_service.remove_job(job_id)
    if result == "removed":
        return f"Removed job {job_id}"
    return f"Job {job_id} not found"
