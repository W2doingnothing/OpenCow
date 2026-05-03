"""Subagent manager — stub for Phase 3."""

from dataclasses import dataclass, field


@dataclass
class SubagentStatus:
    task_id: str
    label: str


class SubagentManager:
    """Placeholder — raises NotImplementedError until Phase 3."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def spawn(self, description: str) -> str:
        raise NotImplementedError("Subagent system not yet implemented (Phase 3)")

    async def list(self) -> list[SubagentStatus]:
        return []

    async def cancel(self, task_id: str) -> None:
        raise NotImplementedError("Subagent system not yet implemented (Phase 3)")
