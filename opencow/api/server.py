"""OpenAI-compatible HTTP API server.

Provides /v1/chat/completions and /v1/models endpoints.
All requests route to a single persistent session.
"""

from __future__ import annotations

import asyncio
import json as _json
import time
import uuid
from typing import Any

from aiohttp import web
from loguru import logger

API_SESSION_KEY = "api:default"
API_CHAT_ID = "default"


def _error_json(status: int, message: str, err_type: str = "invalid_request_error") -> web.Response:
    return web.json_response(
        {"error": {"message": message, "type": err_type, "code": status}},
        status=status,
    )


def _chat_completion_response(content: str, model: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _chunk_json(chunk_id: str, model: str, delta: str) -> str:
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {"index": 0, "delta": {"content": delta}, "finish_reason": None}
        ],
    }
    return _json.dumps(chunk, ensure_ascii=False)


def create_app(agent: Any) -> web.Application:
    """Create an aiohttp app that wraps an OpenCow agent instance."""
    app = web.Application()
    app["agent"] = agent
    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    app.router.add_get("/v1/models", handle_models)
    return app


async def handle_chat_completions(request: web.Request) -> web.Response:
    agent = request.app["agent"]

    try:
        body = await request.json()
    except Exception:
        return _error_json(400, "Invalid JSON body")

    messages = body.get("messages", [])
    if not messages:
        return _error_json(400, "messages is required")

    model = body.get("model", agent._model_name)
    stream = body.get("stream", False)

    # Extract the last user message
    user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_text = m.get("content", "")
            break

    if not user_text:
        return _error_json(400, "At least one user message is required")

    if not stream:
        # Non-streaming response
        result = await agent.run(
            user_text,
            session_key=API_SESSION_KEY,
            channel="api",
        )
        return web.json_response(_chat_completion_response(result or "", model))

    # Streaming response
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={"Content-Type": "text/event-stream"},
    )
    await response.prepare(request)

    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    try:
        # For streaming, run the agent and stream chunks
        result = await agent.run(
            user_text,
            session_key=API_SESSION_KEY,
            channel="api",
        )

        if result:
            # Stream in chunks (simulate streaming from full response)
            words = result.split()
            for i in range(0, len(words), 3):
                delta = " ".join(words[i:i + 3]) + " "
                chunk_str = _chunk_json(chunk_id, model, delta)
                await response.write(f"data: {chunk_str}\n\n".encode("utf-8"))
                await asyncio.sleep(0.01)

        await response.write(b"data: [DONE]\n\n")
    except Exception as e:
        logger.exception("Streaming error")
    finally:
        await response.write_eof()

    return response


async def handle_models(request: web.Request) -> web.Response:
    agent = request.app["agent"]
    return web.json_response({
        "object": "list",
        "data": [
            {
                "id": agent._model_name,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "opencow",
            }
        ],
    })
