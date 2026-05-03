"""Tool registry for dynamic tool management."""

from typing import Any

from langchain_core.tools import BaseTool


class ToolRegistry:
    """Registry for agent tools with schema caching."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._cached_definitions: list[dict[str, Any]] | None = None

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        self._cached_definitions = None

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)
        self._cached_definitions = None

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get OpenAI-format tool schemas with stable ordering for cache-friendly prompts."""
        if self._cached_definitions is not None:
            return self._cached_definitions

        definitions: list[dict[str, Any]] = []
        for tool in sorted(self._tools.values(), key=lambda t: t.name):
            schema = _tool_to_openai_schema(tool)
            definitions.append(schema)

        self._cached_definitions = definitions
        return definitions


def _tool_to_openai_schema(tool: BaseTool) -> dict[str, Any]:
    """Convert a LangChain BaseTool to an OpenAI function schema."""
    # LangChain tools have .args_schema (Pydantic model) for parameters
    schema = {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": _pydantic_to_json_schema(tool.args_schema),
        },
    }
    return schema


def _pydantic_to_json_schema(model: type) -> dict[str, Any]:
    """Convert a Pydantic model to a JSON Schema dict."""
    if model is None:
        return {"type": "object", "properties": {}}
    schema = model.model_json_schema()
    return {
        "type": schema.get("type", "object"),
        "properties": schema.get("properties", {}),
        "required": schema.get("required", []),
    }
