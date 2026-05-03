"""Context builder: assembles the system prompt and runtime context."""

import platform
from pathlib import Path

from opencow.utils.helpers import current_time_str
from opencow.utils.prompt_templates import render_template


class ContextBuilder:
    """Builds the system prompt and runtime context for the agent."""

    BOOTSTRAP_FILES = ["SOUL.md", "USER.md"]

    def __init__(self, workspace: Path, timezone: str | None = None) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.timezone = timezone or "UTC"

    def build_system_prompt(self, channel: str | None = None) -> str:
        """Build the full system prompt from identity, bootstrap files, and memory."""
        parts = [self._get_identity(channel=channel)]

        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        memory = self._load_memory()
        if memory:
            parts.append(f"# Memory\n\n{memory}")

        return "\n\n---\n\n".join(parts)

    def build_runtime_context(
        self,
        channel: str | None = None,
        chat_id: str | None = None,
        sender_id: str | None = None,
        session_summary: str | None = None,
    ) -> str:
        """Build runtime metadata injected before the user message."""
        lines = [f"Current Time: {current_time_str(self.timezone)}"]
        if channel and chat_id:
            lines += [f"Channel: {channel}", f"Chat ID: {chat_id}"]
        if sender_id:
            lines += [f"Sender ID: {sender_id}"]
        if session_summary:
            lines += ["", "[Resumed Session]", session_summary]
        return "[Runtime Context]\n" + "\n".join(lines) + "\n[/Runtime Context]"

    def _get_identity(self, channel: str | None = None) -> str:
        """Build the core identity section."""
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        return render_template(
            "agent/identity.md",
            workspace_path=str(self.workspace),
            runtime=runtime,
            platform_policy=render_template("agent/platform_policy.md", system=system),
            timezone=self.timezone,
        )

    def _load_bootstrap_files(self) -> str | None:
        """Load SOUL.md and USER.md from the workspace."""
        parts = []
        for filename in self.BOOTSTRAP_FILES:
            path = self.workspace / filename
            if path.exists():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"## {filename}\n\n{content}")
        return "\n\n".join(parts) if parts else None

    def _load_memory(self) -> str | None:
        """Load MEMORY.md from the workspace."""
        path = self.workspace / "memory" / "MEMORY.md"
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                return content
        return None
