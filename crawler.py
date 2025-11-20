# -*- coding: utf-8 -*-
"""
@author:XuMing(xuming624@qq.com)
@description:
高并发 URL 网页内容抓取服务，基于 FastAPI + httpx + BeautifulSoup。

Usage (development):
    uvicorn crawler:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import Body, FastAPI, HTTPException
from markdownify import MarkdownConverter

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, default))
    except (TypeError, ValueError):
        logger.warning("%s is not a valid integer, fallback to %s", name, default)
        return default
    return max(minimum, value)


def _env_float(name: str, default: float, minimum: float = 0.1) -> float:
    try:
        value = float(os.getenv(name, default))
    except (TypeError, ValueError):
        logger.warning("%s is not a valid float, fallback to %s", name, default)
        return default
    return max(minimum, value)


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; URLCrawler/1.0; +https://example.com/bot)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
DEFAULT_CONCURRENCY = _env_int("URL_CRAWLER_DEFAULT_CONCURRENCY", 10)
MAX_CONCURRENCY = _env_int("URL_CRAWLER_MAX_CONCURRENCY", max(DEFAULT_CONCURRENCY, 64), minimum=DEFAULT_CONCURRENCY)
MAX_URLS = _env_int("URL_CRAWLER_MAX_URLS", 64)
MAX_BODY_BYTES = _env_int("URL_CRAWLER_MAX_BODY_BYTES", 5 * 1024 * 1024)
MAX_CONNECTIONS = max(_env_int("URL_CRAWLER_MAX_CONNECTIONS", DEFAULT_CONCURRENCY * 4), DEFAULT_CONCURRENCY)
MAX_KEEPALIVE_CONNECTIONS = max(_env_int("URL_CRAWLER_MAX_KEEPALIVE_CONNECTIONS", DEFAULT_CONCURRENCY * 2), DEFAULT_CONCURRENCY)
CONNECT_TIMEOUT = _env_float("URL_CRAWLER_CONNECT_TIMEOUT", 10.0)
READ_TIMEOUT = _env_float("URL_CRAWLER_READ_TIMEOUT", 15.0)
ALLOWED_CONTENT_KEYWORDS = tuple(
    keyword.strip().lower()
    for keyword in os.getenv("URL_CRAWLER_ALLOWED_CONTENT_KEYWORDS", "text,html,xml")
    .split(",")
    if keyword.strip()
)


@dataclass(slots=True)
class FetchRequest:
    """Incoming request body."""

    urls: List[str]
    timeout: float = 15.0
    concurrency: Optional[int] = None
    to_markdown: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.urls, (list, tuple)):
            raise ValueError("urls must be provided as a list of URL strings")

        normalized_urls = [str(url) for url in self.urls]
        if not normalized_urls:
            raise ValueError("urls must contain at least one URL")

        if len(normalized_urls) > MAX_URLS:
            raise ValueError(f"urls cannot contain more than {MAX_URLS} items")

        for url in normalized_urls:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError(f"Invalid URL provided: {url}")

        try:
            timeout_value = float(self.timeout)
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout must be a number") from exc

        if not 1.0 <= timeout_value <= 60.0:
            raise ValueError("timeout must be between 1 and 60 seconds")

        if self.concurrency is None:
            requested_concurrency = DEFAULT_CONCURRENCY
        else:
            try:
                requested_concurrency = int(self.concurrency)
            except (TypeError, ValueError) as exc:
                raise ValueError("concurrency must be an integer") from exc

        if not 1 <= requested_concurrency <= MAX_CONCURRENCY:
            raise ValueError(f"concurrency must be between 1 and {MAX_CONCURRENCY}")

        self.urls = normalized_urls
        self.timeout = timeout_value
        self.concurrency = min(requested_concurrency, len(self.urls), MAX_CONCURRENCY)


@dataclass(slots=True)
class FetchResult:
    url: str
    ok: bool
    status_code: Optional[int] = None
    charset: Optional[str] = None
    text: Optional[str] = None
    markdown: Optional[str] = None
    error: Optional[str] = None
    bytes_downloaded: Optional[int] = None
    elapsed_ms: Optional[int] = None


@dataclass(slots=True)
class FetchResponse:
    total: int
    concurrency: int
    elapsed_ms: int
    results: List[FetchResult]


def extract_readable_text(html: str) -> str:
    """Convert raw HTML into plain text."""

    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    text = soup.get_text(separator="\n")
    cleaned_lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(cleaned_lines)


def parse_html_to_markdown(html: str, url: str) -> str:
    """Parse HTML to markdown format.
    
    Args:
        html: HTML content to convert
        url: Source URL (used for special handling of Wikipedia pages)
        
    Returns:
        Markdown formatted text
    """
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string if soup.title else "No Title"
    
    # Remove javascript, style blocks, and hyperlinks
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    
    # Remove other common irrelevant elements
    for element in soup.find_all(["nav", "footer", "aside", "form", "figure", "header"]):
        element.decompose()
    
    # Special handling for Wikipedia pages
    if "wikipedia.org" in url:
        body_elm = soup.find("div", {"id": "mw-content-text"})
        title_elm = soup.find("span", {"class": "mw-page-title-main"})
        
        if body_elm:
            main_title = title_elm.string if title_elm else title
            webpage_text = f"# {main_title}\n\n" + MarkdownConverter().convert_soup(body_elm)
        else:
            webpage_text = MarkdownConverter().convert_soup(soup)
    else:
        webpage_text = MarkdownConverter().convert_soup(soup)
    
    # Clean up excessive newlines
    webpage_text = re.sub(r"\r\n", "\n", webpage_text)
    webpage_text = re.sub(r"\n{2,}", "\n\n", webpage_text).strip()
    
    # Add title if not already present
    if not webpage_text.startswith("# "):
        webpage_text = f"# {title}\n\n{webpage_text}"
    
    return webpage_text


async def fetch_single(
    url: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    to_markdown: bool = False,
) -> FetchResult:
    """Fetch a single URL and return structured data.
    
    Args:
        url: Target URL to fetch
        client: HTTP client instance
        semaphore: Concurrency control semaphore
        to_markdown: If True, convert HTML to Markdown format
        
    Returns:
        FetchResult with extracted content
    """

    result = FetchResult(url=url, ok=False)
    started = perf_counter()
    async with semaphore:
        try:
            response = await client.get(url)
            result.status_code = response.status_code
            result.charset = response.encoding
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()
            if ALLOWED_CONTENT_KEYWORDS and not any(keyword in content_type for keyword in ALLOWED_CONTENT_KEYWORDS):
                raise ValueError(f"Unsupported content type: {content_type}")

            result.bytes_downloaded = len(response.content)
            content = response.content[:MAX_BODY_BYTES]
            html_content = content.decode(response.encoding or "utf-8", errors="replace")
            
            # Extract plain text
            result.text = extract_readable_text(html_content)
            
            # Convert to markdown if requested
            if to_markdown:
                result.markdown = parse_html_to_markdown(html_content, url)

            result.ok = True
        except httpx.TimeoutException as exc:
            result.error = f"timeout: {exc}"
            logger.warning("Timeout while fetching %s: %s", url, exc)
        except httpx.HTTPError as exc:
            result.error = str(exc)
            logger.warning("HTTP error while fetching %s: %s", url, exc)
        except Exception as exc:  # pylint: disable=broad-except
            result.error = str(exc)
            logger.warning("Failed to fetch %s: %s", url, exc)
        finally:
            result.elapsed_ms = int((perf_counter() - started) * 1000)
    return result


app = FastAPI(title="URL Text Fetcher", version="0.2.0")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/fetch")
async def fetch_urls(payload: dict = Body(...)) -> dict:
    try:
        request = FetchRequest(**payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    start_time = perf_counter()
    concurrency = request.concurrency or DEFAULT_CONCURRENCY
    semaphore = asyncio.Semaphore(concurrency)

    effective_max_connections = max(MAX_CONNECTIONS, concurrency * 2)
    effective_keepalive = max(MAX_KEEPALIVE_CONNECTIONS, concurrency)

    limits = httpx.Limits(
        max_connections=effective_max_connections,
        max_keepalive_connections=effective_keepalive,
    )
    read_timeout = min(READ_TIMEOUT, request.timeout)
    client_timeout = httpx.Timeout(
        connect=min(CONNECT_TIMEOUT, request.timeout),
        read=read_timeout,
        write=request.timeout,
        pool=request.timeout,
    )

    logger.info(
        "Incoming fetch: %s urls, concurrency=%s, timeout=%ss",
        len(request.urls),
        concurrency,
        request.timeout,
    )

    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=client_timeout,
        follow_redirects=True,
        limits=limits,
    ) as client:
        tasks = [
            fetch_single(url, client, semaphore, request.to_markdown)
            for url in request.urls
        ]
        results = await asyncio.gather(*tasks)

    elapsed_ms = int((perf_counter() - start_time) * 1000)
    response = FetchResponse(
        total=len(results),
        concurrency=concurrency,
        elapsed_ms=elapsed_ms,
        results=results,
    )
    return asdict(response)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("crawler:app", host="0.0.0.0", port=8000)
