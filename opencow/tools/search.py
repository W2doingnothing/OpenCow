"""Search tools: grep and glob."""

import subprocess
from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, Field

# Global workspace root, set by OpenCow
_workspace: Path = Path(".")


def set_workspace(path: str) -> None:
    global _workspace
    _workspace = Path(path).expanduser().resolve()


class GrepInput(BaseModel):
    pattern: str = Field(description="The regex pattern to search for (ripgrep syntax)")
    path: str = Field(default=".", description="The directory or file to search in")


class GlobInput(BaseModel):
    pattern: str = Field(description="The glob pattern (e.g., '**/*.py', 'src/**/*.ts')")


@tool(args_schema=GrepInput)
def grep(pattern: str, path: str = ".") -> str:
    """Search file contents using ripgrep. Use regex patterns to find text in files."""
    p = _workspace / path if not Path(path).is_absolute() else Path(path)
    p = p.expanduser().resolve()
    try:
        result = subprocess.run(
            ["rg", "--no-heading", "-n", "--color=never", pattern, str(p)],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        output = result.stdout.strip()
        if not output:
            return f"No matches found for pattern: {pattern}"
        lines = output.split("\n")[:50]
        if len(lines) == 50:
            lines.append("... (output truncated at 50 lines)")
        return "\n".join(lines)
    except FileNotFoundError:
        return "Error: ripgrep (rg) is not installed. Install it from https://github.com/BurntSushi/ripgrep"
    except subprocess.TimeoutExpired:
        return "Error: grep timed out"


@tool(args_schema=GlobInput)
def glob(pattern: str) -> str:
    """Find files matching a glob pattern. Use for fuzzy file search."""
    matches = sorted(_workspace.glob(pattern))
    if not matches:
        return f"No files matched pattern: {pattern}"
    lines = [f"  {m}" for m in matches[:50]]
    if len(matches) > 50:
        lines.append(f"  ... and {len(matches) - 50} more")
    return "\n".join([f"Files matching '{pattern}':"] + lines)
