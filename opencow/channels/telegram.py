"""Telegram channel using python-telegram-bot with long polling."""

from __future__ import annotations

import asyncio
import importlib.util
from typing import Any

from loguru import logger

from opencow.bus.events import InboundMessage, OutboundMessage
from opencow.bus.queue import MessageBus
from opencow.channels.base import BaseChannel

TG_AVAILABLE = importlib.util.find_spec("telegram") is not None


class TelegramChannel(BaseChannel):
    """Telegram channel using long polling (no webhook needed).

    Config fields:
        token: Bot token from @BotFather
        allow_from: Optional list of user IDs to restrict access
        group_policy: "mention" (only respond to @mentions) or "open"
    """

    name = "telegram"
    display_name = "Telegram"

    def __init__(self, bus: MessageBus, **kwargs) -> None:
        super().__init__(bus)
        self._token: str = str(kwargs.get("token", ""))
        self._allow_from: list[str] = kwargs.get("allow_from", []) or []
        self._group_policy: str = str(kwargs.get("group_policy", "mention"))
        self._react_emoji: str = str(kwargs.get("react_emoji", "👀"))
        self._app: Any = None

    async def listen(self) -> None:
        """Start the Telegram bot with long polling."""
        if not TG_AVAILABLE:
            logger.error("Telegram SDK not installed. Run: pip install python-telegram-bot")
            return
        if not self._token:
            logger.error("Telegram: token not configured")
            return

        from telegram.ext import Application, MessageHandler, filters

        self._running = True

        # Build app with long polling
        self._app = (
            Application.builder()
            .token(self._token)
            .connect_timeout(30.0)
            .read_timeout(30.0)
            .build()
        )

        # Register message handler
        self._app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._on_telegram_message,
            )
        )

        # Start polling
        await self._app.initialize()
        await self._app.start()
        logger.info("Telegram: polling started (group_policy={})", self._group_policy)

        await self._app.updater.start_polling(drop_pending_updates=True)

        # Keep alive
        while self._running:
            await asyncio.sleep(1)

    async def _on_telegram_message(self, update: Any, context: Any) -> None:
        """Handle an incoming Telegram message."""
        try:
            logger.debug("Telegram raw update: {}", update.to_dict() if hasattr(update, 'to_dict') else update)
            message = update.message or update.edited_message
            if not message:
                logger.debug("Telegram: no message in update")
                return
            if not message.text:
                logger.debug("Telegram: message has no text (type={})", getattr(message, 'type', '?'))
                return

            chat = message.chat
            user = message.from_user
            chat_id = str(chat.id)
            user_id = str(user.id) if user else "unknown"
            text = message.text.strip()
            is_group = chat.type in ("group", "supergroup")
            logger.info("Telegram inbound: chat_id={} user_id={} text={}", chat_id, user_id, text[:60])

            # Permission check
            if self._allow_from and user_id not in self._allow_from:
                return

            # Group mention check
            if is_group and self._group_policy == "mention":
                bot_username = self._app.bot.username.lower()
                mentioned = f"@{bot_username}" in text.lower()
                if not mentioned:
                    return

            logger.debug("Telegram inbound ({}): {} from {}", "group" if is_group else "private", text[:60], user_id)

            # Add reaction emoji to show "seen" (best-effort, non-blocking)
            await self._add_reaction(chat_id, message.message_id, self._react_emoji)

            msg = InboundMessage(
                text=text,
                channel=self.name,
                chat_id=chat_id,
                message_id=str(message.message_id),
                sender_id=user_id,
            )
            await self.bus.publish_inbound(msg)

        except Exception:
            logger.exception("Telegram: message handling error")

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message to Telegram."""
        if not self._app or not self._app.bot:
            logger.warning("Telegram: send called but bot not ready")
            return
        try:
            chat_id = int(msg.chat_id)
            logger.info("Telegram: sending to chat_id={} text_len={}", chat_id, len(msg.content))
            await self._app.bot.send_message(
                chat_id=chat_id,
                text=msg.content,
            )
        except Exception:
            logger.exception("Telegram: send failed")

    async def _add_reaction(self, chat_id: str, message_id: int, emoji: str) -> None:
        """Add emoji reaction to a message (best-effort, non-blocking)."""
        if not self._app or not emoji:
            return
        try:
            await self._app.bot.set_message_reaction(
                chat_id=int(chat_id),
                message_id=message_id,
                reaction=[{"type": "emoji", "emoji": emoji}],
            )
        except Exception:
            pass

    async def stop(self) -> None:
        self._running = False
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception:
                pass
        logger.info("Telegram: stopped")
