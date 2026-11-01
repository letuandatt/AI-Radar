"""Render repository-owned templates with explicit HTML escaping."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


class TemplateRenderer:
    """Template paths are relative to this module, independent of the working directory."""

    def render(self, name: str, **context: Any) -> str:
        """Render one of the two trusted digest templates."""
        if name not in {"digest.html.jinja2", "digest.txt.jinja2"}:
            raise ValueError("Unsupported email template")
        environment = Environment(
            loader=FileSystemLoader(Path(__file__).resolve().parents[2] / "templates" / "email"),
            autoescape=name.endswith(".html.jinja2"),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        return environment.get_template(name).render(**context)
