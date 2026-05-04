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
    print("Edit this file to set your model and API key, then run: opencow agent")


@app.command()
def serve(
    config: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to config.json"),
    ] = None,
    host: Annotated[str, typer.Option("--host", "-h", help="Bind address")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port", "-p", help="Bind port")] = 8080,
) -> None:
    """Start the OpenAI-compatible API server."""
    from opencow.app import OpenCow

    cow = OpenCow.from_config(config)
    asyncio.run(cow.serve_api(host=host, port=port))


def main() -> None:
    app()
