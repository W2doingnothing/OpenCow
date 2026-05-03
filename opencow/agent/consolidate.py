"""Consolidator and AutoCompact — stub for Phase 2."""


class Consolidator:
    """Compresses conversation history into summaries."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def consolidate(self, session, ratio: float = 0.5):
        pass


class AutoCompact:
    """Detects idle sessions and triggers archival."""

    def __init__(self, *args, **kwargs) -> None:
        pass
