"""Bounded public-page fetches with DNS pinning and redirect revalidation."""

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

MAX_BYTES = 2 * 1024 * 1024
MAX_TEXT = 10_000


class FetchError(ValueError):
    """The URL or response cannot safely be used as an article."""


def public_ip(value: str) -> bool:
    """Reject private, special-use, multicast and IPv6 transition addresses."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if not address.is_global or address.is_multicast or address.is_reserved:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        return (
            address in ipaddress.ip_network("2000::/3")
            and address.ipv4_mapped is None
            and address.sixtofour is None
            and address.teredo is None
        )
    return True


def canonical_url(value: str) -> str:
    """Accept HTTP(S) on standard ports, with no credentials or ambiguous hosts."""
    if len(value) > 2048 or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        raise FetchError("Use a valid public HTTP(S) URL")
    try:
        url = httpx.URL(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.port not in {None, 80 if url.scheme == "http" else 443}
            or "%" in url.host
        ):
            raise ValueError
        host = url.host.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
                raise ValueError from None
        else:
            if not public_ip(host):
                raise ValueError
        return str(url.copy_with(host=host, raw_path=url.raw_path, fragment=None))
    except (ValueError, httpx.InvalidURL) as error:
        raise FetchError("Use a valid public HTTP(S) URL") from error


@dataclass(frozen=True)
class FetchedPage:
    """Normalized readable text; publication time is deliberately not guessed."""

    url: str
    title: str
    text: str
    truncated: bool


class PublicPageFetcher:
    """One fetch is bounded to 20 seconds, 3 redirects and 2 MiB of raw content.

    Each hop gets a fresh client with no cookies, proxy environment or credentials.
    Identity encoding avoids decompression bombs. TLS still verifies the original
    hostname even though the TCP destination is a validated literal IP.
    """

    async def _resolve(self, host: str, port: int) -> list[str]:
        rows = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return sorted({str(row[4][0]) for row in rows})

    async def fetch(self, value: str) -> FetchedPage:
        """Fetch public HTML/plain text; never execute scripts or fetch subresources."""
        try:
            async with asyncio.timeout(20):
                return await self._fetch(value)
        except FetchError:
            raise
        except (httpx.HTTPError, OSError, TimeoutError, UnicodeError) as error:
            raise FetchError("The public page could not be fetched") from error

    async def _fetch(self, value: str) -> FetchedPage:
        current = canonical_url(value)
        for hop in range(4):
            url = httpx.URL(current)
            addresses = await self._resolve(
                url.host, url.port or (443 if url.scheme == "https" else 80)
            )
            if not addresses or any(not public_ip(ip) for ip in addresses):
                raise FetchError("The URL resolves to a blocked address")
            pinned = url.copy_with(host=addresses[0])
            host = f"[{url.host}]" if ":" in url.host else url.host
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=5
            ) as client:
                async with client.stream(
                    "GET",
                    pinned,
                    headers={
                        "Host": host,
                        "Accept-Encoding": "identity",
                        "Accept": "text/html,text/plain",
                        "User-Agent": "AI-Radar/0.5",
                    },
                    extensions={"sni_hostname": url.host},
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if hop == 3 or not location:
                            raise FetchError("Too many redirects or missing redirect target")
                        current = canonical_url(urljoin(current, location))
                        continue
                    if response.status_code != 200:
                        raise FetchError("The public page did not return readable content")
                    mime = response.headers.get("content-type", "").split(";", 1)[0].lower().strip()
                    if mime not in {"text/html", "text/plain", "application/xhtml+xml"}:
                        raise FetchError("Only HTML and plain text pages are supported")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise FetchError("Compressed responses are not supported")
                    size = response.headers.get("content-length")
                    if size and (len(size) > 10 or not size.isdecimal() or int(size) > MAX_BYTES):
                        raise FetchError("The page is too large")
                    body = bytearray()
                    async for chunk in response.aiter_raw():
                        if len(body) + len(chunk) > MAX_BYTES:
                            raise FetchError("The page is too large")
                        body.extend(chunk)
                    # Parsing runs outside the event loop and only sees bounded input.
                    return await asyncio.to_thread(self._parse, current, bytes(body), mime)
        raise FetchError("Too many redirects")

    @staticmethod
    def _parse(url: str, body: bytes, mime: str) -> FetchedPage:
        title = httpx.URL(url).host
        if mime == "text/plain":
            text = body.decode("utf-8", errors="replace")
        else:
            soup = BeautifulSoup(body, "html.parser")
            if soup.title:
                title = soup.title.get_text(" ", strip=True) or title
            for node in soup.select("script,style,noscript,iframe,svg,nav,header,footer,form"):
                node.decompose()
            root = soup.find("article") or soup.find("main") or soup.body or soup
            text = root.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 50:
            raise FetchError("The page has too little readable text")
        return FetchedPage(
            url, " ".join(title.split())[:300], text[:MAX_TEXT], len(text) > MAX_TEXT
        )
