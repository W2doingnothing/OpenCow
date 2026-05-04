# OpenCow

基于 **LangChain** 和 **LangGraph** 的轻量级个人 AI Agent 框架。

[English](README.md)

## 版本

**v0.2.1**

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
| `read_file` | 读取文件内容 |
| `write_file` | 创建或覆写文件 |
| `edit_file` | 精确字符串替换编辑 |
| `list_dir` | 列出目录内容 |
| `grep` | ripgrep 正则搜索 |
| `glob` | 文件模式匹配 |
| `exec_cmd` | 执行 Shell 命令 |
| `web_search` | Tavily 网络搜索 |
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

### API 服务
- `POST /v1/chat/completions`（流式 + 非流式）
- `GET /v1/models`

### 安全
- 可配置的 `restrict_to_workspace` 文件访问控制

### CLI
| 命令 | 描述 |
|------|------|
| `opencow agent` | 交互式聊天模式 |
| `opencow init` | 生成配置模板 |
| `opencow serve` | 启动 API 服务 |
| `opencow status` | 查看配置状态 |

内置命令：`/help` `/status` `/new` `/dream` `/stop`

## 路线图

| 阶段 | 状态 | 内容 |
|------|------|------|
| Phase 1 | ✅ 完成 | 核心 Agent、9 工具、CLI、配置、会话 |
| Phase 2 | ✅ 完成 | 记忆、Dream、Skills、Cron、Heartbeat、API |
| Phase 3 | ⬜ 计划 | 飞书 & QQ 渠道、子代理接口 |
| Phase 4 | ⬜ 计划 | MCP、SSRF、沙箱、多代理网关、文档解析 |

## 快速开始

```bash
pip install -e .
opencow init
# 编辑 ~/.opencow/config.json 填入 API key
opencow agent
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
