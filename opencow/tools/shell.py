"""Shell execution tool."""

import re
import subprocess
import platform

from langchain_core.tools import tool
from pydantic import BaseModel, Field

# Patterns that suggest destructive or dangerous commands.
# These are heuristics, not a security boundary — a local agent needs shell access to be useful.
_DANGEROUS_PATTERNS = [
    # Unix: recursive force remove on root or home
    r"\brm\s+-[^\w]*rf\s+(/(\s|$)|~(\s|$)|/[a-zA-Z])",
    r"\brm\s+-[^\w]*rf\s+/",
    # Windows: recursive force remove on system paths
    r"\brmdir\s+/[sS]\s+/[qQ]\s+[C-Zc-z]:\\",
    r"\bdel\s+/[fF]\s+/[sS]\s+[C-Zc-z]:\\",
    # Disk formatting
    r"\bmkfs\b",
    r"\bformat\s+[C-Zc-z](\s|$)",
    # Fork bomb patterns
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",
    # Direct destructive write to block devices
    r"\bdd\s+if=.*\s+of=/dev/(sd|hd|nvme|mmcblk|xvd)",
    # Scary chmod on system dirs
    r"\bchmod\s+.*777\s+/",
    # Curl/wget piped to shell (supply-chain risk)
    r"\b(curl|wget)\s+.*\s*\|.*\s*(bash|sh|zsh)\b",
]

_DANGEROUS_RE = re.compile("|".join(_DANGEROUS_PATTERNS), re.IGNORECASE)


class ExecInput(BaseModel):
    command: str = Field(description="The shell command to execute")


@tool(args_schema=ExecInput)
def exec_cmd(command: str) -> str:
    """Execute a shell command. Use for running build commands, git operations, etc.

    Destructive commands (rm -rf /, format, dd to block devices, curl|bash, etc.)
    are blocked automatically. Avoid these patterns in your commands.
    """
    if _DANGEROUS_RE.search(command):
        return (
            "Error: command blocked — it matches a destructive pattern "
            "(rm -rf /, format, dd to block device, curl|bash, etc.). "
            "If you believe this is safe, rephrase the command to avoid "
            "the dangerous pattern or ask the user to run it manually."
        )

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
