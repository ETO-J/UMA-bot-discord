"""Skill file loader for the drawing assistant.

Loads all .txt files from the skills directory and concatenates them
into a single context string for the system prompt.
"""
import logging
from pathlib import Path

from config import ARTIST_SKILLS_DIR

logger = logging.getLogger(__name__)


class SkillManager:
    def __init__(self, skills_dir: Path = None):
        self.skills_dir = skills_dir or ARTIST_SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def load_skills(self) -> str:
        """Load and concatenate all skill files into one context string."""
        parts = []
        for f in sorted(self.skills_dir.glob("*.txt")):
            try:
                content = f.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"=== {f.name} ===\n{content}")
            except Exception as e:
                logger.warning("Failed to load skill %s: %s", f.name, e)
        combined = "\n\n".join(parts)
        logger.info("Loaded %d skill files (%d chars)", len(parts), len(combined))
        return combined

    def get_skill_list(self) -> list[str]:
        """Return list of skill file names."""
        return [f.name for f in sorted(self.skills_dir.glob("*.txt"))]

    def reload(self) -> str:
        """Reload skills from disk (same as load_skills)."""
        return self.load_skills()


skill_manager = SkillManager()
