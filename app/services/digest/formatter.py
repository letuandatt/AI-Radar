"""Channel-specific rendering without LLM calls or modifications to the archive."""

import re
from urllib.parse import quote

from app.integrations.email.template_renderer import TemplateRenderer
from app.services.digest.models import DailyDigest
from app.services.digest.organizer import ContentOrganizer
from app.services.email.models import http_url


def prepared(digest: DailyDigest) -> DailyDigest:
    """Organize a display copy and validate every rendered external link."""
    result = ContentOrganizer().organize(digest)
    urls = [i.source_url for s in result.sections for i in s.items]
    urls += [c.source_url for s in result.intelligence.sections for c in s.citations]
    for url in urls:
        http_url(url)
    return result


def markdown_text(value: str) -> str:
    """Keep untrusted text from opening Markdown links, images or HTML tags."""
    return re.sub(r"([\\`*_{}\[\]()<>#!~])", r"\\\1", " ".join(value.split()))


class ZaloFormatter:
    """Compact Markdown; complete item links are never cut at the length boundary."""

    def format(self, digest: DailyDigest) -> str:
        """Render at most 2000 code points, reporting items omitted for space."""
        digest = prepared(digest)
        body = f"# AI-Radar · {digest.digest_date}\n"
        shown = 0
        for section in digest.sections:
            heading_added = False
            for item in section.items:
                url = quote(item.source_url, safe=":/?&=#%+@,;~!-._")
                block = (
                    ("\n## " + section.section_title + "\n" if not heading_added else "")
                    + f"\n- [{markdown_text(item.title[:160])}]({url})\n"
                    + markdown_text(item.summary)
                    + "\n"
                )
                if len(body + block) <= 1900:
                    body += block
                    shown += 1
                    heading_added = True
        omitted = digest.total_items - shown
        if omitted:
            body += f"\n{omitted} more items in the full email/web digest.\n"
        if not digest.total_items:
            body += "\nNo items met the selection policy for this day.\n"
        return body


class EmailFormatter:
    """Render selected items and saved intelligence with source citations."""

    def format_html(self, digest: DailyDigest) -> str:
        """Escape external content; never evaluate it as HTML or a template."""
        return TemplateRenderer().render("digest.html.jinja2", digest=prepared(digest))

    def format_plain(self, digest: DailyDigest) -> str:
        """Produce the text alternative, retaining source URLs."""
        return TemplateRenderer().render("digest.txt.jinja2", digest=prepared(digest))
