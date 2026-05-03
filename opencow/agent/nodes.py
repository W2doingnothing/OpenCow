"""Agent graph nodes: call_model and execute_tools."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import ToolNode

from opencow.agent.state import AgentState

_MAX_EMPTY_RETRIES = 2


def make_call_model_node(chat_model: BaseChatModel, tools: list[Any]):
    """Create the call_model node that invokes the LLM with tools."""

    model_with_tools = chat_model.bind_tools(tools)

    async def call_model(state: AgentState) -> dict[str, Any]:
        messages = state["messages"]
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
