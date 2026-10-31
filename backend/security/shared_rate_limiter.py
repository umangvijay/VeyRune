"""Shared durable rate limiting (v5.6 review §1 — last High finding).

The in-process sliding window is fast but per-replica: N replicas get N
allowances. This store provides a SHARED fixed-window counter in the
durable database — the same guarded-upsert pattern as the usage ledger —
so abuse-sensitive groups (auth, contact, webhook, mcp_build) enforce ONE
limit across every replica and across restarts.

High-volume groups stay in-process by design: a database round-trip per
request would trade the right availability/cost balance for a limit that
Cloud Armor enforces better at the edge.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class SharedRateRepository(Protocol):
    async def admit(self, identifier: str, group: str, window_start: int,
                    max_requests: int) -> bool: ...


class SQLiteSharedRateRepository:
    """Atomic fixed-window admission. The cap guard lives inside the single
    upsert: two replicas racing for the last slot cannot both win."""

    def __init__(self, db):
        self.db = db

    async def admit(self, identifier: str, group: str, window_start: int,
                    max_requests: int) -> bool:
        cursor = await self.db.execute(
            """
            INSERT INTO rate_limits (identifier, group_name, window_start, count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(identifier, group_name, window_start) DO UPDATE SET
                count = count + 1
            WHERE rate_limits.count < ?
            """,
            (identifier, group, window_start, int(max_requests)),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def purge_expired(self, older_than_epoch: int) -> int:
        cursor = await self.db.execute(
            "DELETE FROM rate_limits WHERE window_start < ?", (int(older_than_epoch),)
        )
        await self.db.commit()
        return cursor.rowcount or 0


class FirestoreSharedRateRepository:
    """Transaction-based admission: read-guard-write inside one transaction."""

    def __init__(self):
        self._db = None

    async def _get_db(self):
        if self._db is None:
            from backend.repositories.firestore.database import FirestoreDB
            self._db = await FirestoreDB.get_client()
        return self._db

    @staticmethod
    def _doc_id(identifier: str, group: str, window_start: int) -> str:
        # Deterministic id; window bounds keep the doc space bounded.
        import hashlib as _hashlib
        return _hashlib.sha256(f"{identifier}|{group}|{window_start}".encode()).hexdigest()

    async def admit(self, identifier: str, group: str, window_start: int,
                    max_requests: int) -> bool:
        from google.cloud import firestore
        from google.api_core.exceptions import AlreadyExists
        db = await self._get_db()
        ref = db.collection("rate_limits").document(self._doc_id(identifier, group, window_start))

        @firestore.async_transactional
        async def admit(transaction):
            snap = await ref.get(transaction=transaction)
            if not snap.exists:
                transaction.create(ref, {"count": 1, "window_start": window_start,
                                         "expires_at": window_start + 2 * 60})
                return True
            count = int((snap.to_dict() or {}).get("count") or 0)
            if count >= int(max_requests):
                return False
            transaction.update(ref, {"count": count + 1})
            return True

        try:
            return await admit(db.transaction())
        except AlreadyExists:
            return False

    async def purge_expired(self, older_than_epoch: int) -> int:
        db = await self._get_db()
        query = db.collection("rate_limits").where("window_start", "<", int(older_than_epoch))
        swept = 0
        async for snap in query.stream():
            await snap.reference.delete()
            swept += 1
        return swept


_repo: Optional[SharedRateRepository] = None


def set_shared_rate_repo(repo: Optional[SharedRateRepository]) -> None:
    global _repo
    _repo = repo


def get_shared_rate_repo() -> Optional[SharedRateRepository]:
    return _repo


def current_window(window_seconds: int) -> int:
    return int(time.time()) // max(1, window_seconds)


async def shared_admit(identifier: str, group: str, window_seconds: int,
                       max_requests: int) -> Optional[bool]:
    """Consult the shared store. Returns True/False, or None when no shared
    store is configured (the in-process limiter is then authoritative)."""
    repo = get_shared_rate_repo()
    if repo is None:
        return None
    try:
        return await repo.admit(identifier, group, current_window(window_seconds), max_requests)
    except Exception:
        # A shared-store outage must not take the edge down: fall back to the
        # per-process limit and say so — availability over strictness here is
        # the documented trade-off (the strict cap is enforced at the edge).
        logger.exception("Shared rate store unavailable; falling back to process-local")
        return None
