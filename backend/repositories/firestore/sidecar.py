"""Firestore stores for vault, settings, schedules, tokens, notifications, audit.

Used when STORAGE_BACKEND=firestore so Cloud Run has the same features as local SQLite.
Ciphertext only — SecretsVault still does AES-256-GCM.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.repositories.base import (
    BaseAuditRepository,
    BaseNotificationRepository,
    BaseRefreshTokenRepository,
    BaseScheduleRepository,
    BaseSecretsRepository,
    BaseSettingsRepository,
    BaseTokenDenylistRepository,
    BaseAdaptivePolicyRepository,
    BaseApiKeysRepository,
    BaseOrgRepository,
)
from backend.repositories.firestore.database import FirestoreDB
from backend.repositories.sqlite.settings_repository import DEFAULT_SETTINGS


async def _db():
    return await FirestoreDB.get_client()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FirestoreSecretsRepository(BaseSecretsRepository):
    async def store_secret(self, user_id: str, key: str, encrypted_value: str) -> None:
        db = await _db()
        doc_id = f"{user_id}::{key}"
        await db.collection("vault_secrets").document(doc_id).set(
            {
                "user_id": user_id,
                "key": key,
                "encrypted_value": encrypted_value,
                "updated_at": _now(),
            }
        )

    async def get_secret(self, user_id: str, key: str) -> Optional[str]:
        db = await _db()
        doc = await db.collection("vault_secrets").document(f"{user_id}::{key}").get()
        if not doc.exists:
            return None
        return (doc.to_dict() or {}).get("encrypted_value")

    async def delete_secret(self, user_id: str, key: str) -> bool:
        db = await _db()
        ref = db.collection("vault_secrets").document(f"{user_id}::{key}")
        snap = await ref.get()
        if not snap.exists:
            return False
        await ref.delete()
        return True

    async def list_secret_keys(self, user_id: str) -> List[str]:
        db = await _db()
        keys = []
        async for doc in db.collection("vault_secrets").where("user_id", "==", user_id).stream():
            data = doc.to_dict() or {}
            if data.get("key"):
                keys.append(data["key"])
        return sorted(keys)


class FirestoreSettingsRepository(BaseSettingsRepository):
    async def get_settings(self, user_id: str) -> Dict[str, Any]:
        db = await _db()
        doc = await db.collection("user_settings").document(user_id).get()
        stored = (doc.to_dict() or {}).get("settings") if doc.exists else {}
        if not isinstance(stored, dict):
            stored = {}
        return {**DEFAULT_SETTINGS, **stored}

    async def update_settings(self, user_id: str, updates: Dict[str, Any]) -> None:
        merged = {**(await self.get_settings(user_id)), **updates}
        db = await _db()
        await db.collection("user_settings").document(user_id).set(
            {"user_id": user_id, "settings": merged, "updated_at": _now()}
        )


class FirestoreScheduleRepository(BaseScheduleRepository):
    async def create_schedule(self, schedule_data: Dict[str, Any]) -> None:
        db = await _db()
        sid = schedule_data["schedule_id"]
        payload = dict(schedule_data)
        payload.setdefault("created_at", _now())
        payload["updated_at"] = _now()
        await db.collection("schedules").document(sid).set(payload)

    async def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        db = await _db()
        doc = await db.collection("schedules").document(schedule_id).get()
        return doc.to_dict() if doc.exists else None

    async def list_schedules(self, user_id: str) -> List[Dict[str, Any]]:
        db = await _db()
        out = []
        async for doc in db.collection("schedules").where("user_id", "==", user_id).stream():
            out.append(doc.to_dict() or {})
        return out

    async def update_schedule(self, schedule_id: str, updates: Dict[str, Any]) -> None:
        if not updates:
            return
        db = await _db()
        updates = dict(updates)
        updates["updated_at"] = _now()
        await db.collection("schedules").document(schedule_id).set(updates, merge=True)

    async def delete_schedule(self, schedule_id: str) -> bool:
        db = await _db()
        ref = db.collection("schedules").document(schedule_id)
        snap = await ref.get()
        if not snap.exists:
            return False
        await ref.delete()
        return True

    async def list_due_schedules(self, now_iso: str) -> List[Dict[str, Any]]:
        db = await _db()
        due = []
        async for doc in db.collection("schedules").stream():
            row = doc.to_dict() or {}
            if str(row.get("status") or "").upper() != "ACTIVE":
                continue
            nxt = row.get("next_run_at")
            if nxt and nxt <= now_iso:
                due.append(row)
        return due

    async def record_execution(self, schedule_id: str, run_id: str, status: str) -> None:
        db = await _db()
        eid = str(uuid.uuid4())
        await db.collection("schedule_executions").document(eid).set(
            {
                "schedule_id": schedule_id,
                "run_id": run_id,
                "status": status,
                "triggered_at": _now(),
            }
        )
        await db.collection("schedules").document(schedule_id).set(
            {"last_run_at": _now(), "updated_at": _now()}, merge=True
        )

    async def get_execution_history(self, schedule_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        db = await _db()
        rows = []
        async for doc in (
            db.collection("schedule_executions").where("schedule_id", "==", schedule_id).stream()
        ):
            rows.append(doc.to_dict() or {})
        rows.sort(key=lambda r: r.get("triggered_at") or "", reverse=True)
        return rows[:limit]


class FirestoreRefreshTokenRepository(BaseRefreshTokenRepository):
    async def store_token(self, user_id: str, token_hash: str, expires_at: datetime) -> None:
        db = await _db()
        await db.collection("refresh_tokens").document(token_hash).set(
            {
                "user_id": user_id,
                "token_hash": token_hash,
                "expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at),
                "created_at": _now(),
            }
        )

    async def validate_and_consume(self, token_hash: str) -> Optional[str]:
        db = await _db()
        ref = db.collection("refresh_tokens").document(token_hash)
        doc = await ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        exp = data.get("expires_at") or ""
        if exp < _now():
            await ref.delete()
            return None
        await ref.delete()
        return data.get("user_id")

    async def revoke_all_for_user(self, user_id: str) -> int:
        db = await _db()
        count = 0
        async for doc in db.collection("refresh_tokens").where("user_id", "==", user_id).stream():
            await doc.reference.delete()
            count += 1
        return count

    async def cleanup_expired(self) -> int:
        db = await _db()
        now = _now()
        count = 0
        async for doc in db.collection("refresh_tokens").stream():
            data = doc.to_dict() or {}
            if (data.get("expires_at") or "") < now:
                await doc.reference.delete()
                count += 1
        return count


class FirestoreTokenDenylistRepository(BaseTokenDenylistRepository):
    """Revoked access-token jti registry. Logout writes here; every
    authenticated request reads once. Entries carry the token's own expiry."""

    async def revoke_jti(self, jti: str, expires_at: datetime) -> None:
        if not jti:
            return
        db = await _db()
        expiry = expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at)
        await db.collection("token_denylist").document(jti).set(
            {"jti": jti, "expires_at": expiry, "revoked_at": _now()}
        )

    async def is_revoked(self, jti: str) -> bool:
        if not jti:
            return False
        db = await _db()
        doc = await db.collection("token_denylist").document(jti).get()
        if not doc.exists:
            return False
        data = doc.to_dict() or {}
        # Treated as purged once past expiry — no lingering false positives.
        if (data.get("expires_at") or "") <= _now():
            return False
        return True

    async def purge_expired(self) -> int:
        db = await _db()
        now = _now()
        count = 0
        async for doc in db.collection("token_denylist").where("expires_at", "<=", now).stream():
            await doc.reference.delete()
            count += 1
        return count


class FirestoreApiKeysRepository(BaseApiKeysRepository):
    """Per-user programmatic API keys. Hashes only."""

    async def create_key(self, user_id: str, key_hash: str, prefix: str, name: str) -> str:
        db = await _db()
        key_id = key_hash[:16]
        await db.collection("api_keys").document(key_id).set({
            "id": key_id,
            "user_id": user_id,
            "name": name,
            "key_hash": key_hash,
            "prefix": prefix,
            "created_at": _now(),
            "revoked_at": None,
        })
        return key_id

    async def resolve_key(self, key_hash: str) -> Optional[Dict[str, Any]]:
        db = await _db()
        rows = []
        async for doc in db.collection("api_keys").where("key_hash", "==", key_hash).stream():
            rows.append(doc.to_dict() or {})
        live = [r for r in rows if not r.get("revoked_at")]
        if not live:
            return None
        await db.collection("api_keys").document(live[0]["id"]).set(
            {**live[0], "last_used_at": _now()}
        )
        return {"user_id": live[0]["user_id"], "key_id": live[0]["id"]}

    async def list_keys(self, user_id: str) -> List[Dict[str, Any]]:
        db = await _db()
        rows = []
        async for doc in db.collection("api_keys").where("user_id", "==", user_id).stream():
            data = doc.to_dict() or {}
            data.pop("key_hash", None)
            rows.append(data)
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return rows

    async def revoke_key(self, user_id: str, key_id: str) -> bool:
        db = await _db()
        ref = db.collection("api_keys").document(key_id)
        doc = await ref.get()
        data = doc.to_dict() or {}
        if not doc.exists or data.get("user_id") != user_id or data.get("revoked_at"):
            return False
        await ref.set({**data, "revoked_at": _now()})
        return True


class FirestoreAdaptivePolicyRepository(BaseAdaptivePolicyRepository):
    """Per-model outcome stats for the adaptive selection policy."""

    async def record_outcome(self, model: str, success: bool, latency_ms: float) -> None:
        if not model:
            return
        db = await _db()
        ref = db.collection("model_stats").document(model)
        doc = await ref.get()
        data = doc.to_dict() or {}
        attempts = int(data.get("attempts") or 0) + 1
        successes = int(data.get("successes") or 0) + (1 if success else 0)
        failures = int(data.get("failures") or 0) + (0 if success else 1)
        ewma = float(data.get("ewma_latency_ms") or 0.0) * 0.7 + float(latency_ms) * 0.3
        await ref.set({
            "model": model,
            "attempts": attempts,
            "successes": successes,
            "failures": failures,
            "ewma_latency_ms": ewma,
            "updated_at": _now(),
        })

    async def get_stats(self) -> List[Dict[str, Any]]:
        db = await _db()
        rows = []
        async for doc in db.collection("model_stats").stream():
            rows.append(doc.to_dict() or {})
        rows.sort(key=lambda r: int(r.get("attempts") or 0), reverse=True)
        return rows

    async def reset(self) -> int:
        db = await _db()
        count = 0
        async for doc in db.collection("model_stats").stream():
            await doc.reference.delete()
            count += 1
        return count


class FirestoreNotificationRepository(BaseNotificationRepository):
    async def create_notification(self, notification_data: Dict[str, Any]) -> str:
        nid = notification_data.get("id") or str(uuid.uuid4())
        db = await _db()
        payload = dict(notification_data)
        payload["id"] = nid
        payload.setdefault("is_read", False)
        payload.setdefault("created_at", _now())
        await db.collection("notifications").document(nid).set(payload)
        return nid

    async def list_notifications(
        self, user_id: str, unread_only: bool = False, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        db = await _db()
        rows = []
        async for doc in db.collection("notifications").where("user_id", "==", user_id).stream():
            row = doc.to_dict() or {}
            if unread_only and row.get("is_read"):
                continue
            rows.append(row)
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return rows[offset : offset + limit]

    async def mark_read(self, notification_id: str) -> None:
        db = await _db()
        await db.collection("notifications").document(notification_id).set(
            {"is_read": True}, merge=True
        )

    async def mark_all_read(self, user_id: str) -> int:
        rows = await self.list_notifications(user_id, unread_only=True, limit=500)
        for row in rows:
            await self.mark_read(row["id"])
        return len(rows)

    async def get_unread_count(self, user_id: str) -> int:
        return len(await self.list_notifications(user_id, unread_only=True, limit=500))


class FirestoreOrgRepository(BaseOrgRepository):
    """Orgs and membership. orgs/{org_id} + org_members/{org_id}_{user_id}."""

    async def create_org(self, name: str, owner_id: str) -> Dict[str, Any]:
        import uuid
        db = await _db()
        org_id = str(uuid.uuid4())
        now = _now()
        await db.collection("orgs").document(org_id).set(
            {"org_id": org_id, "name": name, "owner_id": owner_id, "created_at": now}
        )
        await db.collection("org_members").document(f"{org_id}_{owner_id}").set(
            {"org_id": org_id, "user_id": owner_id, "role": "owner", "added_at": now, "added_by": owner_id}
        )
        return {"org_id": org_id, "name": name, "owner_id": owner_id, "created_at": now}

    async def get_org(self, org_id: str) -> Optional[Dict[str, Any]]:
        db = await _db()
        doc = await db.collection("orgs").document(org_id).get()
        return doc.to_dict() if doc.exists else None

    async def list_orgs_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        db = await _db()
        out = []
        async for doc in db.collection("org_members").where("user_id", "==", user_id).stream():
            m = doc.to_dict() or {}
            org = await self.get_org(m.get("org_id") or "")
            if org:
                out.append({**org, "role": m.get("role")})
        out.sort(key=lambda o: o.get("created_at") or "", reverse=True)
        return out

    async def get_member_role(self, org_id: str, user_id: str) -> Optional[str]:
        db = await _db()
        doc = await db.collection("org_members").document(f"{org_id}_{user_id}").get()
        return (doc.to_dict() or {}).get("role") if doc.exists else None

    async def list_members(self, org_id: str) -> List[Dict[str, Any]]:
        db = await _db()
        out = []
        async for doc in db.collection("org_members").where("org_id", "==", org_id).stream():
            m = dict(doc.to_dict() or {})
            user = await db.collection("users").document(m.get("user_id") or "").get()
            if user.exists:
                u = user.to_dict() or {}
                m["email"] = u.get("email")
                m["name"] = u.get("name")
            out.append(m)
        return out

    async def add_member(self, org_id: str, user_id: str, role: str, added_by: str) -> bool:
        if await self.get_org(org_id) is None:
            return False
        db = await _db()
        await db.collection("org_members").document(f"{org_id}_{user_id}").set(
            {"org_id": org_id, "user_id": user_id, "role": role, "added_at": _now(), "added_by": added_by}
        )
        return True

    async def set_member_role(self, org_id: str, user_id: str, role: str) -> bool:
        db = await _db()
        ref = db.collection("org_members").document(f"{org_id}_{user_id}")
        doc = await ref.get()
        data = doc.to_dict() or {}
        if not doc.exists or data.get("role") == "owner":
            return False
        await ref.set({**data, "role": role})
        return True

    async def remove_member(self, org_id: str, user_id: str) -> bool:
        db = await _db()
        ref = db.collection("org_members").document(f"{org_id}_{user_id}")
        doc = await ref.get()
        data = doc.to_dict() or {}
        if not doc.exists or data.get("role") == "owner":
            return False
        await ref.delete()
        return True

    async def delete_org(self, org_id: str) -> bool:
        db = await _db()
        ref = db.collection("orgs").document(org_id)
        doc = await ref.get()
        if not doc.exists:
            return False
        async for m in db.collection("org_members").where("org_id", "==", org_id).stream():
            await m.reference.delete()
        await ref.delete()
        return True


class FirestoreAuditRepository(BaseAuditRepository):
    async def log_event(self, event_data: Dict[str, Any]) -> None:
        db = await _db()
        eid = str(uuid.uuid4())
        payload = dict(event_data)
        payload.setdefault("timestamp", _now())
        await db.collection("audit_logs").document(eid).set(payload)

    async def get_events(self, resource_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        db = await _db()
        rows = []
        async for doc in db.collection("audit_logs").where("resource_id", "==", resource_id).stream():
            rows.append(doc.to_dict() or {})
        rows.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
        return rows[:limit]

    async def list_recent(self, limit: int = 100, offset: int = 0, event_type: str = None) -> List[Dict[str, Any]]:
        """Admin listing: most recent audit events across all resources."""
        db = await _db()
        col = db.collection("audit_logs")
        if event_type:
            col = col.where("event_type", "==", event_type)
        rows = []
        async for doc in col.stream():
            rows.append(doc.to_dict() or {})
        rows.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
        start = max(0, int(offset))
        return rows[start : start + max(1, min(int(limit), 500))]

    async def purge_older_than(self, days: int) -> int:
        """Retention control: delete audit rows older than N days."""
        from datetime import datetime, timedelta, timezone as tz
        db = await _db()
        cutoff = (datetime.now(tz.utc) - timedelta(days=int(days))).isoformat()
        count = 0
        async for doc in db.collection("audit_logs").where("timestamp", "<", cutoff).stream():
            await doc.reference.delete()
            count += 1
        return count
