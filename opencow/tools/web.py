"""Web tools: web_search and web_fetch."""

import os
import re
from html import unescape
from typing import Any

import httpx
from langchain_core.tools import tool
from loguru import logger
from pydantic import BaseModel, Field

# Global API key, set by OpenCow from config
_web_search_api_key: str = ""

_DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
_MAX_REDIRECTS = 5
_SEARCH_TIMEOUT = 10  # DDGS timeout
_FETCH_TIMEOUT = 8.0  # httpx timeout


def set_web_search_key(key: str) -> None:
    global _web_search_api_key
    _web_search_api_key = key


def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return unescape(text).strip()


def _normalize(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


class WebSearchInput(BaseModel):
    query: str = Field(description="The search query")


class WebFetchInput(BaseModel):
    url: str = Field(description="The URL to fetch content from")
    prompt: str = Field(default="Extract the main content from this page")


def _search_ddg(query: str) -> str | None:
    """Try DuckDuckGo search (sync, called from executor thread)."""
    DDGS = None
    try:
        from ddgs import DDGS  # v9.x
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # v8.x
        except ImportError:
            return None

    try:
        ddgs = DDGS(timeout=_SEARCH_TIMEOUT)
        raw = list(ddgs.text(query, max_results=5))
    except Exception as e:
        logger.debug("DuckDuckGo search failed: {}", e)
        return None

    if not raw:
        return None

    lines = [f"Results for: {query}\n"]
    for i, r in enumerate(raw[:5], 1):
        title = _normalize(_strip_tags(r.get("title", "")))
        snippet = _normalize(_strip_tags(r.get("body", "")))
        lines.append(f"{i}. {title}\n   {r.get('href', '')}")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)


def _search_tavily(query: str, api_key: str) -> str | None:
    """Try Tavily search."""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        response = client.search(query, max_results=5)
        raw = response.get("results", [])
        if not raw:
            return None
        lines = [f"Results for: {query}\n"]
        for i, r in enumerate(raw[:5], 1):
            title = r.get("title", "Untitled")
            snippet = r.get("content", "").strip()
            lines.append(f"{i}. {title}\n   {r.get('url', '')}\n   {snippet}")
        return "\n".join(lines)
    except Exception as e:
        logger.debug("Tavily search failed: {}", e)
        return None


@tool(args_schema=WebSearchInput)
def web_search(query: str) -> str:
    """Search the web. Use for finding current information, docs, or answers online."""
    api_key = _web_search_api_key or os.environ.get("TAVILY_API_KEY")

    # Primary: DuckDuckGo (free, no API key)
    ddg_results = _search_ddg(query)
    if ddg_results is not None:
        return ddg_results

    # Fallback: Tavily (requires API key)
    if api_key:
        tavily_results = _search_tavily(query, api_key)
        if tavily_results is not None:
            return tavily_results

    return (
        "Error: web search unavailable. Install duckduckgo-search "
        "(pip install duckduckgo-search) or set a Tavily API key in config."
    )


@tool(args_schema=WebFetchInput)
def web_fetch(url: str, prompt: str = "Extract the main content from this page") -> str:
    """Fetch and extract content from a web page."""
    url = url.strip(' \t\r\n`"\'')
    # Quick URL validation
    if not url.startswith(("http://", "https://")):
        return f"Error: only http/https URLs allowed, got: {url[:50]}"

    try:
        with httpx.Client(
            timeout=_FETCH_TIMEOUT,
            follow_redirects=True,
            max_redirects=_MAX_REDIRECTS,
        ) as client:
            response = client.get(
                url,
                headers={"User-Agent": _DEFAULT_USER_AGENT},
            )
            response.raise_for_status()
            text = response.text[:50000]
            clean = _normalize(_strip_tags(text))
            if not clean:
                return f"Fetched {url} but no readable text extracted ({len(text)} bytes raw HTML)."
            max_chars = 4000
            preview = clean[:max_chars]
            if len(clean) > max_chars:
                preview += f"\n\n... (truncated, {len(clean)} total chars)"
            return f"Content from {url}:\n\n{preview}"
    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code} fetching {url}"
    except httpx.TimeoutException:
        return f"Timeout fetching {url} ({_FETCH_TIMEOUT}s)"
    except Exception as e:
        return f"Error fetching {url}: {e}"
