"""
AgentOS — Organizations (RBAC foundation) tests

Lifecycle, the role ladder (owner > admin > member > viewer),
owner-immutability, anti-enumeration, and oversight scoping.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.api.dependencies.auth import AuthenticatedUser
from backend.api.routers.orgs import (
    add_member,
    create_org,
    delete_org,
    get_org,
    org_run_oversight,
    remove_member,
    set_member_role,
)


def _user(uid: str, role: str = "user") -> AuthenticatedUser:
    return AuthenticatedUser(user_id=uid, email=f"{uid}@x", name=uid, role=role, auth_provider="local")


def _org_repo():
    org_repo = SimpleNamespace(
        create_org=AsyncMock(side_effect=lambda name, owner: {"org_id": "org-1", "name": name, "owner_id": owner, "created_at": "t"}),
        get_org=AsyncMock(side_effect=lambda oid: {"org_id": oid, "name": "Acme", "owner_id": "owner"} if oid == "org-1" else None),
        get_member_role=AsyncMock(side_effect=lambda oid, uid: {
            "owner": "owner", "admin1": "admin", "mem1": "member", "view1": "viewer",
        }.get(uid) if oid == "org-1" else None),
        list_orgs_for_user=AsyncMock(return_value=[]),
        list_members=AsyncMock(return_value=[
            {"user_id": "owner", "role": "owner", "email": "owner@x"},
            {"user_id": "admin1", "role": "admin", "email": "admin@x"},
            {"user_id": "mem1", "role": "member", "email": "mem@x"},
        ]),
        add_member=AsyncMock(return_value=True),
        set_member_role=AsyncMock(return_value=True),
        remove_member=AsyncMock(return_value=True),
        delete_org=AsyncMock(return_value=True),
    )
    factory = SimpleNamespace(
        org_repo=org_repo,
        audit_repo=AsyncMock(),
        user_repo=SimpleNamespace(get_by_email=AsyncMock(side_effect=lambda e: {"id": f"u-{e}", "email": e} if e == "new@x" else None)),
        workflow_repo=SimpleNamespace(list_runs=AsyncMock(side_effect=lambda uid, limit, offset: [
            {"run_id": f"run-{uid}", "user_id": uid, "created_at": "t", "tasks": [{"task_id": "t", "title": "T", "agent": "a", "status": "COMPLETED", "error": None}]},
        ])),
    )
    return factory, org_repo


def _request(repo):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(factory=repo)))


class UnraisableHTTP(HTTPException):
    pass


@pytest.mark.asyncio
async def test_create_org_makes_creator_owner():
    factory, org_repo = _org_repo()
    result = await create_org(SimpleNamespace(name="Acme"), _request(factory), _user("owner"))
    assert result["role"] == "owner" and result["org_id"] == "org-1"
    factory.audit_repo.log_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_member_cannot_add_users_admin_can():
    factory, _ = _org_repo()
    request = _request(factory)
    with pytest.raises(HTTPException) as e:
        await add_member("org-1", SimpleNamespace(email="new@x", role="member"), request, _user("mem1"))
    assert e.value.status_code == 403

    result = await add_member("org-1", SimpleNamespace(email="new@x", role="member"), request, _user("admin1"))
    assert result["user_id"] == "u-new@x" and result["role"] == "member"


@pytest.mark.asyncio
async def test_add_member_anti_enumeration():
    factory, _ = _org_repo()
    with pytest.raises(HTTPException) as e:
        await add_member("org-1", SimpleNamespace(email="ghost@x", role="member"), _request(factory), _user("admin1"))
    assert e.value.status_code == 404
    assert "exist" in e.value.detail


@pytest.mark.asyncio
async def test_owner_cannot_be_removed_or_demoted():
    factory, _ = _org_repo()
    with pytest.raises(HTTPException) as e:
        await remove_member("org-1", "owner", _request(factory), _user("admin1"))
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:
        await set_member_role("org-1", "owner", SimpleNamespace(role="member"), _request(factory), _user("owner"))
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_admin_cannot_remove_admin_only_owner_can():
    factory, _ = _org_repo()
    with pytest.raises(HTTPException) as e:
        await remove_member("org-1", "admin1", _request(factory), _user("admin1"))
    assert e.value.status_code == 403
    result = await remove_member("org-1", "admin1", _request(factory), _user("owner"))
    assert result["removed"] is True


@pytest.mark.asyncio
async def test_role_assignment_is_owner_only():
    factory, _ = _org_repo()
    with pytest.raises(HTTPException) as e:
        await set_member_role("org-1", "mem1", SimpleNamespace(role="admin"), _request(factory), _user("admin1"))
    assert e.value.status_code == 403
    result = await set_member_role("org-1", "mem1", SimpleNamespace(role="admin"), _request(factory), _user("owner"))
    assert result["role"] == "admin"


@pytest.mark.asyncio
async def test_oversight_is_admin_only_and_scopes_task_fields():
    factory, _ = _org_repo()
    with pytest.raises(HTTPException) as e:
        await org_run_oversight("org-1", _request(factory), _user("mem1"), limit=20)
    assert e.value.status_code == 403

    result = await org_run_oversight("org-1", _request(factory), _user("owner"), limit=20)
    assert result["count"] >= 1
    row = result["runs"][0]
    assert row["member_email"] == "owner@x"
    # Oversight is read-only: only summary fields, never full input/output data
    assert set(row["tasks"][0].keys()) == {"task_id", "title", "agent", "status", "error"}


@pytest.mark.asyncio
async def test_non_member_gets_404_not_403_no_existence_leak():
    factory, _ = _org_repo()
    with pytest.raises(HTTPException) as e:
        await get_org("org-1", _request(factory), _user("stranger"))
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_org_is_owner_only():
    factory, _ = _org_repo()
    with pytest.raises(HTTPException) as e:
        await delete_org("org-1", _request(factory), _user("admin1"))
    assert e.value.status_code == 403
    result = await delete_org("org-1", _request(factory), _user("owner"))
    assert result["deleted"] is True
