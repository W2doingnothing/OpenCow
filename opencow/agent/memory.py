"""Memory system — stub for Phase 2."""

from pathlib import Path


class MemoryStore:
    """Pure file I/O for memory files: MEMORY.md, history.jsonl, SOUL.md, USER.md."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.memory_dir = workspace / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "history.jsonl"

    def get_memory_context(self) -> str:
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def read_memory(self) -> str:
        return self.get_memory_context()

    def append_history(self, entry: str) -> None:
        import json
        from datetime import datetime

        record = {"timestamp": datetime.now().isoformat(), "content": entry}
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_unprocessed_history(self, since_cursor: int = 0) -> list[dict]:
        entries = []
        if self.history_file.exists():
            for line in self.history_file.read_text(encoding="utf-8").strip().split("\n"):
                if line:
                    import json
                    entries.append(json.loads(line))
        return entries[since_cursor:]

    def get_last_dream_cursor(self) -> int:
        return 0
