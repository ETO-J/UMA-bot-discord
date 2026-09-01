"""Skill file loader for the drawing assistant.

Loads the always-on "index" routing rule plus individual sub-skills on
demand. The index tells the model when to request which sub-skill; only
requested (or always-on) sub-skills are injected into the system prompt,
keeping token usage proportional to the task instead of the full corpus.
"""
import logging
from pathlib import Path

from config import ARTIST_SKILLS_DIR

logger = logging.getLogger(__name__)

INDEX_FILENAME = "_index.txt"
DEFAULT_SKILLS = ("prompt_structure_guide",)


class SkillManager:
    def __init__(self, skills_dir: Path = None):
        self.skills_dir = skills_dir or ARTIST_SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def _read(self, filename: str) -> str:
        path = self.skills_dir / filename
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning("Failed to load skill %s: %s", filename, e)
            return ""

    @staticmethod
    def _normalize(name: str) -> str:
        name = (name or "").strip()
        if name.lower().endswith(".txt"):
            name = name[: -len(".txt")]
        return name

    def load_index(self) -> str:
        """Return the always-on routing rule (index file contents)."""
        return self._read(INDEX_FILENAME)

    def load_skill(self, name: str) -> str:
        """Load a single sub-skill by its stem name (with or without .txt)."""
        name = self._normalize(name)
        if name == self._normalize(INDEX_FILENAME):
            return self.load_index()
        return self._read(f"{name}.txt")

    def has_skill(self, name: str) -> bool:
        name = self._normalize(name)
        return (self.skills_dir / f"{name}.txt").exists()

    def list_skills(self) -> list[str]:
        """List sub-skill stems, excluding the index file."""
        return [
            f.stem
            for f in sorted(self.skills_dir.glob("*.txt"))
            if f.name != INDEX_FILENAME
        ]

    def get_skill_list(self) -> list[str]:
        """Compatibility alias: list of sub-skill names (no .txt)."""
        return self.list_skills()

    def load_skills(self) -> str:
        """Compatibility: concatenate every non-index skill into one string."""
        parts = []
        for f in sorted(self.skills_dir.glob("*.txt")):
            if f.name == INDEX_FILENAME:
                continue
            content = self._read(f.name)
            if content:
                parts.append(f"=== {f.stem} ===\n{content}")
        combined = "\n\n".join(parts)
        logger.info("load_skills (full) returned %d chars", len(combined))
        return combined

    def reload(self) -> str:
        """Compatibility alias for load_skills."""
        return self.load_skills()


skill_manager = SkillManager()
