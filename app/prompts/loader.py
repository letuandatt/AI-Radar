"""Prompt Loader - loads prompt templates from disk."""

from pathlib import Path

from app.core.logger import get_logger

logger = get_logger(__name__)

# Base directory for prompts (root of project / prompts)
_PROMPTS_BASE_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class PromptNotFoundError(Exception):
    """Raised when a prompt template cannot be found."""

    pass


class PromptLoader:
    """Loads and caches prompt templates from disk."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or _PROMPTS_BASE_DIR
        self._cache: dict[str, str] = {}

    def load(self, prompt_name: str) -> str:
        """
        Load a prompt template by name.

        Args:
            prompt_name: Dot-separated or slash-separated path relative to prompts dir.
                         Example: 'analysis/content_analysis'
                                      -> prompts/analysis/content_analysis.md

        Returns:
            The prompt template string.
        """
        if prompt_name in self._cache:
            return self._cache[prompt_name]

        # Normalize path
        parts = prompt_name.replace(".", "/").split("/")
        # Add .md extension if not present
        if not parts[-1].endswith(".md"):
            parts[-1] = f"{parts[-1]}.md"

        file_path = self._base_dir.joinpath(*parts)

        if not file_path.exists():
            raise PromptNotFoundError(f"Prompt template not found: {file_path}")

        content = file_path.read_text(encoding="utf-8")
        self._cache[prompt_name] = content
        logger.debug("Loaded prompt '%s' from %s", prompt_name, file_path)
        return content

    def list_prompts(self) -> list[str]:
        """List all available prompt names (without .md extension)."""
        prompts = []  # type: ignore[var-annotated]
        if not self._base_dir.exists():
            return prompts

        for path in self._base_dir.rglob("*.md"):
            rel_path = path.relative_to(self._base_dir)
            # Convert path to dot/slash notation without .md
            name = str(rel_path.with_suffix("")).replace("\\", "/")
            prompts.append(name)

        return sorted(prompts)

    def clear_cache(self) -> None:
        """Clear the in-memory prompt cache."""
        self._cache.clear()
