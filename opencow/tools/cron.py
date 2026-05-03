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
    every_seconds: int = Field(default=0, description="Interval in seconds (e.g. 120 = 2 minutes)")
    every_minutes: int = Field(default=0, description="Interval in minutes (e.g. 5 = 5 minutes)")
    every_hours: int = Field(default=0, description="Interval in hours")


class ListCronInput(BaseModel):
    pass


class RemoveCronInput(BaseModel):
    job_id: str = Field(description="The job ID to remove (use list_cron to find IDs)")


@tool(args_schema=AddCronInput)
async def add_cron(prompt: str, every_seconds: int = 0, every_minutes: int = 0, every_hours: int = 0) -> str:
    """Add a scheduled task. The agent will execute the prompt when the timer fires
    and the result will be delivered to you. Use this to set reminders or periodic checks."""
    if _cron_service is None:
        return "Error: cron service not available"

    from opencow.cron.types import CronSchedule

    total_ms = (every_seconds + every_minutes * 60 + every_hours * 3600) * 1000
    if total_ms <= 0:
        return "Error: must specify at least one of every_seconds, every_minutes, every_hours"

    schedule = CronSchedule(kind="every", every_ms=total_ms)
    job = await _cron_service.add_job(prompt, schedule)
    return f"Cron job created: id={job.id} every {total_ms // 1000}s prompt='{prompt}'"


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
        lines.append(f"  {j.id}: {j.prompt[:60]}{next_run}")
    return "\n".join(["Active cron jobs:"] + lines)


@tool(args_schema=RemoveCronInput)
def remove_cron(job_id: str) -> str:
    """Remove a scheduled cron job by its ID."""
    if _cron_service is None:
        return "Error: cron service not available"

    if _cron_service.remove_job(job_id):
        return f"Cron job {job_id} removed."
    return f"Job {job_id} not found."
