"""Skills loader — stub for Phase 2."""

from pathlib import Path


class SkillsLoader:
    """Loads SKILL.md files from workspace/skills/."""

    def __init__(self, workspace: Path, disabled_skills: set[str] | None = None) -> None:
        self.workspace = workspace
        self.skills_dir = workspace / "skills"
        self.disabled_skills = disabled_skills or set()

    def get_always_skills(self) -> list[str]:
        return []

    def load_skills_for_context(self, names: list[str]) -> str:
        return ""

    def build_skills_summary(self, exclude: set[str] | None = None) -> str:
        return ""
