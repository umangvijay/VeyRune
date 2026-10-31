"""In-process Playwright sessions kept alive while a human completes CAPTCHA/OTP/MFA."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Bounded session leases (v5.6 A7): a paused session held for a human
# challenge must not live in the worker's memory forever. Sessions older
# than the lease are swept and closed.
SESSION_LEASE_SECONDS = 1800


@dataclass
class BrowserSession:
    playwright: Any
    browser: Any
    context: Any
    page: Any
    allowed_domains: Set[str]
    secrets: Dict[str, str]
    goal: str
    history: List[str]
    steps: List[Dict[str, Any]]
    step_num: int
    max_steps: int
    challenge_type: str
    url: str
    headed: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())


_SESSIONS: Dict[str, BrowserSession] = {}


def session_key(run_id: str, task_id: str) -> str:
    return f"{run_id}:{task_id}"


def get_session(run_id: str, task_id: str) -> Optional[BrowserSession]:
    return _SESSIONS.get(session_key(run_id, task_id))


def put_session(run_id: str, task_id: str, session: BrowserSession) -> None:
    _SESSIONS[session_key(run_id, task_id)] = session


async def _close_resources(session: BrowserSession) -> None:
    for closer in (
        (session.context.close if session.context else None),
        (session.browser.close if session.browser else None),
        (session.playwright.stop if session.playwright else None),
    ):
        if closer is None:
            continue
        try:
            await closer()
        except Exception:
            logger.debug("browser session close ignored", exc_info=True)


async def close_session(run_id: str, task_id: str) -> None:
    key = session_key(run_id, task_id)
    session = _SESSIONS.pop(key, None)
    if not session:
        return
    await _close_resources(session)


async def sweep_expired_sessions(lease_seconds: int = SESSION_LEASE_SECONDS) -> int:
    """Close and drop sessions whose lease expired — bounded memory on the
    worker even when many challenge pauses accumulate."""
    now = time.time()
    expired = [key for key, s in _SESSIONS.items()
               if now - getattr(s, "created_at", 0) > lease_seconds]
    for key in expired:
        session = _SESSIONS.pop(key, None)
        if not session:
            continue
        await _close_resources(session)
    if expired:
        logger.info("Browser session sweep: %d expired lease(s) closed", len(expired))
    return len(expired)
