"""
AgentOS — Organizations Router (enterprise RBAC foundation)

POST   /api/v1/orgs                        — create an org (creator = owner)
GET    /api/v1/orgs                        — orgs the caller belongs to
GET    /api/v1/orgs/{org_id}               — detail + members (members only)
POST   /api/v1/orgs/{org_id}/members       — add a member by email (admin+)
DELETE /api/v1/orgs/{org_id}/members/{uid} — remove a member (admin+; owner protected)
POST   /api/v1/orgs/{org_id}/members/{uid}/role — set role (owner only)
GET    /api/v1/orgs/{org_id}/runs          — run oversight (owner/admin): read-only
                                            view of member runs
DELETE /api/v1/orgs/{org_id}               — delete (owner only)

Role ladder: owner > admin > member > viewer. Shared vaults and org-scoped
workspaces are the documented next steps (audit §8 P2), not part of this
foundation.
"""

import logging

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from pydantic import BaseModel
from typing import Optional

from backend.api.dependencies.auth import get_current_user, AuthenticatedUser, require_not_viewer
from backend.security.input_sanitizer import sanitize_text, sanitize_email, InputValidationError
from backend.security.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orgs", tags=["orgs"])

ROLE_LADDER = {"owner": 4, "admin": 3, "member": 2, "viewer": 1}
ASSIGNABLE_ROLES = {"admin", "member", "viewer"}


def _get_factory(request: Request):
    factory = getattr(request.app.state, "factory", None)
    if not factory:
        raise HTTPException(status_code=500, detail="Server not initialized")
    return factory


def _require_role(user_role: Optional[str], minimum: str, org_id: str) -> None:
    """Raise 404 for non-members (no existence leak), 403 for insufficient role."""
    if user_role is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if ROLE_LADDER.get(user_role, 0) < ROLE_LADDER[minimum]:
        raise HTTPException(status_code=403, detail=f"Requires the {minimum} role in this organization")


class CreateOrgRequest(BaseModel):
    name: str

class AddMemberRequest(BaseModel):
    email: str
    role: str = "member"   # admin | member | viewer

class SetRoleRequest(BaseModel):
    role: str


@router.post("", status_code=201)
async def create_org(body: CreateOrgRequest, request: Request, user: AuthenticatedUser = Depends(require_not_viewer)):
    """Create an organization. The creator becomes its owner."""
    factory = _get_factory(request)
    check_rate_limit(f"user:{user.user_id}", "general")
    try:
        name = sanitize_text(body.name, "name", max_length=120)
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    if not name.strip():
        raise HTTPException(status_code=422, detail="Organization name cannot be empty")

    org = await factory.org_repo.create_org(name.strip(), user.user_id)
    await factory.audit_repo.log_event({
        "event_type": "ORG_CREATED",
        "actor_id": user.user_id, "actor_type": "USER",
        "resource_id": org["org_id"],
        "details": {"name": name},
    })
    return {**org, "role": "owner"}


@router.get("")
async def list_my_orgs(request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    factory = _get_factory(request)
    orgs = await factory.org_repo.list_orgs_for_user(user.user_id)
    return {"orgs": orgs, "count": len(orgs)}


async def _member_org(org_id: str, request: Request, user: AuthenticatedUser, minimum: str):
    """Resolve the org + caller's role, enforcing the minimum role."""
    factory = _get_factory(request)
    org = await factory.org_repo.get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    role = await factory.org_repo.get_member_role(org_id, user.user_id)
    _require_role(role, minimum, org_id)
    return factory, org, role


@router.get("/{org_id}")
async def get_org(org_id: str, request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    factory, org, role = await _member_org(org_id, request, user, "viewer")
    members = await factory.org_repo.list_members(org_id)
    return {**org, "role": role, "members": members}


@router.post("/{org_id}/members", status_code=201)
async def add_member(org_id: str, body: AddMemberRequest, request: Request, user: AuthenticatedUser = Depends(require_not_viewer)):
    factory, org, role = await _member_org(org_id, request, user, "admin")
    if body.role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(ASSIGNABLE_ROLES)}")
    try:
        email = sanitize_email(body.email)
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    target = await factory.user_repo.get_by_email(email)
    if not target:
        # Do not reveal whether the email exists — same anti-enumeration rule as login.
        raise HTTPException(status_code=404, detail="No user with that email exists")
    if target["id"] == org["owner_id"] and body.role != "owner":
        raise HTTPException(status_code=409, detail="The owner's role is fixed")
    ok = await factory.org_repo.add_member(org_id, target["id"], body.role, user.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Organization not found")
    await factory.audit_repo.log_event({
        "event_type": "ORG_MEMBER_ADDED",
        "actor_id": user.user_id, "actor_type": "USER",
        "resource_id": org_id,
        "details": {"member": target["id"], "role": body.role},
    })
    return {"org_id": org_id, "user_id": target["id"], "role": body.role}


@router.delete("/{org_id}/members/{member_id}")
async def remove_member(org_id: str, member_id: str, request: Request, user: AuthenticatedUser = Depends(require_not_viewer)):
    factory, org, role = await _member_org(org_id, request, user, "admin")
    if member_id == org["owner_id"]:
        raise HTTPException(status_code=409, detail="The owner cannot be removed")
    # Admins may remove members/viewers; only the owner manages other admins.
    target_role = await factory.org_repo.get_member_role(org_id, member_id)
    if target_role is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if target_role == "admin" and role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can remove an admin")
    removed = await factory.org_repo.remove_member(org_id, member_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")
    await factory.audit_repo.log_event({
        "event_type": "ORG_MEMBER_REMOVED",
        "actor_id": user.user_id, "actor_type": "USER",
        "resource_id": org_id,
        "details": {"member": member_id},
    })
    return {"org_id": org_id, "user_id": member_id, "removed": True}


@router.post("/{org_id}/members/{member_id}/role")
async def set_member_role(org_id: str, member_id: str, body: SetRoleRequest, request: Request, user: AuthenticatedUser = Depends(require_not_viewer)):
    factory, org, role = await _member_org(org_id, request, user, "owner")
    if body.role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(ASSIGNABLE_ROLES)}")
    if member_id == org["owner_id"]:
        raise HTTPException(status_code=409, detail="The owner's role is fixed")
    changed = await factory.org_repo.set_member_role(org_id, member_id, body.role)
    if not changed:
        raise HTTPException(status_code=404, detail="Member not found")
    await factory.audit_repo.log_event({
        "event_type": "ORG_MEMBER_ROLE_SET",
        "actor_id": user.user_id, "actor_type": "USER",
        "resource_id": org_id,
        "details": {"member": member_id, "role": body.role},
    })
    return {"org_id": org_id, "user_id": member_id, "role": body.role}


@router.get("/{org_id}/runs")
async def org_run_oversight(
    org_id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
):
    """Read-only oversight of member runs for org admins/owners (the
    enterprise oversight primitive; shared workspaces are a next step)."""
    factory, org, role = await _member_org(org_id, request, user, "admin")
    members = await factory.org_repo.list_members(org_id)
    emails = {m.get("user_id"): m.get("email") for m in members}
    runs = []
    for m in members:
        if not m.get("user_id"):
            continue
        try:
            member_runs = await factory.workflow_repo.list_runs(m["user_id"], limit=limit, offset=0)
        except Exception:
            logger.exception("Org oversight: could not list runs for member")
            continue
        for r in member_runs:
            r = dict(r)
            r["member_email"] = emails.get(r.get("user_id"))
            r["tasks"] = [
                {k: t.get(k) for k in ("task_id", "title", "agent", "status", "error")}
                for t in (r.get("tasks") or [])
            ]
            runs.append(r)
    runs.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return {"org_id": org_id, "runs": runs[:limit], "count": min(len(runs), limit)}


@router.delete("/{org_id}")
async def delete_org(org_id: str, request: Request, user: AuthenticatedUser = Depends(require_not_viewer)):
    factory, org, role = await _member_org(org_id, request, user, "owner")
    deleted = await factory.org_repo.delete_org(org_id)
    await factory.audit_repo.log_event({
        "event_type": "ORG_DELETED",
        "actor_id": user.user_id, "actor_type": "USER",
        "resource_id": org_id,
        "details": {"name": org.get("name")},
    })
    return {"org_id": org_id, "deleted": deleted}
