"""General-purpose utility functions."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import tiktoken

ENCODING = tiktoken.get_encoding("cl100k_base")


def ensure_dir(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(name: str) -> str:
    """Convert a string to a safe filename."""
    return "".join(c for c in name if c.isalnum() or c in "._-")


def current_time_str(timezone: str | None = None) -> str:
    """Return the current time as an ISO-formatted string."""
    now = datetime.now()
    if timezone:
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo(timezone))
        except Exception:
            pass
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


def estimate_message_tokens(msg: dict[str, Any]) -> int:
    """Estimate token count of a message dict."""
    content = msg.get("content", "")
    if isinstance(content, str):
        return len(ENCODING.encode(content))
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict) and "text" in block:
                total += len(ENCODING.encode(block["text"]))
        return total
    return 0


def estimate_prompt_tokens_chain(messages: list[dict[str, Any]]) -> int:
    """Estimate total tokens for a list of messages."""
    return sum(estimate_message_tokens(m) for m in messages)


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, adding ellipsis if truncated."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


def build_assistant_message(content: str) -> dict[str, Any]:
    """Build a simple assistant message dict."""
    return {"role": "assistant", "content": content}


def strip_think(text: str) -> str:
    """Strip <｜end▁of▁thinking｜> and the following paragraph. Use strip_think() instead.

    Returns text with thinking blocks removed.
    """
    import re
    return re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL).strip()
