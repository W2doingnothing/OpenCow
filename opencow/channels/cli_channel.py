"""CLI interactive chat channel using stdin/stdout."""

import asyncio
import sys
import threading
from typing import Any

from loguru import logger

from opencow.bus.events import InboundMessage, OutboundMessage
from opencow.bus.queue import MessageBus
from opencow.channels.base import BaseChannel


class CliChannel(BaseChannel):
    """Interactive command-line chat channel.

    Uses a dedicated daemon thread for stdin reading to avoid
    Windows asyncio + sys.stdin.readline compatibility issues.
    """

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
        self._thread: threading.Thread | None = None

    async def listen(self) -> None:
        """Start a background thread that reads stdin and publishes to the bus."""
        self._running = True
        loop = asyncio.get_running_loop()

        def _read_stdin() -> None:
            while self._running:
                try:
                    line = sys.stdin.readline()
                except (EOFError, KeyboardInterrupt):
                    break

                if not line:
                    # EOF
                    break

                text = line.strip()
                if not text:
                    continue

                logger.debug("CLI inbound: {}", text[:60])

                msg = InboundMessage(
                    text=text,
                    channel=self.name,
                    chat_id="cli-default",
                    sender_name="user",
                )
                # Schedule publish on the event loop from this thread
                asyncio.run_coroutine_threadsafe(
                    self.bus.publish_inbound(msg), loop
                )

        self._thread = threading.Thread(target=_read_stdin, daemon=True)
        self._thread.start()

        # Sleep forever; the thread does the work.
        # We need to stay alive so the channel can be stopped.
        while self._running:
            await asyncio.sleep(0.5)

    async def send(self, msg: OutboundMessage) -> None:
        """Print output to stdout, safe against Windows encoding issues."""
        content = msg.content
        try:
            print(f"\n{content}\n", flush=True)
        except UnicodeEncodeError:
            safe = content.encode("gbk", errors="replace").decode("gbk")
            print(f"\n{safe}\n", flush=True)

    async def send_stream(self, delta: str) -> None:
        """Print a stream delta to stdout without newline."""
        sys.stdout.write(delta)
        sys.stdout.flush()

    async def stop(self) -> None:
        self._running = False
