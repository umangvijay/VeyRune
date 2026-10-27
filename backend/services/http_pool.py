"""Shared outbound HTTP connection pool for workflow tasks.

core.http used to build a fresh httpx.AsyncClient per call — a new TCP +
TLS handshake for every task against the same API host. One pooled client
reuses keepalive connections (measurably faster MCP/API chains) while
per-call timeouts and the engine's redirect/SSRF rules stay unchanged.
"""
import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None
_lock = asyncio.Lock()

# Modest ceilings: workflow fan-out rarely exceeds a handful of hosts,
# and keepalive sockets are cheap to drop after 30s idle.
_limits = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=30.0,
)


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        async with _lock:
            if _client is None or _client.is_closed:
                _client = httpx.AsyncClient(
                    limits=_limits,
                    follow_redirects=False,
                )
                logger.info("HTTP pool started (keepalive 20 conns / 30s)")
    return _client


async def aclose_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        logger.info("HTTP pool closed")
    _client = None
