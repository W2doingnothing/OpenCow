"""LangGraph StateGraph definition -- the core agent execution graph."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from opencow.agent.nodes import make_call_model_node, make_route_edge, make_tool_node
from opencow.agent.state import AgentState


def create_agent_graph(
    chat_model: BaseChatModel,
    tools: list[Any],
    *,
    recursion_limit: int = 200,
):
    """Build a compiled LangGraph agent graph backed by in-memory checkpointer.

    Graph structure:
        START -> call_model -> [has tool_calls?]
                                   |-> yes: execute_tools -> call_model
                                   |-> no:  END
    """
    workflow = StateGraph(AgentState)

    call_model = make_call_model_node(chat_model, tools)
    tool_node = make_tool_node(tools)

    workflow.add_node("call_model", call_model)
    workflow.add_node("execute_tools", tool_node)
    workflow.set_entry_point("call_model")

    workflow.add_conditional_edges(
        "call_model",
        make_route_edge,
        {"execute_tools": "execute_tools", "__end__": END},
    )
    workflow.add_edge("execute_tools", "call_model")

    return workflow.compile(checkpointer=MemorySaver())
