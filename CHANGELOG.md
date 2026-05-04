# OpenCow 更新日志

## 2026-05-04 — 修复（网络超时 & DDGS 警告）

### 修复
- **网络超时不重置会话**：`asyncio.TimeoutError` 不再调用 `_reset_corrupted_session`，避免网络波动导致对话历史丢失
- **ChatOpenAI 显式超时**：添加 `request_timeout=120`，防止 httpx 默认短超时（~5s）先于 `asyncio.wait_for` 触发
- **DDGS RuntimeWarning**：过滤 `duckduckgo_search` 重命名警告（ddgs v9.x 内部兼容层触发）

---

## v0.1.0 (2026-05-04) — Phase 3 & 4 完成

### 新增
- **Telegram 渠道**：长轮询，消息表情回应(👀)，群聊 @提及过滤，白名单控制
- **QQ 渠道（botpy SDK）**：C2C + 群聊 @提及，消息去重，自动重连，复用 nanobot 凭证
- **DuckDuckGo 搜索**：免费免 key，DDGS(timeout=10)，HTML 清洗，Tavily fallback
- **web_fetch 优化**：8s 超时，max 5 重定向，HTML 标签剥离
- **消息出站路由**：非 CLI 渠道的回复自动路由到正确的渠道
- **渠道关闭清理**：先停渠道再清任务，防止 botpy `__del__` 崩溃

### 修复
- **对话记忆丢失**：SessionManager 缓存单例 MemorySaver
- **重复 system prompt**：`_primed_sessions` 追踪，后续轮次跳过
- **Windows stdin 兼容**：CLI 改用 daemon 线程 + `run_coroutine_threadsafe`
- **Cron 反馈循环**：`_in_cron_context` 禁止回调内再创建任务
- **消息清洗器**：发送前自动清除孤立的 tool_calls
- **多个编码/崩溃**：GBK、emoji、NoneType 防御

---

## 2026-05-04 — 清理与补齐

### 清理
- 删除死代码：`consolidate.py`（与 `memory.py` 重复）、`runtime.py` / `middleware.py` 中未使用的函数
- 移除未使用的依赖：`python-dotenv`、`pydantic-settings`
- `restrict_to_workspace` 默认改为 `false`（与 nanobot 对齐）

### 补齐
- `web_search` 从 config 读取 API key，不再仅依赖环境变量
- `grep` / `glob` 使用 workspace 根目录而非 cwd，支持绝对路径自动转换
- 文件工具接入 `restrict_to_workspace`（开启时拒绝 workspace 外的路径）
- `call_model` 节点接入 `trim_messages`，超过 `context_window_tokens` 自动裁剪
- AutoCompact 作为后台任务运行

### 修复
- `glob` 绝对路径 `NotImplementedError` → 自动转为 workspace 相对路径
- AutoCompact 属性名修正 + 取消时不再崩溃

---

## 2026-05-03 — Phase 2 完成

### 新增功能
- **Cron 定时任务**：支持 `at`(一次性)、`every`(间隔)、`cron`(表达式) 三种调度，精确到目标时刻，持久化存储，支持多渠道投递
- **Heartbeat 心跳**：定期读取 `HEARTBEAT.md`，LLM 判断是否有待办并自动执行
- **记忆系统**：MemoryStore 文件持久化、Consolidator 对话压缩、Dream 自动提取记忆
- **Skills 技能系统**：SKILL.md YAML 加载，always/on-demand 分类
- **OpenAI 兼容 API**：`/v1/chat/completions` + `/v1/models`
- **Cron 管理工具**：`add_cron` / `list_cron` / `remove_cron` 共 12 个工具
- **消息清洗器**：发送前自动清除孤立的 tool_calls，防止 API 400 错误

### 修复
- **对话记忆丢失**：SessionManager 缓存 MemorySaver 实例，不再每轮新建
- **重复 system prompt**：首次注入后后续轮次跳过
- **CliChannel Windows 无响应**：独立 daemon 线程读取 stdin
- **Shell 编码崩溃**：GBK/UTF-8 兼容处理
- **Cron 反馈循环**：禁止 cron 回调内再创建 cron
- **history.jsonl 损坏**：自动检测并重建
- **多个 Unicode/GBK 编码崩溃**：统一 `errors="replace"` + `encoding="utf-8"`

---

## v0.1.0 (2026-05-03) — Phase 1 完成

### 新增
- LangGraph StateGraph 自定义 Agent 引擎
- 9 个内置工具（文件、搜索、Shell、网络）
- OpenAI / Anthropic / DeepSeek 多 Provider 支持
- Pydantic v2 配置系统 + `opencow init` 模板生成
- CLI 交互模式 + 斜杠命令
- MemorySaver 会话持久化
- DeepSeek 推理模型 `reasoning_content` fallback

### 修复
- LangGraph 1.x `SqliteSaver` 不存在 → 改用 `MemorySaver`
- `deepseek-v4-flash` thinking 模式干扰 → 默认注入 `{"thinking": {"type": "disabled"}}`
