"""Prompt Builder - constructs prompts with variables and security boundaries."""

import html
import re
from typing import Any

from app.core.logger import get_logger

logger = get_logger(__name__)


class PromptBuildError(Exception):
    """Raised when prompt building fails due to missing variables."""

    pass


class PromptBuilder:
    """
    Builds prompts from templates using simple variable substitution.
    Supports <untrusted_data> boundaries for security (SEC-001).
    """

    def __init__(self, template: str) -> None:
        self._template = template
        self._variables: dict[str, Any] = {}

    @classmethod
    def from_string(cls, template: str) -> "PromptBuilder":
        return cls(template)

    def with_variable(self, key: str, value: Any) -> "PromptBuilder":
        """Add a single variable to the prompt."""
        self._variables[key] = value
        return self

    def with_variables(self, variables: dict[str, Any]) -> "PromptBuilder":
        """Add multiple variables to the prompt."""
        self._variables.update(variables)
        return self

    def with_untrusted_data(self, data: str) -> "PromptBuilder":
        """
        Wrap data in <untrusted_data> tags.
        Maps to the 'untrusted_data' or 'content_text' variable.
        """
        data = html.escape(data)

        # Escape any existing tags in the data to prevent injection
        safe_data = data.replace("<untrusted_data>", "&lt;untrusted_data&gt;")
        safe_data = safe_data.replace("</untrusted_data>", "&lt;/untrusted_data&gt;")

        wrapped = f"<untrusted_data>\n{safe_data}\n</untrusted_data>"
        self._variables["untrusted_data"] = wrapped
        self._variables["content_text"] = wrapped
        return self

    def build(self) -> str:
        """
        Render the final prompt.
        Uses simple {variable} replacement.
        """
        # Find all {key} in template
        required_keys = set(re.findall(r"\{([a-zA-Z0-9_]+)}", self._template))

        missing = required_keys - set(self._variables.keys())
        if missing:
            raise PromptBuildError(f"Missing variables for prompt build: {missing}")

        result = self._template
        for key, value in self._variables.items():
            # Replace {key} with string value
            result = result.replace(f"{{{key}}}", str(value))

        return result
