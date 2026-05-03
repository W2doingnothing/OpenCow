"""Web tools: web_search and web_fetch."""

import os
from typing import Any

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class WebSearchInput(BaseModel):
    query: str = Field(description="The search query")


class WebFetchInput(BaseModel):
    url: str = Field(description="The URL to fetch content from")
    prompt: str = Field(default="Extract the main content from this page")


@tool(args_schema=WebSearchInput)
def web_search(query: str) -> str:
    """Search the web. Use for finding current information, docs, or answers online."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY env var not set. Cannot perform web search."

    try:
        import asyncio as _asyncio
    except ImportError:
        return "Error: asyncio not available"

    # Use tavily synchronously for simplicity
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        response = client.search(query, max_results=5)
        results = response.get("results", [])
        if not results:
            return f"No results found for: {query}"
        lines = []
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "Untitled")
            url = r.get("url", "")
            snippet = r.get("content", "").strip()
            lines.append(f"{i}. {title}\n   {url}\n   {snippet}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"


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
