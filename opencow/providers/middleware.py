"""Middleware for LLM message handling: role alternation and empty-response recovery."""

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def enforce_role_alternation(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge adjacent messages with the same role to prevent API errors."""
    if not messages:
        return messages

    result = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if result and result[-1].get("role") == role:
            # Merge content
            prev = result[-1]
            prev["content"] = _merge_content(prev["content"], content)
            # Keep tool_calls if present
            if "tool_calls" in msg:
                prev["tool_calls"] = msg["tool_calls"]
        else:
            result.append(dict(msg))

    return result


def _merge_content(prev: Any, new: Any) -> Any:
    """Merge two content values, handling strings and lists."""
    if isinstance(prev, str) and isinstance(new, str):
        return f"{prev}\n\n{new}" if prev else new
    if isinstance(prev, list) and isinstance(new, list):
        return prev + new
    return new if new else prev


def is_empty_response(message: AIMessage) -> bool:
    """Check if an AI response is effectively empty (no content and no tool calls)."""
    content = message.content if isinstance(message.content, str) else str(message.content)
    has_tool_calls = bool(message.tool_calls)
    return (not content or not content.strip()) and not has_tool_calls


def build_empty_retry_message() -> HumanMessage:
    """Build a retry prompt for empty responses."""
    return HumanMessage(content="Please provide a substantive response. Your last reply was empty.")
