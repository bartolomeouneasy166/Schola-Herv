"""
Shared aiohttp session factory for Schola-herv.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import aiohttp

_DEFAULT_USER_AGENT = "Schola-herv/2.0.0 (mailto:{email})"


@asynccontextmanager
async def make_session(
    email: Optional[str] = None,
    max_connections: int = 20,
) -> AsyncGenerator[aiohttp.ClientSession, None]:
    """
    Async context manager that yields a single shared aiohttp.ClientSession.

    Args:
        email:           Contact email for polite crawling User-Agent strings.
        max_connections: Total connection pool limit.

    Yields:
        A configured :class:`aiohttp.ClientSession`.
    """
    contact = email or "your.email@example.com"
    headers = {
        "User-Agent": _DEFAULT_USER_AGENT.format(email=contact),
    }
    connector = aiohttp.TCPConnector(limit=max_connections, ssl=False)
    async with aiohttp.ClientSession(
        headers=headers,
        connector=connector,
    ) as session:
        yield session
