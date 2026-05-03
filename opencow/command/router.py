"""Minimal command router for slash commands."""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from opencow.bus.events import InboundMessage, OutboundMessage

Handler = Callable[["CommandContext"], Awaitable["OutboundMessage | None"]]


@dataclass
class CommandContext:
    """Everything a command handler needs."""
    msg: InboundMessage
    raw: str
    args: str = ""
    loop: Any = None


class CommandRouter:
    """Dispatch slash commands by exact match or prefix match."""

    def __init__(self) -> None:
        self._exact: dict[str, Handler] = {}
        self._prefix: list[tuple[str, Handler]] = []

    def exact(self, cmd: str, handler: Handler) -> None:
        self._exact[cmd] = handler

    def prefix(self, pfx: str, handler: Handler) -> None:
        self._prefix.append((pfx, handler))
        self._prefix.sort(key=lambda p: len(p[0]), reverse=True)

    def is_command(self, text: str) -> bool:
        """Check if text is a slash command."""
        return text.strip().startswith("/")

    async def dispatch(self, ctx: CommandContext) -> OutboundMessage | None:
        """Dispatch to the matching handler."""
        cmd = ctx.raw.strip().lower()
        handler = self._exact.get(cmd)
        if handler:
            return await handler(ctx)
        for pfx, handler in self._prefix:
            if cmd.startswith(pfx):
                return await handler(ctx)
        return None
