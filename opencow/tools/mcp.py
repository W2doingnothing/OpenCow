"""MCP protocol tools via langchain-mcp-adapters."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger


async def load_mcp_tools(servers: dict[str, Any]) -> list[Any]:
    """Load tools from configured MCP servers.

    Args:
        servers: Dict of server_name -> {command, args, env} or {url} for HTTP.

    Returns:
        List of LangChain tools loaded from MCP servers.
    """
    tools: list[Any] = []
    try:
        from langchain_mcp_adapters.tools import load_mcp_tools as _load
    except ImportError:
        logger.warning("langchain-mcp-adapters not installed. MCP tools unavailable.")
        return tools

    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        try:
            if "url" in cfg:
                # HTTP-based MCP server
                loaded = await _load({"transport": "sse", "url": cfg["url"]})
            elif "command" in cfg:
                # Stdio-based MCP server
                loaded = await _load({
                    "transport": "stdio",
                    "command": cfg["command"],
                    "args": cfg.get("args", []),
                    "env": cfg.get("env", {}),
                })
            else:
                continue
            tools.extend(loaded)
            logger.info("MCP: loaded {} tools from {}", len(loaded), name)
        except Exception:
            logger.exception("MCP: failed to load tools from {}", name)

    return tools
