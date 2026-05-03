"""Channel manager: starts, stops, and monitors all channels."""

import asyncio
from typing import Any

from loguru import logger

from opencow.bus.queue import MessageBus
from opencow.channels.base import BaseChannel


class ChannelManager:
    """Manages the lifecycle of all chat channels."""

    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus
        self._channels: list[BaseChannel] = []
        self._tasks: list[asyncio.Task] = []

    def register(self, channel: BaseChannel) -> None:
        self._channels.append(channel)

    async def start_all(self) -> None:
        for channel in self._channels:
            task = asyncio.create_task(self._run_channel(channel))
            self._tasks.append(task)
            logger.info("Started channel: {}", channel.display_name)

    async def stop_all(self) -> None:
        for channel in self._channels:
            await channel.stop()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("All channels stopped")

    async def _run_channel(self, channel: BaseChannel) -> None:
        try:
            await channel.listen()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Channel {} crashed", channel.display_name)
