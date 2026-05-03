"""AgentState definition for the LangGraph agent."""

from typing import Annotated, Any

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """The state of the agent graph.

    LangGraph uses this as the schema that flows through nodes.
    `messages` uses the `add_messages` reducer, so new messages are appended.
    """

    messages: Annotated[list[Any], add_messages]
    session_key: str
    iteration_count: int
    empty_response_count: int
