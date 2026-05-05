"""Filesystem tools: read_file, write_file, edit_file, list_dir."""

from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from opencow.utils.document import parse_document

# Global config, set by OpenCow
_restrict_to_workspace: bool = True
_workspace_root: Path = Path(".")


def set_workspace_config(workspace: str, restrict: bool) -> None:
    global _workspace_root, _restrict_to_workspace
    _workspace_root = Path(workspace).expanduser().resolve()
    _restrict_to_workspace = restrict


def _resolve_path(path_str: str) -> Path:
    p = Path(path_str).expanduser().resolve()
    if _restrict_to_workspace:
        # Use strict path containment check — no prefix-match bypass
        try:
            p.relative_to(_workspace_root)
        except ValueError:
            raise PermissionError(f"Access denied: {path_str} is outside workspace {_workspace_root}")
        # Resolve symlinks to prevent symlink escapes
        resolved = p.resolve()
        try:
            resolved.relative_to(_workspace_root.resolve())
        except ValueError:
            raise PermissionError(f"Access denied: {path_str} resolves outside workspace")
    return p


class ReadFileInput(BaseModel):
    file_path: str = Field(description="The path to the file to read")


class WriteFileInput(BaseModel):
    file_path: str = Field(description="The path to write to")
    content: str = Field(description="The content to write")


class EditFileInput(BaseModel):
    file_path: str = Field(description="The path to edit")
    old_string: str = Field(description="The exact text to replace")
    new_string: str = Field(description="The replacement text")


class ListDirInput(BaseModel):
    path: str = Field(default=".", description="The directory to list")


@tool(args_schema=ReadFileInput)
def read_file(file_path: str) -> str:
    """Read a file from the filesystem. Supports PDF, DOCX, TXT, and Markdown."""
    p = _resolve_path(file_path)
    if not p.exists():
        return f"Error: file not found: {file_path}"
    if p.is_dir():
        return f"Error: {file_path} is a directory, use list_dir instead"

    # Use document parser for PDF/DOCX
    if p.suffix.lower() in (".pdf", ".docx", ".doc"):
        return parse_document(str(p))

    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: cannot read {file_path} as text (binary file)"


@tool(args_schema=WriteFileInput)
def write_file(file_path: str, content: str) -> str:
    """Write content to a file. Creates or overwrites the file."""
    p = _resolve_path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Successfully wrote {len(content)} chars to {file_path}"


@tool(args_schema=EditFileInput)
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """Make an exact string replacement in an existing file."""
    p = _resolve_path(file_path)
    if not p.exists():
        return f"Error: file not found: {file_path}"
    content = p.read_text(encoding="utf-8")
    if old_string not in content:
        return f"Error: old_string not found in {file_path}. Use read_file to verify the exact content."
    if old_string == new_string:
        return "No change: old_string and new_string are identical."
    count = content.count(old_string)
    if count > 1:
        return (
            f"Error: old_string appears {count} times in {file_path}. "
            f"Please provide more surrounding context to make the match unique."
        )
    new_content = content.replace(old_string, new_string, 1)
    p.write_text(new_content, encoding="utf-8")
    return f"Successfully edited {file_path}"


@tool(args_schema=ListDirInput)
def list_dir(path: str = ".") -> str:
    """List the contents of a directory."""
    p = _resolve_path(path)
    if not p.exists():
        return f"Error: directory not found: {path}"
    if not p.is_dir():
        return f"Error: {path} is not a directory"
    items = []
    for child in sorted(p.iterdir()):
        suffix = "/" if child.is_dir() else ""
        items.append(f"  {child.name}{suffix}")
    if not items:
        return f"{path} is empty"
    return "\n".join([f"Contents of {path}:"] + items)
