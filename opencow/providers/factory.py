"""Create LLM ChatModel instances from opencow config."""

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from opencow.config.schema import Config


def make_chat_model(config: Config) -> BaseChatModel:
    """Create a LangChain ChatModel from opencow config."""
    model_str = config.agents.defaults.model
    provider_name = config.get_provider_name(model_str)
    provider = config.get_provider(model_str)
    api_base = config.get_api_base(model_str)

    model_name = model_str.split("/", 1)[1] if "/" in model_str else model_str

    kwargs = dict(
        model=model_name,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
    )

    # Merge user-configured extra_body (if any)
    extra_body = dict(provider.extra_body) if provider.extra_body else {}

    if provider_name == "anthropic":
        return ChatAnthropic(
            anthropic_api_key=provider.api_key,
            anthropic_api_base=api_base or None,
            **kwargs,
        )

    if provider_name == "deepseek":
        # DeepSeek reasoning models produce reasoning_content instead of content.
        # Disable thinking by default so the model gives direct answers and
        # function calls work correctly. Set extra_body to {} in config to undo.
        if "thinking" not in extra_body:
            extra_body["thinking"] = {"type": "disabled"}
        if extra_body:
            kwargs["extra_body"] = extra_body
        return ChatOpenAI(
            api_key=provider.api_key or "dummy",
            base_url=api_base or "https://api.deepseek.com",
            request_timeout=120,
            **kwargs,
        )

    # Default: OpenAI-compatible
    if extra_body:
        kwargs["extra_body"] = extra_body
    return ChatOpenAI(
        api_key=provider.api_key or "dummy",
        base_url=api_base or None,
        request_timeout=120,
        **kwargs,
    )
