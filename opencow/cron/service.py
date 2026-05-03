"""Cron service for scheduling agent tasks — _arm_timer precision scheduling."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine, Literal

from filelock import FileLock
from loguru import logger

from opencow.cron.types import (
    CronJob,
    CronJobState,
    CronPayload,
    CronRunRecord,
    CronSchedule,
    CronStore,
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _compute_next_run(schedule: CronSchedule, now_ms: int) -> int | None:
    """Compute next run time in ms."""
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


def _validate_schedule(schedule: CronSchedule) -> None:
    if schedule.tz and schedule.kind != "cron":
        raise ValueError("tz can only be used with cron schedules")
    if schedule.kind == "cron" and schedule.tz:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(schedule.tz)
        except Exception:
            raise ValueError(f"unknown timezone '{schedule.tz}'") from None


class CronService:
    """Manages and executes scheduled cron jobs with precise _arm_timer scheduling."""

    _MAX_RUN_HISTORY = 20

    def __init__(
        self,
        store_path: Path,
        on_job: Callable[[CronJob], Coroutine[Any, Any, str | None]] | None = None,
        max_sleep_ms: int = 60_000,  # 1 minute fallback
    ) -> None:
        self.store_path = store_path
        self._action_path = store_path.parent / "action.jsonl"
        self._lock = FileLock(str(store_path.parent / "cron.lock"))
        self.on_job = on_job
        self.max_sleep_ms = max_sleep_ms
        self._store: CronStore | None = None
        self._timer_task: asyncio.Task | None = None
        self._running = False
        self._timer_active = False

    # -- persistent store ----------------------------------------------------

    def _load_store(self) -> CronStore:
        if self._timer_active and self._store:
            return self._store

        jobs: list[CronJob] = []
        version = 1
        if self.store_path.exists():
            try:
                data = json.loads(self.store_path.read_text(encoding="utf-8", errors="replace"))
                version = data.get("version", 1)
                for j in data.get("jobs", []):
                    jobs.append(CronJob.from_dict(j))
            except Exception:
                logger.exception("Failed to load cron store, starting fresh")

        self._store = CronStore(version=version, jobs=jobs)
        self._merge_action()
        return self._store

    def _save_store(self) -> None:
        if not self._store:
            return
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": self._store.version,
            "jobs": [
                {
                    "id": j.id,
                    "name": j.name,
                    "enabled": j.enabled,
                    "schedule": {
                        "kind": j.schedule.kind,
                        "at_ms": j.schedule.at_ms,
                        "every_ms": j.schedule.every_ms,
                        "expr": j.schedule.expr,
                        "tz": j.schedule.tz,
                    },
                    "payload": {
                        "kind": j.payload.kind,
                        "message": j.payload.message,
                        "deliver": j.payload.deliver,
                        "channel": j.payload.channel,
                        "to": j.payload.to,
                        "channel_meta": j.payload.channel_meta,
                        "session_key": j.payload.session_key,
                    },
                    "state": {
                        "next_run_at_ms": j.state.next_run_at_ms,
                        "last_run_at_ms": j.state.last_run_at_ms,
                        "last_status": j.state.last_status,
                        "last_error": j.state.last_error,
                        "run_history": [
                            {"run_at_ms": r.run_at_ms, "status": r.status,
                             "duration_ms": r.duration_ms, "error": r.error}
                            for r in j.state.run_history[-self._MAX_RUN_HISTORY:]
                        ],
                    },
                    "created_at_ms": j.created_at_ms,
                    "updated_at_ms": j.updated_at_ms,
                    "delete_after_run": j.delete_after_run,
                }
                for j in self._store.jobs
            ],
        }
        try:
            self.store_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Failed to save cron store")

    def _merge_action(self) -> None:
        if not self._action_path.exists():
            return
        jobs_map = {j.id: j for j in self._store.jobs}

        with self._lock:
            lines = self._action_path.read_text(encoding="utf-8", errors="replace").strip().split("\n")
            changed = False
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    action = json.loads(line)
                    act = action.get("action")
                    params = action.get("params", {})
                    if act == "del":
                        jobs_map.pop(params.get("job_id"), None)
                    elif act in ("add", "update"):
                        j = CronJob.from_dict(params)
                        jobs_map[j.id] = j
                    changed = True
                except Exception:
                    pass

            self._store.jobs = list(jobs_map.values())
            if self._running and changed:
                self._action_path.write_text("", encoding="utf-8")
                self._save_store()

    def _append_action(self, action: Literal["add", "del", "update"], params: dict) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with open(self._action_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"action": action, "params": params}, ensure_ascii=False) + "\n")

    # -- timer scheduling ----------------------------------------------------

    def _recompute_next_runs(self) -> None:
        if not self._store:
            return
        now = _now_ms()
        for job in self._store.jobs:
            if job.enabled:
                job.state.next_run_at_ms = _compute_next_run(job.schedule, now)

    def _get_next_wake_ms(self) -> int | None:
        if not self._store:
            return None
        times = [
            j.state.next_run_at_ms for j in self._store.jobs
            if j.enabled and j.state.next_run_at_ms
        ]
        return min(times) if times else None

    def _arm_timer(self) -> None:
        """Re-arm the timer for the next due job.

        Safe to call from both async and sync contexts. When called from a
        sync context (e.g. LangChain tool executing in a thread pool), the
        timer is NOT re-armed -- the main cron loop will pick up the change
        on its next wake (within max_sleep_ms).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Sync context -- skip, the main loop will handle it
            return

        if self._timer_task:
            self._timer_task.cancel()

        if not self._running:
            return

        next_wake = self._get_next_wake_ms()
        if next_wake is None:
            delay_ms = self.max_sleep_ms
        else:
            delay_ms = min(self.max_sleep_ms, max(0, next_wake - _now_ms()))
        delay_s = delay_ms / 1000

        async def _tick() -> None:
            await asyncio.sleep(delay_s)
            if self._running:
                await self._on_timer()

        self._timer_task = loop.create_task(_tick())

    async def _on_timer(self) -> None:
        self._load_store()
        if not self._store:
            self._arm_timer()
            return

        self._timer_active = True
        try:
            now = _now_ms()
            due_jobs = [
                j for j in self._store.jobs
                if j.enabled and j.state.next_run_at_ms and now >= j.state.next_run_at_ms
            ]
            for job in due_jobs:
                await self._execute_job(job)
            self._save_store()
        finally:
            self._timer_active = False
        self._arm_timer()

    async def _execute_job(self, job: CronJob) -> None:
        start_ms = _now_ms()
        logger.info("Cron: executing job '{}' ({})", job.name, job.id)

        try:
            if self.on_job:
                await self.on_job(job)
            job.state.last_status = "ok"
            job.state.last_error = None
        except Exception as e:
            job.state.last_status = "error"
            job.state.last_error = str(e)
            logger.error("Cron: job '{}' failed: {}", job.name, e)

        end_ms = _now_ms()
        job.state.last_run_at_ms = start_ms
        job.updated_at_ms = end_ms

        job.state.run_history.append(CronRunRecord(
            run_at_ms=start_ms,
            status=job.state.last_status,
            duration_ms=end_ms - start_ms,
            error=job.state.last_error,
        ))
        job.state.run_history = job.state.run_history[-self._MAX_RUN_HISTORY:]

        # Handle post-execution state
        if job.schedule.kind == "at":
            # One-shot: disable after running
            if job.delete_after_run:
                self._store.jobs = [j for j in self._store.jobs if j.id != job.id]
            else:
                job.enabled = False
                job.state.next_run_at_ms = None
        else:
            # Repeating: compute next run
            job.state.next_run_at_ms = _compute_next_run(job.schedule, _now_ms())

    # -- public API ----------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        self._load_store()
        self._recompute_next_runs()
        self._save_store()
        self._arm_timer()
        logger.info("Cron service started with {} jobs", len(self._store.jobs if self._store else []))

    async def stop(self) -> None:
        self._running = False
        if self._timer_task:
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
            self._timer_task = None

    def list_jobs(self, include_disabled: bool = False) -> list[CronJob]:
        store = self._load_store()
        jobs = store.jobs if include_disabled else [j for j in store.jobs if j.enabled]
        return sorted(jobs, key=lambda j: j.state.next_run_at_ms or float("inf"))

    def add_job(
        self,
        name: str,
        schedule: CronSchedule,
        message: str,
        *,
        deliver: bool = True,
        channel: str | None = None,
        to: str | None = None,
        delete_after_run: bool = False,
        channel_meta: dict | None = None,
        session_key: str | None = None,
    ) -> CronJob:
        _validate_schedule(schedule)
        now = _now_ms()

        job = CronJob(
            id=str(uuid.uuid4())[:8],
            name=name,
            enabled=True,
            schedule=schedule,
            payload=CronPayload(
                kind="agent_turn",
                message=message,
                deliver=deliver,
                channel=channel,
                to=to,
                channel_meta=channel_meta or {},
                session_key=session_key,
            ),
            state=CronJobState(next_run_at_ms=_compute_next_run(schedule, now)),
            created_at_ms=now,
            updated_at_ms=now,
            delete_after_run=delete_after_run,
        )

        if self._running:
            store = self._load_store()
            store.jobs.append(job)
            self._save_store()
            self._arm_timer()  # Re-arm immediately for precise timing
        else:
            self._append_action("add", {
                "id": job.id, "name": job.name, "enabled": job.enabled,
                "schedule": {"kind": schedule.kind, "at_ms": schedule.at_ms,
                             "every_ms": schedule.every_ms, "expr": schedule.expr, "tz": schedule.tz},
                "payload": {"kind": "agent_turn", "message": message, "deliver": deliver,
                            "channel": channel, "to": to, "channel_meta": channel_meta or {},
                            "session_key": session_key},
                "state": {"next_run_at_ms": job.state.next_run_at_ms},
                "created_at_ms": now, "updated_at_ms": now,
                "delete_after_run": delete_after_run,
            })

        logger.info("Cron: added job '{}' ({})", name, job.id)
        return job

    def remove_job(self, job_id: str) -> Literal["removed", "not_found"]:
        store = self._load_store()
        before = len(store.jobs)
        store.jobs = [j for j in store.jobs if j.id != job_id]
        if len(store.jobs) < before:
            if self._running:
                self._save_store()
                self._arm_timer()
            else:
                self._append_action("del", {"job_id": job_id})
            logger.info("Cron: removed job {}", job_id)
            return "removed"
        return "not_found"

    def get_job(self, job_id: str) -> CronJob | None:
        store = self._load_store()
        return next((j for j in store.jobs if j.id == job_id), None)
