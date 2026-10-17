"""
AgentOS — SQLite Adaptive Policy Repository

Persistent memory for the online-learning model-selection policy:
per-model attempt/success counters and EWMA latency, updated from real
task outcomes. See backend/services/adaptive_policy.py for the policy.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.repositories.base import BaseAdaptivePolicyRepository
from backend.repositories.sqlite.database import DatabaseManager

logger = logging.getLogger(__name__)


class SQLiteAdaptivePolicyRepository(BaseAdaptivePolicyRepository):

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def record_outcome(self, model: str, success: bool, latency_ms: float) -> None:
        if not model:
            return
        now = datetime.now(timezone.utc).isoformat()
        conn = await self.db.connection()
        await conn.execute(
            """
            INSERT INTO model_stats (model, attempts, successes, failures, ewma_latency_ms, updated_at)
            VALUES (?, 1, ?, ?, ?, ?)
            ON CONFLICT(model) DO UPDATE SET
                attempts = attempts + 1,
                successes = successes + ?,
                failures = failures + ?,
                ewma_latency_ms = ewma_latency_ms * 0.7 + ? * 0.3,
                updated_at = ?
            """,
            (
                model,
                1 if success else 0,
                0 if success else 1,
                float(latency_ms),
                now,
                1 if success else 0,
                0 if success else 1,
                float(latency_ms),
                now,
            ),
        )
        await conn.commit()

    async def get_stats(self) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all("SELECT * FROM model_stats ORDER BY attempts DESC")
        return [dict(r) for r in rows]

    async def reset(self) -> int:
        conn = await self.db.connection()
        cursor = await conn.execute("DELETE FROM model_stats")
        await conn.commit()
        return cursor.rowcount or 0
