"""
AgentOS — Organizations Router (enterprise RBAC foundation)

POST   /api/v1/orgs                        — create an org (creator = owner)
GET    /api/v1/orgs                        — orgs the caller belongs to
GET    /api/v1/orgs/{org_id}               — detail + members (members only)
POST   /api/v1/orgs/{org_id}/members       — add a member by email (admin+)
POST   /api/v1/orgs/{org_id}/invitations   — invite by email (admin+); token
                                             returned once, membership created
                                             on ACCEPTANCE (audit F01)
GET    /api/v1/orgs/{org_id}/invitations   — pending invitations (admin+)
POST   /api/v1/orgs/invitations/accept     — the invited user accepts (token)
DELETE /api/v1/orgs/{org_id}/invitations/{iid} — revoke a pending invite
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
from datetime import datetime, timezone

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


class InviteRequest(BaseModel):
    email: str
    role: str = "member"


class AcceptInviteRequest(BaseModel):
    token: str


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


@router.post("/{org_id}/members", status_code=202)
async def add_member(org_id: str, body: AddMemberRequest, request: Request, user: AuthenticatedUser = Depends(require_not_viewer)):
    """Legacy alias for the invitation flow (audit v5.6 finding: this route
    used to enroll members DIRECTLY, bypassing acceptance). It now creates a
    pending invitation — membership is created only on ACCEPTANCE."""
    factory, org, role = await _member_org(org_id, request, user, "admin")
    if body.role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(ASSIGNABLE_ROLES)}")
    if body.role == "admin" and role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can appoint an admin")
    try:
        email = sanitize_email(body.email)
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    import hashlib
    import secrets as secrets_lib
    from datetime import timedelta

    # If the invited email already belongs to a member, refuse (no invite spam).
    target = await factory.user_repo.get_by_email(email)
    if target and await factory.org_repo.get_member_role(org_id, target["id"]) is not None:
        raise HTTPException(status_code=409, detail="Already a member; use the owner-only role endpoint")
    if target and target["id"] == org["owner_id"] and body.role != "owner":
        raise HTTPException(status_code=409, detail="The owner's role is fixed")
    token = secrets_lib.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=INVITATION_TTL_DAYS)).isoformat()
    invite = await factory.org_repo.create_invitation(org_id, email, body.role, user.user_id, token_hash, expires_at)
    if not invite:
        raise HTTPException(status_code=409, detail="A pending invitation for this email already exists")
    await factory.audit_repo.log_event({
        "event_type": "ORG_INVITATION_CREATED",
        "actor_id": user.user_id, "actor_type": "USER",
        "resource_id": org_id,
        "details": {"email": email, "role": body.role, "via": "members-endpoint"},
    })
    # 202 Accepted: this request did NOT create a membership. The token is
    # delivered once; membership exists only after acceptance.
    return {"org_id": org_id, "email": email, "role": body.role,
            "invitation_id": invite["invitation_id"], "expires_at": invite["expires_at"],
            "token": token, "status": "invitation_pending"}


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
    """Summarize explicitly organization-owned runs; membership is not sharing."""
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
            # Legacy and personal runs have no organization ownership. Never
            # infer sharing from membership, including newly added members.
            if r.get("org_id") != org_id:
                continue
            r["member_email"] = emails.get(r.get("user_id"))
            r["tasks"] = [
                {k: t.get(k) for k in ("task_id", "title", "agent", "status", "error")}
                for t in (r.get("tasks") or [])
            ]
            runs.append(r)
    runs.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return {"org_id": org_id, "runs": runs[:limit], "count": min(len(runs), limit)}


# ── Invitation lifecycle (audit F01): membership requires acceptance ──

INVITATION_TTL_DAYS = 7


@router.post("/{org_id}/invitations", status_code=201)
async def invite_member(org_id: str, body: InviteRequest, request: Request, user: AuthenticatedUser = Depends(require_not_viewer)):
    """Create a pending invitation. The raw token is returned exactly once —
    the inviter delivers it out of band; only its hash is stored. Membership
    is created when the invited user ACCEPTS, never by this call."""
    import hashlib
    import secrets as secrets_lib
    from datetime import timedelta

    factory, org, role = await _member_org(org_id, request, user, "admin")
    if body.role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(ASSIGNABLE_ROLES)}")
    if body.role == "admin" and role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can invite an admin")
    try:
        email = sanitize_email(body.email)
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    # If the invited email already belongs to a member, do not invite.
    existing_user = await factory.user_repo.get_by_email(email)
    if existing_user and await factory.org_repo.get_member_role(org_id, existing_user["id"]) is not None:
        raise HTTPException(status_code=409, detail="Already a member; use the owner-only role endpoint")

    token = secrets_lib.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=INVITATION_TTL_DAYS)).isoformat()

    invite = await factory.org_repo.create_invitation(org_id, email, body.role, user.user_id, token_hash, expires_at)
    if not invite:
        raise HTTPException(status_code=409, detail="A pending invitation for this email already exists")
    await factory.audit_repo.log_event({
        "event_type": "ORG_INVITATION_CREATED",
        "actor_id": user.user_id, "actor_type": "USER",
        "resource_id": org_id,
        "details": {"email": email, "role": body.role},
    })
    return {"invitation_id": invite["invitation_id"], "org_id": org_id, "email": email,
            "role": body.role, "expires_at": invite["expires_at"], "token": token}


@router.get("/{org_id}/invitations")
async def list_pending_invitations(org_id: str, request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    factory, org, role = await _member_org(org_id, request, user, "admin")
    invitations = await factory.org_repo.list_invitations(org_id, "pending")
    # Tokens are never listable — only their existence and expiry.
    return {"org_id": org_id, "invitations": invitations}


@router.post("/invitations/accept")
async def accept_invitation(body: AcceptInviteRequest, request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    """The invited user accepts. Membership is created atomically with the
    create-only invariant; the invitation must match the caller's email and
    be unexpired."""
    import hashlib

    factory = _get_factory(request)
    check_rate_limit(f"user:{user.user_id}", "general")
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    try:
        membership = await factory.org_repo.accept_invitation(token_hash, user.user_id, user.email)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await factory.audit_repo.log_event({
        "event_type": "ORG_INVITATION_ACCEPTED",
        "actor_id": user.user_id, "actor_type": "USER",
        "resource_id": membership["org_id"],
        "details": {"role": membership["role"]},
    })
    return {"org_id": membership["org_id"], "role": membership["role"], "accepted": True}


@router.delete("/{org_id}/invitations/{invitation_id}")
async def revoke_invitation(org_id: str, invitation_id: str, request: Request, user: AuthenticatedUser = Depends(require_not_viewer)):
    factory, org, role = await _member_org(org_id, request, user, "admin")
    revoked = await factory.org_repo.revoke_invitation(org_id, invitation_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Pending invitation not found")
    await factory.audit_repo.log_event({
        "event_type": "ORG_INVITATION_REVOKED",
        "actor_id": user.user_id, "actor_type": "USER",
        "resource_id": org_id,
        "details": {"invitation_id": invitation_id},
    })
    return {"org_id": org_id, "invitation_id": invitation_id, "revoked": True}


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
