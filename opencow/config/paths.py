"""Runtime path helpers."""

import os
from pathlib import Path


def get_config_dir() -> Path:
    """Get the opencow config directory."""
    env = os.environ.get("OPENCOW_CONFIG_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".opencow"


def get_config_path() -> Path:
    """Get the path to config.json."""
    return get_config_dir() / "config.json"


def get_default_workspace() -> Path:
    """Get the default workspace path."""
    return get_config_dir() / "workspace"
