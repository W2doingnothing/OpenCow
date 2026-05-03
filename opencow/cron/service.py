"""Cron service for scheduling agent tasks."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine

from filelock import FileLock
from loguru import logger

from opencow.cron.types import CronJob, CronRunRecord, CronSchedule, CronStore


def _now_ms() -> int:
    return int(time.time() * 1000)


def _compute_next_run(schedule: CronSchedule, now_ms: int) -> int | None:
    """Compute the next run time for a schedule."""
    if schedule.kind == "at":
        return schedule.at_ms if schedule.at_ms and schedule.at_ms > now_ms else None

    if schedule.kind == "every":
        if not schedule.every_ms or schedule.every_ms <= 0:
            return None
        return now_ms + schedule.every_ms

    if schedule.kind == "cron" and schedule.expr:
        try:
            from zoneinfo import ZoneInfo
            from croniter import croniter

            tz = ZoneInfo(schedule.tz) if schedule.tz else datetime.now().astimezone().tzinfo
            base_dt = datetime.fromtimestamp(now_ms / 1000, tz=tz)
            cron = croniter(schedule.expr, base_dt)
            next_dt = cron.get_next(datetime)
            return int(next_dt.timestamp() * 1000)
        except Exception:
            return None

    return None


class CronService:
    """Manages and executes scheduled cron jobs."""

    _MAX_RUN_HISTORY = 20

    def __init__(
        self,
        store_path: Path,
        on_job: Callable[[CronJob], Coroutine[Any, Any, str | None]] | None = None,
        max_sleep_ms: int = 300_000,  # 5 minutes
    ) -> None:
        self.store_path = store_path
        self._action_path = store_path.parent / "action.jsonl"
        self._lock = FileLock(str(store_path.parent / "cron.lock"))
        self.on_job = on_job
        self.max_sleep_ms = max_sleep_ms
        self._store: CronStore | None = None
        self._running = False
        self._wake_event = asyncio.Event()

    # -- public API -----------------------------------------------------------

    async def add_job(self, prompt: str, schedule: CronSchedule) -> CronJob:
        """Add a new cron job."""
        job = CronJob(
            id=uuid.uuid4().hex[:12],
            schedule=schedule,
            prompt=prompt,
            created_at=_now_ms(),
        )
        job.next_run_at = _compute_next_run(schedule, _now_ms())
        self._ensure_store()
        self._store.jobs[job.id] = job
        self._save()
        self._wake_event.set()
        logger.info("Cron job added: {} ({})", job.id, prompt[:50])
        return job

    def list_jobs(self) -> list[CronJob]:
        self._ensure_store()
        return list(self._store.jobs.values())

    def remove_job(self, job_id: str) -> bool:
        self._ensure_store()
        if job_id in self._store.jobs:
            del self._store.jobs[job_id]
            self._save()
            return True
        return False

    async def start(self) -> None:
        """Start the cron loop."""
        self._running = True
        self._ensure_store()
        logger.info("Cron service started ({} jobs)", len(self._store.jobs))
        await self._loop()

    async def stop(self) -> None:
        """Stop the cron loop."""
        self._running = False
        self._wake_event.set()

    # -- internal -------------------------------------------------------------

    def _ensure_store(self) -> None:
        if self._store is not None:
            return
        if self.store_path.exists():
            try:
                raw = json.loads(self.store_path.read_text(encoding="utf-8"))
                jobs = {
                    k: CronJob(**v) if isinstance(v, dict) else v
                    for k, v in raw.get("jobs", {}).items()
                }
                history = [
                    CronRunRecord(**h) if isinstance(h, dict) else h
                    for h in raw.get("run_history", [])
                ]
                self._store = CronStore(jobs=jobs, run_history=history)
                return
            except Exception:
                logger.exception("Failed to load cron store, starting fresh")
        self._store = CronStore()

    def _save(self) -> None:
        if self._store is None:
            return
        raw = {
            "jobs": {
                k: {
                    "id": v.id,
                    "schedule": {
                        "kind": v.schedule.kind,
                        "at_ms": v.schedule.at_ms,
                        "every_ms": v.schedule.every_ms,
                        "expr": v.schedule.expr,
                        "tz": v.schedule.tz,
                    },
                    "prompt": v.prompt,
                    "state": v.state,
                    "created_at": v.created_at,
                    "last_run_at": v.last_run_at,
                    "next_run_at": v.next_run_at,
                }
                for k, v in self._store.jobs.items()
            },
            "run_history": [
                {"job_id": h.job_id, "run_at": h.run_at, "result": h.result, "error": h.error}
                for h in self._store.run_history[-self._MAX_RUN_HISTORY:]
            ],
        }
        self.store_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False))

    async def _loop(self) -> None:
        while self._running:
            now = _now_ms()
            next_time = None

            for job in list(self._store.jobs.values()):
                if job.state != "active":
                    continue
                if job.next_run_at and job.next_run_at <= now:
                    await self._execute(job)
                    job.last_run_at = now
                    job.next_run_at = _compute_next_run(job.schedule, now)
                    self._save()

                if job.next_run_at and (next_time is None or job.next_run_at < next_time):
                    next_time = job.next_run_at

            # Sleep until next job or max_sleep_ms
            if next_time:
                sleep_ms = min(next_time - _now_ms(), self.max_sleep_ms)
                sleep_ms = max(sleep_ms, 0) / 1000.0
            else:
                sleep_ms = self.max_sleep_ms / 1000.0

            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=sleep_ms)
                self._wake_event.clear()
            except asyncio.TimeoutError:
                pass

    async def _execute(self, job: CronJob) -> None:
        if self.on_job is None:
            return
        try:
            result = await self.on_job(job)
            self._store.run_history.append(CronRunRecord(
                job_id=job.id, run_at=_now_ms(), result=result,
            ))
        except Exception as e:
            logger.exception("Cron job {} failed", job.id)
            self._store.run_history.append(CronRunRecord(
                job_id=job.id, run_at=_now_ms(), error=str(e),
            ))
        # Trim history
        if len(self._store.run_history) > self._MAX_RUN_HISTORY:
            self._store.run_history = self._store.run_history[-self._MAX_RUN_HISTORY:]
