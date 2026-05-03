"""Jinja2-based prompt template rendering."""

from jinja2 import Environment, BaseLoader


_env = Environment(loader=BaseLoader())


def render_template(name: str, **kwargs) -> str:
    """Render a named template. Falls back to built-in templates for identity/skills."""
    builtins = get_builtin_templates()
    if name in builtins:
        template = _env.from_string(builtins[name])
        return template.render(**kwargs)

    # For file-based templates, try loading from disk
    from pathlib import Path
    import os

    template_path = Path(__file__).parent.parent / "templates" / name
    if template_path.exists():
        template = _env.from_string(template_path.read_text(encoding="utf-8"))
        return template.render(**kwargs)

    raise FileNotFoundError(f"Template not found: {name}")


def get_builtin_templates() -> dict[str, str]:
    """Return built-in prompt templates."""
    return {
        "agent/identity.md": _IDENTITY_TEMPLATE,
        "agent/platform_policy.md": _PLATFORM_POLICY_TEMPLATE,
        "agent/skills_section.md": _SKILLS_SECTION_TEMPLATE,
    }


_IDENTITY_TEMPLATE = """You are OpenCow, an AI assistant running on the user's local machine.

## Environment
- Workspace: {{ workspace_path }}
- Platform: {{ runtime }}
- Current timezone: {{ timezone | default("UTC") }}

## Capabilities
You have access to tools for:
- Reading, writing, and editing files in the workspace
- Searching code with grep and glob
- Executing shell commands
- Searching and fetching web content

## Guidelines
- Be direct and concise. No unnecessary preamble.
- Use tools when you need real information — don't guess.
- When editing files, use exact string replacements.
- Respect the user's workspace boundaries.
- If you're unsure, ask rather than assuming.

{{ platform_policy }}
"""

_PLATFORM_POLICY_TEMPLATE = """{% if system == "Windows" %}
You are running on Windows. Use PowerShell-compatible commands in exec().
Prefer forward slashes in file paths where possible.
{% else %}
You are running on {{ system }}. Use standard Unix shell commands in exec().
{% endif %}
"""

_SKILLS_SECTION_TEMPLATE = """## Available Skills
The following skills are available. Ask the user to enable them if relevant:

{{ skills_summary }}
"""
