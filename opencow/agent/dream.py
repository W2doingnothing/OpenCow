"""Dream -- two-phase memory consolidation during idle time."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from opencow.utils.helpers import current_time_str


class Dream:
    """Two-phase memory consolidation that extracts learnings from history.

    Phase 1: Read recent history + existing MEMORY.md, identify candidate memories.
    Phase 2: Update MEMORY.md via tool calls (uses the agent's edit_file tool).
    """

    def __init__(
        self,
        workspace: Path,
        chat_model: Any,
        memory_store: Any,
        timezone: str | None = None,
    ) -> None:
        self.workspace = workspace
        self.chat_model = chat_model
        self.memory = memory_store
        self.timezone = timezone or "UTC"
        self.memory_file = workspace / "memory" / "MEMORY.md"

    async def run(self, max_entries: int = 20) -> str | None:
        """Run one dream cycle.

        Returns the updated memory content, or None if nothing changed.
        """
        # Read existing memory
        existing_memory = self.memory.get_memory_context()

        # Read recent unprocessed history
        cursor = self.memory.get_last_dream_cursor()
        entries = self.memory.read_unprocessed_history(since_cursor=cursor)
        if not entries:
            return None

        capped = entries[-max_entries:]
        history_text = "\n".join(
            f"- [{e.get('timestamp', '?')}] {e.get('content', '')[:300]}"
            for e in capped
        )

        # Phase 1: LLM identifies candidate memories
        prompt = (
            "You are a memory consolidation assistant. Review the recent conversation "
            "history and the existing memory file. Identify any new, non-obvious "
            "insights worth remembering permanently. "
            "Only flag things that are: (1) facts about the user, (2) important "
            "decisions made, (3) recurring patterns, or (4) lessons learned.\n\n"
            f"## Existing Memory\n{existing_memory or '(empty)'}\n\n"
            f"## Recent History\n{history_text}\n\n"
            "Return a JSON list of memory entries to add or update. Each entry "
            'should have "type" (user/project/feedback/reference) and "content" fields. '
            "If there is nothing worth remembering, return an empty list []."
        )

        try:
            from langchain_core.messages import HumanMessage

            response = await self.chat_model.ainvoke([HumanMessage(content=prompt)])
            content = getattr(response, "content", "") or ""

            # Try to extract JSON from response
            candidates = self._parse_json_list(content)
            if not candidates:
                return None

            # Phase 2: Update MEMORY.md
            updated = self._update_memory(existing_memory, candidates)
            if updated != existing_memory:
                self.memory_file.write_text(updated, encoding="utf-8")
                logger.info("Dream: updated MEMORY.md with {} new entries", len(candidates))

            # Update cursor
            new_cursor = cursor + len(capped)
            self.memory.set_dream_cursor(new_cursor)

            return updated

        except Exception:
            logger.exception("Dream cycle failed")
            return None

    def _parse_json_list(self, text: str) -> list[dict[str, Any]]:
        """Extract a JSON list from LLM response text."""
        import json
        import re

        # Try to find a JSON array in the text
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return []

    def _update_memory(
        self,
        existing: str,
        candidates: list[dict[str, Any]],
    ) -> str:
        """Merge candidate memories into the existing memory text."""
        now = current_time_str(self.timezone)
        new_entries = []

        for c in candidates:
            entry_type = c.get("type", "reference")
            content = c.get("content", "")
            if not content:
                continue
            new_entries.append(f"- [{now}] [{entry_type}] {content}")

        if not new_entries:
            return existing

        addition = "\n".join(new_entries)
        if existing.strip():
            return existing.rstrip() + "\n\n" + addition
        return addition
