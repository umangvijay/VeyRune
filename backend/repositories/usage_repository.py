"""Durable per-user daily token accounting (audit F08).

The in-memory ContextManager totals are process-local: API and worker
processes do not share them and a restart resets them. This ledger is the
shared source of truth for the daily spending cap — every LLM path records
here, and budget checks read the maximum of the two so nothing undercounts.
"""
import logging
from datetime import date, timezone
from typing import Any, Dict, Optional, Protocol

logger = logging.getLogger(__name__)


def today_utc() -> str:
    return datetime_now_utc()[:10]


def datetime_now_utc() -> str:
    from datetime import datetime
    return datetime.now(timezone.utc).isoformat()


class UsageRepository(Protocol):
    async def add_usage(self, user_id: str, day: str, tokens: int) -> None: ...
    async def get_usage(self, user_id: str, day: str) -> int: ...


class SQLiteUsageRepository:
    """Atomic per-(user, day) accumulator. Concurrent writers in any process
    sharing the database converge — INSERT..ON CONFLICT does the addition
    inside SQLite's write lock."""

    def __init__(self, db_manager):
        self.db = db_manager

    async def add_usage(self, user_id: str, day: str, tokens: int) -> None:
        if tokens <= 0:
            return
        # COMMIT is required: DatabaseManager.execute runs on a shared
        # connection WITHOUT auto-commit. Without it the spend sits in an
        # open transaction and vanishes on rollback/restart (v5.6 review
        # blocker) — and other processes/connections can never see it.
        await self.db.execute(
            """
            INSERT INTO usage_ledger (user_id, day, tokens, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, day) DO UPDATE SET
                tokens = tokens + excluded.tokens,
                updated_at = excluded.updated_at
            """,
            (user_id, day, int(tokens), datetime_now_utc()),
        )
        await self.db.commit()

    async def get_usage(self, user_id: str, day: str) -> int:
        row = await self.db.fetch_one(
            "SELECT tokens FROM usage_ledger WHERE user_id = ? AND day = ?",
            (user_id, day),
        )
        return int(row["tokens"]) if row else 0

    async def reserve_usage(self, user_id: str, day: str, tokens: int, cap: int) -> bool:
        """Atomic budget reservation (v5.6 A3): the guarded upsert admits the
        reservation ONLY IF reserved+actual+tokens stays within the cap. Two
        processes racing near the cap cannot both win — the guard is inside
        the single UPDATE."""
        if tokens <= 0:
            return True
        cursor = await self.db.execute(
            """
            INSERT INTO usage_ledger (user_id, day, tokens, reserved, updated_at)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT(user_id, day) DO UPDATE SET
                reserved = reserved + excluded.reserved,
                updated_at = excluded.updated_at
            WHERE usage_ledger.reserved + usage_ledger.tokens + excluded.reserved <= %d
            """ % int(cap),
            (user_id, day, int(tokens), datetime_now_utc()),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def settle_usage(self, user_id: str, day: str, reserved_tokens: int, actual_tokens: int) -> None:
        """Replace the hold with the real spend: release the reserved amount,
        count the actual tokens. Committed before returning."""
        release = int(max(0, reserved_tokens))
        spend = int(max(0, actual_tokens))
        now = datetime_now_utc()
        cursor = await self.db.execute(
            """
            UPDATE usage_ledger
            SET reserved = MAX(0, reserved - ?),
                tokens = tokens + ?,
                updated_at = ?
            WHERE user_id = ? AND day = ?
            """,
            (release, spend, now, user_id, day),
        )
        if cursor.rowcount == 0:
            # Defensive: a settle without a visible reservation row still
            # records the actual spend (the cap check already happened).
            await self.db.execute(
                """
                INSERT INTO usage_ledger (user_id, day, tokens, reserved, updated_at)
                VALUES (?, ?, ?, 0, ?)
                ON CONFLICT(user_id, day) DO UPDATE SET
                    tokens = tokens + excluded.tokens,
                    updated_at = excluded.updated_at
                """,
                (user_id, day, spend, now),
            )
        await self.db.commit()

    async def get_committed_usage(self, user_id: str, day: str) -> int:
        """Spend counted against the cap: settled actuals + open holds."""
        row = await self.db.fetch_one(
            "SELECT tokens, reserved FROM usage_ledger WHERE user_id = ? AND day = ?",
            (user_id, day),
        )
        if not row:
            return 0
        return int(row["tokens"] or 0) + int(row["reserved"] or 0)


class FirestoreUsageRepository:
    """FieldValue.increment is atomic server-side: concurrent replicas cannot
    lose increments the way read–modify–write would."""

    def __init__(self):
        self._db = None

    async def _get_db(self):
        if self._db is None:
            from backend.repositories.firestore.database import FirestoreDB
            self._db = await FirestoreDB.get_client()
        return self._db

    @staticmethod
    def _doc_id(user_id: str, day: str) -> str:
        return f"{user_id}_{day}"

    async def add_usage(self, user_id: str, day: str, tokens: int) -> None:
        if tokens <= 0:
            return
        from google.cloud.firestore import Increment
        db = await self._get_db()
        await db.collection("usage_ledger").document(self._doc_id(user_id, day)).set({
            "user_id": user_id,
            "day": day,
            "tokens": Increment(int(tokens)),
            "updated_at": datetime_now_utc(),
        }, merge=True)

    async def get_usage(self, user_id: str, day: str) -> int:
        db = await self._get_db()
        snap = await db.collection("usage_ledger").document(self._doc_id(user_id, day)).get()
        if not snap.exists:
            return 0
        return int((snap.to_dict() or {}).get("tokens") or 0)

    async def reserve_usage(self, user_id: str, day: str, tokens: int, cap: int) -> bool:
        from google.cloud import firestore
        db = await self._get_db()
        ref = db.collection("usage_ledger").document(self._doc_id(user_id, day))

        @firestore.async_transactional
        async def reserve(transaction):
            snap = await ref.get(transaction=transaction)
            data = snap.to_dict() or {}
            actual = int(data.get("tokens") or 0)
            reserved = int(data.get("reserved") or 0)
            if actual + reserved + int(tokens) > int(cap):
                return False
            transaction.set(ref, {
                "user_id": user_id, "day": day,
                "tokens": actual, "reserved": reserved + int(tokens),
                "updated_at": datetime_now_utc(),
            }, merge=True)
            return True

        return await reserve(db.transaction())

    async def settle_usage(self, user_id: str, day: str, reserved_tokens: int, actual_tokens: int) -> None:
        from google.cloud import firestore
        db = await self._get_db()
        ref = db.collection("usage_ledger").document(self._doc_id(user_id, day))

        @firestore.async_transactional
        async def settle(transaction):
            snap = await ref.get(transaction=transaction)
            data = snap.to_dict() or {}
            current_reserved = int(data.get("reserved") or 0)
            transaction.set(ref, {
                "user_id": user_id, "day": day,
                "tokens": int(data.get("tokens") or 0) + int(max(0, actual_tokens)),
                "reserved": max(0, current_reserved - int(max(0, reserved_tokens))),
                "updated_at": datetime_now_utc(),
            }, merge=True)

        await settle(db.transaction())

    async def get_committed_usage(self, user_id: str, day: str) -> int:
        db = await self._get_db()
        snap = await db.collection("usage_ledger").document(self._doc_id(user_id, day)).get()
        if not snap.exists:
            return 0
        data = snap.to_dict() or {}
        return int(data.get("tokens") or 0) + int(data.get("reserved") or 0)


# ── Process-wide holder (wired by RepositoryFactory.initialize) ────────

_repo: Optional[UsageRepository] = None


def set_usage_repo(repo: Optional[UsageRepository]) -> None:
    global _repo
    _repo = repo


def get_usage_repo() -> Optional[UsageRepository]:
    return _repo


async def record_usage_durably(user_id: str, tokens: int) -> None:
    """Persist a token spend so the daily cap holds across processes and
    restarts. Fire-and-forget friendly: logs and drops on failure rather
    than breaking the LLM call that earned the spend."""
    repo = get_usage_repo()
    if repo is None or tokens <= 0:
        return
    try:
        await repo.add_usage(user_id, today_utc(), tokens)
    except Exception:
        logger.exception("Durable usage recording failed for %s", user_id)


async def get_durable_usage(user_id: str) -> int:
    repo = get_usage_repo()
    if repo is None:
        return 0
    try:
        return await repo.get_usage(user_id, today_utc())
    except Exception:
        logger.exception("Durable usage read failed for %s", user_id)
        raise


async def get_committed_usage(user_id: str) -> int:
    """Module-level helper: settled actuals + open reservation holds for the
    user's current UTC day — the number the budget cap counts."""
    repo = get_usage_repo()
    if repo is None:
        return 0
    try:
        return await repo.get_committed_usage(user_id, today_utc())
    except Exception:
        logger.exception("Committed usage read failed for %s", user_id)
        raise
