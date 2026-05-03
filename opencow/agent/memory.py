"""Memory system: file I/O store, Consolidator, and AutoCompact."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from opencow.utils.helpers import ensure_dir, estimate_message_tokens, truncate_text


# ---------------------------------------------------------------------------
# MemoryStore -- pure file I/O
# ---------------------------------------------------------------------------

class MemoryStore:
    """Pure file I/O for memory files: MEMORY.md, history.jsonl, SOUL.md, USER.md."""

    _DEFAULT_MAX_HISTORY = 1000
    _MAX_RECENT_HISTORY = 50
    _MAX_HISTORY_CHARS = 32_000

    def __init__(self, workspace: Path, max_history_entries: int = _DEFAULT_MAX_HISTORY):
        self.workspace = workspace
        self.max_history_entries = max_history_entries
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "history.jsonl"
        self.soul_file = workspace / "SOUL.md"
        self.user_file = workspace / "USER.md"
        self._cursor_file = self.memory_dir / ".cursor"
        self._dream_cursor_file = self.memory_dir / ".dream_cursor"

    # -- read helpers --------------------------------------------------------

    def read_file(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def get_memory_context(self) -> str:
        """Return MEMORY.md content for injection into the system prompt."""
        return self.read_file(self.memory_file)

    def read_memory(self) -> str:
        return self.get_memory_context()

    # -- history -------------------------------------------------------------

    def append_history(self, content: str) -> None:
        """Record a history entry."""
        record = {"timestamp": datetime.now().isoformat(), "content": content}
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._trim_history()

    def read_unprocessed_history(self, since_cursor: int = 0) -> list[dict[str, Any]]:
        """Read history entries from a given cursor position."""
        entries = self._read_all_history()
        return entries[since_cursor:]

    def get_last_dream_cursor(self) -> int:
        """Return the last dream cursor (position in history already processed)."""
        try:
            return int(self._dream_cursor_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def set_dream_cursor(self, pos: int) -> None:
        self._dream_cursor_file.write_text(str(pos))

    def get_recent_history_text(self) -> str:
        """Return the most recent history entries as formatted text for prompts."""
        entries = self._read_all_history()
        capped = entries[-self._MAX_RECENT_HISTORY:]
        text = "\n".join(
            f"- [{e.get('timestamp', '')}] {e.get('content', '')}"
            for e in capped
        )
        return truncate_text(text, self._MAX_HISTORY_CHARS)

    # -- cursors -------------------------------------------------------------

    def get_cursor(self) -> int:
        try:
            return int(self._cursor_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def set_cursor(self, pos: int) -> None:
        self._cursor_file.write_text(str(pos))

    # -- internal ------------------------------------------------------------

    def _read_all_history(self) -> list[dict[str, Any]]:
        if not self.history_file.exists():
            return []
        try:
            raw = self.history_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # File corrupted (e.g. mixed GBK/UTF-8 bytes) -- delete and start fresh
            logger.warning("history.jsonl corrupted, resetting")
            self.history_file.unlink(missing_ok=True)
            return []
        entries = []
        for line in raw.strip().split("\n"):
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries

    def _trim_history(self) -> None:
        """Keep only the most recent N entries."""
        try:
            entries = self._read_all_history()
            if len(entries) > self.max_history_entries:
                trimmed = entries[-self.max_history_entries:]
                self.history_file.write_text(
                    "\n".join(json.dumps(e, ensure_ascii=False) for e in trimmed) + "\n",
                    encoding="utf-8",
                )
        except Exception:
            logger.exception("Failed to trim history")


# ---------------------------------------------------------------------------
# Consolidator -- LLM-driven conversation compression
# ---------------------------------------------------------------------------

class Consolidator:
    """Use a lightweight LLM call to compress conversation history into a summary."""

    def __init__(self, chat_model: Any) -> None:
        self.chat_model = chat_model

    async def consolidate(
        self,
        messages: list[dict[str, Any]],
        consolidation_ratio: float = 0.5,
    ) -> str:
        """Compress a list of messages into a structured summary.

        Args:
            messages: The messages to compress.
            consolidation_ratio: Target compression ratio (0.5 = 50% of original tokens).
        """
        if not messages:
            return ""

        # Build a transcript
        transcript_parts = []
        for m in messages:
            role = m.get("role", "?")
            content = m.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    b.get("text", "") if isinstance(b, dict) else str(b)
                    for b in content
                )
            if content and isinstance(content, str):
                transcript_parts.append(f"[{role}]: {content[:500]}")

        transcript = "\n".join(transcript_parts)
        if not transcript.strip():
            return ""

        prompt = (
            "Summarize the following conversation into a concise structured summary. "
            "Focus on: key decisions made, important facts learned, actions taken, "
            "and any user preferences or context that should be remembered. "
            "Keep the summary under 500 words.\n\n"
            f"Conversation:\n{transcript}"
        )

        try:
            from langchain_core.messages import HumanMessage
            response = await self.chat_model.ainvoke([HumanMessage(content=prompt)])
            return getattr(response, "content", "") or ""
        except Exception:
            logger.exception("Consolidation failed")
            return ""


# ---------------------------------------------------------------------------
# AutoCompact -- proactive idle-session compression
# ---------------------------------------------------------------------------

class AutoCompact:
    """Detect idle sessions and compress them to reduce token cost and latency."""

    _RECENT_SUFFIX_MESSAGES = 8

    def __init__(
        self,
        consolidator: Consolidator,
        session_ttl_minutes: int = 0,
    ) -> None:
        self.consolidator = consolidator
        self._ttl = session_ttl_minutes

    def is_expired(self, updated_at: datetime | str | None, now: datetime | None = None) -> bool:
        if self._ttl <= 0 or not updated_at:
            return False
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        return ((now or datetime.now()) - updated_at).total_seconds() >= self._ttl * 60

    async def archive(
        self,
        session_messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Archive old messages, return (kept_messages, summary)."""
        if len(session_messages) <= self._RECENT_SUFFIX_MESSAGES:
            return session_messages, None

        to_archive = session_messages[:-self._RECENT_SUFFIX_MESSAGES]
        kept = session_messages[-self._RECENT_SUFFIX_MESSAGES:]

        summary = await self.consolidator.consolidate(to_archive)
        return kept, summary
