"""Session manager -- wraps LangGraph MemorySaver-backed graphs.

The compiled graph with its MemorySaver is created once and cached.
All sessions share the same checkpointer, separated by thread_id.
"""

from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from opencow.agent.graph import create_agent_graph


class SessionManager:
    """Manages agent sessions backed by a single shared MemorySaver instance."""

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path
        self._graph: Any = None
        self._checkpointer: MemorySaver | None = None

    def get_graph(
        self,
        chat_model: Any,
        tools: list[Any],
        *,
        recursion_limit: int = 200,
    ):
        """Return the compiled agent graph, creating it on first call.

        The graph and its MemorySaver are cached -- subsequent calls return
        the SAME instance, so conversation history is preserved across turns
        (separated by thread_id in the config).
        """
        if self._graph is None:
            self._checkpointer = MemorySaver()
            self._graph = create_agent_graph(
                chat_model=chat_model,
                tools=tools,
                checkpointer=self._checkpointer,
            )
        return self._graph

    @staticmethod
    def session_key(channel: str, chat_id: str) -> str:
        return f"{channel}:{chat_id}"
