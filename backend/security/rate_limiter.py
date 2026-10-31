"""
AgentOS — Advanced Rate Limiter

Sliding window counter per (user_id, endpoint_group).
Tighter limits on auth and MCP-build endpoints.
Supports per-IP limiting for unauthenticated routes.
"""

import time
import logging
from collections import defaultdict
from typing import Optional, Dict, Tuple
from threading import Lock

from fastapi import HTTPException, Request, status

from backend.config.settings import settings

logger = logging.getLogger(__name__)


class SlidingWindowCounter:
    """
    Sliding window rate limiter.
    
    Instead of fixed windows (which allow bursts at boundaries),
    this interpolates between the current and previous window to give
    a smooth rate limit.
    """

    def __init__(self, max_keys: int = 10000):
        self._lock = Lock()
        self._max_keys = max_keys
        self._next_cleanup = 0.0
        # Key: (identifier, group) → {window_start, prev_count, curr_count}
        self._windows: Dict[Tuple[str, str], Dict] = defaultdict(
            lambda: {"window_start": 0, "prev_count": 0, "curr_count": 0}
        )

    def check_rate_limit(
        self,
        identifier: str,
        group: str,
        max_requests: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, dict]:
        """
        Check if a request is allowed.
        
        Returns:
            (allowed, info_dict) where info_dict contains:
            - limit: max requests
            - remaining: requests remaining
            - reset: seconds until window resets
            - retry_after: seconds to wait (only if blocked)
        """
        now = time.time()
        key = (identifier, group)

        with self._lock:
            if now >= self._next_cleanup:
                stale = [key for key, state in self._windows.items() if state.get("expires_at", 0) <= now]
                for stale_key in stale:
                    del self._windows[stale_key]
                self._next_cleanup = now + 60
            if key not in self._windows and len(self._windows) >= self._max_keys:
                return False, {"limit": max_requests, "remaining": 0, "reset": 60, "retry_after": 60}
            state = self._windows[key]
            state["expires_at"] = now + 2 * window_seconds
            window_start = state["window_start"]
            elapsed = now - window_start

            if elapsed >= window_seconds:
                # Move to new window
                if elapsed >= 2 * window_seconds:
                    # Fully expired — reset both
                    state["prev_count"] = 0
                else:
                    state["prev_count"] = state["curr_count"]
                state["curr_count"] = 0
                state["window_start"] = now - (elapsed % window_seconds)
                elapsed = now - state["window_start"]

            # Sliding window estimate
            weight = 1.0 - (elapsed / window_seconds)
            estimated = state["prev_count"] * weight + state["curr_count"]

            if estimated >= max_requests:
                retry_after = window_seconds - elapsed
                return False, {
                    "limit": max_requests,
                    "remaining": 0,
                    "reset": int(retry_after),
                    "retry_after": int(retry_after) + 1,
                }

            # Allow and increment
            state["curr_count"] += 1
            remaining = max(0, int(max_requests - estimated - 1))

            return True, {
                "limit": max_requests,
                "remaining": remaining,
                "reset": int(window_seconds - elapsed),
            }


# ── Singleton ─────────────────────────────────────────────────────
_limiter = SlidingWindowCounter()


# ── Rate Limit Groups ─────────────────────────────────────────────
# Each group has its own limit. Tighter on sensitive endpoints.

RATE_LIMIT_GROUPS = {
    "contact": 3,
    "webhook": 10,
    "auth": settings.RATE_LIMIT_AUTH,           # 5/min — login, signup, password
    "workflow": settings.RATE_LIMIT_WORKFLOW,   # 10/min — workflow creation
    "mcp_build": settings.RATE_LIMIT_MCP_BUILD, # 3/min — MCP factory
    "general": settings.RATE_LIMIT_GENERAL,     # 60/min — everything else
}


def check_rate_limit(
    identifier: str,
    group: str = "general",
    window_seconds: int = 60,
) -> dict:
    """
    Check rate limit for an identifier (user_id or IP) and group.
    Raises HTTPException(429) if limit exceeded.
    Returns rate limit info headers.
    """
    max_requests = RATE_LIMIT_GROUPS.get(group, RATE_LIMIT_GROUPS["general"])

    allowed, info = _limiter.check_rate_limit(
        identifier, group, max_requests, window_seconds
    )

    if not allowed:
        logger.warning(
            f"Rate limit exceeded: {identifier} on {group} "
            f"(limit={max_requests}/{window_seconds}s)"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {info['retry_after']} seconds.",
            headers={
                "Retry-After": str(info["retry_after"]),
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(info["reset"]),
            },
        )

    return info


def get_client_identifier(request: Request, user_id: Optional[str] = None) -> str:
    """
    Get a rate limit identifier.
    Prefer user_id if authenticated, fall back to client IP.
    """
    if user_id:
        return f"user:{user_id}"

    # ASGI server middleware owns trusted-proxy parsing. Raw forwarded headers
    # are caller-controlled and must never replace the authenticated peer here.
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


# ── Shared admission (v5.6 §1) ────────────────────────────────────
# Async helper the abuse-sensitive routes await BEFORE the in-process
# check. Enforces ONE fixed-window limit across all replicas sharing the
# durable store; returns cleanly when no shared store is configured.

SHARED_GROUPS = {"auth", "contact", "webhook", "mcp_build"}


async def check_shared_rate_limit(identifier: str, group: str = "general",
                                  window_seconds: int = 60) -> dict:
    """Durable cross-replica admission for abuse-sensitive groups. Raises
    HTTPException(429) when the SHARED window is exhausted. When no shared
    store is configured or the store is down, returns the in-process info —
    the per-process limit still applies and the edge (Cloud Armor) is the
    documented volume control."""
    from backend.security.shared_rate_limiter import shared_admit
    max_requests = RATE_LIMIT_GROUPS.get(group, RATE_LIMIT_GROUPS["general"])
    result = await shared_admit(identifier, group, window_seconds, max_requests)
    if result is False:
        window = max(1, window_seconds - (int(time.time()) % max(1, window_seconds)))
        logger.warning("Shared rate limit exceeded: %s on %s (limit=%d/%ds)",
                       identifier, group, max_requests, window_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {window + 1} seconds.",
            headers={
                "Retry-After": str(window + 1),
                "X-RateLimit-Limit": str(max_requests),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(window),
            },
        )
    return {"limit": max_requests, "shared": result is not True and result is not False and result is None}
