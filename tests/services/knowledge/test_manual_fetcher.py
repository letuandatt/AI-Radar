"""Outbound HTTP security checks use mocked DNS and transport only."""

from unittest.mock import AsyncMock

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.services.knowledge.url_fetcher import (
    MAX_BYTES,
    FetchError,
    PublicPageFetcher,
    canonical_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/a",
        "http://user:pass@example.com",
        "http://127.0.0.1",
        "http://[::1]",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost./",
        "https://test.local",
        "http://10.0.0.1",
        "http://[::ffff:127.0.0.1]",
        "http://[64:ff9b::7f00:1]",
        "http://224.0.0.1",
        "https://example.com:6333/",
        "https://example.com\\@127.0.0.1",
        "https://example.com\n/path",
    ],
)
def test_reject_unsafe_syntax(url):
    with pytest.raises(FetchError):
        canonical_url(url)


@pytest.mark.parametrize(
    "addresses", [["127.0.0.1"], ["93.184.216.34", "10.0.0.1"], ["::1"], ["100.64.0.1"], []]
)
async def test_reject_dns_targets_before_connecting(addresses, httpx_mock):
    fetcher = PublicPageFetcher()
    fetcher._resolve = AsyncMock(return_value=addresses)
    with pytest.raises(FetchError):
        await fetcher.fetch("https://example.org/article")
    assert httpx_mock.get_requests() == []


async def test_pins_connection_preserves_tls_host_and_normalizes_html(httpx_mock: HTTPXMock):
    fetcher = PublicPageFetcher()
    fetcher._resolve = AsyncMock(return_value=["93.184.216.34"])
    httpx_mock.add_response(
        url="https://93.184.216.34/a",
        headers={"content-type": "text/html"},
        content=b"<title>Title</title><nav>omit</nav><article>"
        + b"Useful research text. " * 10
        + b"<script>bad()</script></article>",
    )
    result = await fetcher.fetch("https://example.org/a#section")
    request = httpx_mock.get_request()
    assert request.headers["host"] == "example.org"
    assert request.extensions["sni_hostname"] == "example.org"
    assert request.headers["accept-encoding"] == "identity"
    assert "authorization" not in request.headers
    assert "cookie" not in request.headers
    assert result.url == "https://example.org/a"
    assert result.title == "Title"
    assert "omit" not in result.text and "bad()" not in result.text
    fetcher._resolve.assert_awaited_once()


async def test_revalidates_redirect_dns_without_forwarding_cookies(httpx_mock):
    fetcher = PublicPageFetcher()
    fetcher._resolve = AsyncMock(side_effect=[["93.184.216.34"], ["127.0.0.1"]])
    httpx_mock.add_response(
        status_code=302,
        headers={"location": "https://other.example/secret", "set-cookie": "secret=value"},
    )
    with pytest.raises(FetchError):
        await fetcher.fetch("https://example.org/a")
    assert len(httpx_mock.get_requests()) == 1


async def test_public_redirect_is_bounded_and_fetches_final_content(httpx_mock):
    fetcher = PublicPageFetcher()
    fetcher._resolve = AsyncMock(return_value=["93.184.216.34"])
    httpx_mock.add_response(status_code=302, headers={"location": "/final", "set-cookie": "a=b"})
    httpx_mock.add_response(headers={"content-type": "text/plain"}, content=b"Readable text " * 10)
    page = await fetcher.fetch("https://example.org/a")
    assert page.url == "https://example.org/final"
    assert "cookie" not in httpx_mock.get_requests()[1].headers


@pytest.mark.parametrize(
    "headers,body",
    [
        ({"content-type": "application/pdf"}, b"PDF"),
        ({"content-type": "text/html", "content-encoding": "gzip"}, b"x"),
        ({"content-type": "text/html", "content-length": str(MAX_BYTES + 1)}, b"x"),
        ({"content-type": "text/plain"}, b"x" * (MAX_BYTES + 1)),
        ({"content-type": "text/plain"}, b"short"),
    ],
    ids=["unsupported-mime", "compressed", "large-header", "large-body", "short-text"],
)
async def test_reject_unreadable_or_unbounded_responses(headers, body, httpx_mock):
    fetcher = PublicPageFetcher()
    fetcher._resolve = AsyncMock(return_value=["93.184.216.34"])
    httpx_mock.add_response(headers=headers, stream=httpx.ByteStream(body))
    with pytest.raises(FetchError):
        await fetcher.fetch("https://example.org/a")


async def test_redirect_limit_and_transport_failure_are_safe(httpx_mock):
    fetcher = PublicPageFetcher()
    fetcher._resolve = AsyncMock(return_value=["93.184.216.34"])
    for _ in range(4):
        httpx_mock.add_response(status_code=302, headers={"location": "/loop"})
    with pytest.raises(FetchError, match="Too many redirects"):
        await fetcher.fetch("https://example.org/a")
    httpx_mock.add_exception(httpx.ConnectError("upstream secret"))
    with pytest.raises(FetchError, match="could not be fetched") as error:
        await fetcher.fetch("https://example.org/a")
    assert "secret" not in str(error.value)


def test_text_limit_is_explicit():
    page = PublicPageFetcher._parse("https://example.org/a", b"word " * 3000, "text/plain")
    assert page.truncated and len(page.text) == 10_000


def test_canonicalization_preserves_encoded_paths_and_query():
    assert canonical_url("https://EXAMPLE.org/a%2Fb?q=x%2Fy#part") == (
        "https://example.org/a%2Fb?q=x%2Fy"
    )
    assert canonical_url("https://example.org") == "https://example.org/"


def test_html_preserves_reading_blocks_and_one_math_representation():
    body = b"""
    <article><h2>Abstract</h2>
    <p>A sufficiently long research paragraph with <strong>important</strong> evidence.</p>
    <p>Coverage improves from <math><semantics><mn>0.625</mn>
    <annotation encoding="application/x-tex">0.625</annotation></semantics></math>.</p>
    <ul><li><p>First useful finding.</p></li><li>Second useful finding.</li></ul>
    <!-- This comment is not article text. -->
    </article>"""
    page = PublicPageFetcher._parse("https://example.org/paper", body, "text/html")

    assert page.text.startswith("## Abstract\n\n")
    assert "with important evidence." in page.text
    assert "\n\nCoverage improves" in page.text
    assert "• First useful finding.\n• Second useful finding." in page.text
    assert page.text.count("0.625") == 1
    assert "comment" not in page.text and "<strong>" not in page.text


def test_plain_text_keeps_existing_paragraphs():
    text = "The first paragraph contains enough readable material.\r\n\r\nSecond paragraph."
    page = PublicPageFetcher._parse("https://example.org/text", text.encode(), "text/plain")

    assert page.text == text.replace("\r\n", "\n")
