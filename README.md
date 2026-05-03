# OpenCow

A lightweight personal AI agent framework powered by **LangChain** and **LangGraph**.

## Version

**v0.1.0** — Phase 1 complete

## Features (Phase 1 — Minimal Viable)

### LLM Providers
- OpenAI (official + proxy/中转站)
- Anthropic (official + proxy/中转站)
- DeepSeek (official + proxy/中转站)
- Auto-detection from model name (with or without `provider/` prefix)

### Agent Engine
- Custom LangGraph StateGraph (ReAct loop: call_model → execute_tools → call_model)
- Empty-response recovery with automatic retry
- Reasoning model support (DeepSeek v4/R1 series, `reasoning_content` fallback)
- In-memory checkpointing via `MemorySaver` (persists within process lifetime)
- Configurable max tool iterations (default 200)
- 120s LLM timeout with clear error reporting

### Tools (9 built-in)
| Tool | Description |
|------|-------------|
| `read_file` | Read file contents (text, images, PDFs) |
| `write_file` | Create or overwrite files |
| `edit_file` | Exact string replacement in files |
| `list_dir` | List directory contents |
| `grep` | Regex search via ripgrep |
| `glob` | File pattern matching |
| `exec_cmd` | Shell command execution (PowerShell on Windows, bash on Unix) |
| `web_search` | Web search via Tavily API |
| `web_fetch` | Fetch and extract web page content |

### Session & Context
- Session isolation by `channel:chat_id` key
- System prompt with identity, workspace info, and platform-aware policies
- Runtime context injection (time, channel, sender)
- Bootstrap files: `SOUL.md`, `USER.md` auto-loaded from workspace
- Persistent memory via `workspace/memory/MEMORY.md`

### CLI
- `opencow agent` — Interactive chat mode
- `opencow init` — Generate config template with step-by-step guide
- `opencow status` — Show current configuration
- `opencow serve` — API server (Phase 2)
- Built-in slash commands: `/help`, `/status`, `/new`, `/history`, `/stop`

### Configuration
- Pydantic v2 config schema (camelCase + snake_case compatible)
- Auto-generated template via `opencow init`
- Provider-specific API keys and base URLs
- Config lives at `~/.opencow/config.json` (outside git repos, safe for secrets)

## Roadmap

| Phase | Status | Features |
|-------|--------|----------|
| **Phase 1** | ✅ Done | Core agent, 9 tools, CLI, config, session management |
| **Phase 2** | 🚧 In Progress | Memory system, Consolidator, Dream, Skills, OpenAI API, Cron/Heartbeat |
| **Phase 3** | ⬜ Planned | Feishu & QQ channels, subagent interface |
| **Phase 4** | ⬜ Planned | MCP protocol, SSRF protection, shell sandbox, multi-agent gateway, docs parsing |

## Quick Start

```bash
pip install -e .
opencow init        # Generate ~/.opencow/config.json
# Edit config.json with your API keys
opencow agent       # Start chatting
```

## Architecture

```
CLI / API / Channels
        │
   MessageBus (asyncio.Queue × 2)
        │
   OpenCow (app.py)
        │
   ┌────┴────┐
   │ AgentLoop │── ContextBuilder ── MemoryStore / Skills
   │ (graph.py)│── ToolRegistry ─── 9 built-in tools
   │           │── SessionManager ── MemorySaver
   └────┬────┘
        │
   Provider Factory
   (OpenAI / Anthropic / DeepSeek)
```

## License

MIT
