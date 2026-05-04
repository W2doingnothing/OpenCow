"""QQ channel using napcat / LLOneBot reverse WebSocket protocol.

Connects to a QQ bot client (napcat, LLOneBot, etc.) via WebSocket.
The bot client forwards QQ messages as JSON events; opencow sends
responses back via HTTP API.

Requires a running QQ bot client:
- napcat: https://github.com/NapNeko/NapCatQQ
- LLOneBot: https://github.com/LLOneBot/LLOneBot
"""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from typing import Any

import aiohttp
from loguru import logger

from opencow.bus.events import InboundMessage, OutboundMessage
from opencow.bus.queue import MessageBus
from opencow.channels.base import BaseChannel


def _extract_text(data: dict) -> str:
    """Extract plain text from a QQ message."""
    raw = data.get("raw_message", "") or data.get("message", "")
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        parts = []
        for seg in raw:
            if isinstance(seg, dict):
                seg_type = seg.get("type", "")
                seg_data = seg.get("data", {})
                if seg_type == "text":
                    parts.append(seg_data.get("text", ""))
                elif seg_type == "image":
                    parts.append("[image]")
                elif seg_type == "at":
                    parts.append(f"@{seg_data.get('qq', '?')}")
                else:
                    parts.append(f"[{seg_type}]")
        return " ".join(parts).strip()
    return ""


class QQChannel(BaseChannel):
    """QQ channel using napcat/LLOneBot reverse WebSocket + HTTP API.

    Config fields:
        ws_url: WebSocket URL of the bot client (e.g. ws://localhost:3001)
        http_url: HTTP API base URL (e.g. http://localhost:3000)
        access_token: Optional access token for authentication
        allow_from: Optional list of user IDs to restrict access
        ack_message: Optional text to send as immediate acknowledgment
    """

    name = "qq"
    display_name = "QQ"

    def __init__(self, bus: MessageBus, **kwargs) -> None:
        super().__init__(bus)
        self._ws_url: str = str(kwargs.get("ws_url", "ws://localhost:3001"))
        self._http_url: str = str(kwargs.get("http_url", "http://localhost:3000"))
        self._access_token: str = str(kwargs.get("access_token", ""))
        self._allow_from: list[str] = kwargs.get("allow_from", []) or []
        self._ack_message: str = str(kwargs.get("ack_message", ""))
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._processed_ids: OrderedDict[str, None] = OrderedDict()

    async def listen(self) -> None:
        """Connect to QQ bot WebSocket and process events."""
        self._running = True
        headers = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        self._session = aiohttp.ClientSession()

        while self._running:
            try:
                async with self._session.ws_connect(self._ws_url, headers=headers) as ws:
                    self._ws = ws
                    logger.info("QQ: connected to {}", self._ws_url)

                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(raw.data)
                            await self._handle_event(data)
                        except json.JSONDecodeError:
                            continue
                        except Exception:
                            logger.exception("QQ: event handling error")

            except aiohttp.ClientError as e:
                logger.warning("QQ: connection lost ({}) retrying in 5s...", e)
            except Exception:
                logger.exception("QQ: unexpected error, retrying in 5s...")

            if self._running:
                await asyncio.sleep(5)

        if self._session:
            await self._session.close()

    async def _handle_event(self, data: dict) -> None:
        """Process a QQ event."""
        post_type = data.get("post_type", "")

        if post_type == "message":
            await self._handle_message(data)
        elif post_type == "meta_event":
            logger.debug("QQ meta: {}", data.get("meta_event_type", ""))
        elif post_type == "notice":
            logger.debug("QQ notice: {}", data.get("notice_type", ""))

    async def _handle_message(self, data: dict) -> None:
        msg_type = data.get("message_type", "private")
        message_id = str(data.get("message_id", ""))

        # Dedup
        if message_id in self._processed_ids:
            return
        self._processed_ids[message_id] = None
        while len(self._processed_ids) > 500:
            self._processed_ids.popitem(last=False)

        sender_id = str(data.get("sender", {}).get("user_id", "unknown"))

        # Permission check
        if self._allow_from and sender_id not in self._allow_from:
            logger.debug("QQ: blocked message from {}", sender_id)
            return

        # For groups, check @mention
        if msg_type == "group":
            group_id = str(data.get("group_id", ""))
            chat_id = f"group_{group_id}"
            # Only process if bot was @mentioned
            raw = data.get("raw_message", "") or data.get("message", "")
            is_at_bot = False
            if isinstance(raw, list):
                for seg in raw:
                    if isinstance(seg, dict) and seg.get("type") == "at":
                        is_at_bot = True
                        break
            else:
                is_at_bot = True  # Plain text in group = likely @mention
            if not is_at_bot:
                return
        elif msg_type == "private":
            chat_id = f"user_{sender_id}"
        else:
            return

        text = _extract_text(data)
        if not text:
            return

        logger.debug("QQ inbound: {} from {}", text[:60], sender_id)

        msg = InboundMessage(
            text=text,
            channel=self.name,
            chat_id=chat_id,
            message_id=message_id,
            sender_id=sender_id,
        )
        await self.bus.publish_inbound(msg)

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message to QQ via HTTP API."""
        if not self._session:
            return

        chat_id = msg.chat_id
        if chat_id.startswith("group_"):
            group_id = chat_id[6:]
            endpoint = f"{self._http_url}/send_group_msg"
            payload = {"group_id": int(group_id), "message": msg.content}
        else:
            user_id = chat_id.replace("user_", "")
            endpoint = f"{self._http_url}/send_private_msg"
            payload = {"user_id": int(user_id), "message": msg.content}

        headers = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            async with self._session.post(
                endpoint, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    logger.warning("QQ: send failed (HTTP {})", resp.status)
        except aiohttp.ClientError:
            raise  # Let ChannelManager retry
        except Exception:
            logger.exception("QQ: send error")

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
