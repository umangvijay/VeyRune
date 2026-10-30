"""
AgentOS — SQLite Org Repository

Orgs and membership for the enterprise RBAC foundation. Roles:
owner > admin > member > viewer. The owner's membership is immutable
(cannot be removed or demoted) to keep the accountability chain intact.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.repositories.base import BaseOrgRepository
from backend.repositories.sqlite.database import DatabaseManager

logger = logging.getLogger(__name__)

OWNER_ROLE = "owner"


class SQLiteOrgRepository(BaseOrgRepository):

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def create_org(self, name: str, owner_id: str) -> Dict[str, Any]:
        org_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "INSERT INTO orgs (org_id, name, owner_id, created_at) VALUES (?, ?, ?, ?)",
            (org_id, name, owner_id, now),
        )
        await self.db.execute(
            "INSERT INTO org_members (org_id, user_id, role, added_at, added_by) VALUES (?, ?, ?, ?, ?)",
            (org_id, owner_id, OWNER_ROLE, now, owner_id),
        )
        await self.db.commit()
        return {"org_id": org_id, "name": name, "owner_id": owner_id, "created_at": now}

    async def get_org(self, org_id: str) -> Optional[Dict[str, Any]]:
        row = await self.db.fetch_one("SELECT * FROM orgs WHERE org_id = ?", (org_id,))
        return dict(row) if row else None

    async def list_orgs_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all(
            """
            SELECT o.org_id, o.name, o.owner_id, o.created_at, m.role
            FROM orgs o JOIN org_members m ON m.org_id = o.org_id
            WHERE m.user_id = ?
            ORDER BY o.created_at DESC
            """,
            (user_id,),
        )
        return [dict(r) for r in rows]

    async def get_member_role(self, org_id: str, user_id: str) -> Optional[str]:
        row = await self.db.fetch_one(
            "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?",
            (org_id, user_id),
        )
        return row["role"] if row else None

    async def list_members(self, org_id: str) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all(
            """
            SELECT m.user_id, m.role, m.added_at, u.email, u.name
            FROM org_members m LEFT JOIN users u ON u.id = m.user_id
            WHERE m.org_id = ?
            ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, m.added_at
            """,
            (org_id,),
        )
        return [dict(r) for r in rows]

    async def add_member(self, org_id: str, user_id: str, role: str, added_by: str) -> bool:
        if await self.get_org(org_id) is None:
            return False
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.db.execute(
            """
            INSERT INTO org_members (org_id, user_id, role, added_at, added_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(org_id, user_id) DO NOTHING
            """,
            (org_id, user_id, role, now, added_by),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def set_member_role(self, org_id: str, user_id: str, role: str) -> bool:
        cursor = await self.db.execute(
            """
            UPDATE org_members SET role = ?
            WHERE org_id = ? AND user_id = ? AND role != 'owner'
            """,
            (role, org_id, user_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def remove_member(self, org_id: str, user_id: str) -> bool:
        cursor = await self.db.execute(
            "DELETE FROM org_members WHERE org_id = ? AND user_id = ? AND role != 'owner'",
            (org_id, user_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def delete_org(self, org_id: str) -> bool:
        conn = await self.db.connection()
        cursor = await conn.execute("DELETE FROM orgs WHERE org_id = ?", (org_id,))
        await conn.commit()
        return cursor.rowcount > 0
