"""Agent graph nodes: call_model and execute_tools."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, trim_messages
from langgraph.prebuilt import ToolNode

from opencow.agent.state import AgentState

_MAX_EMPTY_RETRIES = 2
_CONTEXT_WINDOW_TOKENS = 65536


def set_context_window(tokens: int) -> None:
    global _CONTEXT_WINDOW_TOKENS
    _CONTEXT_WINDOW_TOKENS = tokens


def _sanitize_messages(messages: list[Any]) -> list[Any]:
    """Remove orphaned tool_calls that lack matching ToolMessages.

    Some APIs (DeepSeek, strict OpenAI-compatible) reject messages if an
    AIMessage with tool_calls is not immediately followed by the
    corresponding ToolMessage(s). This can happen after timeouts or partial
    failures leave the checkpointer state corrupted.

    Strategy: walk the list, and for each AIMessage with tool_calls, verify
    that the next N messages are ToolMessages with matching tool_call_ids.
    If not, strip the tool_calls from the AIMessage (converting it to a
    plain text message).
    """
    if not messages:
        return messages

    cleaned: list[Any] = []
    i = 0
    while i < len(messages):
        msg = messages[i]

        if isinstance(msg, AIMessage) and msg.tool_calls:
            tc_ids = {tc["id"] for tc in msg.tool_calls if isinstance(tc, dict) and "id" in tc}
            if not tc_ids:
                cleaned.append(msg)
                i += 1
                continue

            # Collect the ToolMessages that follow this AIMessage
            tool_msgs: list[Any] = []
            j = i + 1
            while j < len(messages) and isinstance(messages[j], ToolMessage):
                tool_msgs.append(messages[j])
                j += 1

            # Check if all tool_call_ids are covered
            tm_ids = {tm.tool_call_id for tm in tool_msgs if hasattr(tm, "tool_call_id")}
            if tc_ids == tm_ids and len(tool_msgs) == len(tc_ids):
                # Valid: keep the AIMessage + ToolMessages
                cleaned.append(msg)
                cleaned.extend(tool_msgs)
                i = j
            else:
                # Orphaned tool_calls: strip tool_calls, keep as plain message
                content = msg.content or ""
                if isinstance(content, list):
                    content = " ".join(
                        b.get("text", "") if isinstance(b, dict) else str(b)
                        for b in content
                    )
                cleaned.append(AIMessage(content=content or "[tool calls omitted]"))
                # Skip the ToolMessages too (they're orphaned without their parent)
                i = j
        else:
            cleaned.append(msg)
            i += 1

    return cleaned


def make_call_model_node(chat_model: BaseChatModel, tools: list[Any]):
    """Create the call_model node that invokes the LLM with tools."""

    model_with_tools = chat_model.bind_tools(tools)

    async def call_model(state: AgentState) -> dict[str, Any]:
        messages = _sanitize_messages(list(state["messages"]))

        # Trim to stay within context window (keep system message + recent messages)
        if len(messages) > 4:  # Only trim if there's enough history to matter
            try:
                messages = trim_messages(
                    messages,
                    max_tokens=_CONTEXT_WINDOW_TOKENS,
                    token_counter=chat_model.get_num_tokens_from_messages
                    if hasattr(chat_model, "get_num_tokens_from_messages")
                    else len,
                    strategy="last",
                    start_on="human",
                    include_system=True,
                )
            except Exception:
                pass  # Never let trimming break the call

        iteration = state.get("iteration_count", 0)
        empty_count = state.get("empty_response_count", 0)

        response = await model_with_tools.ainvoke(messages)

        # Check for empty response (skip retry if reasoning_content is present)
        content = getattr(response, "content", "") or ""
        reasoning = (getattr(response, "additional_kwargs", {}) or {}).get("reasoning_content", "")
        has_tool_calls = bool(getattr(response, "tool_calls", None))
        is_empty = (not content.strip() and not reasoning.strip()) and not has_tool_calls

        if is_empty and empty_count < _MAX_EMPTY_RETRIES:
            retry_msg = HumanMessage(
                content="Please provide a substantive response. Your last reply was empty."
            )
            return {
                "messages": [retry_msg],
                "iteration_count": iteration + 1,
                "empty_response_count": empty_count + 1,
            }

        return {
            "messages": [response],
            "iteration_count": iteration + 1,
            "empty_response_count": 0,
        }

    return call_model


def make_tool_node(tools: list[Any]) -> ToolNode:
    """Create the execute_tools node using LangGraph's ToolNode."""
    return ToolNode(tools)


def make_route_edge(state: AgentState) -> str:
    """Determine next step: execute tools or end."""
    messages = state["messages"]
    if not messages:
        return "__end__"

    last_msg = messages[-1]
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "execute_tools"

    return "__end__"
