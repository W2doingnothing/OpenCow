"""Runtime constants and message builders."""

EMPTY_FINAL_RESPONSE_MESSAGE = "I have no response to provide."


def is_blank_text(content: str | None) -> bool:
    """Check if content is effectively empty."""
    if content is None:
        return True
    return not content.strip()


def build_finalization_retry_message() -> dict:
    """Message injected when the assistant stops without producing a response."""
    return {
        "role": "user",
        "content": (
            "Your last response was empty or contained only tool calls without final text. "
            "Please provide a natural-language summary or answer to the user."
        ),
    }


def build_length_recovery_message() -> dict:
    """Message injected when the model's output was truncated."""
    return {
        "role": "user",
        "content": "Your previous response was cut off. Please continue from where you stopped.",
    }


def ensure_nonempty_tool_result(result: str) -> str:
    """Ensure a tool result is never empty (some LLMs crash on empty tool results)."""
    if not result or not result.strip():
        return "[Tool produced no output]"
    return result
