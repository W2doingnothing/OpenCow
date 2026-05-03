"""Base channel interface for chat platforms."""

from abc import ABC, abstractmethod

from opencow.bus.events import InboundMessage, OutboundMessage
from opencow.bus.queue import MessageBus


class BaseChannel(ABC):
    """Abstract base class for chat channel implementations."""

    name: str = "base"
    display_name: str = "Base"

    def __init__(self, bus: MessageBus, **kwargs) -> None:
        self.bus = bus
        self._running = False

    @abstractmethod
    async def listen(self) -> None:
        """Start listening for incoming messages."""
        ...

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message to the chat platform."""
        ...

    async def stop(self) -> None:
        """Stop the channel."""
        self._running = False
