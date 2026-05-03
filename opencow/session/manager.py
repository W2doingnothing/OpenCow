"""Session manager -- wraps LangGraph MemorySaver-backed graphs."""

from typing import Any

from opencow.agent.graph import create_agent_graph


class SessionManager:
    """Manages agent sessions backed by LangGraph's MemorySaver.

    Each session has a unique thread_id, tracked by the checkpointer.
    Conversations persist within a process lifetime; restart = clean slate.
    SQLite persistence will be added when langgraph-checkpoint-sqlite stabilizes.
    """

    def __init__(self, db_path: str = "") -> None:
        # db_path kept for API compatibility; MemorySaver doesn't use it.
        self._db_path = db_path

    def get_graph(
        self,
        chat_model: Any,
        tools: list[Any],
        *,
        recursion_limit: int = 200,
    ):
        return create_agent_graph(
            chat_model=chat_model,
            tools=tools,
            recursion_limit=recursion_limit,
        )

    @staticmethod
    def session_key(channel: str, chat_id: str) -> str:
        return f"{channel}:{chat_id}"
