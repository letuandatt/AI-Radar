"""Content Sanitization Service for SEC-001 (Prompt Injection Defense).

This service sanitizes untrusted content BEFORE it enters the LLM prompt.
It is the first line of defense against prompt injection attacks.

Sanitization steps:
1. Strip residual HTML tags (BeautifulSoup)
2. Remove control characters
3. Remove prompt injection patterns (regex)
4. Truncate to max length (token overflow prevention)
5. Normalize whitespace
"""

import re
import unicodedata

from bs4 import BeautifulSoup

from app.core.logger import get_logger

logger = get_logger(__name__)

# Maximum content length in characters (prevents token overflow)
_MAX_CONTENT_LENGTH = 10_000

# Regex patterns that indicate prompt injection attempts
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?prior\s+instructions", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?previous\s+(instructions|context)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|in)", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"assistant\s*:\s*", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"output\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"print\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"what\s+(is|are)\s+your\s+(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"repeat\s+(the\s+)?(above|previous)\s+(text|instructions)", re.IGNORECASE),
]

# Regex to remove control characters (except newline and tab)
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Regex to collapse multiple whitespace
_WHITESPACE_PATTERN = re.compile(r"\s+")


class ContentSanitizer:
    """Sanitizes untrusted content before LLM processing.

    This is the pre-processing layer of SEC-001 (Trust Boundary).
    It removes potentially dangerous content before it enters the LLM prompt.

    Thread Safety:
        This class is stateless and thread-safe.
    """

    def sanitize(self, content: str) -> str:
        """Sanitize untrusted content for safe LLM processing.

        Args:
            content: Raw untrusted content string.

        Returns:
            Sanitized content string, safe for LLM input.
        """
        if not content:
            return ""

        # Step 1: Strip residual HTML tags
        content = self._strip_html(content)

        # Step 2: Remove control characters
        content = _CONTROL_CHAR_PATTERN.sub("", content)

        # Step 3: Unicode NFC normalization
        content = unicodedata.normalize("NFC", content)

        # Step 4: Remove injection patterns
        content = self._remove_injection_patterns(content)

        # Step 5: Truncate to max length
        if len(content) > _MAX_CONTENT_LENGTH:
            logger.info(
                "Content truncated: %d -> %d chars",
                len(content),
                _MAX_CONTENT_LENGTH,
            )
            content = content[:_MAX_CONTENT_LENGTH]

        # Step 6: Normalize whitespace (preserve paragraph structure)
        content = self._normalize_whitespace(content)

        return content.strip()

    def _strip_html(self, content: str) -> str:
        """Strip HTML tags using BeautifulSoup.

        This handles any residual HTML that wasn't removed in Sprint 10.
        Uses BeautifulSoup for robust parsing (handles nested tags, entities, etc.)

        Args:
            content: Content potentially containing HTML.

        Returns:
            Plain text with HTML removed.
        """
        try:
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            return text
        except Exception as e:
            logger.warning("HTML stripping failed: %s", e)
            return content

    def _remove_injection_patterns(self, content: str) -> str:
        """Remove prompt injection patterns from content.

        Replaces detected injection patterns with [FILTERED] marker.
        This neutralizes the injection while preserving context that
        the content contained suspicious text.

        Args:
            content: Content to scan for injection patterns.

        Returns:
            Content with injection patterns replaced.
        """
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(content):
                logger.warning(
                    "Injection pattern detected and filtered: %s",
                    pattern.pattern,
                )
                content = pattern.sub("[FILTERED]", content)

        return content

    def _normalize_whitespace(self, content: str) -> str:
        """Normalize whitespace while preserving paragraph structure.

        - Collapses multiple spaces/tabs into single space
        - Preserves paragraph breaks (double newlines)
        - Collapses 3+ newlines into 2

        Args:
            content: Content to normalize.

        Returns:
            Content with normalized whitespace.
        """
        # Collapse multiple newlines (3+) into double newline
        content = re.sub(r"\n{3,}", "\n\n", content)

        # Process each line: collapse horizontal whitespace
        lines = content.split("\n")
        lines = [_WHITESPACE_PATTERN.sub(" ", line).strip() for line in lines]
        content = "\n".join(lines)

        return content
