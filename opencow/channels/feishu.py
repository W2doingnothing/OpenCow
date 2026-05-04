"""Feishu/Lark channel using lark-oapi SDK with WebSocket long connection."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import threading
from collections import OrderedDict
from typing import Any

from loguru import logger

from opencow.bus.events import InboundMessage, OutboundMessage
from opencow.bus.queue import MessageBus
from opencow.channels.base import BaseChannel

FEISHU_AVAILABLE = importlib.util.find_spec("lark_oapi") is not None

MSG_TYPE_MAP = {
    "image": "[image]",
    "audio": "[audio]",
    "file": "[file]",
    "sticker": "[sticker]",
}


def _parse_feishu_content(content_str: str, msg_type: str) -> str:
    """Parse Feishu message content JSON into plain text."""
    if msg_type == "text":
        try:
            content = json.loads(content_str)
            return content.get("text", "")
        except (json.JSONDecodeError, TypeError):
            return content_str

    if msg_type in MSG_TYPE_MAP:
        return MSG_TYPE_MAP[msg_type]

    # Try to extract text from other message types
    try:
        content = json.loads(content_str)
        if isinstance(content, dict):
            text = content.get("text", "") or content.get("title", "")
            if text:
                return text
    except (json.JSONDecodeError, TypeError):
        pass

    return f"[{msg_type}]"


class FeishuChannel(BaseChannel):
    """Feishu/Lark channel using WebSocket long connection.

    Requires:
    - App ID and App Secret from Feishu Open Platform
    - Bot capability enabled with im:message permission
    - Event subscription: im.message.receive_v1

    Install: pip install lark-oapi
    """

    name = "feishu"
    display_name = "Feishu"

    def __init__(self, bus: MessageBus, **kwargs) -> None:
        super().__init__(bus)
        self._app_id: str = kwargs.get("app_id", "")
        self._app_secret: str = kwargs.get("app_secret", "")
        self._domain: str = kwargs.get("domain", "feishu")  # "feishu" or "lark"
        self._client: Any = None
        self._ws_client: Any = None
        self._ws_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._processed_ids: OrderedDict[str, None] = OrderedDict()

    async def listen(self) -> None:
        """Start the Feishu WebSocket connection."""
        if not FEISHU_AVAILABLE:
            logger.error("Feishu SDK not installed. Run: pip install lark-oapi")
            return

        if not self._app_id or not self._app_secret:
            logger.error("Feishu: app_id and app_secret not configured")
            return

        import lark_oapi as lark
        from lark_oapi.core.const import FEISHU_DOMAIN, LARK_DOMAIN

        self._running = True
        self._loop = asyncio.get_running_loop()

        # Create client for sending messages
        domain = LARK_DOMAIN if self._domain == "lark" else FEISHU_DOMAIN
        self._client = (
            lark.Client.builder()
            .app_id(self._app_id)
            .app_secret(self._app_secret)
            .domain(domain)
            .build()
        )

        # Register event handler and start WebSocket
        def _on_event(event_data: Any) -> None:
            self._on_event_sync(event_data)

        event_handler = (
            lark.ws.Client.builder()
            .app_id(self._app_id)
            .app_secret(self._app_secret)
            .domain(domain)
            .event_handler("im.message.receive_v1", _on_event)
            .build()
        )

        self._ws_client = event_handler

        def _ws_loop() -> None:
            event_handler.start()

        self._ws_thread = threading.Thread(target=_ws_loop, daemon=True)
        self._ws_thread.start()
        logger.info("Feishu: WebSocket started")

        # Keep the listen coroutine alive
        while self._running:
            await asyncio.sleep(1)

    def _on_event_sync(self, data: Any) -> None:
        """Sync handler called from WebSocket thread."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._on_event(data), self._loop)

    async def _on_event(self, data: Any) -> None:
        """Handle an incoming message event from Feishu."""
        try:
            event = data.event
            message = event.message
            sender = event.sender

            # Dedup
            msg_id = message.message_id
            if msg_id in self._processed_ids:
                return
            self._processed_ids[msg_id] = None
            while len(self._processed_ids) > 500:
                self._processed_ids.popitem(last=False)

            # Skip bot messages
            if sender.sender_type == "bot":
                return

            sender_id = sender.sender_id.open_id if sender.sender_id else "unknown"
            chat_id = message.chat_id
            chat_type = message.chat_type
            msg_type = message.message_type

            # For group messages, only respond when @mentioned
            if chat_type == "group":
                mentions = getattr(message, "mentions", []) or []
                if not any(m.name == self.display_name for m in mentions):
                    return

            text = _parse_feishu_content(message.content, msg_type)
            if not text.strip():
                return

            logger.debug("Feishu inbound: {} from {}", text[:60], sender_id)

            msg = InboundMessage(
                text=text,
                channel=self.name,
                chat_id=chat_id,
                message_id=msg_id,
                sender_id=sender_id,
            )
            await self.bus.publish_inbound(msg)

        except Exception:
            logger.exception("Feishu: event handling error")

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message to Feishu."""
        if not self._client:
            return

        import lark_oapi as lark
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        try:
            content = json.dumps({"text": msg.content})
            body = CreateMessageRequestBody(
                receive_id=msg.chat_id,
                msg_type="text",
                content=content,
            )
            req = CreateMessageRequest(
                receive_id_type="chat_id",
                request_body=body,
            )
            self._client.im.v1.message.create(req)
        except Exception:
            logger.exception("Feishu: send failed")

    async def stop(self) -> None:
        self._running = False
        if self._ws_client:
            try:
                self._ws_client.stop()
            except Exception:
                pass
