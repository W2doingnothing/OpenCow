"""Shell execution tool."""

import subprocess
import platform

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ExecInput(BaseModel):
    command: str = Field(description="The shell command to execute")


@tool(args_schema=ExecInput)
def exec_cmd(command: str) -> str:
    """Execute a shell command. Use for running build commands, git operations, etc."""
    system = platform.system()
    if system == "Windows":
        shell_cmd = ["powershell", "-Command", command]
    else:
        shell_cmd = ["bash", "-c", command]

    try:
        result = subprocess.run(
            shell_cmd,
            capture_output=True,
            text=True,
            timeout=120,
            # Don't force utf-8; let Python use the system locale (e.g. GBK on Windows)
            errors="replace",
        )
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        output = stdout
        if stderr:
            if output:
                output += "\n[stderr]\n" + stderr
            else:
                output = stderr
        if not output:
            return f"Command completed with exit code {result.returncode} (no output)"
        max_chars = 8000
        if len(output) > max_chars:
            output = output[:max_chars] + f"\n... (truncated, {len(output)} total chars)"
        return output
    except subprocess.TimeoutExpired:
        return "Error: command timed out (120s)"
