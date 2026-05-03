"""Cron management tools -- add, list, remove scheduled tasks."""

from langchain_core.tools import tool
from pydantic import BaseModel, Field


# Global reference set by OpenCow.__init__
_cron_service = None


def set_cron_service(service) -> None:
    global _cron_service
    _cron_service = service


class AddCronInput(BaseModel):
    prompt: str = Field(description="What to tell the agent when the timer fires")
    every_seconds: int = Field(
        default=0,
        description="Repeat interval in seconds. Use ONLY for repeating tasks.",
    )
    every_minutes: int = Field(
        default=0,
        description="Repeat interval in minutes. Use ONLY for repeating tasks.",
    )
    every_hours: int = Field(
        default=0,
        description="Repeat interval in hours. Use ONLY for repeating tasks.",
    )
    at_datetime: str = Field(
        default="",
        description=(
            "ISO datetime for a ONE-SHOT task (e.g. '2026-05-03T21:01:00'). "
            "Use this INSTEAD of every_* for a once-off reminder. "
            "IMPORTANT: always use the CURRENT YEAR (2026) and local timezone (Asia/Shanghai)."
        ),
    )


class ListCronInput(BaseModel):
    pass


class RemoveCronInput(BaseModel):
    job_id: str = Field(description="The job ID to remove (use list_cron to find IDs)")


@tool(args_schema=AddCronInput)
async def add_cron(
    prompt: str,
    every_seconds: int = 0,
    every_minutes: int = 0,
    every_hours: int = 0,
    at_datetime: str = "",
) -> str:
    """Add a scheduled task. When the time comes, the agent will execute the prompt
    and the result will be delivered to you.

    For ONE-TIME reminders (e.g. "remind me at 3pm"), use at_datetime with an ISO
    timestamp like '2026-05-03T15:00:00' (use Asia/Shanghai timezone).

    For REPEATING tasks (e.g. "check every 5 minutes"), use every_* parameters.
    """
    if _cron_service is None:
        return "Error: cron service not available"

    from datetime import datetime
    from opencow.cron.types import CronSchedule

    if at_datetime:
        # One-shot: parse the ISO datetime
        try:
            dt = datetime.fromisoformat(at_datetime)
            at_ms = int(dt.timestamp() * 1000)
            now_ms = int(datetime.now().timestamp() * 1000)
            if at_ms <= now_ms:
                return f"Error: at_datetime '{at_datetime}' is in the past (now is {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')})"
            schedule = CronSchedule(kind="at", at_ms=at_ms)
            job = await _cron_service.add_job(prompt, schedule)
            return f"One-shot job created: id={job.id} at {at_datetime}"
        except ValueError as e:
            return f"Error parsing at_datetime '{at_datetime}': {e}. Use ISO format like '2026-05-03T21:01:00'"

    # Repeating: interval-based
    total_ms = (every_seconds + every_minutes * 60 + every_hours * 3600) * 1000
    if total_ms <= 0:
        return "Error: must specify at_datetime for one-shot, or every_seconds/every_minutes/every_hours for repeating"

    schedule = CronSchedule(kind="every", every_ms=total_ms)
    job = await _cron_service.add_job(prompt, schedule)
    return f"Repeating job created: id={job.id} every {total_ms // 1000}s prompt='{prompt}'"


@tool(args_schema=ListCronInput)
def list_cron() -> str:
    """List all active scheduled cron jobs."""
    if _cron_service is None:
        return "Error: cron service not available"

    jobs = _cron_service.list_jobs()
    if not jobs:
        return "No active cron jobs."
    lines = []
    for j in jobs:
        next_run = ""
        if j.next_run_at:
            import datetime
            dt = datetime.datetime.fromtimestamp(j.next_run_at / 1000)
            next_run = f" next at {dt.strftime('%H:%M:%S')}"
        schedule_type = j.schedule.kind
        lines.append(f"  {j.id} ({schedule_type}): {j.prompt[:60]}{next_run}")
    return "\n".join(["Active cron jobs:"] + lines)


@tool(args_schema=RemoveCronInput)
def remove_cron(job_id: str) -> str:
    """Remove a scheduled cron job by its ID."""
    if _cron_service is None:
        return "Error: cron service not available"

    if _cron_service.remove_job(job_id):
        return f"Cron job {job_id} removed."
    return f"Job {job_id} not found."
