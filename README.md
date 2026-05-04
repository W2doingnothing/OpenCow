# OpenCow

A lightweight personal AI agent framework powered by **LangChain** and **LangGraph**.

[中文版](README_CN.md)

## Version

**v0.2.1**

## Features

### LLM Providers
- OpenAI / Anthropic / DeepSeek (official + proxy)
- Auto-detection from model name
- Reasoning model support (`thinking: disabled` by default, `reasoning_content` fallback)

### Agent Engine
- Custom LangGraph StateGraph (ReAct loop)
- Empty-response recovery (max 2 retries)
- Message sanitizer: auto-strips orphaned `tool_calls` before LLM calls
- `trim_messages` for context window management
- In-memory checkpointing via `MemorySaver` (shared across turns)

### Tools (12 built-in)
| Tool | Description |
|------|-------------|
| `read_file` | Read file contents |
| `write_file` | Create or overwrite files |
| `edit_file` | Exact string replacement in files |
| `list_dir` | List directory contents |
| `grep` | Regex search via ripgrep |
| `glob` | File pattern matching |
| `exec_cmd` | Shell command execution |
| `web_search` | Web search via Tavily |
| `web_fetch` | Fetch web page content |
| `add_cron` | Schedule one-shot or repeating tasks |
| `list_cron` | List active cron jobs |
| `remove_cron` | Remove a cron job by ID |

### Memory & Context
- `MemoryStore`: file-based persistence (MEMORY.md, history.jsonl, SOUL.md, USER.md)
- `Consolidator`: LLM-driven conversation compression
- `Dream`: two-phase memory extraction during idle time
- Multi-turn conversation memory (same-thread message accumulation)
- System prompt injected once per session
- Auto-recovery: corrupted sessions auto-reset

### Cron Service
- `at` (one-shot), `every` (interval), `cron` (expression) scheduling
- Precise `_arm_timer` (no polling)
- One-shot jobs auto-delete after execution
- Persistent storage survives restarts
- Anti-feedback-loop: cron callbacks cannot create new cron jobs

### Heartbeat Service
- Periodic reading of `HEARTBEAT.md` (configurable interval)
- Two-phase: LLM decision → Agent execution
- Results delivered to CLI via outbound bus

### API Server
- `POST /v1/chat/completions` (stream + non-stream)
- `GET /v1/models`

### Security
- Configurable `restrict_to_workspace` (file access control)

### CLI
| Command | Description |
|---------|-------------|
| `opencow agent` | Interactive chat mode |
| `opencow init` | Generate config template |
| `opencow serve` | Start API server |
| `opencow status` | Show configuration |

Slash commands: `/help` `/status` `/new` `/dream` `/stop`

## Roadmap

| Phase | Status | Features |
|-------|--------|----------|
| Phase 1 | ✅ Done | Core agent, 9 tools, CLI, config, sessions |
| Phase 2 | ✅ Done | Memory, Dream, Skills, Cron, Heartbeat, API |
| Phase 3 | ⬜ Planned | Feishu & QQ channels, subagent interface |
| Phase 4 | ⬜ Planned | MCP, SSRF, sandbox, multi-agent gateway, docs parsing |

## Quick Start

```bash
pip install -e .
opencow init
# Edit ~/.opencow/config.json with your API keys
opencow agent
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
   │ Agent    │── ContextBuilder ── MemoryStore / Skills
   │ Graph    │── ToolRegistry ─── 12 tools
   │          │── SessionManager ── MemorySaver
   │          │── CronService ───── _arm_timer
   │          │── HeartbeatService ─ HEARTBEAT.md
   └────┬────┘
        │
   Provider Factory
   (OpenAI / Anthropic / DeepSeek)
```

## License

MIT
