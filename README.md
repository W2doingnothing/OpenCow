# OpenCow

A lightweight personal AI agent that runs on your machine — chat via CLI, integrate with QQ/Telegram, schedule tasks, and give it tools to read, write, search, and execute code. Powered by **LangChain** and **LangGraph**.

[中文版](README_CN.md)

## Version

**v0.1.0**

## Updates

【2026-05-04：OpenCow officially released — welcome to try it out!】

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
- `MemorySaver` in-memory checkpointing (shared across turns)

### Tools (12 built-in)
| Tool | Description |
|------|-------------|
| `read_file` | Read file contents (auto-parses PDF/DOCX) |
| `write_file` | Create or overwrite files |
| `edit_file` | Exact string replacement in files |
| `list_dir` | List directory contents |
| `grep` | Regex search via ripgrep |
| `glob` | File pattern matching |
| `exec_cmd` | Shell command execution |
| `web_search` | Web search via DuckDuckGo (free) or Tavily |
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

### Channels
- **Telegram**: long polling, 👀 reaction on receipt, group @mention filtering
- **QQ**: official botpy SDK, C2C + group @message support
- **Feishu**: WebSocket long connection (opt-in)

### API Server
- `POST /v1/chat/completions` (stream + non-stream)
- `GET /v1/models`

### Security
- Configurable `restrict_to_workspace` (file access control)
- SSRF protection on `web_fetch`

### CLI
| Command | Description |
|---------|-------------|
| `opencow agent` | Interactive chat mode |
| `opencow init` | Generate config template |
| `opencow serve` | Start API server |
| `opencow status` | Show configuration |

Slash commands: `/help` `/status` `/new` `/dream` `/stop`

## Quick Start

### 1. Install

```bash
git clone https://github.com/W2doingnothing/OpenCow.git
cd OpenCow
pip install -e .
```

Optional extras (install as needed):

```bash
pip install -e ".[telegram]"   # Telegram bot channel
pip install -e ".[qq]"         # QQ bot channel (botpy SDK)
pip install -e ".[search]"     # Tavily search (fallback)
pip install -e ".[mcp]"        # MCP protocol support
```

### 2. Initialize config

```bash
opencow init
```

This creates `~/.opencow/config.json` with a default template.

### 3. Edit config — pick a model and set API keys

Open `~/.opencow/config.json` in your editor. The two things you must set:

**Pick a model** under `agents.defaults.model`:

| Model string | What it is |
|---|---|
| `deepseek/deepseek-chat` | DeepSeek V3 |
| `deepseek/deepseek-reasoner` | DeepSeek R1 |
| `openai/gpt-4o` | OpenAI GPT-4o |
| `openai/gpt-4.1-mini` | OpenAI budget |
| `anthropic/claude-sonnet-4-6` | Claude Sonnet 4.6 |
| `anthropic/claude-opus-4-5` | Claude Opus 4.5 |

**Set credentials** under `providers` — fill in `apiKey` and optionally `apiBase` for your provider:

```json
{
  "providers": {
    "deepseek": {
      "apiKey": "sk-xxxxxxxx",
      "apiBase": ""
    }
  }
}
```

For proxy/zhongzhuanzhan, set `apiBase` to the proxy URL (keep the provider prefix, e.g. `openai/gpt-4o` for OpenAI-compatible proxies).

### 4. Verify

```bash
opencow status
```

### 5. Start chatting

```bash
opencow agent
```

Type your message and press Enter. Try things like:

```
> Hello!
> Read pyproject.toml and tell me what dependencies are listed
> Search the web for today's top news
> Run git log --oneline -5
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
