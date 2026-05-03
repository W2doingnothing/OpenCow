"""Skills loader for agent capabilities."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

# YAML frontmatter: opening ---, body (group 1), closing ---
_STRIP_FRONTMATTER = re.compile(
    r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?",
    re.DOTALL,
)

BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillsLoader:
    """Loads SKILL.md files from workspace/skills/ and built-in skills.

    Skills are markdown files with YAML frontmatter that teach the agent
    how to use specific tools or perform certain tasks.
    """

    def __init__(
        self,
        workspace: Path,
        builtin_skills_dir: Path | None = None,
        disabled_skills: set[str] | None = None,
    ) -> None:
        self.workspace = workspace
        self.workspace_skills_dir = workspace / "skills"
        self.builtin_skills_dir = builtin_skills_dir or BUILTIN_SKILLS_DIR
        self.disabled_skills = disabled_skills or set()

    def list_skills(self) -> list[dict[str, str]]:
        """List all available skills with metadata."""
        entries: list[dict[str, str]] = []
        # Built-in skills
        entries.extend(self._scan_dir(self.builtin_skills_dir, "builtin"))
        # Workspace skills (override built-in with same name)
        workspace_skills = {s["name"]: s for s in self._scan_dir(self.workspace_skills_dir, "workspace")}
        # Merge: workspace overrides builtin
        result = []
        seen = set()
        for s in workspace_skills.values():
            if s["name"] not in self.disabled_skills:
                result.append(s)
                seen.add(s["name"])
        for s in entries:
            if s["name"] not in seen and s["name"] not in self.disabled_skills:
                result.append(s)
        return result

    def get_always_skills(self) -> list[str]:
        """Return names of skills marked as always-active."""
        names = []
        for s in self.list_skills():
            frontmatter = self._read_frontmatter(Path(s["path"]))
            if frontmatter.get("always"):
                names.append(s["name"])
        return names

    def load_skills_for_context(self, names: list[str]) -> str:
        """Load and return the full content of the named skills."""
        parts = []
        for s in self.list_skills():
            if s["name"] in names:
                content = self._read_body(Path(s["path"]))
                if content:
                    parts.append(f"## Skill: {s['name']}\n\n{content}")
        return "\n\n".join(parts)

    def build_skills_summary(self, exclude: set[str] | None = None) -> str:
        """Build a summary of available skills for the system prompt."""
        exclude = exclude or set()
        available = [s for s in self.list_skills() if s["name"] not in exclude]
        if not available:
            return ""
        lines = []
        for s in available:
            frontmatter = self._read_frontmatter(Path(s["path"]))
            desc = frontmatter.get("description", "")
            lines.append(f"- **{s['name']}** ({s['source']}): {desc}")
        return "\n".join(lines)

    def get_skill(self, name: str) -> dict[str, str] | None:
        """Get a single skill by name."""
        for s in self.list_skills():
            if s["name"] == name:
                return s
        return None

    # -- internal ------------------------------------------------------------

    def _scan_dir(self, base: Path, source: str) -> list[dict[str, str]]:
        if not base.exists():
            return []
        entries = []
        for skill_dir in sorted(base.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            entries.append({
                "name": skill_dir.name,
                "path": str(skill_file),
                "source": source,
            })
        return entries

    def _read_frontmatter(self, path: Path) -> dict:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return {}
        match = _STRIP_FRONTMATTER.match(text)
        if match:
            try:
                return yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                return {}
        return {}

    def _read_body(self, path: Path) -> str:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return ""
        match = _STRIP_FRONTMATTER.match(text)
        if match:
            return text[match.end():].strip()
        return text.strip()
