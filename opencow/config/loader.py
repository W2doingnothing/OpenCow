"""Load and save configuration with environment variable interpolation."""

import json
import os
import re
from pathlib import Path

from loguru import logger

from opencow.config.paths import get_config_path
from opencow.config.schema import Config, ProviderConfig, ProvidersConfig, ToolsConfig

_ENV_VAR_RE = re.compile(r"\$\{(.+?)\}")


def _resolve_env(value: str) -> str:
    """Resolve ${VAR} placeholders in a string."""
    if not isinstance(value, str):
        return value
    def replacer(m: re.Match) -> str:
        return os.environ.get(m.group(1), m.group(0))
    return _ENV_VAR_RE.sub(replacer, value)


def resolve_config_env_vars(config: Config) -> Config:
    """Recursively resolve env var references in config values."""
    raw = config.model_dump()
    resolved = _resolve_dict(raw)
    return Config(**resolved)


def _resolve_dict(obj: dict) -> dict:
    """Recursively resolve env vars in dict values."""
    result = {}
    for k, v in obj.items():
        if isinstance(v, str):
            result[k] = _resolve_env(v)
        elif isinstance(v, dict):
            result[k] = _resolve_dict(v)
        elif isinstance(v, list):
            result[k] = [
                _resolve_dict(item) if isinstance(item, dict)
                else _resolve_env(item) if isinstance(item, str)
                else item
                for item in v
            ]
        else:
            result[k] = v
    return result


def load_config(config_path: Path | None = None) -> Config:
    """Load the config from disk, or return a default Config."""
    path = config_path or get_config_path()
    if not path.exists():
        logger.info("No config found at {}, using defaults", path)
        return Config()

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return Config(**data)


def save_config(config: Config, config_path: Path | None = None) -> None:
    """Save config to disk."""
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(exclude_none=True), f, indent=2, ensure_ascii=False)
