"""Web tools: web_search and web_fetch."""

import os
from typing import Any

import httpx
from langchain_core.tools import tool
from loguru import logger
from pydantic import BaseModel, Field

# Global API key, set by OpenCow from config
_web_search_api_key: str = ""


def set_web_search_key(key: str) -> None:
    global _web_search_api_key
    _web_search_api_key = key


class WebSearchInput(BaseModel):
    query: str = Field(description="The search query")


class WebFetchInput(BaseModel):
    url: str = Field(description="The URL to fetch content from")
    prompt: str = Field(default="Extract the main content from this page")


@tool(args_schema=WebSearchInput)
def web_search(query: str) -> str:
    """Search the web. Use for finding current information, docs, or answers online."""
    api_key = _web_search_api_key or os.environ.get("TAVILY_API_KEY")

    # Primary: DuckDuckGo (free, no API key, ~1-2s)
    ddg_results = _search_ddg(query)
    if ddg_results is not None:
        return ddg_results

    # Fallback: Tavily (requires API key, ~0.5-1s)
    if api_key:
        tavily_results = _search_tavily(query, api_key)
        if tavily_results is not None:
            return tavily_results

    return (
        "Error: web search unavailable. Install duckduckgo-search "
        "(pip install duckduckgo-search) or set a Tavily API key in config."
    )


def _search_ddg(query: str) -> str | None:
    """Try DuckDuckGo search, return formatted results or None on failure."""
    DDGS = None
    try:
        from ddgs import DDGS  # v9.x (preferred)
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # v8.x (legacy)
        except ImportError:
            return None

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=5))
    except Exception as e:
        logger.debug("DuckDuckGo search failed: {}", e)
        return None

    if not raw:
        return f"No results found for: {query}"

    lines = []
    for i, r in enumerate(raw[:5], 1):
        title = r.get("title", "Untitled")
        url = r.get("href", "")
        snippet = r.get("body", "").strip()
        lines.append(f"{i}. {title}\n   {url}\n   {snippet}")
    return "\n\n".join(lines)


def _search_tavily(query: str, api_key: str) -> str | None:
    """Try Tavily search, return formatted results or None on failure."""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        response = client.search(query, max_results=5)
        raw = response.get("results", [])
        if not raw:
            return f"No results found for: {query}"
        lines = []
        for i, r in enumerate(raw[:5], 1):
            title = r.get("title", "Untitled")
            url = r.get("url", "")
            snippet = r.get("content", "").strip()
            lines.append(f"{i}. {title}\n   {url}\n   {snippet}")
        return "\n\n".join(lines)
    except Exception as e:
        logger.debug("Tavily search failed: {}", e)
        return None


@tool(args_schema=WebFetchInput)
def web_fetch(url: str, prompt: str = "Extract the main content from this page") -> str:
    """Fetch and extract content from a web page."""
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; opencow/0.1)"},
            )
            response.raise_for_status()
            text = response.text[:50000]
            return f"Fetched {len(text)} chars from {url}. Content preview:\n\n{text[:4000]}"
    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code} fetching {url}"
    except Exception as e:
        return f"Error fetching {url}: {e}"
