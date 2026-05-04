"""Configuration schema using Pydantic v2."""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ProviderConfig(Base):
    """A single LLM provider configuration.

    Typical usage per provider:

    - Official API:  just set apiKey (reads from env if you use ${VAR} syntax)
    - Proxy/中转站:    set apiKey + apiBase (your proxy URL)
    - Local model:     set apiBase only (e.g. http://localhost:11434/v1 for Ollama)
    """

    api_key: str = ""
    api_base: str = ""
    # Extra HTTP headers forwarded to the provider (e.g. {"APP-Code": "xxx"} for AiHubMix)
    extra_headers: dict[str, str] | None = None
    # Extra JSON fields merged into every request body (e.g. thinking, response_format)
    extra_body: dict[str, Any] | None = None


class ProvidersConfig(Base):
    """LLM provider configurations. Key = provider name (lowercase).

    Built-in providers: openai, anthropic, deepseek.
    You can add custom ones for中转站:
      "my-proxy": { "apiKey": "sk-xxx", "apiBase": "https://..." }
    """
    model_config = ConfigDict(extra="allow")
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)


class AgentDefaults(Base):
    """Default agent behavior. Most fields have sane defaults."""

    workspace: str = Field(
        default="~/.opencow/workspace",
        description="Agent's working directory — files, memory, sessions live here",
    )
    model: str = Field(
        default="deepseek/deepseek-chat",
        description="Model identifier: provider/model-name (e.g. deepseek/deepseek-chat)",
    )
    max_tokens: int = Field(default=8192, description="Max tokens per LLM response")
    context_window_tokens: int = Field(default=65536, description="Max context window the model supports")
    context_block_limit: int | None = Field(default=None, description="Max content blocks (images/files) in context")
    temperature: float = Field(default=0.1, description="LLM temperature (0.0 = deterministic)")
    max_tool_iterations: int = Field(default=200, description="Max tool-calling rounds per turn")
    max_tool_result_chars: int = Field(default=16000, description="Truncate tool output beyond this length")
    provider_retry_mode: Literal["standard", "persistent"] = Field(
        default="standard", description="standard = exponential backoff; persistent = keep retrying"
    )
    timezone: str = Field(default="Asia/Shanghai", description="IANA timezone for timestamps")
    session_ttl_minutes: int = Field(default=0, ge=0, description="Auto-compact idle sessions after N minutes (0=off)")
    max_messages: int = Field(default=120, ge=0, description="Max history messages to replay per session")
    consolidation_ratio: float = Field(default=0.5, ge=0.1, le=0.95, description="How much to compress history (0.5 = 50%)")


class AgentsConfig(Base):
    """Agent configuration wrapper."""
    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ToolsConfig(Base):
    """Built-in tool configuration."""

    restrict_to_workspace: bool = Field(default=False, description="Block file access outside workspace")
    web_search_api_key: str = Field(default="", description="Tavily API key for web_search tool")
    web_search_provider: str = Field(default="tavily", description="Search backend: tavily")
    exec_timeout_seconds: int = Field(default=120, description="Shell command timeout")
    max_file_read_chars: int = Field(default=50000, description="Truncate file reads beyond this")


class FeishuConfig(Base):
    """Feishu/Lark channel config."""
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    domain: str = "feishu"  # "feishu" or "lark"
    allow_from: list[str] = Field(default_factory=list)
    send_progress: bool = True


class TelegramConfig(Base):
    """Telegram channel config."""
    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)
    group_policy: Literal["open", "mention"] = "mention"
    send_progress: bool = True


class QQConfig(Base):
    """QQ channel config (official botpy SDK)."""
    enabled: bool = False
    app_id: str = ""
    secret: str = ""
    allow_from: list[str] = Field(default_factory=list)
    msg_format: Literal["plain", "markdown"] = "plain"
    ack_message: str = ""
    send_progress: bool = True


class ChannelsConfig(Base):
    """Channel configurations. Set enabled=true to activate."""
    model_config = ConfigDict(extra="allow")
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    qq: QQConfig = Field(default_factory=QQConfig)


class ApiConfig(Base):
    """OpenAI-compatible API server (Phase 2)."""
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8080


class Config(Base):
    """Top-level opencow configuration.

    Lives at ~/.opencow/config.json — outside any git repo, safe for secrets.
    """

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    enabled_channels: list[str] = Field(default_factory=list)
    mcp_servers: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Helpers (used by downstream code)
    # ------------------------------------------------------------------

    @property
    def workspace_path(self) -> Path:
        return Path(self.agents.defaults.workspace).expanduser().resolve()

    def get_provider_name(self, model: str) -> str:
        # If model has explicit prefix: "deepseek/deepseek-chat"
        if "/" in model:
            prefix = model.split("/")[0].lower()
            known = {"openai", "anthropic", "deepseek"}
            if prefix in known:
                return prefix

        # Auto-detect from model name patterns
        m = model.lower()
        if "deepseek" in m:
            return "deepseek"
        if "claude" in m:
            return "anthropic"
        if any(k in m for k in ("gpt", "o1", "o3", "o4", "davinci")):
            return "openai"

        # Default to openai-compatible
        return "openai"

    def get_provider(self, model: str) -> ProviderConfig:
        name = self.get_provider_name(model)
        return getattr(self.providers, name, ProviderConfig())

    def get_api_base(self, model: str) -> str | None:
        base = self.get_provider(model).api_base
        return base if base else None
