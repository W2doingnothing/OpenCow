# OpenCow

A lightweight personal AI agent framework powered by **LangChain** and **LangGraph**.

## Version

**v0.2.0** — Phase 2 complete

## Features

### LLM Providers
- OpenAI (official + proxy/中转站)
- Anthropic (official + proxy/中转站)
- DeepSeek (official + proxy/中转站)
- Auto-detection from model name (with or without `provider/` prefix)
- Reasoning model support (`thinking: disabled` for DeepSeek by default, `reasoning_content` fallback)

### Agent Engine
- Custom LangGraph StateGraph (ReAct loop: call_model → execute_tools → call_model)
- Empty-response recovery with automatic retry (max 2)
- Message sanitizer: auto-strips orphaned tool_calls before LLM call (prevents 400 errors)
- In-memory checkpointing via `MemorySaver` (persists within process lifetime, shared across turns)
- Session isolation by `thread_id`, cron/heartbeat use dedicated sessions
- Configurable max tool iterations (default 200), 120s LLM timeout

### Tools (12 built-in)
| Tool | Description |
|------|-------------|
| `read_file` | Read file contents |
| `write_file` | Create or overwrite files |
| `edit_file` | Exact string replacement in files |
| `list_dir` | List directory contents |
| `grep` | Regex search via ripgrep |
| `glob` | File pattern matching |
| `exec_cmd` | Shell command execution (PowerShell on Windows, bash on Unix) |
| `web_search` | Web search via Tavily API |
| `web_fetch` | Fetch and extract web page content |
| `add_cron` | Schedule one-shot or repeating tasks |
| `list_cron` | List all active cron jobs |
| `remove_cron` | Remove a cron job by ID |

### Memory System
- `MemoryStore`: file-based persistence (MEMORY.md, history.jsonl, SOUL.md, USER.md)
- `Consolidator`: LLM-driven conversation compression into structured summaries
- `AutoCompact`: idle session detection and archival
- `Dream`: two-phase memory extraction from conversation history
- Corruption-resistant: auto-resets corrupted files, memory failures never crash the agent

### Cron Service
- Precise `_arm_timer` scheduling (no polling)
- Three schedule types: `at` (one-shot), `every` (interval), `cron` (expression)
- One-shot jobs auto-delete after execution
- Persistent storage (`cron/jobs.json`) survives restarts
- Multi-instance safe via `FileLock` + `action.jsonl`
- Context-aware delivery: cron results routed to the user's channel
- Anti-feedback-loop: cron-triggered LLM cannot create new cron jobs

### Heartbeat Service
- Periodic task checking (configurable interval, reads `HEARTBEAT.md`)
- Two-phase: LLM decision → Agent execution
- Results delivered to CLI via outbound bus

### Skills System
- SKILL.md files with YAML frontmatter (always / on-demand)
- Workspace skills override built-in skills
- Auto-injected into system prompt

### OpenAI-Compatible API
- `POST /v1/chat/completions` (stream + non-stream)
- `GET /v1/models`
- aiohttp-based, SSE streaming

### Session & Context
- Multi-turn conversation memory (same-thread message accumulation)
- System prompt injected once per session (no duplicate system messages)
- Runtime context injection (time, channel, sender)
- Auto-recovery: corrupted sessions auto-reset with fresh state
- Bootstrap files: `SOUL.md`, `USER.md` auto-loaded from workspace

### CLI
| Command | Description |
|---------|-------------|
| `opencow agent` | Interactive chat mode |
| `opencow init` | Generate config template with step-by-step guide |
| `opencow serve` | Start OpenAI-compatible API server |
| `opencow status` | Show current configuration |

### Built-in Slash Commands
`/help` `/status` `/new` `/dream` `/stop`

## Roadmap

| Phase | Status | Features |
|-------|--------|----------|
| **Phase 1** | ✅ Done | Core agent, 9 tools, CLI, config, session management |
| **Phase 2** | ✅ Done | Memory, Dream, Skills, Cron, Heartbeat, OpenAI API, message sanitizer |
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
   │ (graph.py)│── ToolRegistry ─── 12 tools
   │           │── SessionManager ── MemorySaver
   │           │── CronService ───── _arm_timer
   │           │── HeartbeatService ─ HEARTBEAT.md
   └────┬────┘
        │
   Provider Factory
   (OpenAI / Anthropic / DeepSeek)
```

## License

MIT
