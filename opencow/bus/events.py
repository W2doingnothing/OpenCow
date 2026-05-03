"""Async message types for the bus."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InboundMessage:
    """A message coming in from a channel."""
    text: str
    channel: str
    chat_id: str
    message_id: str | None = None
    sender_id: str | None = None
    sender_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    media_urls: list[str] = field(default_factory=list)

    @property
    def session_key(self) -> str:
        return f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """A message going out to a channel."""
    content: str
    channel: str
    chat_id: str
    reply_to: str | None = None
    session_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
