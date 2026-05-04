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
        # Optional access control list (empty = allow all)
        self._allow_from: list[str] = kwargs.get("allow_from", []) or []

    def is_allowed(self, sender_id: str) -> bool:
        """Check if a sender is allowed to interact with this channel."""
        if not self._allow_from:
            return True
        return sender_id in self._allow_from

    @abstractmethod
    async def listen(self) -> None:
        """Start listening for incoming messages."""
        ...

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message to the chat platform."""
        ...

    async def send_delta(self, msg_id: str, delta: str) -> None:
        """Send a streaming delta (optional, override in subclasses)."""
        pass

    async def stop(self) -> None:
        """Stop the channel."""
        self._running = False
