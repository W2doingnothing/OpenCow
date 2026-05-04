# OpenCow

运行在你本机的轻量级个人 AI Agent。支持 CLI 对话、QQ/Telegram 接入、定时任务，能读写文件、搜索网络、执行代码。基于 **LangChain** 和 **LangGraph** 构建。

[English](README.md)

## 版本

**v0.1.0**

## 更新公告

【2026-05-04：OpenCow 正式发布，欢迎体验！】

## 功能

### LLM 提供商
- OpenAI / Anthropic / DeepSeek（官方 + 中转站）
- 从模型名称自动识别 provider
- 推理模型支持（默认关闭 `thinking`，`reasoning_content` 自动 fallback）

### Agent 引擎
- 自定义 LangGraph StateGraph（ReAct 循环）
- 空响应自动重试（最多 2 次）
- 消息清洗器：发送 LLM 前自动剔除孤立的 `tool_calls`
- `trim_messages` 上下文窗口管理
- `MemorySaver` 进程内持久化（跨轮次共享）

### 工具（12 个内置）
| 工具 | 描述 |
|------|------|
| `read_file` | 读取文件内容（自动解析 PDF/DOCX） |
| `write_file` | 创建或覆写文件 |
| `edit_file` | 精确字符串替换编辑 |
| `list_dir` | 列出目录内容 |
| `grep` | ripgrep 正则搜索 |
| `glob` | 文件模式匹配 |
| `exec_cmd` | 执行 Shell 命令 |
| `web_search` | DuckDuckGo（免费）或 Tavily 网络搜索 |
| `web_fetch` | 网页内容抓取 |
| `add_cron` | 创建一次性或重复定时任务 |
| `list_cron` | 列出所有定时任务 |
| `remove_cron` | 删除指定定时任务 |

### 记忆系统
- `MemoryStore`：文件持久化（MEMORY.md、history.jsonl、SOUL.md、USER.md）
- `Consolidator`：LLM 驱动的对话压缩
- `Dream`：空闲时两阶段记忆提取
- 多轮对话记忆（同 thread 消息累积）
- System prompt 每个 session 只注入一次
- 会话污染自动恢复

### 定时任务
- 三种调度：`at`（一次性）、`every`（间隔）、`cron`（表达式）
- `_arm_timer` 精确触发，不轮询
- 一次性任务自动删除
- 持久化存储，重启不丢失
- 防反馈循环：cron 回调中禁止创建新 cron

### 心跳服务
- 定期读取 `HEARTBEAT.md`（间隔可配）
- 两阶段：LLM 判断 → Agent 执行
- 结果通过出站总线投递到 CLI

### 多渠道接入
- **Telegram**：长轮询，👀 消息表情回应，群聊 @提及过滤
- **QQ**：官方 botpy SDK，C2C + 群聊 @消息
- **飞书**：WebSocket 长连接（可选）

### API 服务
- `POST /v1/chat/completions`（流式 + 非流式）
- `GET /v1/models`

### 安全
- 可配置的 `restrict_to_workspace` 文件访问控制
- `web_fetch` SSRF 防护

### CLI
| 命令 | 描述 |
|------|------|
| `opencow agent` | 交互式聊天模式 |
| `opencow init` | 生成配置模板 |
| `opencow serve` | 启动 API 服务 |
| `opencow status` | 查看配置状态 |

内置命令：`/help` `/status` `/new` `/dream` `/stop`

## 快速开始

### 1. 安装

```bash
git clone https://github.com/W2doingnothing/OpenCow.git
cd OpenCow
pip install -e .
```

按需安装可选依赖：

```bash
pip install -e ".[telegram]"   # Telegram 机器人
pip install -e ".[qq]"         # QQ 机器人（botpy SDK）
pip install -e ".[search]"     # Tavily 搜索（备用）
pip install -e ".[mcp]"        # MCP 协议支持
```

### 2. 初始化配置

```bash
opencow init
```

会在 `~/.opencow/config.json` 生成默认配置模板。

### 3. 编辑配置 — 选择模型并填入 API 密钥

用编辑器打开 `~/.opencow/config.json`。必须设置两项：

**选择模型**，在 `agents.defaults.model` 中填写：

| 模型标识 | 对应模型 |
|---|---|
| `deepseek/deepseek-chat` | DeepSeek V3 |
| `deepseek/deepseek-reasoner` | DeepSeek R1 |
| `openai/gpt-4o` | OpenAI GPT-4o |
| `openai/gpt-4.1-mini` | OpenAI 经济版 |
| `anthropic/claude-sonnet-4-6` | Claude Sonnet 4.6 |
| `anthropic/claude-opus-4-5` | Claude Opus 4.5 |

**设置凭证**，在 `providers` 下填入对应 provider 的 `apiKey` 和（可选）`apiBase`：

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

使用中转站时，将 `apiBase` 设为代理地址（模型前缀保持不变，如 OpenAI 兼容的中转站填 `openai/gpt-4o`）。

### 4. 验证配置

```bash
opencow status
```

### 5. 开始对话

```bash
opencow agent
```

输入消息按回车即可。试试这些：

```
> 你好！
> 读一下 pyproject.toml，告诉我有哪些依赖
> 帮我搜索今天的热点新闻
> 执行 git log --oneline -5
```

## 架构

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
