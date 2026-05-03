"""CLI entry point using typer."""

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

app = typer.Typer(
    name="opencow",
    help="OpenCow — A lightweight personal AI agent framework",
)


@app.command()
def agent(
    config: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = None,
) -> None:
    """Start the agent in interactive CLI mode."""
    from opencow.app import OpenCow

    cow = OpenCow.from_config(config)
    asyncio.run(cow.serve())


@app.command()
def status(
    config: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = None,
) -> None:
    """Show current configuration and status."""
    from opencow.config.loader import load_config, resolve_config_env_vars
    import json

    cfg = resolve_config_env_vars(load_config(Path(config) if config else None))
    print("Config path:", config or "~/.opencow/config.json")
    print("Model:", cfg.agents.defaults.model)
    print("Workspace:", str(cfg.workspace_path))
    print("Timezone:", cfg.agents.defaults.timezone)
    print("Max iterations:", cfg.agents.defaults.max_tool_iterations)
    print("Context window tokens:", cfg.agents.defaults.context_window_tokens)


@app.command()
def init() -> None:
    """Initialize config: generate ~/.opencow/config.json from template."""
    from opencow.config.paths import get_config_path
    from opencow.config.loader import save_config
    from opencow.config.schema import Config

    target = get_config_path()

    if target.exists():
        print(f"Config already exists at: {target}")
        overwrite = input("Overwrite with fresh template? [y/N]: ").strip().lower()
        if overwrite not in ("y", "yes"):
            print("Cancelled.")
            return

    config = Config()
    target.parent.mkdir(parents=True, exist_ok=True)
    save_config(config, target)

    print(f"Created: {target}")
    print()
    _print_config_guide(target)


def _print_config_guide(target) -> None:
    """Print a detailed annotation guide for the config file."""
    print("=" * 64)
    print("  CONFIGURATION GUIDE")
    print("=" * 64)
    print()
    print(f"  File: {target}")
    print("  (This file lives under ~/.opencow/ -- outside any git repo;")
    print("   you can safely paste API keys directly into it.)")
    print()

    # ---- Step 1 ----
    print("  STEP 1 -- Pick a model")
    print("  ------------------------")
    print('  Find "agents" -> "defaults" -> "model". Change it to one of:')
    print()
    print("    deepseek/deepseek-chat          DeepSeek V3")
    print("    deepseek/deepseek-reasoner      DeepSeek R1")
    print("    openai/gpt-4o                   OpenAI GPT-4o")
    print("    openai/gpt-4.1-mini             OpenAI budget")
    print("    anthropic/claude-sonnet-4-6     Claude Sonnet 4.6")
    print("    anthropic/claude-opus-4-5       Claude Opus 4.5")
    print()
    print("  If you use a proxy (zhongzhuanzhan), keep the prefix that")
    print("  matches the original provider (e.g. 'openai/gpt-4o' for")
    print("  OpenAI-compatible proxies).")
    print()

    # ---- Step 2 ----
    print("  STEP 2 -- Fill in API credentials")
    print("  -----------------------------------")
    print('  Find "providers" -> "<your-provider>". Fill these fields:')
    print()
    print("    apiKey    Your API key / token")
    print("    apiBase   API endpoint URL (leave empty for official)")
    print()
    print("  Examples:")
    print()
    print("  # DeepSeek official:")
    print('  "deepseek": { "apiKey": "sk-xxxxxxxx", "apiBase": "" }')
    print()
    print("  # OpenAI proxy:")
    print('  "openai": { "apiKey": "sk-xxxxxxxx", "apiBase": "https://your-proxy.com/v1" }')
    print()
    print("  # Anthropic proxy:")
    print('  "anthropic": { "apiKey": "sk-xxxxxxxx", "apiBase": "https://your-proxy.com" }')
    print()
    print("  # Local Ollama:")
    print('  "openai": { "apiKey": "ollama", "apiBase": "http://localhost:11434/v1" }')
    print()

    # ---- Step 3 ----
    print("  STEP 3 -- Tune agent behavior (optional)")
    print("  -------------------------------------------")
    print('  In "agents" -> "defaults", you can adjust:')
    print()
    print("    workspace              Where files/memory/sessions live")
    print("    temperature            0.0 = deterministic, 1.0 = creative")
    print("    maxToolIterations      Max tool calls per turn (default 200)")
    print("    timezone               e.g. 'Asia/Shanghai', 'America/New_York'")
    print()

    # ---- Step 4 ----
    print("  STEP 4 -- Verify")
    print("  -----------------")
    print("  Run: opencow status")
    print("  Then: opencow agent")
    print()
    print("=" * 64)


@app.command()
def serve(
    config: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = None,
) -> None:
    """Start the OpenAI-compatible API server."""
    print("API server not yet implemented — coming in Phase 2.")


def main() -> None:
    app()
