# -*- coding: utf-8 -*-
"""
@author:XuMing(xuming624@qq.com)
@description: Simple client demo for the URL text fetcher service.

Run the FastAPI service first:
    uvicorn crawler:app --host 0.0.0.0 --port 8000

Then execute this script:
    python demo.py --urls https://example.com https://www.python.org --timeout 12 --concurrency 32
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Optional, Sequence

import httpx

DEFAULT_ENDPOINT = "http://127.0.0.1:8000/fetch"
DEFAULT_URLS = ["https://www.python.org", "https://github.com"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Demo client for URL text fetcher service")
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"Fetch endpoint (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        default=DEFAULT_URLS,
        help="List of URLs to crawl (e.g., 'https://example.com' 'https://example.org')",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Per-request timeout in seconds (1-60)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Override server-side concurrency level (>=1)",
    )
    parser.add_argument(
        "--to-markdown",
        action="store_true",
        default=True,
        help="Convert HTML to Markdown format (default: True)",
    )
    parser.add_argument(
        "--no-markdown",
        dest="to_markdown",
        action="store_false",
        help="Disable Markdown conversion, return plain text only",
    )
    return parser


async def fetch(
    endpoint: str,
    urls: Sequence[str],
    timeout: float,
    concurrency: Optional[int],
    to_markdown: bool = True,
) -> None:
    payload = {"urls": list(urls), "timeout": timeout, "to_markdown": to_markdown}
    if concurrency is not None:
        payload["concurrency"] = concurrency

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(endpoint, json=payload)
        response.raise_for_status()
    data = response.json()
    print(json.dumps(data, indent=2, ensure_ascii=False))


async def async_main(args: argparse.Namespace) -> None:
    await fetch(args.endpoint, args.urls, args.timeout, args.concurrency, args.to_markdown)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
