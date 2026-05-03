"""CLI interactive chat channel using stdin/stdout."""

import asyncio
import sys
from typing import Any

from loguru import logger

from opencow.bus.events import InboundMessage, OutboundMessage
from opencow.bus.queue import MessageBus
from opencow.channels.base import BaseChannel


class CliChannel(BaseChannel):
    """Interactive command-line chat channel."""

    name = "cli"
    display_name = "CLI"

    def __init__(
        self,
        bus: MessageBus,
        *,
        on_stream: Any = None,
        **kwargs,
    ) -> None:
        super().__init__(bus)
        self._on_stream = on_stream
        self._running = False

    async def listen(self) -> None:
        """Read from stdin in a loop, publish to inbound bus."""
        self._running = True
        loop = asyncio.get_event_loop()

        while self._running:
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
            except (EOFError, KeyboardInterrupt):
                break

            if not line:
                break

            text = line.strip()
            if not text:
                continue

            msg = InboundMessage(
                text=text,
                channel=self.name,
                chat_id="cli-default",
                sender_name="user",
            )
            await self.bus.publish_inbound(msg)

    async def send(self, msg: OutboundMessage) -> None:
        """Print output to stdout."""
        content = msg.content
        print(f"\n{content}\n")

    async def send_stream(self, delta: str) -> None:
        """Print a stream delta to stdout without newline."""
        sys.stdout.write(delta)
        sys.stdout.flush()

    async def stop(self) -> None:
        self._running = False
