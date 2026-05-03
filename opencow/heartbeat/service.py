"""Heartbeat service -- periodic LLM-driven wake-up to check for tasks."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine

from loguru import logger


class HeartbeatService:
    """Periodic heartbeat that wakes the agent to check for pending tasks.

    Two-phase flow:
      1. Decision: reads HEARTBEAT.md, asks LLM whether there are active tasks.
      2. Execution: only triggered when Phase 1 returns "run".
    """

    def __init__(
        self,
        workspace: Path,
        chat_model: Any,
        model: str,
        on_execute: Callable[[str], Coroutine[Any, Any, str]] | None = None,
        on_notify: Callable[[str], Coroutine[Any, Any, None]] | None = None,
        interval_s: int = 30 * 60,
        enabled: bool = True,
        timezone: str | None = None,
    ) -> None:
        self.workspace = workspace
        self.chat_model = chat_model
        self.model = model
        self.on_execute = on_execute
        self.on_notify = on_notify
        self.interval_s = interval_s
        self.enabled = enabled
        self.timezone = timezone
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def heartbeat_file(self) -> Path:
        return self.workspace / "HEARTBEAT.md"

    def _read_file(self) -> str | None:
        if self.heartbeat_file.exists():
            content = self.heartbeat_file.read_text(encoding="utf-8").strip()
            if content:
                return content
        return None

    async def check(self) -> tuple[str, str | None]:
        """Phase 1: ask the LLM whether there are tasks to run.

        Returns ("skip" | "run", tasks_summary | None).
        """
        tasks_text = self._read_file()
        if not tasks_text:
            return "skip", None

        from langchain_core.messages import HumanMessage

        prompt = (
            "You are a task-checking agent. Below is a list of potential tasks "
            "described in a HEARTBEAT.md file. Review them and decide if any "
            "of them are active and need attention RIGHT NOW.\n\n"
            f"Tasks:\n{tasks_text}\n\n"
            "Reply with exactly one word on the first line: RUN if there are "
            "active tasks to execute, or SKIP if there is nothing to do. "
            "If RUN, include a one-line summary of the tasks on the second line."
        )

        try:
            response = await self.chat_model.ainvoke([HumanMessage(content=prompt)])
            content = (getattr(response, "content", "") or "").strip()
            lines = content.split("\n")
            decision = lines[0].upper().strip() if lines else "SKIP"
            summary = lines[1].strip() if len(lines) > 1 else None

            if "RUN" in decision:
                return "run", summary or "Active tasks found"
            return "skip", None
        except Exception:
            logger.exception("Heartbeat decision check failed")
            return "skip", None

    async def start(self) -> None:
        """Start the heartbeat loop."""
        if not self.enabled:
            logger.info("Heartbeat disabled")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Heartbeat started (interval {}s)", self.interval_s)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.interval_s)
                decision, summary = await self.check()

                if decision == "run" and self.on_execute:
                    logger.info("Heartbeat: executing task -- {}", summary)
                    result = await self.on_execute(summary or "Execute pending tasks")
                    if result and self.on_notify:
                        await self.on_notify(result)
                else:
                    logger.debug("Heartbeat: nothing to do")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Heartbeat loop error")
