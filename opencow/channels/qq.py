"""QQ channel using official botpy SDK.

Supports:
- C2C (private) messages via on_c2c_message_create
- Group @mentions via on_group_at_message_create
- Plain text and markdown output
- Auto-reconnect on disconnect

Requires: pip install qq-botpy
"""

from __future__ import annotations

import asyncio
import importlib.util
from collections import deque
from typing import Any

from loguru import logger

from opencow.bus.events import InboundMessage, OutboundMessage
from opencow.bus.queue import MessageBus
from opencow.channels.base import BaseChannel

QQ_AVAILABLE = importlib.util.find_spec("botpy") is not None


def _make_bot_class(channel: QQChannel) -> type:
    """Create a botpy Client subclass bound to the given channel."""
    import botpy

    intents = botpy.Intents(public_messages=True, direct_message=True)

    class _Bot(botpy.Client):
        def __init__(self) -> None:
            super().__init__(intents=intents, ext_handlers=False)

        async def on_ready(self) -> None:
            logger.info("QQ bot ready: {}", self.robot.name if hasattr(self, "robot") else "?")

        async def on_c2c_message_create(self, message: Any) -> None:
            await channel._on_message(message, is_group=False)

        async def on_group_at_message_create(self, message: Any) -> None:
            await channel._on_message(message, is_group=True)

        async def on_direct_message_create(self, message: Any) -> None:
            await channel._on_message(message, is_group=False)

    return _Bot


class QQChannel(BaseChannel):
    """QQ channel using official botpy SDK.

    Config fields:
        app_id: QQ bot App ID
        secret: QQ bot App Secret
        allow_from: Optional list of user IDs to restrict access
        msg_format: "plain" or "markdown"
        ack_message: Optional text to send as immediate acknowledgment
    """

    name = "qq"
    display_name = "QQ"

    def __init__(self, bus: MessageBus, **kwargs) -> None:
        super().__init__(bus)
        self._app_id: str = str(kwargs.get("app_id", ""))
        self._secret: str = str(kwargs.get("secret", ""))
        self._allow_from: list[str] = kwargs.get("allow_from", []) or []
        self._msg_format: str = str(kwargs.get("msg_format", "plain"))
        self._ack_message: str = str(kwargs.get("ack_message", ""))
        self._client: Any = None
        self._processed_ids: deque[str] = deque(maxlen=1000)
        self._msg_seq: int = 1
        self._chat_type_cache: dict[str, str] = {}

    async def listen(self) -> None:
        """Start the QQ bot with auto-reconnect."""
        if not QQ_AVAILABLE:
            logger.error("QQ SDK not installed. Run: pip install qq-botpy")
            return
        if not self._app_id or not self._secret:
            logger.error("QQ: app_id and secret not configured")
            return

        import botpy

        self._running = True
        self._client = _make_bot_class(self)()

        logger.info("QQ: connecting to bot platform...")
        while self._running:
            try:
                await self._client.start(appid=self._app_id, secret=self._secret)
                logger.info("QQ: client.start() returned normally")
            except Exception as e:
                logger.exception("QQ bot connection error: {}", e)
            if self._running:
                logger.info("QQ: reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _on_message(self, data: Any, is_group: bool = False) -> None:
        """Handle an incoming QQ message."""
        try:
            msg_id = getattr(data, "id", "") or ""
            if msg_id in self._processed_ids:
                return
            self._processed_ids.append(msg_id)

            content = (getattr(data, "content", "") or "").strip()
            if not content:
                return

            # Extract sender + chat identifiers
            if is_group:
                chat_id = getattr(data, "group_openid", "")
                user_id = getattr(data.author, "member_openid", "unknown") if hasattr(data, "author") else "unknown"
                self._chat_type_cache[chat_id] = "group"
            else:
                user_id = str(getattr(data.author, "id", None)
                              or getattr(data.author, "user_openid", "unknown"))
                chat_id = user_id
                self._chat_type_cache[chat_id] = "c2c"

            # Permission check
            if self._allow_from and "*" not in self._allow_from and user_id not in self._allow_from:
                logger.debug("QQ: blocked message from {}", user_id)
                return

            logger.debug("QQ inbound ({}): {} from {}", "group" if is_group else "c2c", content[:60], user_id)

            # Optional ack
            if self._ack_message:
                try:
                    await self._send_text(chat_id, self._ack_message, is_group, msg_id)
                except Exception:
                    pass

            msg = InboundMessage(
                text=content,
                channel=self.name,
                chat_id=chat_id,
                message_id=msg_id,
                sender_id=user_id,
            )
            await self.bus.publish_inbound(msg)

        except Exception:
            logger.exception("QQ: message handling error for id={}", getattr(data, "id", "?"))

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message to QQ."""
        if not self._client:
            logger.warning("QQ client not initialized")
            return

        chat_type = self._chat_type_cache.get(msg.chat_id, "c2c")
        is_group = chat_type == "group"
        message_id = msg.metadata.get("message_id") if msg.metadata else None

        if msg.content and msg.content.strip():
            await self._send_text(msg.chat_id, msg.content.strip(), is_group, message_id)

    async def _send_text(
        self,
        chat_id: str,
        content: str,
        is_group: bool,
        msg_id: str | None = None,
    ) -> None:
        """Send a plain text or markdown message via botpy API."""
        if not self._client:
            return

        self._msg_seq += 1
        use_markdown = self._msg_format == "markdown"

        payload: dict[str, Any] = {
            "msg_type": 2 if use_markdown else 0,
            "msg_id": msg_id,
            "msg_seq": self._msg_seq,
        }
        if use_markdown:
            payload["markdown"] = {"content": content}
        else:
            payload["content"] = content

        if is_group:
            await self._client.api.post_group_message(group_openid=chat_id, **payload)
        else:
            await self._client.api.post_c2c_message(openid=chat_id, **payload)

    async def stop(self) -> None:
        self._running = False
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
        self._client = None
        logger.info("QQ bot stopped")
